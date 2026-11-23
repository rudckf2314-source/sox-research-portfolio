"""Phase2-B 입력 고정 및 게이트 A 검사. 근거 미충족 시 주간 구축 없이 중단한다."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[2]
AUDIT=OUT.parent/'prebuild_D10_audit'
APPROVAL=AUDIT/'approval_v1_0'
LOCK=ROOT/'research_C/phase1_research_design/approval_lock_v1_1'
INSTRUCTION=Path(r'C:\Users\rudck\.codex\attachments\f823e911-dcfc-4934-9b09-d08b1d5c4b0e\Pasted text.txt')
EXPECTED={
    '02':'00aecd96d4501eee1ad9e36f24a282239e03982612df931287505aa37c37faa5',
    '04':'e7d98d15efbb6a07982dbc9e83f889419621c056434ff707f8d99d9a5cb8f586',
    '08':'9dab052c7e18f371a893f13a7777d7b1da09f11affbbb2250511abb221a4f54c',
    '10':'45508b90248470eaff54adb87da9b12f9d12ab8578b9d68ff56c3af3c0e7ea78',
    '11':'8806acc3c5c8f82d9d8bfabc07ecb8bf7d87c9a02ec733f3aff5de73f7f8ef5f',
    '12':'d708902a4c618195de0784d25c947a025a7362dca819b51538dc5d9e3fdccd23',
    '15':'04c9f287fb1e39f60e677db71b2d31df1fd2bd614637e7d490965a5f8a95409d'}
BLOCKED='BLOCKED_D10_CALENDAR_OR_RELEASE_EVIDENCE'

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def put(rel,obj):
    with (OUT/rel).open('x',encoding='utf-8',newline='\n') as f:
        f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def changed_inputs(m):
    return [r for r,v in m['protected_files'].items() if not (ROOT/r).exists() or sha(ROOT/r)!=v['sha256']]

def prepare():
    if (OUT/'inputs/PHASE2B_INPUT_MANIFEST.json').exists():
        raise SystemExit('기존 실행 산출물을 덮어쓰지 않습니다.')
    for d in ['inputs','code','calendar','data','lineage','qc','reports','logs']:
        (OUT/d).mkdir(parents=True,exist_ok=True)
    old=load(APPROVAL/'D10_INPUT_MANIFEST.json')
    assert not changed_inputs(old),'기존 보호 입력 해시 불일치'
    seal=load(APPROVAL/'D10_OUTPUT_MANIFEST.json')
    assert all(sha(APPROVAL/r['path'])==r['sha256'] for r in seal['files']),'승인 산출물 해시 불일치'
    checksum=(APPROVAL/'D10_OUTPUT_MANIFEST.sha256').read_text(encoding='utf-8').split()[0]
    assert checksum==sha(APPROVAL/'D10_OUTPUT_MANIFEST.json')
    protected=dict(old['protected_files'])
    for p in [APPROVAL/r['path'] for r in seal['files']]+[APPROVAL/'D10_OUTPUT_MANIFEST.json',APPROVAL/'D10_OUTPUT_MANIFEST.sha256',ROOT/'Research_C_RAW3_PrePhase2B_Audit.md']:
        protected[p.relative_to(ROOT).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    refs=[ROOT/'Research_C_Study_Plan_v1_20261016.md',
          *[LOCK/r for r in ['PHASE1_LOCKED_SPEC_v1_1.json','PHASE1_LOCKED_SPEC_v1_1.md','PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json',
                            'PHASE1_GATE_REGISTER.json','reports/PHASE1_LOCK_HANDOFF.md']],
          *[APPROVAL/r for r in ['D10_APPROVED_POLICY.json','D10_GATE_STATUS.json','D10_APPROVAL_HANDOFF.md']],
          AUDIT/'audit/D10_RELEASE_TIMING_AUDIT.md',AUDIT/'reports/PHASE2A_D10_REPORT.md',
          ROOT/'research_C/phase0_raw_audit/PHASE0_COLLECTION_QC.md',
          ROOT/'research_C/phase0_raw_audit/additional_academic_raw_collection/ACADEMIC_RAW_AVAILABILITY_AUDIT.md',
          ROOT/'data/metadata/DATA_SOURCE_REGISTRY.csv',ROOT/'Research_C_RAW3_PrePhase2B_Audit.md',INSTRUCTION]
    read_log=[]
    for p in refs:
        content=p.read_text(encoding='utf-8-sig')
        read_log.append({'path':str(p),'sha256':sha(p),'entire_file_read':True,'characters':len(content)})
    with (OUT/'inputs/USER_PHASE2B_INSTRUCTION.txt').open('xb') as f:
        f.write(INSTRUCTION.read_bytes())
    version_rows=[]; core={}; inventories=[]
    canonical=sorted((ROOT/'data/raw').glob('*/*_RAW_*.csv'))
    for path in canonical:
        first=path.read_text(encoding='utf-8-sig').splitlines()[0]
        df=pd.read_csv(path,comment='#')
        date_col='Date' if 'Date' in df.columns else None
        dates=pd.to_datetime(df[date_col],errors='coerce',format='mixed') if date_col else None
        value_columns=[c for c in df.columns if c!=date_col]
        record={'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size,
                'dataset_id':path.parent.name,'columns':list(df.columns),'rows':len(df),
                'source_metadata':first if first.startswith('# SOURCE') else None,
                'date_column':date_col,'min_date':str(dates.min().date()) if dates is not None and dates.notna().any() else None,
                'max_date':str(dates.max().date()) if dates is not None and dates.notna().any() else None,
                'missing_value_cells':int(df[value_columns].isna().sum().sum()),
                'invalid_or_missing_Date':int(dates.isna().sum()) if dates is not None else None,
                'duplicate_Date':int(dates.duplicated().sum()) if dates is not None else None,
                'date_duplicate_interpretation':'24번은 (Date,HS_Code) 결합키를 검사. 이벤트33번은 Date 단일 시계열로 오인하지 않음.'}
        if path.parent.name.startswith('24_'):
            record['duplicate_Date_HS_Code']=int(df.duplicated(['Date','HS_Code']).sum())
        inventories.append(record)
        prefix=path.parent.name[:2]
        if prefix in EXPECTED:
            version_rows.append({'dataset_id':path.parent.name,'path':record['path'],'sha256':record['sha256'],
                                 'expected_sha256':EXPECTED[prefix],'matches':record['sha256']==EXPECTED[prefix]})
            core[prefix]=(df,dates,record)
    assert len(version_rows)==7,'핵심 canonical 경로 유일성 문제'
    mismatches=[x for x in version_rows if not x['matches']]
    packages={}
    for pkg in ['pandas','numpy','requests','exchange-calendars','pandas-market-calendars','holidays','tzdata']:
        try:
            packages[pkg]=importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            packages[pkg]=None
    zip_paths=[]
    for parent,dirs,files in os.walk(ROOT):
        dirs[:]=[d for d in dirs if d not in {'.venv','.venv_W1','.git','__pycache__'} and Path(parent)/d!=OUT]
        zip_paths += [str(Path(parent)/n) for n in files if n.lower()=='raw(3).zip']
    downloads=Path(r'C:\Users\rudck\Downloads')
    if downloads.exists():
        zip_paths += [str(p) for p in downloads.glob('raw(3).zip')]
    zip_audit={'searched':'프로젝트 전체(가상환경/.git 제외), 사용자 Downloads 최상위',
               'paths':sorted(set(zip_paths)), 'expected_sha256':'70df78b577a969e3e749c00d45714736e902610cccfb0f2db78383e3e1a3baa8',
               'fallback':'압축본 미발견 시 사용자 지시의 개별7개 해시·실제 통계로 대조. ZIP CRC/350항목은 본 실행에서 재검증한 사실이 아님.'}
    if zip_paths:
        zip_audit['found_hashes']=[{'path':p,'sha256':sha(Path(p))} for p in zip_audit['paths']]
    manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'execution_authority':'이번 사용자 제공 Phase2-B 지시문. 기존 승인본의 phase2B_authorized=false는 당시 이력이며 이번 실행지시와 모순 아님.',
        'allowed_scope':'Phase2-B만, 순서 게이트A 선행. Phase3 이후 미승인.',
        'input_read_log':read_log,'protected_files':protected,'raw_canonical_inventory':inventories,
        'core_expected_vs_actual_hashes':version_rows,'raw3_zip_check':zip_audit,
        'runtime':{'python':sys.version,'executable':sys.executable,'packages':packages},
        'versions_installed_or_changed':False,'core_input_mismatches':mismatches}
    put('inputs/PHASE2B_INPUT_MANIFEST.json',manifest)
    put('inputs/RAW_VERSION_AUDIT.json',{'canonical_dataset_folders':len(set(p.parent.name for p in canonical)),
        'canonical_CSV_files':len(canonical),'core_hashes':version_rows,'zip_check':zip_audit,'inventory':inventories})
    if mismatches:
        put('qc/INPUT_VERSION_BLOCK.json',{'status':'BLOCKED_INPUT_VERSION_MISMATCH','mismatches':mismatches})
        raise SystemExit('BLOCKED_INPUT_VERSION_MISMATCH: 원본을 편집하지 말고 확인 필요')
    sox,sox_dates,_=core['02']
    sox_set=set(sox['Date'])
    core_stats={}
    use_columns={'02':'Close','04':'Close','08':'VIXCLS','10':'Adj Close','11':'Fear Greed','12':'Close','15':'DGS10'}
    for k,(frame,dt,rec) in core.items():
        vals=pd.to_numeric(frame[use_columns[k]],errors='raise')
        core_stats[k]={**{x:rec[x] for x in ['path','sha256','rows','min_date','max_date','duplicate_Date']},
            'value_column':use_columns[k],'missing_values':int(vals.isna().sum()),'non_numeric_nonmissing':0,
            'non_finite_values':int((vals.notna() & ~vals.map(lambda v:float('-inf')<v<float('inf'))).sum()),
            'missing_valid_dates_relative_to_SOX':len(sox_set-set(frame.loc[vals.notna(),'Date']))}
    fgi=core['11'][0]
    fgi_specific={d:fgi.loc[fgi.Date.eq(d)].to_dict('records') for d in ['2026-03-12','2026-10-06']}
    gh_path=ROOT/'data/metadata/FGI_REFRESH_20261016/fear-greed_github_d31dc52e.csv'
    gh=pd.read_csv(gh_path,comment='#')
    gh_specific={d:gh.loc[gh.Date.eq(d)].to_dict('records') for d in ['2026-03-12','2026-10-06']}
    monday_labels={str((d-timedelta(days=d.weekday())).date()) for d in sox_dates}
    daily_qc={'status':'PASS','core':core_stats,'SOX_Volume_all_zero':bool(sox.Volume.eq(0).all()),
        'SOX_observed_calendar_week_labels':len(monday_labels),'week_labels_are_valid_model_sample':False,
        'FGI_current_target_rows':fgi_specific,'FGI_retained_GitHub_target_rows':gh_specific,
        'FGI_GitHub_snapshot_path':gh_path.relative_to(ROOT).as_posix(),'FGI_GitHub_snapshot_sha256':sha(gh_path),
        'FGI_source_metadata':core['11'][2]['source_metadata'],
        'FGI_20260312_first_posting_status':'UNVERIFIED','weekly_common_sample_count':None}
    put('qc/RAW_PREFLIGHT_QC.json',daily_qc)
    sources=[
        {'id':'E1','url':'https://www.federalreserve.gov/aboutthefed/k8.htm',
         'observation':'현행 K.8 표는2026~2030. Board/Reserve Banks 토요일 휴일 대체 규칙 차이 확인.',
         'suffices_full_history':False},
        {'id':'E2','url':'https://www.federalreserve.gov/feeds/h15.html',
         'observation':'과거 특별폐쇄·금리 누락/정정 및2016 게시구조 변경 공지. 개별 사건 근거이며 전수 게시일·재개시각 목록 아님.',
         'suffices_full_history':False},
        {'id':'E3','url':'https://www.federalreserve.gov/newsevents/calendar-archive.htm',
         'observation':'열람한 아카이브 인덱스에2017~2022 월별 링크 존재. 전 연구기간의 실제 일별 게시/예외 일정은 확보하지 못함.',
         'suffices_full_history':False},
        {'id':'E4','url':'https://www.federalreserve.gov/newsevents/2026-october.htm',
         'observation':'2026-10 H.15 예정 발표일 및10-12 휴일 이월 확인. 예정 일정은 실제 공개/수신 로그 아님.',
         'suffices_full_history':False},
        {'id':'E5','url':'https://www.federalreserve.gov/releases/h15/20120625/',
         'observation':'2012-06-25 개별 주간 release 접근 성공. 주간/일별 업데이트 및 월요일 휴일 처리 설명 확인.',
         'suffices_full_history':False},
        {'id':'E6','url':'https://www.federalreserve.gov/releases/h15/default.htm',
         'observation':'과거 release의 Release Dates 링크가 현행 페이지로 연결됨. 이 경로로 전수 역사 발표일 목록 확보 못함.',
         'suffices_full_history':False},
        {'id':'E7','url':'https://www.federalreserve.gov/releases/h15/update/default.htm',
         'observation':'구 daily update 경로는2016-10-07 제목으로 응답했으나 추출 본문 없음. 연구기간 전수 근거로 채택하지 않음.',
         'suffices_full_history':False}]
    gaps=[{'start_date':'2011-01-01','end_date':'2016-12-31','status':'FULL_COVERAGE_NOT_ESTABLISHED',
           'missing':'전체 Board 휴일/특별폐쇄 및 daily/weekly release 재개일의 일별 증거. 개별2012 release와 사건 공지만 확인.'},
          {'start_date':'2017-01-01','end_date':'2025-12-31','status':'FULL_COVERAGE_NOT_ESTABLISHED',
           'missing':'일부 월별 아카이브 링크와 사건 공지는 있으나 완전한 일별 H.15 게시일·예외 대조가 미완료.'},
          {'start_date':'2026-01-01','end_date':'2026-10-09','status':'PARTIAL_OFFICIAL_EVIDENCE_ONLY',
           'missing':'2026 법정휴일표와10월 예정일은 확인. 전체기간 특별폐쇄/누락·정정/지연의 usable release 매핑 미완료.'}]
    evidence={'status':BLOCKED,'full_historical_Board_calendar_verified':False,
        'first_source_week_lookback_needs_2010_review':True,'required_research_period':['2011-01-01','2026-10-09'],
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'sources':sources,'coverage_gaps':gaps,
        'failed_queries':[{'url':'https://www.federalreserve.gov/newsevents/2011-january.htm','result':'조회 도구 접근 실패. 공식 원천 자체 부재라고 단정하지 않음.'},
                          {'url':'https://www.federalreserve.gov/newsevents/2016-january.htm','result':'조회 도구 접근 실패. 공식 원천 자체 부재라고 단정하지 않음.'}],
        'authoritative_complete_calendar_file':None,'synthetic_calendar_cannot_replace_actual_evidence':True}
    put('calendar/D10_CALENDAR_EVIDENCE.json',evidence)
    policy=load(APPROVAL/'D10_APPROVED_POLICY.json')
    et=ZoneInfo('America/New_York')
    boundary=datetime(2026,10,5,9,tzinfo=et)
    synthetic={
        'summer_release_UTC':datetime(2026,10,2,16,15,tzinfo=et).astimezone(timezone.utc).hour==20,
        'winter_release_UTC':datetime(2026,1,9,16,15,tzinfo=et).astimezone(timezone.utc).hour==21,
        'DST_spring_origin':datetime(2026,3,9,9,tzinfo=et).astimezone(timezone.utc).hour==13,
        'DST_fall_origin':datetime(2026,11,2,9,tzinfo=et).astimezone(timezone.utc).hour==14,
        'strict_before':boundary-timedelta(microseconds=1)<boundary,
        'equality_excluded':not(boundary<boundary),
        'late_actual_veto':not(datetime(2026,10,5,16,15,tzinfo=et)<boundary),
        'friday_observation_next_Monday_release_not_usable_Monday':not(datetime(2026,10,6,8,tzinfo=et)<boundary),
        'release_next_calendar_day_may_be_Saturday':datetime(2026,10,3,8,tzinfo=et).weekday()==5,
        'mock_holiday_must_not_imply_historical_verification':not evidence['full_historical_Board_calendar_verified']}
    d10={'status':BLOCKED,'gate_A_passed':False,'D10_POLICY':'APPROVED',
         'D10_IMPLEMENTATION_QC':'BLOCKED_INCOMPLETE_CALENDAR_EVIDENCE',
         'policy_id':policy['policy_id'],'synthetic_logic_checks':synthetic,'synthetic_logic_passed':all(synthetic.values()),
         'actual_historical_calendar_QC':'NOT_PASSED','full_observation_availability_mapping_built':False,
         'weekly_B10_created':False,'actual_available_at':None,'publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED',
         'coverage_evidence':'../calendar/D10_CALENDAR_EVIDENCE.json',
         'reason_ko':'시간 논리 및 승인 문서만으로 전기간 Board 실제 게시일·휴일·특별폐쇄·알려진 지연의 구현 QC를 PASS 처리할 수 없다.',
         'original_gate_files_changed':False}
    put('qc/D10_IMPLEMENTATION_QC.json',d10)
    put('calendar/CALENDAR_POLICY_AND_EXCEPTIONS.md','''# Phase2-B 달력 정책·근거 공백

판정: **BLOCKED_D10_CALENDAR_OR_RELEASE_EVIDENCE**. 실제 전수 미국 주식 세션/Board 게시 달력을 생성·검증 완료했다고 표시하지 않는다.

승인된 D10 정책은 관측 다음 실제 Board H.15 게시 영업일16:15 ET, 다음 달력일08:00 ET 가정이다. 승인된 시간 가정과 완전한 역사 게시일 달력은 별개다. 일반 법정휴일 계산, 현재 휴일 규칙의 소급, NYSE 달력 또는 DGS10 결측일을 Board 게시일의 대용으로 쓸 수 없다.

## 확인한 근거와 부족 범위

- [K.8](https://www.federalreserve.gov/aboutthefed/k8.htm)의 현행2026~2030 휴일표만으로2011~2025 전체를 확증할 수 없다.
- [월별 아카이브 인덱스](https://www.federalreserve.gov/newsevents/calendar-archive.htm)와 [2026-10 일정](https://www.federalreserve.gov/newsevents/2026-october.htm)은 일부 링크/예정일 근거다. 전체기간 실제 게시일·예외 대조가 미완료다.
- [2012-06-25 H.15](https://www.federalreserve.gov/releases/h15/20120625/)는 과거 weekly/daily 구조의 개별 근거다. 같은 페이지의 Release Dates는 현행 페이지로 연결됐다. 이것만으로 전체 daily publication calendar를 만들지 않는다.
- [H.15 공지](https://www.federalreserve.gov/feeds/h15.html)에는2016-01-22/25/26 지연과2018-03-21 H.15 예정대로 발행 사례가 있다. 모든 Board 폐쇄가 같은 지연을 낳는다고 가정할 수 없다. 2020-08-19 관측의 늦은 보완,2023-09-12 관측 누락 등도 반영할 usable release 근거가 필요하다. 알려진 사건을 일부 수집했다는 사실이 목록 완전성을 보장하지 않는다.

근거 공백은2011~2016,2017~2025,2026-01~10 연구 구간 전체의 일별 대조에 걸쳐 있다. 2010년 전전주 예열 구간도 첫 원점 구현 시 별도 확인해야 한다. 이는 과거 자료가 존재하지 않는다는 판정이 아니라 이번에 완전한 근거 테이블을 확보/검증하지 못했다는 판정이다.

시간대/DST/strict 경계 소규모 테스트는 PASS지만 실제 달력 QC는 미통과다. 확정적 일별 BOARD_H15_PUBLICATION_CALENDAR.csv를 가짜 값 또는 UNVERIFIED를 숨긴 값으로 만들지 않았다. 빈 헤더를 완료 산출물처럼 만들지도 않았다.

## 필요한 다음 조치

공식 역사 예정/실제 게시 달력과 특별폐쇄·누락·정정의 영향 관측/재개 근거를 수집해 coverage를 전수 대조해야 한다. 그 근거가 끝내 불충분하다면, 미확인 주 제외 또는 제한적인 달력 가정 허용은 현재 순서 게이트를 완화하는 연구 정책 변경이므로 사용자 별도 승인이 필요하다. 자동 진행·범위 축소·B10 삭제로 우회하지 않는다.
''')
    put('lineage/SOURCE_CONFLICT_REGISTER.md',f'''# Phase2-B 원천·이력 충돌 기록

## 입력 버전

핵심7개 RAW는 사용자 지시 해시와 전부 일치한다. 전체47폴더/48 canonical CSV를 실제 검사했다. raw(3).zip은 지정 검색 범위에서 {'발견됨' if zip_paths else '미발견'}이며, ZIP CRC/350항목 및 raw(2) 대비349개 불변은 사용자 독립감사 문서의 보고 사실이다. 이 실행에서 압축본 비교를 수행한 결과로 표현하지 않는다.

## CNN FGI 2026-03-12

현재 canonical에21.15, extreme fear가1행 존재한다. 결측으로 취급하거나 이번 작업에서 복원하지 않았다. 사용자 raw(3) 감사는 raw(2) 대비 이 행1개 추가를 설명한다. SOURCE의 기존 변환 설명은 이 행의 추가 경위·최초 게시시각을 개별 증명하지 않는다. 보존 GitHub 스냅샷의 해당 날짜 행수는 {len(gh_specific['2026-03-12'])}개다. 이 비교는 점수 자체의 거짓/참을 판정하는 것이 아니며 최초 원천·게시·빈티지는 UNVERIFIED다. 기존 계획서의 과거 결손 문구와 현재 존재 상태를 구분한다.

## CNN FGI 2026-10-06

현재 로컬 우선 값47.3714285714286과 보존 GitHub46.8 충돌 이력을 유지한다. canonical을 수정하지 않았다. 자세한 실제 행·원천 해시는 qc/RAW_PREFLIGHT_QC.json에 있다.

## 구버전 레지스트리

기존 DATA_SOURCE_REGISTRY.csv에는 NOT_COLLECTED/TBD 등 과거 상태가 남아 있다. 현재 파일 존재와 모순되는 상태는 역사 메타데이터로 기록하며 원본을 편집하지 않았다. 실제 입력 판정은 current canonical 해시·SOURCE·승인 사양을 우선한다.

## 게시·빈티지

HYG Adj Close와 나머지 현재 수정 원천의 과거 최초 빈티지 및 게시시각 UNVERIFIED를 유지한다. 날짜 교집합이나 현재값 존재를 실제 PIT 검증으로 승격하지 않는다. SOX Volume=0 전체이며 거래량 X로 사용하지 않는다.
''')
    put('lineage/POLICY_APPLICATION_SUMMARY.json',{'status':BLOCKED,
        'phase2B_preflight_execution_authorized_by_current_user_instruction':True,
        'D04_policy_id':'C_DAILY_EOD_NEXT_US_SESSION_0800_ET_v1_1','D10_policy_id':policy['policy_id'],
        'D04_applied_to_DGS10':False,'actual_policy_application_to_entire_series':False,
        'reason':'게이트A 달력 근거 미충족, 전수 시점매핑/주간 변수 생성 전 중단',
        'actual_available_at':None,'publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED',
        'D13_status':'PENDING_WEEKLY_MISSINGNESS_AUDIT',
        'execution_counts':{'full_US_session_calendar':0,'full_Board_publication_calendar':0,'weekly_B10':0,'weekly_X':0,
                            'weekly_Y':0,'weekly_common_dataset':0,'model_fits':0,'predictions':0,'test_metrics':0,'robustness_experiments':0}})
    checks={
        'required_inputs_read_and_hashed':len(read_log)==16,
        'prior_protected_hashes_verified':not changed_inputs(manifest),
        'approval_output_seal_verified':True,'core7_hashes_match_user':not mismatches,
        '47_RAW_folders_48_canonical_files':len(set(p.parent.name for p in canonical))==47 and len(canonical)==48,
        'core_dates_valid_and_unique':all(x['duplicate_Date']==0 for x in core_stats.values()),
        'SOX3966_FGI3970_DGS104378':core_stats['02']['rows']==3966 and core_stats['11']['rows']==3970 and core_stats['15']['rows']==4378,
        'DGS10_180_VIX116_missing_preserved':core_stats['15']['missing_values']==180 and core_stats['08']['missing_values']==116,
        'SOX_core_date_coverage':all(core_stats[k]['missing_valid_dates_relative_to_SOX']==0 for k in ['04','08','10','11','12']),
        'FGI_0312_present_not_newly_restored':len(fgi_specific['2026-03-12'])==1 and fgi_specific['2026-03-12'][0]['Fear Greed']==21.15,
        'SOX_volume_not_a_trade_volume_X':daily_qc['SOX_Volume_all_zero'],
        'synthetic_clock_tests_pass':all(synthetic.values()),
        'full_historical_Board_evidence':False,
        'weekly_build_stopped_before_gate_A':not list((OUT/'data').iterdir()),
        'no_full_actual_timestamps_invented':d10['actual_available_at'] is None,
        'D13_not_automatically_locked':True}
    qc={'status':BLOCKED,'gate_A_passed':False,'checks':checks,'test_count':len(checks),
        'failed_required_checks':[k for k,v in checks.items() if not v],
        'independent_QC_pending':True,'not_a_completed_Phase2B_QC_PASS':True,
        'input_version_status':'PASS','clock_unit_logic_status':'PASS','historical_calendar_status':'BLOCKED',
        'weekly_sample_counts':{'C_M0':None,'C_M1':None,'common':None},
        'protected_count':len(protected),'protected_changes':changed_inputs(manifest),
        'raw_downloads':0,'models_fit':0,'weekly_XY_created':0,'D13_details_locked':False}
    put('qc/PHASE2B_QC.json',qc)
    put('logs/PHASE2B_WORK_LOG.md',f'''# Phase2-B 실행 로그

UTC {datetime.now(timezone.utc).isoformat()}. 사용자 제공 지시문을 로컬에서 읽고 원문 바이트와 해시를 보존했다. 이전 실행 불변 기준과 승인 output manifest를 대조했다.

핵심7개 해시 일치, 전체 canonical48개/47폴더 원본 통계 검사. 실제 수치·Date·결측만 검증하며 목표 Y 통계·성능·상관은 출력하지 않았다. 원천 재수집/수정0건.

공식 현행 휴일표·과거 개별release·월별인덱스·공지·2026-10 일정을 조사했다.2011/2016 January 직접추측 경로는 접근 실패였으며 공식 원천 자체 부재라고 해석하지 않았다. 전수 Board H.15 게시달력 근거는 미충족이다.

순서 게이트A {BLOCKED}. 시간 논리 synthetic {len(synthetic)}개 PASS와 실제 전수 달력 검증을 구별했다. 주간 B10/공통표본/X/Y/미국 세션 전수 매핑은 생성하지 않았다. 이후 단계0회.

이 부분 실행을 완료된 Phase2-B라고 표현하지 않는다. 독립 검사 및 차단 보고서만 작성하고 종료한다. 이전 단계 원본 게이트·승인 정책은 변경하지 않는다.
''')
    put('README.md','''# 연구 C Phase2-B 게이트A 중단 기록

상태: **BLOCKED_D10_CALENDAR_OR_RELEASE_EVIDENCE**. 입력버전 사전점검 및 달력 근거 조사까지만 수행했다. 주간 데이터 구축은 실행되지 않았다.

reports/PHASE2B_REPORT.md에서 중단 원인·필요 근거·미생성 항목을 확인한다. 원본 자료나 정책이 잘못됐다는 판정이 아니라, 이번 지시가 요구한 전기간 역사 Board 게시달력 근거가 충족되지 않았다는 판정이다.

code/phase2b_preflight.py prepare → code/independent_preflight_qc.py → code/phase2b_preflight.py seal 순서로 사전점검을 재현한다. 기존 실행을 덮어쓰지 않으므로 같은 깊이의 새 폴더에 code만 두고 사용한다. 이 코드는 주간 X/Y 구축기가 아니다. 활성 연구 C 가상환경과 입력 버전은 inputs manifest에 있다.

data 폴더는 비어 있다. 실제 전수 달력, FEATURE_AVAILABILITY_LOG.csv, SOX_WEEKLY_Y.csv, WEEKLY_CORE_X.csv, WEEKLY_C_M0_M1_DATASET.csv는 게이트 때문에 만들지 않았다. Phase3 이후는 실행하지 않았다.
''')
    print(json.dumps({'status':BLOCKED,'input_hashes':'7/7 PASS','canonical_files':len(canonical),
        'protected':len(protected),'SOX_raw_calendar_week_labels':len(monday_labels),'weekly_dataset_created':False,
        'failed_checks':qc['failed_required_checks']},ensure_ascii=False,indent=2))

def seal():
    m=load(OUT/'inputs/PHASE2B_INPUT_MANIFEST.json'); q=load(OUT/'qc/PHASE2B_QC.json')
    independent=load(OUT/'qc/PHASE2B_INDEPENDENT_QC.json')
    assert independent['independent_preflight_check_status']=='PASS'
    assert not changed_inputs(m)
    raw=load(OUT/'qc/RAW_PREFLIGHT_QC.json')
    lines=['|원천|실제 SHA-256|대조|','|---|---|---|']
    lines += [f"|{r['dataset_id']}|`{r['sha256']}`|PASS|" for r in m['core_expected_vs_actual_hashes']]
    report=f'''# 연구 C Phase2-B 사전점검 및 게이트A 중단 보고서

## 1. 최종 판정

**{BLOCKED}**. Phase2-B 실행 지시는 승계했지만, 전 기간 실제 Federal Reserve Board H.15 게시 영업일/휴일/특별폐쇄/알려진 지연 근거의 구현 QC를 통과하지 못했다. 지시문2절 순서 게이트A와7절 중단 규칙에 따라 **주간 B10·주력 공통표본 구축 전에 중단**했다. 이는 Phase2-B 완료/성공 보고서가 아니다.

## 2. 실제 RAW 버전·무결성

전체47 RAW 폴더/48 canonical CSV를 검사했고, 핵심7개 해시는 지시문과 모두 일치했다.

{chr(10).join(lines)}

raw(3).zip은 지정한 로컬 검색에서 미발견이므로 사용자 지시가 허용한 개별 해시·통계 대조를 사용했다. 압축본350항목·CRC정상·raw(2) 대비FGI1행 차이는 사용자 제공 독립감사 문서의 보고 사실이며 이번에 ZIP을 직접 재검증했다고 주장하지 않는다. 상세 인벤토리와 SOURCE는 inputs/RAW_VERSION_AUDIT.json에 있다.

SOX3966행(2011-01-03~2026-10-09), FGI3970행(2011-01-03~2026-10-15), DGS104378행(결측180), VIX4115행(결측116)을 재현했다. 핵심 날짜 중복0, SOX 날짜의 SPX/NDX/HYG/유효VIX/FGI 누락0이다. 일별 날짜 교집합은 시점가용성 입증이 아니다. SOX Volume 전체0이며 입력으로 사용하지 않았다.

## 3. 거래주·유효표본

SOX RAW에 관측이 존재하는 미국 월요일 달력 주 표지는 **{raw['SOX_observed_calendar_week_labels']}개**다. 이는 실제 거래소 세션·주간 Y·주력 X의 유효표본 수가 아니다. 거래소 달력 전수 대조와 주간 구축을 게이트 후로 보류했으므로 **C-M0/C-M1/공통 유효주수 및 시작·종료주는 미산출(null)**이다. 특정 숫자로 강제 맞추지 않았다. 마지막 SOX 관측10-09/완료주후보10-05는 원천 사실이며 실제 주간 라벨을 생성하지 않았다.

## 4. D10 구현 게이트 및 부족 근거

승인 정책 C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1 자체는 APPROVED로 유지한다. 구현 게이트A는 차단이다. NY DST/strict before/known-late veto의 소규모 논리검사10개는 PASS지만 전수 실제 달력 검증은 아니다.

현행 [K.8 휴일표](https://www.federalreserve.gov/aboutthefed/k8.htm)는2026~2030 범위다. [과거 월별 인덱스](https://www.federalreserve.gov/newsevents/calendar-archive.htm)와 [2012 개별release](https://www.federalreserve.gov/releases/h15/20120625/) 접근만으로 전기간 일별 실제 게시일·휴일·특별폐쇄 완전성을 입증할 수 없다. [H.15 공지](https://www.federalreserve.gov/feeds/h15.html)는 실제 지연·누락/정정의 개별 근거지만 완전한 usable release 매핑이 아니다.

부족 범위:2011~2016 전수 daily/weekly 게시·휴일·재개일;2017~2025 완전한 일별 달력/예외 대조;2026-01~10 전체 예외 매핑. 첫 원점에 필요한2010 예열 주도 검토가 필요하다. 실제 자료의 부재가 아니라 이번 근거 확보·대조의 미완료다. 공급자 최초 게시시각·빈티지 UNVERIFIED는 승인된 한계로 그대로 유지한다. 현재 장애는 그 한계를 재승인받으려는 것이 아니라 **이번 지시가 별도로 요구한 달력 전수 QC 미충족**이다.

## 5. FGI lineage

2026-03-12=21.15, extreme fear가 현재 파일에1행 존재한다. 결측 처리하거나 이번에 복원하지 않았다. 사용자 독립감사는 raw(3) 추가1행을 설명한다. SOURCE의 과거 변환 문구만으로 최초 출처/게시를 입증할 수 없고 보존 GitHub 스냅샷에는 이 날짜 행이 없다. 이 사실은 점수 오류 판정이 아니다. 게시/빈티지 UNVERIFIED,2026-10-06 로컬47.3714285714286 대 GitHub46.8 충돌 이력은 유지했다. 원본과 메타데이터는 편집하지 않았다.

## 6. D13 및 다음 결정

실제 주간 공통표본이 없으므로 D13 결손 패턴·연속주 길이·재표본 n을 계산할 수 없다. D13은 PENDING_WEEKLY_MISSINGNESS_AUDIT이며 세부 LOCK을 하지 않았다. 숫자·재추출 규칙을 임의로 채우지 않는다.

우선 공식 역사 게시달력·휴일·특별폐쇄·누락/정정의 영향 관측/재개 근거를 보완해야 한다. 끝내 완전한 근거가 부족하다면 미확인 주 제외 또는 명시적인 달력 가정 허용은 현재 게이트를 변경하는 별도 승인사항이다. B10을 조용히 제외하거나D04로 대체하지 않는다. 승인 정책·Y 정의·연구기간을 임의 변경하지 않는다.

## 7. QC 및 보호

자동 검사{q['test_count']}개 중 전수 역사 Board 근거1개가 미통과다. 따라서 전체 QC는 **{BLOCKED}**이며 PASS로 표현하지 않는다. 독립 검사는 **{independent['test_count']}개 사전점검 검사 PASS, 차단 판정 재현**이다. 동일 Codex 내 별도 구현이며 외부 심사가 아니다. 입력·보호 해시 및 일별 수치를 stdlib 방식으로 재대조하고 작성 코드를 import하지 않았다.

보호파일 **{len(m['protected_files'])}개 SHA-256 불변**. RAW·freeze·Phase0/1·Phase2-A 감사/승인 원본 변경0건. 전체 X/Y 생성, 실제 주간 B10, 공통표본 확정, 전처리 fit, Phase3 학습/튜닝, Phase4 예측/오차/성능, Phase5 강건성은 모두0회다. 최종 시험 Y를 새로 생성하거나 타깃 통계·성능·상관을 출력하지 않았다.

## 8. 산출물과 중단

전용경로: research_C/phase2_weekly_dataset/build_v1_0/. 입력manifest·원문 지시·원천QA, 근거공백, lineage충돌, D10/전체/독립QC, 코드·로그·README·보고서·인수인계를 저장했다. 출력해시는 qc/PHASE2B_OUTPUT_MANIFEST.json과 별도 .sha256에 기록한다.

**미생성 항목:** US_MARKET_SESSIONS.csv, BOARD_H15_PUBLICATION_CALENDAR.csv, FEATURE_AVAILABILITY_LOG.csv 및 data의 주간Y/X/통합3개CSV. 게이트 미통과이므로 빈 파일이나 미검증 날짜로 완료 산출물처럼 만들지 않았다. data 폴더는 비어 있다. 사용자 검토를 기다리며 중단한다.
'''
    put('reports/PHASE2B_REPORT.md',report)
    put('reports/PHASE2B_D13_MISSINGNESS_AUDIT.md','''# D13 결손 감사 미실행 기록

상태 PENDING_WEEKLY_MISSINGNESS_AUDIT / NOT_EXECUTED_GATE_A_BLOCKED. D10 게이트A의 전수 역사 달력 근거가 미충족되어 주간 공통표본을 생성하지 않았다. 따라서 결손주·연속구간·유효쌍수는 미산출(null)이다. 일별 원천 결측수를 주간 결손수로 대체하지 않는다.

Bootstrap 최소n, 부족/빈반복 처리, 재추출 최대횟수·실패처리는 원래 미확정 상태로 유지한다. 사용자의 후속 지시로 D10 장애가 해소되고 주간 자료/QC가 준비되면 실제 결손패턴을 근거로 사용자에게 별도 LOCK을 요청한다. 최종 시험 오차·성능 열람 전 확정해야 하며 이번에 추론·잠금을 수행하지 않았다.
''')
    put('reports/PHASE2B_HANDOFF.md','''# Phase2-B 게이트A 중단 인수인계

현재 실행 상태 BLOCKED_D10_CALENDAR_OR_RELEASE_EVIDENCE. 사용자 실행지시는 인정되나 지시문 순서 게이트A의 전기간 역사 Board H.15 게시달력·예외 근거를 확보/검증하지 못했다. 핵심7개RAW 해시는 모두 raw(3) 기준과 일치했다. 원본 수정·재수집은0건이다.

먼저 PHASE2B_REPORT.md, ../calendar/D10_CALENDAR_EVIDENCE.json, ../calendar/CALENDAR_POLICY_AND_EXCEPTIONS.md, ../qc/D10_IMPLEMENTATION_QC.json, ../qc/PHASE2B_INDEPENDENT_QC.md를 읽는다. 승인된 D10 정책의16:15→다음 달력일08시 가정과 실제 달력 전수 검증은 별개다. 과거 actual/vintage UNVERIFIED 한계는 이미 승인됐으므로 이를 새로운 정책 미승인 문제로 바꾸지 않는다.

필요 조치는2011~2026 및 필요한2010예열 주의 공식 게시일·Board 휴일·특별폐쇄·금리 누락/정정의 usable release 근거 보완이다. 근거가 부족한 구간의 제외 또는 별도 달력 가정 허용은 현재 게이트 변경이므로 명시적 사용자 승인을 받아야 한다. 임의 미국 연방휴일/NYSE 달력이나 원천 결측으로 전수 확인을 대신하지 않는다.

주간 B10, Y, CORE X, 공통표본은 미생성이고 data 폴더는 비어 있다. D13 실제 결손 감사·상세 LOCK도 미실행이다. Phase3 학습·Phase4 최종시험·강건성0회. 기존 Phase1 LOCK 및 D10 승인 원본 상태는 그대로다. 이 폴더는 완료된 연구용 데이터셋이 아니라 중단된 사전점검의 재현기록이다.

같은 실행 폴더 재실행/덮어쓰기를 금지하는 코드로 보존했다. 후속 승인이 있으면 새 실행 버전에 재현코드와 달력 근거를 보완하고 이전 중단 기록은 유지한다. 전체 산출물 해시는 qc output manifest를 확인한다. 사용자 검토를 기다린다.
''')
    q['independent_QC_pending']=False
    q['independent_QC_status']=independent['independent_preflight_check_status']
    q['independent_status_note']='사전점검 교차확인 및 차단판정 재현. 전체 Phase2-B PASS가 아님.'
    # 이번 새 실행의 QC만 최종화. 기존 Phase2-A/원천 파일에는 쓰지 않는다.
    (OUT/'qc/PHASE2B_QC.json').write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert not changed_inputs(m)
    files=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file()]
    output={'status':BLOCKED,'file_count_including_manifest_and_checksum':len(files)+2,'files':files,
        'excluded_from_hash':['qc/PHASE2B_OUTPUT_MANIFEST.json','qc/PHASE2B_OUTPUT_MANIFEST.sha256'],
        'protected_inputs_unchanged':len(m['protected_files']),'protected_changes':[],
        'weekly_datasets_created':False,'Phase3_executed':False,'not_a_completed_Phase2B_PASS':True}
    put('qc/PHASE2B_OUTPUT_MANIFEST.json',output)
    put('qc/PHASE2B_OUTPUT_MANIFEST.sha256',sha(OUT/'qc/PHASE2B_OUTPUT_MANIFEST.json')+'  PHASE2B_OUTPUT_MANIFEST.json\n')
    print(json.dumps({'status':BLOCKED,'files':len(files)+2,'protected_unchanged':len(m['protected_files']),
        'report':str(OUT/'reports/PHASE2B_REPORT.md')},ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','seal'])
    args=parser.parse_args()
    {'prepare':prepare,'seal':seal}[args.stage]()
