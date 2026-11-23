"""동일 Codex 작업 내 별도 구현 QC. 작성/자동QC 코드와 pandas를 import하지 않는다."""
import ast
import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
LOCK = ROOT/'research_C/phase1_research_design/approval_lock_v1_1'

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def digest(p):
    return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()

def main():
    if (OUT/'qc/PHASE2A_INDEPENDENT_QC.md').exists():
        raise SystemExit('독립 QC 기존 결과 덮어쓰기 금지')
    inp = load(OUT/'inputs/PHASE2A_INPUT_MANIFEST.json')
    stats = load(OUT/'audit/D10_RAW_STATISTICS.json')
    proposal = load(OUT/'audit/D10_POLICY_PROPOSAL.json')
    recommendation = load(OUT/'audit/D10_GATE_RECOMMENDATION.json')
    sources = load(OUT/'audit/OFFICIAL_EVIDENCE_REGISTER.json')
    examples = load(OUT/'audit/D10_TIMING_LOGIC_EXAMPLES.json')['examples']
    raw = ROOT/stats['raw_path']
    with raw.open(encoding='utf-8-sig',newline='') as f:
        metadata=f.readline().strip()
        rows=list(csv.DictReader(f))
    with (ROOT/stats['source_original_path']).open(encoding='utf-8-sig',newline='') as f:
        originals=list(csv.DictReader(f))
    ds = [date.fromisoformat(r['Date']) for r in rows]
    nums = [None if r['DGS10'].strip() in ('','.','NA','NaN') else Decimal(r['DGS10']) for r in rows]
    valid = [x for x in nums if x is not None]
    original_pairs=[(r.get('observation_date',r.get('Date')),r['DGS10']) for r in originals]
    canonical_pairs=[(r['Date'],r['DGS10']) for r in rows]
    counts={}
    for y in sorted(set(d.year for d in ds)):
        positions=[i for i,d in enumerate(ds) if d.year==y]
        counts[y]={'year':y,'rows':len(positions),'valid':sum(nums[i] is not None for i in positions),
                   'missing':sum(nums[i] is None for i in positions)}
    finite_dates=[d for d,v in zip(ds,nums) if v is not None]
    maximum_gap=max((b-a).days for a,b in zip(finite_dates,finite_dates[1:]))
    expected_weekdays=set()
    day=min(ds)
    while day<=max(ds):
        if day.weekday()<5:
            expected_weekdays.add(day)
        day += timedelta(days=1)
    changes=[r for r,v in inp['protected_files'].items() if not (ROOT/r).exists() or digest(ROOT/r)!=v['sha256']]
    spec=load(LOCK/'PHASE1_LOCKED_SPEC_v1_1.json')
    gate=load(LOCK/'PHASE1_GATE_REGISTER.json')
    auto=load(OUT/'qc/PHASE2A_QC.json')
    checks=[]
    def check(name,ok,detail):
        checks.append({'check':name,'passed':bool(ok),'detail_ko':detail})
    check('독립 csv/Decimal 원본 파싱',len(rows)==stats['rows'] and len(valid)==stats['valid_values'] and
          len(nums)-len(valid)==stats['missing_values'],'pandas 및 작성 코드 미사용. 원본 공란을 0으로 바꾸지 않음.')
    check('최소/최대 날짜·중복·오름차순',str(min(ds))==stats['min_date'] and str(max(ds))==stats['max_date'] and
          len(ds)-len(set(ds))==stats['duplicate_dates'] and ds==sorted(ds),'날짜 목록 직접 대조.')
    check('금리 범위·유한성·비양수',float(min(valid))==stats['min_value'] and float(max(valid))==stats['max_value'] and
          all(x.is_finite() for x in valid) and sum(x<=0 for x in valid)==stats['negative_or_zero_values'],'Decimal 유한성 및 범위 검사.')
    check('연도별 결측 독립 집계',list(counts.values())==stats['annual_counts'],'연도별 원본행·유효·결측 직접 합산.')
    check('평일 날짜 격자·최대 간격',set(ds)==expected_weekdays and maximum_gap==stats['max_gap_between_valid_dates_days'],
          '평일 격자는 감사용 집합이며 신규 금융 관측값을 만들지 않음. 휴일 공란 정상 보존.')
    check('canonical과 보존 HTTP 응답 일치',canonical_pairs==original_pairs and digest(ROOT/stats['source_original_path'])==metadata.split('source_sha256=')[1],
          '날짜 헤더 이외 날짜·금리 문자열·공란 일치. 메타데이터 해시 별도 계산.')
    check('원천 정의와 공식 H15 근거', 'series_or_symbol=DGS10' in metadata and 'provider=FRED' in metadata and
          any(e['id']=='E01' and e['url']=='https://www.federalreserve.gov/releases/h15/' for e in sources['sources']),
          '공식 계열/발표 근거 연결 검사. 웹 내용 검토는 동일 Codex 감사이며 독립 외부 실사가 아님.')
    check('관측일·실제·가정 필드 분리',all(e['actual_release_at'] is None and e['actual_available_at'] is None and
          e['publication_status']=='UNVERIFIED' for e in examples) and proposal['actual_available_at'] is None,
          '실제 시각을 관측일 자정 또는 일정16:15로 위조하지 않음.')
    check('가정 게시/이용 시각·엄격 경계',all(
          (datetime.fromisoformat(e['assumed_available_at'])<datetime.fromisoformat(e['prediction_origin']))==e['assumed_eligible']
          for e in examples) and proposal['strict_operator']=='<', '별도 datetime 비교. 원점 동시각 부적격.')
    origin=datetime(2026,10,5,13,tzinfo=timezone.utc)
    cases=[(origin-timedelta(microseconds=1),True),(origin,False),(origin+timedelta(microseconds=1),False)]
    check('원점 전·동시·후 독립 경계',all((t<origin)==want for t,want in cases),'원점1마이크로초 전만 적격.')
    et=ZoneInfo('America/New_York')
    utc_hours=[datetime(2026,m,d,16,15,tzinfo=et).astimezone(timezone.utc).hour for m,d in [(1,9),(10,2)]]
    spring=datetime(2026,3,9,9,tzinfo=et).astimezone(timezone.utc).hour
    fall=datetime(2026,11,2,9,tzinfo=et).astimezone(timezone.utc).hour
    check('겨울·여름·DST 전환 UTC',utc_hours==[21,20] and spring==13 and fall==14,'수동 기대 UTC 시각과 zoneinfo 대조. 주간 매핑 아님.')
    check('Board 휴일·첫 주식 세션 예시', [e['assumed_eligible'] for e in examples]==[False,True,True,False,True,False,False,True] and
          any(e['id']=='E05' for e in sources['sources']), '2026 Board 휴일 근거와 조건부 예시 구분. 실제 거래소 전수 일정 검증을 주장하지 않음.')
    check('실제 지연·빈티지 한계 보존','지연' in proposal['known_delay_rule'] and recommendation['vintage_status']=='UNVERIFIED' and
          recommendation['historical_publication_status']=='UNVERIFIED','일정 기반 추정으로 알려진 지연을 무시하지 않음. 빈티지 전수 검증 미실시.')
    check('B10 원래 산식/단위 보존',inp['B10_formula_unchanged']==proposal['formula']==spec['core_variables']['B10']['formula'] and
          spec['core_variables']['B10']['unit']=='bp','같은 O에서 각 원천 주 내부 적격값. 실제 B10 전체 계산 없음.')
    check('D04 부당 전용 없음','B10' in spec['information_availability']['not_automatically_applicable_to'] and
          proposal['D04_applied_to_DGS10'] is False,'DGS10 전용 제안 NOT_APPROVED. 승인된 일반 daily 정책 적용 안 함.')
    check('원래 D10·D13 상태 보존',gate['D10_GATE_STATUS']=='PENDING_PHASE2_PREBUILD_AUDIT' and
          gate['D13_GATE_STATUS']=='PENDING_WEEKLY_MISSINGNESS_AUDIT' and not gate['gates']['D10']['passed'] and
          not gate['gates']['D13']['passed'],'본 감사 권고는 원본 게이트 통과 선언이 아님.')
    check('권고와 추가 승인 분리',recommendation['recommendation']=='CONDITIONAL_RECOMMENDED' and
          not recommendation['assumption_approved'] and not recommendation['weekly_build_authorized'] and not recommendation['D13_audited'],
          '새 가정 승인 및 후속 단계 실행 승인 대기.')
    check('주간 손실 미확정을 수치로 단정하지 않음',stats['exact_B10_valid_week_count'] is None and stats['exact_common_sample_loss'] is None,
          '일별 공란 수와 주간 공통표본 손실은 별개.')
    source=(OUT/'code/run_d10_audit.py').read_text(encoding='utf-8')
    tree=ast.parse(source)
    imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    attrs=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
           and not (n.func.attr=='join' and isinstance(n.func.value,ast.Constant) and isinstance(n.func.value.value,str))]
    forbidden={'fit','fit_transform','predict','merge','join','resample','rolling','pct_change','ffill','bfill','interpolate','to_csv'}
    check('실행 코드 범위 정적 검사',not forbidden.intersection(attrs) and not any(
          i and i.startswith(('sklearn','statsmodels','xgboost','lightgbm')) for i in imports),
          '실행 작성 코드 AST 검사. 작성 코드 미실행의 별도 증명이나 OS 전체 감시는 아님.')
    other_dirs=[str(p.relative_to(ROOT)) for p in (OUT.parent).iterdir() if p!=OUT]
    check('주간 X/Y·모델 산출물 부재',not list(OUT.rglob('*.csv')) and not list(OUT.rglob('*.pkl')) and not other_dirs and
          all(v==0 for v in auto['execution_counts'].values()), 'Phase2-A 전용 폴더만 존재. 실행기록·산출물·코드를 함께 대조.')
    check('보호 파일 SHA256 유지',not changes,f"{len(inp['protected_files'])}개 재해시, 변경 {len(changes)}개.")
    result={'qc_status':'PASS' if all(x['passed'] for x in checks) else 'FAIL','test_count':len(checks),'checks':checks,
            'method':'동일 Codex 작업 내 독립 구현. 작성 코드/자동 QC 함수를 import하지 않고 stdlib csv/Decimal로 원본 재계산. 외부 심사 아님.',
            'protected_files_checked':len(inp['protected_files']),'changed_files':changes,
            'independent_evidence_limit':'공식 문서 내용은 별도로 검토했지만 자동 검사만으로 역사 최초 게시시각을 입증하지 않음.'}
    with (OUT/'qc/PHASE2A_INDEPENDENT_QC.json').open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    lines=['# Phase 2-A 독립 QC', '', result['method'], '',f"판정: **{result['qc_status']}**, {len(checks)}개 검사.", '',
           '|검사|결과|방법·범위|','|---|---|---|']
    lines += [f"|{x['check']}|{'PASS' if x['passed'] else 'FAIL'}|{x['detail_ko']}|" for x in checks]
    lines += ['', '감사 코드·원천 수치·정책 구분에 대한 QC다. D10의 실제 역사 가용성 PASS, 외부 심사 통과 또는 Phase 2-B 실행 승인으로 해석하지 않는다.',
              '공식 근거: ../audit/D10_RELEASE_TIMING_AUDIT.md. 실제/가정 예시는 ../audit/D10_TIMING_LOGIC_EXAMPLES.json. 최종 출력 해시는 PHASE2A_OUTPUT_MANIFEST.json에서 자체 파일을 제외하고 기록한다.']
    (OUT/'qc/PHASE2A_INDEPENDENT_QC.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'qc_status':result['qc_status'],'tests':len(checks),'failures':[x['check'] for x in checks if not x['passed']]},ensure_ascii=False))
    if result['qc_status']!='PASS':
        raise SystemExit(1)

if __name__=='__main__':
    main()
