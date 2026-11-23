"""최종 자동 QC·한국어 보고서·D10 상태·출력 봉인. 시험 수치 통계/모델 계산 없음."""
import ast,importlib.metadata
from collections import Counter
from common import *

def main():
    c=load(OUT/'data/WEEKLY_SAMPLE_COUNTS.json');ind=load(OUT/'qc/PHASE2B_INDEPENDENT_QC.json')
    e3=load(OUT/'qc/H15_CALENDAR_QC.json');ex=load(OUT/'qc/EXCHANGE_CALENDAR_QC.json')
    gate=load(OUT/'qc/D10_PREBUILD_GATE.json');timeqc=load(OUT/'availability/D10_INFORMATION_LEAKAGE_TESTS.json')
    manifest=load(OUT/'qc/PHASE2B_INPUT_MANIFEST.json')
    missing=readcsv(OUT/'data/WEEKLY_MISSINGNESS_AUDIT.csv')
    logs=readcsv(OUT/'availability/FEATURE_AVAILABILITY_LOG.csv')
    av=readcsv(OUT/'availability/D10_OBSERVATION_AVAILABILITY.csv')
    e4=readcsv(OUT/'availability/D10_E4_OBSERVATION_WEEK_IMPACT.csv')
    ds=readcsv(OUT/'calendar/D10_E3_DATEWISE_DECISIONS.csv')
    changed=[r for r,v in manifest['protected_files'].items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    noleak=all(r['valid']!='True' or r['latest_assumed_available_at'] and datetime.fromisoformat(r['latest_assumed_available_at'])<datetime.fromisoformat(r['prediction_origin']) for r in logs)
    required=['calendar/US_MARKET_SESSIONS.csv','calendar/BOARD_H15_PUBLICATION_CALENDAR.csv',
        'calendar/D10_E3_DATEWISE_DECISIONS.csv','calendar/D10_E4_CONFLICT_HANDLING.csv','calendar/D10_CALENDAR_IMPLEMENTATION_REPORT.md',
        'availability/D10_OBSERVATION_AVAILABILITY.csv','availability/FEATURE_AVAILABILITY_LOG.csv',
        'availability/D10_ASOF_AUDIT.md','availability/D10_INFORMATION_LEAKAGE_TESTS.json',
        'data/WEEKLY_DATA_DICTIONARY.md','data/WEEKLY_MISSINGNESS_AUDIT.csv','data/WEEKLY_SAMPLE_COUNTS.json',
        *['data/train_dev/'+x for x in ['SOX_WEEKLY_Y.csv','WEEKLY_FEATURES_B10_F1.csv','WEEKLY_CORE_COMBINED.csv']],
        *['data/sealed_test/'+x for x in ['SOX_WEEKLY_Y_TEST.csv','WEEKLY_FEATURES_TEST.csv','WEEKLY_CORE_TEST.csv']]]
    checks={
        'RAW47폴더48CSV해시일치':load(OUT/'inputs/RAW_VERSION_AUDIT.json')['all_unchanged'],
        '핵심RAW구조_범위_중복':load(OUT/'qc/RAW_PREFLIGHT_QC.json')['status']=='PASS',
        '보호파일SHA256불변':not changed,
        '미국거래소규칙특별폐장대조':ex['status']=='PASS',
        'SOX거래일3966일일치':ex['sessions_main']==3966,
        'E3_637개개별7조건':len(ds)==637 and all(all(r['condition_'+str(i)]=='SATISFIED' for i in range(1,8))==(r['decision']=='CONDITIONALLY_ALLOWED') for r in ds),
        'E4_6이벤트차단':e3['E4_count']==6 and e3['E4_all_blocked'],
        '역사발표체계_휴일분리':not ex['full_historical_official_daywise_document_verification'],
        'D10_14개시점테스트':timeqc['status']=='D10_PREBUILD_QC_PASS' and len(timeqc['tests'])==14 and all(r['pass'] for r in timeqc['tests']),
        '사전게이트후주간생성':gate['status']=='D10_PREBUILD_QC_PASS' and all((OUT/p).stat().st_mtime>=(OUT/'qc/D10_PREBUILD_GATE.json').stat().st_mtime for p in required if '/train_dev/' in p or '/sealed_test/' in p),
        'actual_assumed_UNVERIFIED분리':all(r['actual_release_at']==r['actual_available_at']=='null' and r['publication_status']==r['vintage_status']=='UNVERIFIED' for r in av),
        'X가정시각원점엄격이전':bool(noleak),
        '주간격자823_비중첩_중복0':len(missing)==823 and len({r['week_start'] for r in missing})==823 and all(date.fromisoformat(r['week_start']).weekday()==0 for r in missing),
        '주간Y독립재계산':ind['status']=='PASS',
        'B1_B10_F1독립재계산':ind['status']=='PASS',
        '단위_bp_ddof1_Wilder_AdjClose':ind['status']=='PASS',
        'FGI_80퍼센트_무LOCF':all(int(r['detail'] and json.loads(r['detail'])['minimum'])==math.ceil(.8*json.loads(r['detail'])['N_expected']) for r in logs if r['feature_id']=='F1'),
        '결측무보간_주내선택':ind['status']=='PASS',
        '공통표본818_쌍동일':c['paired_common_valid']==818 and c['M0_Y_valid']==c['M1_Y_valid'],
        '기간분리_격리시험':all(r['split']=='sealed_test' for r in missing if r['week_start']>='2021-01-01'),
        '시험Y수치성과미출력':not c['Y_statistics_or_performance_computed'] and not ind['performance_computed'],
        'E3대안가용성만비교':c['B10_valid_without_E3']<=c['feature_valid']['B10'] and c['paired_without_E3_valid']<=c['paired_common_valid'],
        '주전체자동삭제없음':all(r['whole_week_deleted']=='False' for r in e4),
        '별도독립QC통과':ind['status']=='PASS',
        '필수CalendarAvailabilityData파일존재':all((OUT/p).is_file() for p in required)}
    # 코드에서 모델/성능 API 호출이 없는지 별도 AST 검사한다.
    forbidden={'fit','fit_transform','predict','corr','corrcoef','mean_squared_error','r2_score','mean_absolute_error'}
    calls=[]
    for path in (OUT/'code').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in forbidden:calls.append(path.name+':'+node.func.attr)
    checks['모델학습튜닝예측성과0회']=not calls
    status='PASS' if all(checks.values()) else 'BLOCKED'
    save('qc/PHASE2B_QC.json',{'status':status,'checks':checks,'count':len(checks),'protected_count':len(manifest['protected_files']),
        'protected_changed':changed,'independent_QC_status':ind['status'],'independent_checks':ind['count'],
        'scope':'승인된 가정 및 제외 정책 아래 데이터 구축·정보시점 로직 검증. 최초 빈티지 실증 검증 아님.',
        'execution_counts':{'model_fit':0,'tuning':0,'model_prediction':0,'test_performance':0,'scaler_fit':0,'PCA_fit':0,'D13_detail_lock':0}})
    if status!='PASS':raise SystemExit('최종 QC BLOCKED. 보고 수치 조정/다음단계 진입 금지.')
    state={'D10_TIMING_POLICY':'APPROVED','D10_E3_CALENDAR_POLICY':'APPROVED','D10_E4_CONSERVATIVE_POLICY':'APPROVED',
        'D10_CALENDAR_IMPLEMENTATION_QC':'PASS','D10_WEEKLY_B10_IMPLEMENTATION_QC':'PASS',
        'D10_GATE':'IMPLEMENTATION_PASS','D10_PREBUILD':'D10_PREBUILD_QC_PASS','PHASE2B_DATASET_QC':'PASS',
        'D13_GATE':'PENDING_WEEKLY_MISSINGNESS_REVIEW','historical_publication_status':'UNVERIFIED','historical_vintage_status':'UNVERIFIED',
        'policy_ids':[TIMING,CALPOL],'phase3_execution_authorized':False,
        'scope':'승인된 가정/제외의 구현 QC 통과. 원본 게이트 파일은 당시 이력으로 변경하지 않음.'}
    save('qc/PHASE2B_D10_GATE_RESULT.json',state)
    feature_table='\n'.join('| '+k+' | '+str(v)+' | '+str(c['calendar_weeks']-v)+' |' for k,v in c['feature_valid'].items())
    split_table='\n'.join('| '+k+' | '+str(v['weeks'])+' | '+str(v['Y_valid'])+' | '+str(v['paired_common_valid'])+' | '+v['first_week']+' ~ '+v['last_week']+' |' for k,v in c['splits'].items())
    excluded=[r['calendar_date'] for r in ds if r['decision']=='EXCLUDED']
    impact_table='\n'.join('| '+r['conflict_date']+' | '+r['blocked_observation_dates']+' | '+str(len(json.loads(r['potential_feature_weeks'])))+' | '+str(len(json.loads(r['B10_missing_feature_weeks'])))+' |' for r in e4)
    reason_counts=Counter()
    for r in missing:
        for item in r['missing_reasons'].split(';'):
            if item:reason_counts[item]+=1
    save('data/WEEKLY_MISSING_REASON_COUNTS.json',dict(reason_counts))
    dgs_missing=[r['week_start'] for r in missing if r['B10_valid']=='False']
    info=f'''# 연구 C Phase2-B D10 구현 결과

최종 **D10_GATE=IMPLEMENTATION_PASS**, 사전 **D10_PREBUILD_QC_PASS**. 이는 승인된 달력/시각 가정과 제외 정책 구현의 통과이며 실제 최초 게시시각·빈티지 입증이 아니다.

미국 실제 세션 규칙과 공식 특별휴장/확보된 연간자료를 교차대조해 SOX 3,966개 날짜와 일치했다. 일반16:00/조기13:00 ET와 DST를 저장했다. 개별 날짜 공식문서 전수 확보를 주장하지 않는다. 주식시장/Board/연방휴일 달력을 구분했고 Board 가정은 별도 근거 필드를 둔다.

E3 후보637일 중 **조건부 허용634 / 제외3 / 판정보류0**. 제외 날짜 {', '.join(excluded)}는 발표 이벤트 지연·정정/재개 불확실성으로 조건4를 통과하지 못했다. 2011-03-10·2014-01-14는 금리 관측일이고 관련 발표일은3/11·1/15이므로 서로 혼동하지 않았다. 원본 등급은 바꾸지 않았다. 조건부 허용은 실제 게시 확인이나 VERIFIED 승격이 아니다. E3 주말·일반 비게시일·2010 승인범위 밖 후보를 자동 사용하지 않았다.

E4 여섯 발표 이벤트는 모두 미해결로 차단했다. 해당 이벤트에 의존하는 관측은 자동 재배정하지 않았다. 아래에서 주간 후보 수는 영향을 점검한 대상이지 삭제된 주 수가 아니다.

|E4 날짜|차단된 의존 관측일|영향 가능 특징 주수|그중 B10 결측 주수|
|---|---|---|---|
{impact_table}

독립적으로 적격인 같은 주 금리값으로 모두 주간 선택을 유지할 수 있었으며 주 전체 자동 삭제는0건이다. E4 차단과 원천 관측이 아예 없는 사례는 구분한다. 알려진10년물/Treasury 전체 정정·누락7개 관측일은 복구 최초 시점 미확인으로 별도 보류했고 다른 만기만의 정정은 DGS10으로 오인하지 않았다.

관측일 다음 H15 게시 가능일16:15 ET → 다음 달력일08:00 ET, strict `< origin`을 구현했다. E4/조건실패 후보를 다음 날짜로 조용히 이동하지 않고 해당 의존 관측을 보류한다. 명시적 정상 휴일·폐쇄는 게시일이 아니므로 독립 근거가 있는 다음 게시일을 사용한다. 실제 알려진 더 늦은 근거가 우선하며 actual 필드는 null이다.

시점 테스트14개 통과: 금요일 부적격/목요일 적격, Board 월·금 휴일, Good Friday/Columbus 구분, DST, E3/E4, 실제 늦은 가용성 합성사례, null,09시 동시각, 결측·정정, 미래자료 교란, 관측일 이후 게시. 미래자료 교란 검사는 선택 로직만 검증하며 현재 수정본이 최초 빈티지와 같다는 주장이 아니다.

B10 유효822주, 결측1주: {dgs_missing}. 각 원천 주 내부에서만 최신 적격 관측을 선택해 bp 차이를 계산했고 타 주 이월·금요일 강제·보간은 없다. B10이 유효해도 전체 B1~B9의 예열 때문에 공통표본에서 제외될 수 있다.
'''
    save('reports/PHASE2B_D10_IMPLEMENTATION_REPORT.md',info)
    missing_report=f'''# 연구 C Phase2-B 결측·표본 보고서

원래 미국 월요일 주 격자823주, 실제 SOX 거래가 있는 주823주. Y유효822주. 현재 원천 마지막 거래일2026-10-09, 마지막 완료 주2026-10-05이다. 다음 주를 임의 생성하지 않았다.

|변수|유효 주수|결측 주수|
|---|---|---|
{feature_table}

|구간|격자 주수|Y유효|M0/M1/Y 공통|week_start 범위|
|---|---|---|---|---|
{split_table}

M0 X유효{c['M0_X_valid']}, M1 X유효{c['M1_X_valid']}, M0/Y {c['M0_Y_valid']}, M1/Y {c['M1_Y_valid']}, 공통 {c['paired_common_valid']}주다. 공통 기간 {c['paired_first_week']}~{c['paired_last_week']}. 별도 공통 날짜 목록과 모든 격자의 제외 사유를 보존했다.

주된 손실은 첫 주 SOX 선행 가격 부재와 초기 B1/B2/B3/B4/B5/B9 예열이다. B2는 연속5주 끝가격이 필요해 공통표본 첫5주를 제외한다. B3는 첫 실제 세션의 선행 SOX 가격 부재를 건너뛰지 않고 결측 처리했다. RSI는15개 연속가격/14개 변화 SMA seed이다. NDＸ2010 예열은 활용하되 SOX2010을 생성하지 않았다.

관측이 실제로 없는 경우, 필요한 예열이 없는 경우, 관측은 있으나 가용시점·E4·정정 문제로 제외한 경우를 각각 기록했다. DGS10 원천 결측180개를 0으로 채우지 않았다. 주 내 다른 독립 적격 관측을 선택하는 것은 주 밖 이월이나 보간이 아니다.

E3 허용 시 B10유효822주, E3 미허용657주: 가용성 차이165주. 공통표본818 대656주: 차이162주. **모델 성능 비교가 아닌 데이터 가용성 QC**다. E3 미허용 시 과거 구간이 줄어드는 사실을 숨기지 않았다.

공통 결손 최장5주(2011-01-03~2011-01-31), 이후2011-02-07~2026-10-05는818개 연속 유효 주간이다. 전체 결측·연속구간 목록은 data/WEEKLY_MISSINGNESS_AUDIT.csv, COMMON_WEEK_CONTIGUOUS_RUNS.csv, 변수별 사유 집계 JSON을 참조한다. 시험기간에는 유효·결측 개수만 보고하며 Y 수치·분포·상관은 출력하지 않는다.
'''
    save('reports/PHASE2B_MISSINGNESS_REPORT.md',missing_report)
    save('reports/PHASE2B_D13_PREPARATION_REPORT.md',f'''# D13 준비용 결측 감사

D13_GATE=PENDING_WEEKLY_MISSINGNESS_REVIEW. 상세 확정이나 Bootstrap 실행을 하지 않았다.

원래823주 격자와 공통818주 위치, 최대 연속결손5주 및 연속유효구간을 data에 보존했다. 초기학습308/개발209/시험301 유효주다. 원래 격자를 압축하지 않는다. E3 미허용 대안 공통656주와의 차이는 별도 가용성 QC다.

기존 블록8주/민감도4·12주를 유지한다. 이 격자의 초기 결손을 포함한 블록과 부분 구간별 유효n 문제를 후속 정책에서 검토할 수 있다. 이번에 재표본추출, n 하한이나 반복 규칙을 실행·확정하지 않았다.

min_valid_n=null, 부족/빈 반복 처리=null, 최대 재시도=null, 실패 블록 처리=null. 별도 사용자 검토로 상세를 잠근 뒤에만 최종 시험오차·성과 열람을 검토한다. 모형 성능에 유리하도록 결손정책을 선택하지 않는다.
''')
    save('reports/PHASE2B_REPORT.md',f'''# 연구 C Phase2-B v1.1 결과보고서

연구: CNN Fear & Greed Index의 SOX 주간 수익률 추가 예측 정보가치. 작성2026-10-17 KST.

**PHASE2B_DATASET_QC=PASS, D10_GATE=IMPLEMENTATION_PASS**. 승인된 가정·보수적 제외 정책 아래 주간 데이터셋 구축을 완료했다. 실제 최초 공개시각과 빈티지는 계속 UNVERIFIED이며 실증적 실시간 PIT 입증으로 해석하지 않는다.

## 입력 보호 및 설계 승계

연구계획서, Phase1 LOCK/승인결정/검색/게이트, 기존 시차정책, 달력감사, E3 승인 및 과거 차단결과를 실제 열람하고 입력 해시를 기록했다. RAW47종48 canonical CSV 및 핵심7개는 이전 기록과 일치한다. FGI2026-03-12=21.15 존재, SOX 종료2026-10-09, HYG Adj Close 존재를 확인했다. 지수 Volume은 사용하지 않았다.

보호파일 **{manifest['count']}개 SHA-256 불변**, 변경0건. 기존 build_v1_0, 감사·승인·LOCK·RAW·freeze는 바꾸지 않았다. 새 build_v1_1 안에만 썼으며 기존 가상환경은 변경하지 않고 PDF 라이브러리를 새 code/vendor에 격리 설치했다.

## Gate A/B

거래소 규칙·공식 일정·특별휴장 근거와 SOX3966세션을 대조했다. 조기폐장·DST·한 달력과 다른 Board/연방휴일을 별도 저장했다. 전기간 각 날짜의 독립 공식 문서까지 확보했다고 주장하지 않는다.

E3 후보637일: 조건부 허용634, 제외3, 보류0. 제외 {', '.join(excluded)}. 날짜별7조건과 근거ID/URL을 저장했고 실제 게시확인으로 등급을 승격하지 않았다. E4 6건은 미해결 이벤트와 의존 관측을 차단했으며 다른 주로 이동하거나 주 전체를 자동 삭제하지 않았다. 주내 독립 적격 금리로 선택을 유지했다.

D10 사전시점14개 테스트 PASS를 주간 생성 전에 저장했다. 알려진 지연·폐쇄·정정을 일반 가정보다 우선하고 실제/가정 시각을 구분했다. 미래자료 교란 테스트와 독립 재계산을 통과했다. 자세한 E4 영향 관측·주간 후보는 PHASE2B_D10_IMPLEMENTATION_REPORT.md와 availability/D10_E4_OBSERVATION_WEEK_IMPACT.csv에 있다.

## Gate C/D — 구축 결과

미국 달력 주 월~일 비중첩 Y=100*(이번 주 SOX 마지막 Close/직전 주 마지막 Close−1). 부호 유지, 연속 달력 주만 사용, 내부 세션 누락 검사를 적용했다. 첫 주는 선행 SOX 가격이 없어 결측이다. 승인 B1~B10과 F1을 구축했고 학습·표준화·PCA를 하지 않았다.

|변수|유효 주수|결측 주수|
|---|---|---|
{feature_table}

전체823주, Y유효822주. M0 X유효818, M1 X유효818, M0/Y818, M1/Y818, **paired 공통818주**. 공통 시작2011-02-07, 종료2026-10-05(목표 마지막 거래일10/09)다.

|구간|전체 주|Y유효|공통 유효|week_start 범위|
|---|---|---|---|---|
{split_table}

최초 공통5주 손실은 B2 등 예열과 선행 SOX 부족으로 설명된다. 관측 결손과 정책상 가용성 보류를 구분했다. E3 허용/미허용의 B10가용822/657, 공통818/656주 차이는 모델 성능 검정이 아니다.

시험기간 X/Y는 data/sealed_test에만 분리했다. 보고서·로그에는 시험 Y 수치·분포·상관·오차·성과를 출력하지 않았다. 이는 폴더/해시/운영 규칙에 따른 격리이며 암호화된 접근통제라는 주장은 아니다. Phase3는 data/train_dev만 읽어야 한다.

## QC·오류 이력

자동 QC **{len(checks)}/{len(checks)} PASS**, 별도 구현 독립 QC **{ind['count']}/{ind['count']} PASS**. 동일 Codex 작업 안의 별도 구현이며 외부 독립심사가 아니다. 823주 전수 Y 및11개 X 재계산, D10 관측별 시각, E3 637일 조건, E4, 휴일/DST/동시각, 미래자료 교란, 결측·기간분리·보호해시를 검사했다. 시험 값은 계산 비교만 하고 숫자/통계를 로그에 출력하지 않았다.

중간 작업에서는 FGI 열명이 Fear Greed임을 명시하도록 수정했고, 대형 전체 규정집 PDF 전면 추출이 오래 걸려 중단 후 표적 일정 공시만 추출했다. 라이브러리 설치시 신규 vendor가 임시 폴더 권한을 이어받아 읽히지 않는 문제는 신규 폴더만 부모 기본권한으로 복구했다. 원본은 변경하지 않았다.

달력 구현 검토에서 정정 **관측일**과 장애 **발표일**을 구분하도록 바로잡은 뒤 사전 게이트를 재실행했다. 최초11개 중간 산출물은 logs/initial_prebuild_date_role_review에 보존했다. 이후 주간 데이터는 수정된 게이트 PASS 후 생성했다.

독립 QC 최초 검사에서 파일명 WEEKLY 안의 Y를 목표값 파일로 오인한 오탐1건이 있었다. 실제 CSV 열을 검사하도록 수정했고 최초 FAIL 기록도 logs/INITIAL_FILENAME_CHECK_*로 보존했다. 수정된 독립 QC에서 모든 검사가 통과했다. 데이터나 결과를 예상치에 맞춰 조정하지 않았다.

## 상태·후속 조건

D10_TIMING_POLICY/E3_CALENDAR_POLICY/E4_CONSERVATIVE_POLICY=APPROVED. D10_CALENDAR_IMPLEMENTATION_QC=PASS, D10_WEEKLY_B10_IMPLEMENTATION_QC=PASS, D10_GATE=IMPLEMENTATION_PASS, PHASE2B_DATASET_QC=PASS.

D13_GATE=PENDING_WEEKLY_MISSINGNESS_REVIEW. 기존8주블록·4/12주민감도는 보존했고 min_valid_n·재추출·최대재시도·실패처리는 null/미확정이다. 데이터셋 구축 성공은 D13 확정이나 Phase3 실행 승인이 아니다.

최종 시험오차·성과를 열람하기 전에 D13 상세를 사용자 검토로 잠가야 한다. Phase3 모델 학습·튜닝은 별도 승인 후 시작한다. 이번에는 모델 fit/튜닝/예측/시험성과/표준화/PCA/D13확정 모두0회로 종료한다.

주요 산출물은 calendar/, availability/, data/train_dev/, data/sealed_test/, qc/, reports/, code/, logs/에 있다. 입력·원본해시는 qc/PHASE2B_INPUT_MANIFEST.json, 출력해시는 qc/PHASE2B_OUTPUT_MANIFEST.json과 별도 sha256에 기록한다. 상세 산식은 data/WEEKLY_DATA_DICTIONARY.md, 후속 접근 규칙은 PHASE2B_HANDOFF.md에 있다.
''')
    save('reports/PHASE2B_HANDOFF.md','''# 연구 C Phase2-B v1.1 인수인계

데이터 구축·정보시점 QC PASS. D10 구현 PASS는 승인된 가정·제외 아래의 로직 검증이며 최초 실제 게시시각/빈티지는 UNVERIFIED다. 기존 gate 원본은 당시 이력으로 보존했고 최신 상태는 qc/PHASE2B_D10_GATE_RESULT.json을 참조한다.

Phase3 개발 입력은 data/train_dev/WEEKLY_CORE_COMBINED.csv 및 paired_common_valid 필터다. 초기학습308, 개발209 공통주다. 전체818/시험301 공통주를 혼용하지 않는다. 예측원점마다 성숙한 라벨만 사용하고 label_assumed_available_at<origin을 검사해야 한다. 기존 최소156주, Expanding/최근5달력년 Rolling, 승인 검색18후보·seed20261016 등 LOCK을 유지한다. 이번에는 학습창/하이퍼파라미터를 선택하지 않았다.

data/sealed_test는2021~2026-10-05주 시험 X/Y 격리 경로다. Phase3 개발 코드가 이 경로의 시험 Y를 읽거나 변수선택·튜닝에 사용하면 안 된다. 동일 시장기간의 이전 D1/W1 열람 이력과 가정 기반 연구 한계를 유지한다.

먼저 입력/출력 manifest와 봉인 sha256을 확인한다. 달력·D10 시각/E3/E4·선택 관측·변수별 source_dates는 별도 감사파일로 추적한다. E3 제외3일과 E4이벤트6일, 알려진 정정관측7일의 보류는 데이터 오류로 자동 수정하거나 보간하지 않는다.

D13은 PENDING_WEEKLY_MISSINGNESS_REVIEW. 원래823주/공통818주의 결손 격자와 초기5주 결손을 검토한 뒤 min_valid_n/부족·빈반복/최대재시도/실패처리를 별도 사용자 승인으로 확정해야 한다. Bootstrap·모델 성능·시험 오차는 아직 보지 않았다.

사용자의 Phase3 실행 승인 없이 학습·튜닝·예측을 시작하지 않는다. Phase2-B 종료.
''')
    save('README.md','''# 연구 C Phase2-B 주간 데이터셋 build_v1_1

reports/PHASE2B_REPORT.md → D10 구현/결측/D13 준비 보고서 → PHASE2B_HANDOFF.md 순서로 읽는다. 기존 build_v1_0은 당시 차단 이력이며 이번에는 변경하지 않았다.

- inputs: 지시문·RAW 재대조·공식 거래소 원본과 HTTP/해시 기록
- calendar: 독립 거래소 규칙 달력·Board H15 조건부 달력·E3/E4 판정
- availability: 관측별 실제/가정 시각·feature 의존 날짜·D10 주내 선택·RSI state
- data/train_dev:2011~2020 Y/X/통합; data/sealed_test:2021이후 격리 시험 Y/X/통합
- data: 산식 사전·결측/공통표본 플래그·유효 개수·연속구간만 공개
- qc: 사전/최종 D10 게이트·자동/독립 QC·입력/출력 해시
- code/logs: 재현 코드·의존성·오류 및 수정 이력

실행 순서 common.py → collect_calendar_sources.py → collect_supplement.py → calendars.py → d10_prebuild.py(PASS 필수) → build_weekly.py → independent_qc.py → finalize.py. 기존 완료 산출물은 덮어쓰지 않으며 신규 재실행은 별도 버전 경로를 사용한다. 기존 스냅샷 검증은 independent_qc.py --check-only와 출력 manifest 대조로 가능하다.

Python은 research_C/phase0_raw_audit/.venv/Scripts/python.exe를 사용한다. PDF 읽기용 pypdf6.21.0만 신규 code/vendor에 격리 설치했다. ENVIRONMENT_LOCK.json에 실제 버전과 설치경위를 기록한다. 라이브러리 임시 ACL은 신규 vendor만 부모 기본권한으로 복구했다. API 키는 사용하지 않았다.

출력 manifest는 자기 자신 및 별도 봉인 sha256을 제외한 신규 파일 전수를 기록한다. code/vendor의 의존성도 포함한다. 기존 원본은 입력 manifest로 보호한다.

PIT 가정의 실제 최초 게시·빈티지 미검증을 유지한다. 모델/성과/표준화/PCA는 미실행. D13 상세 및 Phase3는 별도 사용자 승인 대기다.
''')
    versions={}
    for p in ['pandas','numpy','requests','beautifulsoup4','python-dateutil','tzdata']:
        try:versions[p]=importlib.metadata.version(p)
        except importlib.metadata.PackageNotFoundError:versions[p]='not_installed'
    save('inputs/ENVIRONMENT_LOCK.json',{'python':__import__('sys').version,'executable':__import__('sys').executable,'packages':versions,
        'isolated_dependency':{'pypdf':'6.21.0','path':'code/vendor','installed_without_modifying_existing_environment':True},
        'models_fit':0,'network_sources':'공식 거래소 공개일정만 수집. 금융 RAW 재수집 및 API 키 사용 없음.'})
    save('logs/WORK_LOG.md','''# Phase2-B 작업 기록

2026-10-17 KST. 기존 승인·RAW 해시를 확인하고 신규 build_v1_1에서만 작업했다. 기존1247개 보호파일 무변경.

공식 거래소 HTTP 응답 및 실패를 모두 저장했다. 일부 annual URL404, Nasdaq IR403은 자료 부재로 단정하지 않고 Nasdaq Trader의 대체 공지로 확인했다. PDF 읽기 pypdf를 신규 vendor에만 설치했으며 임시 ACL상속 문제는 해당 신규 폴더 권한만 reset했다. 기존 환경 변경 없음.

초기 FGI score 컬럼 탐색 실패를 실제 Fear Greed 헤더로 수정한 후 RAW 검증을 재개했다. 전체 규정집 PDF 28MB 전면 추출은 중단하고 연간 공시·표적 공식 규칙을 검증했다. 날짜 역할 검토에서 정정 관측일/발표 이벤트일을 분리하고 초기 결과11개를 보존한 뒤 달력 및14개 D10테스트를 재실행했다.

D10_PREBUILD_QC_PASS 파일을 주간 생성 전에 저장한 후에만 Y/X를 생성했다. 실행 출력은 유효·결측 개수만 기록했고 시험 Y 값/통계/성과는 출력하지 않았다. 주간823/공통818주를 만들었다.

독립 QC 최초 파일명 패턴이 WEEKLY의 Y를 목표값 파일로 오인해1건 FAIL했다. 실제 열 검사로 수정하고 최초 결과를 logs에 보존했다. 별도 구현으로823주 Y/X 및 가용성·공통표본을 전수 재계산한 최종19개검사가 PASS다. 실제 데이터 조정이나 모델 실행은 없다.

최종 자동 QC·보고서·인수인계·상태·출력해시를 작성하고 원본 SHA를 재확인했다. D13 상세 확정/Phase3/모델/튜닝/예측/시험성과 미실행 상태로 종료한다.
''')
    # 모든 필수 최종 문서 존재 후 봉인한다.
    for r in ['reports/PHASE2B_REPORT.md','reports/PHASE2B_D10_IMPLEMENTATION_REPORT.md','reports/PHASE2B_MISSINGNESS_REPORT.md',
        'reports/PHASE2B_D13_PREPARATION_REPORT.md','reports/PHASE2B_HANDOFF.md','qc/PHASE2B_QC.json',
        'qc/PHASE2B_INDEPENDENT_QC.md','qc/PHASE2B_D10_GATE_RESULT.json','qc/PHASE2B_INPUT_MANIFEST.json']:
        assert (OUT/r).is_file(),r
    outputs=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*'))
        if p.is_file() and p.name not in {'PHASE2B_OUTPUT_MANIFEST.json','PHASE2B_OUTPUT_MANIFEST.sha256'}]
    save('qc/PHASE2B_OUTPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':outputs,
        'excluded_self_and_seal':True,'protected_files_unchanged':manifest['count'],'dataset_QC':'PASS','D10_gate':state['D10_GATE']})
    save('qc/PHASE2B_OUTPUT_MANIFEST.sha256',sha(OUT/'qc/PHASE2B_OUTPUT_MANIFEST.json')+'  PHASE2B_OUTPUT_MANIFEST.json\n')
    print(json.dumps({'status':'PASS','automatic_QC':len(checks),'independent_QC':ind['count'],'protected':manifest['count'],
        'output_files_hashed':len(outputs),'D10_gate':state['D10_GATE'],'D13_gate':state['D13_GATE']},ensure_ascii=False))

if __name__=='__main__':main()
