"""독립 사전점검: 작성기/pandas 미사용. 게이트 차단을 전체 구축 PASS와 구별한다."""
import ast
import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[2]

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(262144),b''):
            h.update(block)
    return h.hexdigest()

def csv_rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(line for line in f if not line.startswith('#')))

def main():
    if (OUT/'qc/PHASE2B_INDEPENDENT_QC.md').exists():
        raise SystemExit('독립 QC 기존 결과를 덮어쓰지 않습니다.')
    manifest=load(OUT/'inputs/PHASE2B_INPUT_MANIFEST.json')
    daily=load(OUT/'qc/RAW_PREFLIGHT_QC.json')
    auto=load(OUT/'qc/PHASE2B_QC.json')
    gate=load(OUT/'qc/D10_IMPLEMENTATION_QC.json')
    evidence=load(OUT/'calendar/D10_CALENDAR_EVIDENCE.json')
    application=load(OUT/'lineage/POLICY_APPLICATION_SUMMARY.json')
    checks=[]
    def check(name,cond,how):
        checks.append({'name':name,'passed':bool(cond),'method_ko':how})
    expected={
        '02':'00aecd96d4501eee1ad9e36f24a282239e03982612df931287505aa37c37faa5',
        '04':'e7d98d15efbb6a07982dbc9e83f889419621c056434ff707f8d99d9a5cb8f586',
        '08':'9dab052c7e18f371a893f13a7777d7b1da09f11affbbb2250511abb221a4f54c',
        '10':'45508b90248470eaff54adb87da9b12f9d12ab8578b9d68ff56c3af3c0e7ea78',
        '11':'8806acc3c5c8f82d9d8bfabc07ecb8bf7d87c9a02ec733f3aff5de73f7f8ef5f',
        '12':'d708902a4c618195de0784d25c947a025a7362dca819b51538dc5d9e3fdccd23',
        '15':'04c9f287fb1e39f60e677db71b2d31df1fd2bd614637e7d490965a5f8a95409d'}
    core_rows={k:csv_rows(ROOT/r['path']) for k,r in daily['core'].items()}
    check('핵심7개 사용자 해시 독립 대조',all(digest(ROOT/daily['core'][k]['path'])==v for k,v in expected.items()),
          '별도 상수·스트리밍 SHA256로 원천 직접 재계산. 작성기 상수를 import하지 않음.')
    files=sorted((ROOT/'data/raw').glob('*/*_RAW_*.csv'))
    inv=manifest['raw_canonical_inventory']
    inventory_map={r['path']:r for r in inv}
    check('47폴더·48파일 및 모든 해시',len(files)==48 and len(set(p.parent for p in files))==47 and
          len(inv)==48 and all(digest(p)==inventory_map[p.relative_to(ROOT).as_posix()]['sha256'] for p in files),
          '디스크 목록을 새로 열거. 모든 canonical 실제 파일 해시 대조.')
    check('전체48개 원천 행수',all(len(csv_rows(p))==inventory_map[p.relative_to(ROOT).as_posix()]['rows'] for p in files),
          'stdlib csv로 SOURCE 행을 제외한 원본 행 수만 검사. 이벤트·다중키 자료를 단일 날짜 지수로 오인하지 않음.')
    stats_match=True
    for k,rows in core_rows.items():
        rec=daily['core'][k]
        dates=[date.fromisoformat(r['Date']) for r in rows]
        nums=[None if r[rec['value_column']].strip()=='' else Decimal(r[rec['value_column']]) for r in rows]
        stats_match &= len(rows)==rec['rows'] and len(dates)-len(set(dates))==rec['duplicate_Date']
        stats_match &= str(min(dates))==rec['min_date'] and str(max(dates))==rec['max_date']
        stats_match &= sum(n is None for n in nums)==rec['missing_values'] and all(n is None or n.is_finite() for n in nums)
    check('핵심 원천 기간·행수·공란·중복·유한성',stats_match,
          'csv/date/Decimal 독립 파싱. 금융 변수 산식/라벨을 계산하지 않음.')
    sox_dates={r['Date'] for r in core_rows['02']}
    check('SOX 날짜의 타 핵심 값 존재',all(sox_dates.issubset({r['Date'] for r in rows if r[daily['core'][k]['value_column']].strip()})
          for k,rows in core_rows.items() if k in {'04','08','10','11','12'}),
          '일별 원천 날짜 집합 대조. as-of/주간 공통표본으로 표현하지 않음.')
    weeks={date.fromisoformat(d)-timedelta(days=date.fromisoformat(d).weekday()) for d in sox_dates}
    check('원천 달력 주 표지 수 구분',len(weeks)==daily['SOX_observed_calendar_week_labels']==823 and
          daily['week_labels_are_valid_model_sample'] is False and daily['weekly_common_sample_count'] is None,
          '823은 SOX 원천 날짜의 월요일 표지 수일 뿐 유효 모델주수 아님.')
    march=[r for r in core_rows['11'] if r['Date']=='2026-03-12']
    gh=csv_rows(ROOT/daily['FGI_GitHub_snapshot_path'])
    check('FGI0312 현재 존재·역사 출처 구분',len(march)==1 and Decimal(march[0]['Fear Greed'])==Decimal('21.15') and
          not any(r['Date']=='2026-03-12' for r in gh) and daily['FGI_20260312_first_posting_status']=='UNVERIFIED',
          '새 복원/기존 결측으로 표시하지 않음. GitHub 보존본 미포함이 점수 오류를 뜻하지 않음.')
    local_oct=[r for r in core_rows['11'] if r['Date']=='2026-10-06'][0]
    gh_oct=[r for r in gh if r['Date']=='2026-10-06'][0]
    check('FGI1006 충돌 이력',abs(Decimal(local_oct['Fear Greed'])-Decimal('47.3714285714286'))<Decimal('1e-12') and
          Decimal(gh_oct['Fear Greed'])==Decimal('46.8'),'로컬 우선 유지. 원천 수정이나 병합 안 함.')
    check('SOX0거래량 유지',all(Decimal(r['Volume'])==0 for r in core_rows['02']),
          '지수 거래량을 체결거래량 X로 전환하지 않음.')
    customs=[p for p in files if p.parent.name.startswith('24_')][0]
    customs_rows=csv_rows(customs)
    check('24번 결합키 유일성',len(customs_rows)==len({(r['Date'],r['HS_Code']) for r in customs_rows}),
          'Date 단독 중복을 결함으로 판정하지 않음.')
    check('새 지시와 과거 승인권한 구분','이번 사용자' in manifest['execution_authority'] and
          application['phase2B_preflight_execution_authorized_by_current_user_instruction'],
          '과거 승인본의 phase2B=false를 현재 실행지시 거부 사유로 쓰지 않음.')
    check('D10 승인·실제달력 근거 공백 구분',gate['D10_POLICY']=='APPROVED' and
          evidence['full_historical_Board_calendar_verified'] is False and evidence['authoritative_complete_calendar_file'] is None and
          len(evidence['coverage_gaps'])==3 and all(s['suffices_full_history'] is False for s in evidence['sources']),
          '시간 가정 승인과 달력 전수 검증은 별도. 근거 부재 자체는 외부 조사로 독립 증명한 것이 아님.')
    check('지시문 게이트A 차단 재현',gate['status']==auto['status']=='BLOCKED_D10_CALENDAR_OR_RELEASE_EVIDENCE' and
          not gate['gate_A_passed'] and auto['failed_required_checks']==['full_historical_Board_evidence'],
          '필수 실제달력 검사가 false이므로 전체 QC PASS 금지. 독립 사전점검 PASS와 구별.')
    et=ZoneInfo('America/New_York')
    ori=datetime(2026,10,5,9,tzinfo=et)
    unit_checks=[datetime(2026,10,2,16,15,tzinfo=et).astimezone(timezone.utc).hour==20,
                 datetime(2026,1,9,16,15,tzinfo=et).astimezone(timezone.utc).hour==21,
                 ori-timedelta(microseconds=1)<ori,not(ori<ori),
                 not(datetime(2026,10,5,16,15,tzinfo=et)<ori)]
    check('독립 UTC·엄격경계·늦은발표 논리',all(unit_checks) and gate['synthetic_logic_passed'],
          '소규모 synthetic 시간 논리만 재계산. 휴일 달력/실제 공개전수 확인으로 승격하지 않음.')
    check('실제시각·빈티지 미검증 유지',gate['actual_available_at'] is None and gate['publication_status']==gate['vintage_status']=='UNVERIFIED' and
          application['actual_available_at'] is None and not application['D04_applied_to_DGS10'],
          '가짜 actual 필드 또는 D04로 D10 대체 없음.')
    no_weekly=not list((OUT/'data').iterdir())
    no_full_calendars=not (OUT/'calendar/US_MARKET_SESSIONS.csv').exists() and not (OUT/'calendar/BOARD_H15_PUBLICATION_CALENDAR.csv').exists()
    check('게이트 전 X/Y·확정 달력 미생성',no_weekly and no_full_calendars and
          not (OUT/'lineage/FEATURE_AVAILABILITY_LOG.csv').exists() and all(n==0 for n in application['execution_counts'].values()),
          '헤더만 있는 완료형 파일도 만들지 않음. 필요한 산출물은 중단 보고서에 미생성으로 명시.')
    source=(OUT/'code/phase2b_preflight.py').read_text(encoding='utf-8')
    tree=ast.parse(source)
    imports=[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
    check('학습·주간계산·네트워크 실행 없음',not any(x.startswith(('sklearn','statsmodels','xgboost','lightgbm','requests','yfinance')) for x in imports) and
          not {'fit','fit_transform','predict','resample','rolling','pct_change','ffill','interpolate'}.intersection(calls),
          '실행 작성 코드 AST 점검. 전체 OS 프로세스 감시나 외부 심사 아님.')
    mismatches=[p for p,v in manifest['protected_files'].items() if not (ROOT/p).is_file() or digest(ROOT/p)!=v['sha256']]
    check('보호파일1055개 해시',not mismatches and len(manifest['protected_files'])==1055,
          '기존1054개 및 새 사용자 제공 사전감사문서1개를 원본에서 다시 해시.')
    instruction_copy=OUT/'inputs/USER_PHASE2B_INSTRUCTION.txt'
    ext_instruction=Path(manifest['input_read_log'][-1]['path'])
    check('원문 지시·필수입력 읽기 해시',digest(instruction_copy)==digest(ext_instruction) and all(
          digest(Path(r['path']))==r['sha256'] and r['entire_file_read'] for r in manifest['input_read_log']),
          '사용자 원문 바이트 및 읽은 필수문서 현재 해시 대조.')
    check('D13 미잠금 및 유효주수 미산출',application['D13_status']=='PENDING_WEEKLY_MISSINGNESS_AUDIT' and
          auto['D13_details_locked'] is False and all(v is None for v in auto['weekly_sample_counts'].values()),
          '주간 자료가 없으므로 결손패턴이나 Bootstrap 최소n을 임의로 생성하지 않음.')
    result={'independent_preflight_check_status':'PASS' if all(t['passed'] for t in checks) else 'FAIL',
        'overall_Phase2B_status':'BLOCKED_D10_CALENDAR_OR_RELEASE_EVIDENCE','test_count':len(checks),'checks':checks,
        'failures':[t['name'] for t in checks if not t['passed']],
        'protected_files_checked':len(manifest['protected_files']),'protected_hash_changes':mismatches,
        'method':'동일 Codex 작업 내 별도 구현. 작성 코드/pandas 미사용, csv/Decimal/date/스트리밍 해시로 재검사. 외부 심사 아님.',
        'full_B10_implementation_QC_passed':False,'original_policy_updated':False,'models_fit':0}
    with (OUT/'qc/PHASE2B_INDEPENDENT_QC.json').open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    lines=['# Phase2-B 독립 사전점검 및 차단 판정','',result['method'],'',
           f"독립 사전점검 **{result['independent_preflight_check_status']} {len(checks)}/{len(checks)}**. 전체 Phase2-B는 **{result['overall_Phase2B_status']}**이며 구축 성공/PASS가 아니다.",'',
           '|검사|결과|독립방법·범위|','|---|---|---|']
    lines += [f"|{t['name']}|{'PASS' if t['passed'] else 'FAIL'}|{t['method_ko']}|" for t in checks]
    lines += ['','실제 역사 달력의 전수 근거가 미충족임을 확인해 지시문 게이트A에서 중단하는 처리를 재현했다. 소규모 시간 테스트만으로 전수 달력·실제 가용성·주간B10 검증을 통과 처리하지 않았다.',
              '공식 원천 자체가 존재하지 않는다고 증명한 것은 아니다. 본 조사로 완전한 커버리지를 확보·검증하지 못했다는 사실을 기록한다.']
    with (OUT/'qc/PHASE2B_INDEPENDENT_QC.md').open('x',encoding='utf-8') as f:
        f.write('\n'.join(lines)+'\n')
    print(json.dumps({'independent_preflight_check_status':result['independent_preflight_check_status'],
        'test_count':len(checks),'failures':result['failures'],'overall_status':result['overall_Phase2B_status']},ensure_ascii=False))
    if result['failures']:
        raise SystemExit(1)

if __name__=='__main__':
    main()
