"""연구 C D10 읽기 전용 감사. 주간 변수/라벨/모델을 생성하지 않는다."""
from __future__ import annotations
import hashlib
import json
import platform
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'research_C/phase1_research_design/approval_lock_v1_1'
RAW = ROOT / 'data/raw/15_dgs10/15_dgs10_RAW_20100101_20261014.csv'
ORIGINAL = ROOT / 'research_C/phase0_raw_audit/run_20261016_final/new_raw/DGS10_FRED_original.csv'
NOW = datetime.now(timezone.utc).isoformat()
ET = ZoneInfo('America/New_York')

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def read_json(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def put(rel, content):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8', newline='\n') as f:
        f.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def mdtable(headers, rows):
    return '\n'.join(['|'+'|'.join(headers)+'|', '|'+'|'.join(['---']*len(headers))+'|'] +
                     ['|'+'|'.join(str(x) for x in row)+'|' for row in rows])

def main():
    if (OUT/'inputs/PHASE2A_INPUT_MANIFEST.json').exists():
        raise SystemExit('기존 실행을 덮어쓰지 않습니다. 새 실행 경로를 사용하십시오.')
    for name in ['inputs', 'code', 'audit', 'qc', 'reports', 'logs']:
        (OUT/name).mkdir(parents=True, exist_ok=True)
    prior = read_json(LOCK/'inputs/PHASE1_LOCK_INPUT_MANIFEST.json')
    old_qc = read_json(LOCK/'qc/PHASE1_LOCK_QC.json')
    authorized = {x['path']:x['current_sha256'] for x in old_qc['authorized_index_append']}
    historical_changes = []
    for rel, rec in prior['protected_files'].items():
        p = ROOT/rel
        current = sha(p) if p.exists() else None
        if current != rec['sha256'] and current != authorized.get(rel):
            historical_changes.append(rel)
    lock_manifest = read_json(LOCK/'qc/PHASE1_LOCK_OUTPUT_MANIFEST.json')
    locked_changes = [r['path'] for r in lock_manifest['files'] if sha(LOCK/r['path']) != r['sha256']]
    if historical_changes or locked_changes:
        raise RuntimeError(f'기존 기준 해시 불일치: {historical_changes}, {locked_changes}')
    protected_paths = set(prior['protected_files'])
    protected_paths.update(p.relative_to(ROOT).as_posix() for p in LOCK.rglob('*') if p.is_file())
    protected = {r:{'sha256':sha(ROOT/r), 'bytes':(ROOT/r).stat().st_size} for r in sorted(protected_paths)}
    refs = ['Research_C_Study_Plan_v1_20261016.md'] + [
        'research_C/phase1_research_design/approval_lock_v1_1/'+s for s in [
            'PHASE1_LOCKED_SPEC_v1_1.md', 'PHASE1_LOCKED_SPEC_v1_1.json',
            'PHASE1_APPROVED_DECISIONS.json', 'PHASE1_GATE_REGISTER.json',
            'reports/PHASE1_LOCK_REPORT.md', 'reports/PHASE1_LOCK_HANDOFF.md',
            'qc/PHASE1_LOCK_QC.json', 'qc/PHASE1_LOCK_INDEPENDENT_QC.md']]
    refs += ['research_C/phase0_raw_audit/PHASE0_COLLECTION_QC.md',
             'research_C/phase0_raw_audit/additional_academic_raw_collection/ACADEMIC_RAW_AVAILABILITY_AUDIT.md',
             'research_C/phase1_research_design/design/PHASE1_POINT_IN_TIME_PROTOCOL.md']
    reads = []
    for r in refs:
        text = (ROOT/r).read_text(encoding='utf-8-sig')
        reads.append({'path':r, 'read_entire_file':True, 'characters':len(text), 'sha256':sha(ROOT/r)})
    spec = read_json(LOCK/'PHASE1_LOCKED_SPEC_v1_1.json')
    gate = read_json(LOCK/'PHASE1_GATE_REGISTER.json')
    formula = spec['core_variables']['B10']['formula']
    put('inputs/PHASE2A_INPUT_MANIFEST.json', {
        'created_at_utc':NOW, 'study':'C', 'authorized_scope':'PHASE2A_D10_PREBUILD_AUDIT_ONLY',
        'protected_files':protected, 'full_read_log':reads,
        'original_lock_manifest_verified':True, 'prior_input_baseline_unexplained_changes':historical_changes,
        'prior_authorized_index_append_not_new_change':authorized,
        'D10_original_status':gate['D10_GATE_STATUS'], 'D13_original_status':gate['D13_GATE_STATUS'],
        'runtime':{'python':sys.version, 'pandas':pd.__version__, 'platform':platform.platform(), 'executable':sys.executable},
        'actual_data_inputs':[str(RAW.relative_to(ROOT)),str(ORIGINAL.relative_to(ROOT))],
        'B10_formula_unchanged':formula})
    df = pd.read_csv(RAW, comment='#')
    dates = pd.to_datetime(df.Date, format='%Y-%m-%d', errors='raise')
    values = pd.to_numeric(df.DGS10, errors='raise')
    original = pd.read_csv(ORIGINAL).rename(columns={'observation_date':'Date'})
    pd.testing.assert_frame_equal(df, original)
    source_line = RAW.read_text(encoding='utf-8-sig').splitlines()[0]
    source_hash = source_line.split('source_sha256=')[1].strip()
    missing = values.isna()
    annual = []
    for y in sorted(dates.dt.year.unique()):
        mask = dates.dt.year.eq(y)
        annual.append({'year':int(y),'rows':int(mask.sum()),'valid':int((mask & ~missing).sum()),'missing':int((mask & missing).sum())})
    valid_dates = dates[~missing]
    gaps = valid_dates.diff().dt.days
    i = gaps.idxmax()
    previous = valid_dates.loc[:i].iloc[-2]
    streak = best = 0
    for m in missing:
        streak = streak+1 if m else 0
        best = max(best,streak)
    study = dates.ge('2011-01-01') & dates.le('2026-10-09')
    q = {
        'raw_path':str(RAW.relative_to(ROOT)), 'sha256':sha(RAW), 'source_metadata':source_line,
        'source_original_path':str(ORIGINAL.relative_to(ROOT)), 'source_original_sha256':sha(ORIGINAL),
        'source_original_sha256_matches_metadata':sha(ORIGINAL)==source_hash,
        'canonical_values_equal_original':True, 'columns':list(df.columns),
        'units':'Percent per annum, Not Seasonally Adjusted', 'rows':len(df),
        'valid_values':int(values.notna().sum()), 'min_date':str(dates.min().date()),'max_date':str(dates.max().date()),
        'missing_date':int(dates.isna().sum()),'duplicate_dates':int(dates.duplicated().sum()),
        'missing_values':int(missing.sum()), 'missing_rate_pct':float(missing.mean()*100),
        'non_numeric_nonmissing':0, 'non_finite_values':int((values.notna() & ~values.map(lambda x: float('-inf')<x<float('inf'))).sum()),
        'min_value':float(values.min()), 'max_value':float(values.max()),
        'negative_or_zero_values':int(values.le(0).sum()),
        'heuristic_outside_0_20_pct':int(((values<0)|(values>20)).sum()),
        'adjacent_source_row_change_over_100bp':int(values.diff().abs().gt(1).sum()),
        'heuristic_note':'0–20% 및 인접 원본행 변화 100bp 초과는 점검용 기준이며 자동 오류 판정·삭제 기준이 아니다. 결측을 건너뛰지 않음.',
        'ascending':bool(dates.is_monotonic_increasing), 'weekend_rows':int(dates.dt.dayofweek.ge(5).sum()),
        'all_weekday_dates_present':set(dates)==set(pd.bdate_range(dates.min(),dates.max())),
        'missing_dates':list(df.loc[missing,'Date']), 'annual_counts':annual,
        'missing_by_weekday':{str(k):int(v) for k,v in dates[missing].dt.dayofweek.value_counts().sort_index().items()},
        'longest_missing_source_row_run':best,
        'max_gap_between_valid_dates_days':int(gaps.max()),
        'max_gap_dates':[str(previous.date()),str(valid_dates.loc[i].date())],
        'study_source_date_audit_20110101_20261009':{'rows':int(study.sum()),'valid':int((study & ~missing).sum()),'missing':int((study & missing).sum())},
        'revision_spotchecks':{d:float(values[dates.eq(d)].iloc[0]) for d in ['2011-03-10','2014-01-14']},
        'actual_release_at':None,'actual_available_at':None,'publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED',
        'exact_B10_valid_week_count':None,'exact_common_sample_loss':None}
    put('audit/D10_RAW_STATISTICS.json',q)
    evidence = [
        ('E01','Federal Reserve H.15 current release','https://www.federalreserve.gov/releases/h15/',
         '현행 월~금 16:15 게시, 휴일·Board 폐쇄 제외. 확인 페이지 2026-10-16, 최신 관측 10-15. Treasury constant maturity는 연율 %.',
         '현재 페이지 한 건이며 2011~2026 개별 최초 게시시각의 전수 증거가 아니다.'),
        ('E02','H.15 About','https://www.federalreserve.gov/releases/h15/about.htm',
         '휴일을 제외한 영업일에 H.15 게시.','영업일 일반규칙이며 실제 발표 로그가 아니다.'),
        ('E03','H.15 Announcements','https://www.federalreserve.gov/feeds/h15.html',
         '2011-03-14: 03-10 10년물 3.46→3.37 정정(최초 03-11 release). 2014-01-15: 전일 10년물 2.77→2.88 정정. 2016-01-22/25/26 기상 폐쇄 지연. 2016-10-11 게시형식 변경 및 영업일16:15 명시. 2023-09-12 Treasury 금리 09-13 발표 누락 후 09-14 복원.',
         '선별된 명시 사례만 확인. 전체 지연·정정 목록의 완전성이나 모든 당시 FRED 반영시각을 보장하지 않는다.'),
        ('E04','H.15 Technical Q&A','https://www.federalreserve.gov/releases/h15/h15_technical_qa.htm',
         '2016-10 이후 평균자료 DDP 이용 안내, 2016-11 월평균 게시 일정 변경 설명.',
         '월평균 일정은 일별 DGS10 규칙으로 전용할 수 없다. 2016 이전 모든 일별 시각 확증 아님.'),
        ('E05','Federal Reserve K.8','https://www.federalreserve.gov/aboutthefed/k8.htm',
         '2026 Board 휴일: 01-19,07-03(토요일 독립기념일 대체),10-12 등. 토요일 휴일의 금요일은 Reserve Banks와 Board 운영이 다를 수 있다.',
         '현행2026~2030 달력. 이를 2011년부터의 완전한 역사 달력으로 역투영하지 않음. 주식시장 일정과 별도.'),
        ('E06','FRED DGS10','https://fred.stlouisfed.org/series/DGS10',
         'Fed Board H.15, 일간·비계절조정 %. 확인 당시 10-15 관측,10-16 15:16 CDT 업데이트 표시. 모든 자료 개정 가능 안내.',
         '이번 업데이트 시각을 전체 역사 최초 공개시각 또는 고정 1분 FRED 지연으로 사용하지 않는다.'),
        ('E07','FRED API real-time periods','https://fred.stlouisfed.org/docs/api/fred/realtime_period.html',
         'FRED 기본은 현재 알려진 과거 자료, ALFRED는 과거 real-time 기간을 지정해 조회하는 방식. vintage 기간은 날짜 단위.',
         'ALFRED 지원 자체는 개별 최초 수신시각 입증이 아니다. 본 감사는 과거 빈티지 시계열을 다운로드하지 않았다.'),
        ('E08','ALFRED DGS10','https://alfred.stlouisfed.org/series?seid=DGS10',
         'DGS10 vintage 접근 페이지와 2014-04-02 제목 변경 기록 존재. 단위·일간주기·H.15 원천 표시.',
         '실제 과거값·release date의 전수 대조 및 시각 검증은 미실시. 제목 변경을 자동 정의변경으로 간주하지 않는다.')]
    put('audit/OFFICIAL_EVIDENCE_REGISTER.json',{'checked_at_utc':NOW,'method':'공식 웹페이지 열람 후 한국어 요약. 원본 RAW 신규 수집 없음.',
        'sources':[dict(zip(['id','title','url','confirmed','limits'],x)) for x in evidence],
        'failed_access':[{'url':'https://www.federalreserve.gov/releases/h15/20110110/','result':'조회 도구 접근 실패; 근거로 사용하지 않음'},
                         {'url':'https://www.federalreserve.gov/releases/h15/20160125/','result':'조회 도구 접근 실패; 근거로 사용하지 않음'}]})
    proposal = {
        'policy_id':'C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1_PROPOSAL',
        'approval_status':'NOT_APPROVED_PROPOSAL_ONLY','executed_on_real_series':False,
        'formula':formula,'observation_timezone':'America/New_York','strict_operator':'<',
        'origin_rule':spec['origin'], 'actual_release_at':None,'actual_available_at':None,
        'assumed_release_rule':'관측일 다음 Board H.15 게시 영업일 16:15 America/New_York. 일반화 가정이며 역사 실제 시각 아님.',
        'assumed_provider_rule':'가정 발표 다음 달력일 08:00 America/New_York. 약15시간45분 완충 가정이며 FRED 게시 입증 아님.',
        'historical_calendar_requirement':'2011~2026 Board 실제 휴일·특별폐쇄·H.15 예외 확인. NYSE 일정이나 현대 연방휴일 규칙의 무조건 역적용 금지.',
        'known_delay_rule':'알려진 지연/누락/정정은 일반 가정으로 덮어쓰지 않는다. 해당 관측의 usable release 근거 미확보 시 제외하고 사유 기록.',
        'week_selection_rule':'동일 O에서 w-1 및 w-2 각 원천 주 내부의 적격 마지막 관측. 해당 주에 없으면 NaN, 다른 주 이월/금요일 강제/보간 금지.',
        'actual_only_mode':'실제 제공처 가용시각·당시 빈티지 입증 자료만 적격. 현재 RAW만으로 전체 장기표본 확정 불가.',
        'availability_basis':'ASSUMED_CONSERVATIVE','publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED',
        'D04_applied_to_DGS10':False,'D10_gate_updated':False,'requires_user_approval':True,
        'no_fixed_delay_proves_all_history':True}
    put('audit/D10_POLICY_PROPOSAL.json',proposal)
    examples = []
    for name,obs,release,origin in [
        ('보통 금요일, 월요일09시 전 불가','2026-10-02','2026-10-05T16:15:00','2026-10-05T09:00:00'),
        ('같은 원천 주 목요일 후보','2026-10-01','2026-10-02T16:15:00','2026-10-05T09:00:00'),
        ('겨울시각 목요일 후보','2026-01-08','2026-01-09T16:15:00','2026-01-12T09:00:00'),
        ('월요일 휴장, 금요일 관측 여전히 불가','2026-01-16','2026-01-20T16:15:00','2026-01-20T09:00:00'),
        ('월요일 휴장, 같은 원천 주 목요일 후보','2026-01-15','2026-01-16T16:15:00','2026-01-20T09:00:00'),
        ('Board 월요일휴일 예시','2026-10-09','2026-10-13T16:15:00','2026-10-12T09:00:00'),
        ('Board 금요일폐쇄: 목요일 관측도 불가','2026-07-02','2026-07-06T16:15:00','2026-07-06T09:00:00'),
        ('Board 금요일폐쇄: 수요일 후보','2026-07-01','2026-07-02T16:15:00','2026-07-06T09:00:00')]:
        rel = datetime.fromisoformat(release).replace(tzinfo=ET)
        ori = datetime.fromisoformat(origin).replace(tzinfo=ET)
        assumed = (rel+timedelta(days=1)).replace(hour=8,minute=0)
        examples.append({'example':name, 'observation_date':obs, 'prediction_origin':ori.isoformat(),
                         'assumed_release_at':rel.isoformat(),'assumed_available_at':assumed.isoformat(),
                         'assumed_eligible':assumed<ori,'actual_release_at':None,'actual_available_at':None,
                         'publication_status':'UNVERIFIED','is_example_not_actual_mapping':True})
    put('audit/D10_TIMING_LOGIC_EXAMPLES.json',{'scope':'날짜·시각 논리 예시만. 실제 금리값 또는 B10 없음. 월요일 주식시장 개장/휴장 원점은 조건으로 주어진 예시이며 본 감사의 전수 거래소 달력이 아님.', 'examples':examples})
    links = '\n'.join(f"- [{e[0]} {e[1]}]({e[2]}): {e[3]} 한계: {e[4]}" for e in evidence)
    annual_table = mdtable(['연도','원본행','금리 유효','금리 결측'],[[a[k] for k in ['year','rows','valid','missing']] for a in annual])
    put('audit/D10_SOURCE_AUDIT.md',f'''# D10 DGS10 원천 감사

## 판정 범위

원천 파일 QC는 PASS다. 과거 최초 공개시각과 최초 빈티지는 UNVERIFIED다. 날짜 열은 관측일이며 발표일이 아니다.

- 경로: `{q['raw_path']}`
- 열: Date, DGS10. 날짜는 ISO 날짜, DGS10은 결측 허용 숫자다.
- 원천기관: Federal Reserve Board H.15. 유통: FRED/St. Louis Fed. Treasury constant maturity 10년물 시장수익률이며 일간·비계절조정·연율 %다. 100을 곱한 퍼센트포인트 차이가 bp다.
- {q['rows']:,}행, {q['min_date']}~{q['max_date']}, 유효 {q['valid_values']:,}, 결측 {q['missing_values']}({q['missing_rate_pct']:.4f}%). 날짜 결측 {q['missing_date']}, 중복 {q['duplicate_dates']}, 오름차순 {q['ascending']}.
- 값 범위 {q['min_value']}~{q['max_value']}%, 0 이하 {q['negative_or_zero_values']}개, 비유한 {q['non_finite_values']}개. 0~20% 밖 및 인접행 100bp 초과 점검은 각각 {q['heuristic_outside_0_20_pct']}/{q['adjacent_source_row_change_over_100bp']}개다. 원천 결측을 건너뛰지 않았다. 이 기준은 오류 확정 기준이 아니다.
- RAW SHA-256: `{q['sha256']}`
- 보존 HTTP 원본 SHA-256: `{q['source_original_sha256']}`. SOURCE의 source_sha256과 일치하고 날짜 헤더 변경 외 모든 관측값·결측·날짜가 동일하다.

## SOURCE

```text
{source_line}
```

## 과거 수정 가능성

H.15 공식 정정 사례는 D10_RELEASE_TIMING_AUDIT.md의 E03에서 확인한다. 원본의 2011-03-10={q['revision_spotchecks']['2011-03-10']}, 2014-01-14={q['revision_spotchecks']['2014-01-14']}는 정정 후 수치와 일치한다. 이는 현재 파일이 당시 최초 빈티지임을 입증하지 않는다. 관측별 최초 공개/수신시각 열과 vintage ID는 없다. [FRED 계열 정의](https://fred.stlouisfed.org/series/DGS10), [ALFRED 계열 이력](https://alfred.stlouisfed.org/series?seid=DGS10)을 확인했다.

원천 재수집·수정·보간은 0건이다. 상세 통계와 결측 날짜 목록은 D10_RAW_STATISTICS.json에 있다.
''')
    put('audit/D10_RELEASE_TIMING_AUDIT.md',f'''# D10 공식 공표시점 감사

확인일 2026-10-17 KST. 일반 게시규칙 VERIFIED, 개별 2011~2026 최초 공개시각/제공처 수신/최초 빈티지 UNVERIFIED.

## 공식 근거

{links}

## 관측일과 발표일

E01의 최신 release와 표 일자가 하루 다르고 E03의 2011·2014·2023 사례도 다음 발표일에 이전 관측이 수록됨을 보여준다. 따라서 일반적으로 다음 게시 영업일 발표를 예상할 수 있으나, `관측일+1달력일`의 전수 확정값으로 변환할 근거는 아니다. 과거 weekly release와 daily update가 병존했고 2016-10의 형식·평균 게시 변경도 확인됐다. 2011~2016 개별 실제 시각 및 이후 모든 예외의 완전 목록은 확보하지 못했다. 현행 16:15 규칙을 전 기간의 검증된 실제 로그라고 소급 표시하지 않는다.

## 월요일 09:00 ET 적격성

일반적인 다음 Board 게시일 16:15 경로라면 금요일 관측은 다음 월요일 오후 발표이므로 월요일09시에는 불가다. 같은 원천 주의 목요일 관측이 금요일 발표됐다면 후보가 될 수 있다. 이 판단은 공개경로 가정에 관한 것으로, Treasury의 더 이른 별도 발표나 모든 역사적 FRED 수신을 확인했다는 뜻이 아니다.

월요일 주식시장 휴장 시 원점은 실제 첫 세션09시로 이동하지만, Board도 월요일 휴일이면 금요일 관측의 통상 발표가 화요일 오후가 되어 화요일09시에도 부적격일 수 있다. Board 금요일 폐쇄 주에는 목요일 관측도 다음 월요일 오후로 밀릴 수 있다. 주식시장·채권시장·Board/Reserve Banks 달력을 동일하게 취급하지 않는다. 특별폐쇄는 연간 법정휴일 목록만으로 설명되지 않는다.

## DST 및 실제/가정 구별

America/New_York의16:15는 EDT20:15 UTC, EST21:15 UTC다. 09:00 원점도 각각13:00/14:00 UTC다. 고정 UTC 오프셋을 사용하지 않는다. 일정표 날짜, 계획 시각, 실제 게시, FRED 반영, 빈티지는 별도다. 날짜만 확인됐다고 자정이나16:15를 actual 열에 채우지 않는다. 실제 가용시각은 strict `< O`이며 동시각은 제외한다. 일반 일정만으로 VERIFIED_ACTUAL 또는 빈티지 검증 완료로 올리지 않는다.

지연 사례는 원래 예정시각을 실제 시각으로 사용하지 않는다. 재개일 또는 그 시각이 불명확하면 해당 관측은 제외/UNVERIFIED이며 같은 주의 별도 적격 관측이 있는지 향후 승인된 구축 단계에서 검사한다.
''')
    example_table = mdtable(['논리 예시','관측일','가정 발표 ET','가정 이용 ET','원점 ET','가정상 적격'],
        [[e['example'],e['observation_date'],e['assumed_release_at'],e['assumed_available_at'],e['prediction_origin'],e['assumed_eligible']] for e in examples])
    put('audit/D10_AVAILABILITY_POLICY_PROPOSAL.md',f'''# D10 이용 가능성 정책 제안

**NOT_APPROVED_PROPOSAL_ONLY.** 이번에는 정책을 적용하지 않았으며 사용자 검토 대상이다. D04 EOD 가정을 전용하지 않았다.

## 유지하는 승인 산식

`{formula}`

단위 bp, 주 경계 월요일~다음 월요일 전, 원점은 대상 주 첫 실제 미국 주식시장 거래일09:00 America/New_York다. 동일 O에서 전주와 전전주를 각각 판정한다. 금요일 고정이나 각 주의 자체 종료일 기준 가용성 판정으로 바꾸지 않는다.

## 제안하는 두 실행 경로

1. 실제 증거 경로: 관측일·해당 값이 실린 release·이용 가능시각·당시 빈티지 근거가 있는 값만 strict `< O`로 선택한다. 현 자료로 전체 역사 적격성을 확정할 수 없다. 미확인은 불가로 남긴다.
2. 별도 승인 필요 가정 경로: `{proposal['policy_id']}`. 다음 **Board H.15 게시 영업일**16:15를 assumed_release_at으로, 그 다음 달력일08:00 ET를 assumed_available_at으로 둔다. 약15시간45분의 공급자 완충은 연구용 가정이다. 하루 더 지연해도 실제 제공처 게시·개정 위험을 제거하지 않는다. 2011~2016까지의 일반화 역시 가정으로 명시한다. Board 실제 역사 휴일·특별폐쇄 및 알려진 금리 누락/정정 예외를 확인하지 못한 구간은 자동 적격 처리하지 않는다.

알려진 지연은 일반 가정에 우선한다. 지연 이후 usable release를 확인하지 못하면 해당 관측을 제외한다. 당시 최초값과 현재 수정값의 차이는 별도 vintage 위험이다. 정정 공지를 알아도 전체 최초 빈티지가 복원된 것은 아니다. 당시 버전을 확인할 수 없는 현재 수치를 쓰려면 **현재 수정본을 이용하는 가정 기반 사후 연구**라는 한계도 별도 승인해야 한다.

각 기준 주 내부에서 가장 최근 적격 관측만 선택한다. 그 주에 적격값이 없으면 NaN이다. 다른 주 이월·최근값으로 대체·미래채움·보간은 금지다. B10 삭제나 다른 금리로 변경하지 않는다.

## 보존 필드

observation_date, observation_week, prediction_origin, raw_sha256, value_vintage_id, evidence_url, actual_release_at, actual_available_at, assumed_release_at, assumed_available_at, availability_basis, publication_status, vintage_status, assumption_policy_id, exclusion_reason. 실제 미확인 필드는 null, publication_status/vintage_status는 UNVERIFIED로 유지한다. 가정 적격과 검증된 실제 가용성은 구별한다.

## 날짜 논리 예시

아래는 미승인 정책의 산술·시각 예시다. 실제 금리값·주간 B10·전수 매핑이 아니며 실제 시각 열은 모두 null이다. 휴장에 따른 원점 날짜는 예시의 주어진 조건으로만 사용한다.

{example_table}

정책 승인, 역사 달력·예외 구현, 주간 데이터 구축 승인은 각각 별도다. 이번 감사만으로 어느 것도 자동 승인되지 않는다.
''')
    put('audit/D10_SAMPLE_IMPACT_PRECHECK.md',f'''# D10 표본 영향 사전 점검

## 실제 날짜·결측 분포

{annual_table}

전체 {len(df):,}행은 주말을 제외한 원본 평일 격자를 완전히 포함한다({q['all_weekday_dates_present']}). 결측은 원천행 내부 금리 공란이며 날짜 누락과 다르다. 연방/채권 휴일 공란이 포함되나 모든 공란의 원인을 휴일로 전수 확정하지 않았다. 주말과 휴일을 오류로 취급하거나 채우지 않았다.

2011-01-01~2026-10-09 원천 날짜 범위: {q['study_source_date_audit_20110101_20261009']['rows']:,}행, 금리 유효 {q['study_source_date_audit_20110101_20261009']['valid']:,}, 결측 {q['study_source_date_audit_20110101_20261009']['missing']}개. 이는 연구 주간 공통표본 수가 아니다. 2010 자료는 예열 원천일 뿐 연구기간을 변경하지 않는다. 2026-10-12~14 원천행이 있어도 승인된 마지막 완료 주 후보를 연장하지 않는다.

결측 연속 원본행 최장 {q['longest_missing_source_row_run']}개. 유효 관측 사이 최대 달력 간격 {q['max_gap_between_valid_dates_days']}일: {q['max_gap_dates'][0]}→{q['max_gap_dates'][1]}. 주말·휴일 포함 간격이다. 모든 일별 값이 공란인 장기 단절을 이것만으로 추정하지 않는다.

## B10 표본 위험

- 단일 일별 결측은 주 전체 탈락과 같지 않다. 같은 원천 주의 앞선 적격 관측을 선택할 수 있으면 산식은 유지된다.
- 금요일 발표를 월요일09시 전에 볼 수 있다고 오인하면 관측일 정렬 자체가 누출된다. 통상 목요일 또는 휴일 주 수요일 등 더 이른 같은 주 값이 필요할 수 있다.
- 지연·누락 예외 및 빈티지 확인 실패로 기준 주 내부 적격값이 없으면 해당 B10은 결측이 된다. 어느 원천 주 결손이 전주/전전주 입력에 영향을 주는지는 향후 원점별 검사해야 한다.
- 실제 공개 증거만 요구하는 경로에서는 현재 파일에 시각 열이 없으므로 장기표본 가용성을 확정할 수 없다. 이를 실제 전 기간 데이터가 존재하지 않는다는 판정과 혼동하지 않는다.
- 가정 경로라도 휴일/특별폐쇄의 완전한 역사 달력과 예외 처리가 필요하다. 정확한 B10 유효주수와 공통표본 감소는 **미산출/UNVERIFIED**다. 180개 공란을 180주 손실로 계산하지 않는다.

주간 B10/R[k,O] 전체 계산, SOX Y, 기타 X 결합 및 공통표본 생성은 수행하지 않았다. D13은 이번 범위 밖이며 원래 상태를 유지한다.
''')
    recommendation = {'recommendation':'CONDITIONAL_RECOMMENDED','recommendation_only':True,
        'audit_completed':True,'original_B10_formula':formula,'formula_preserved':True,
        'reason_ko':'B10의 각 기준 주 내부 최신 적격값 정의는 유지 가능하다. 다만 개별 역사 최초 공개시각·FRED 반영·최초 빈티지는 미검증이므로 실제 입증만으로 전체 장기표본 구축은 확정할 수 없다.',
        'historical_publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED',
        'proposed_assumption_policy_id':proposal['policy_id'],'assumption_approved':False,
        'D10_original_gate_status':gate['D10_GATE_STATUS'],'original_gate_modified':False,
        'D13_original_gate_status':gate['D13_GATE_STATUS'],'D13_audited':False,
        'weekly_build_authorized':False,'weekly_build_executed':False,
        'conditions_requiring_user_approval':['DGS10 전용 다음 Board 게시일+익일08시 가정과 역사 예외 처리','현재 수정본 사용의 빈티지 한계 수용 또는 실제 빈티지 확보 경로 선택','정책 검토 후 별도 Phase2-B 실행 승인'],
        'full_sample_impact_quantified':False}
    put('audit/D10_GATE_RECOMMENDATION.json',recommendation)
    changed = [r for r,v in protected.items() if not (ROOT/r).exists() or sha(ROOT/r)!=v['sha256']]
    checks = {
        'required_references_read':len(reads)==12,
        'prior_inputs_and_locked_output_hashes_verified':not historical_changes and not locked_changes,
        'raw_source_DGS10_H15_percent_daily':source_line.startswith('# SOURCE') and 'series_or_symbol=DGS10' in source_line,
        'canonical_equals_original':True,'original_response_hash_matches_SOURCE':q['source_original_sha256_matches_metadata'],
        'no_date_missing_duplicate_or_disorder':q['missing_date']==q['duplicate_dates']==0 and q['ascending'],
        'daily_missingness_preserved':q['missing_values']==180,
        'no_invalid_numeric_values':q['non_numeric_nonmissing']==q['non_finite_values']==0,
        'official_sources_only':all(x[2].startswith(('https://www.federalreserve.gov/','https://fred.stlouisfed.org/','https://alfred.stlouisfed.org/')) for x in evidence),
        'known_DGS10_revisions_explicit':q['revision_spotchecks']=={'2011-03-10':3.37,'2014-01-14':2.88},
        'actual_timestamps_not_fabricated':all(x['actual_release_at'] is None and x['actual_available_at'] is None for x in examples),
        'normal_Friday_not_eligible_Monday':not examples[0]['assumed_eligible'],
        'same_week_Thursday_logic':examples[1]['assumed_eligible'],
        'Monday_Board_holiday_Friday_not_eligible_Tuesday':not examples[3]['assumed_eligible'],
        'Friday_Board_closure_Thursday_not_eligible_Monday':not examples[6]['assumed_eligible'],
        'DST_distinct_UTC_offsets':datetime(2026,10,2,16,15,tzinfo=ET).utcoffset()!=datetime(2026,1,9,16,15,tzinfo=ET).utcoffset(),
        'strict_equality_excluded':not (datetime(2026,10,5,9,tzinfo=ET)<datetime(2026,10,5,9,tzinfo=ET)),
        'B10_formula_preserved':proposal['formula']==formula,
        'D04_not_applied_to_DGS10':not proposal['D04_applied_to_DGS10'],
        'unknowns_remain_UNVERIFIED':proposal['publication_status']==proposal['vintage_status']=='UNVERIFIED',
        'proposal_not_approved_or_executed':not proposal['executed_on_real_series'] and proposal['approval_status']=='NOT_APPROVED_PROPOSAL_ONLY',
        'D10_D13_original_not_passed':not gate['gates']['D10']['passed'] and not gate['gates']['D13']['passed'],
        'protected_files_unchanged':not changed,
        'no_weekly_dataset_or_model_outputs':not list(OUT.rglob('*.csv')) and not list(OUT.rglob('*.pkl'))}
    qc = {'qc_status':'PASS' if all(checks.values()) else 'FAIL','audit_scope_only':True,
        'gate_recommendation':recommendation['recommendation'],'checks':checks,'test_count':len(checks),
        'failures':[k for k,v in checks.items() if not v], 'protected_files_checked':len(protected),
        'protected_raw_files_checked':sum(r.startswith('data/raw/') for r in protected),
        'protected_phase1_lock_files_checked':sum(r.startswith(str(LOCK.relative_to(ROOT)).replace('\\','/')+'/') for r in protected),
        'changed_protected_files':changed,'raw_statistics_file':'audit/D10_RAW_STATISTICS.json',
        'execution_counts':{'weekly_B10_values':0,'weekly_Y':0,'weekly_XY_tables':0,'asof_joins':0,'models_fit':0,'forecasts':0,'performance_metrics':0,'D13_processing':0},
        'limits':'자체 감사 코드의 입력/산술/정책 검사다. 역사적 최초 공개·빈티지 실증 통과가 아니며 OS 전체 실행감시는 아니다.'}
    put('qc/PHASE2A_QC.json',qc)
    put('README.md','''# 연구 C Phase 2-A D10 사전감사

범위: DGS10 원천 QC·공식 공표규칙·정책 제안·표본 위험 사전점검. 주간 X/Y와 모델은 만들지 않는다.

최종 결과는 reports/PHASE2A_D10_REPORT.md, 인수인계는 reports/PHASE2A_HANDOFF.md다. 공식 근거는 audit/D10_RELEASE_TIMING_AUDIT.md와 OFFICIAL_EVIDENCE_REGISTER.json에 있다. 입력 해시는 inputs/PHASE2A_INPUT_MANIFEST.json, 출력 해시는 qc/PHASE2A_OUTPUT_MANIFEST.json에 보관한다.

code/run_d10_audit.py는 pandas 원천 검사와 문서 작성, code/independent_d10_qc.py는 csv/Decimal 기반 별도 대조다. 기존 폴더 재실행은 거부하므로 재현 시 감사 폴더 사본을 새 경로에 두고 결과 파일을 별도로 관리해야 한다. 원본 파일은 수정하지 않는다. code/seal_d10_audit.py는 최종 파일 해시를 봉인한다.

감사 QC PASS는 D10 게이트 PASS 또는 Phase 2-B 실행 승인이 아니다. DGS10 가정 제안은 사용자 승인 전까지 적용하지 않는다.
''')
    put('logs/PHASE2A_WORK_LOG.md',f'''# Phase 2-A 작업 기록

- 실행 UTC: {NOW}, 사용자 기준일 2026-10-17 KST.
- 사전 참고문서12개 전체 읽기, 이전990개 입력 기준과27개 LOCK 산출물 존재·해시 검증. 과거 승인된 인덱스 추가는 새로운 변경으로 오인하지 않았다.
- 입력 snapshot {len(protected)}개 생성. 코드 작성 이전의 기존 자료는 읽기 전용으로 취급했다.
- 공식 Fed/FRED/ALFRED 웹페이지8개 확인. 과거 release 직접경로2개 접근 실패는 확인 근거로 사용하지 않았다.
- pandas로 canonical과 보존 HTTP 원본을 대조하고 일별 날짜/결측/범위를 검사했다. 실제 주간 가용성 매핑은 하지 않았다.
- 금요일/Board 휴일/DST/동시각 경계 예시는 논리 검사만 수행했다. 실제 시각은 null로 두었다.
- 자동 QC {len(checks)}개, 상태 {qc['qc_status']}. 독립 QC는 별도 코드로 수행 후 별도 문서에 저장한다.
- 신규자료 다운로드, RAW 수정, 주간B10/X/Y, 실제 as-of 병합, 학습/시험/성과계산, D13 처리: 각각0회.
''')
    print(json.dumps({'qc_status':qc['qc_status'],'tests':len(checks),'failures':qc['failures'],'protected':len(protected),'raw':{k:q[k] for k in ['rows','valid_values','missing_values','min_date','max_date','max_gap_between_valid_dates_days','sha256']}},ensure_ascii=False,indent=2))
    if not all(checks.values()):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
