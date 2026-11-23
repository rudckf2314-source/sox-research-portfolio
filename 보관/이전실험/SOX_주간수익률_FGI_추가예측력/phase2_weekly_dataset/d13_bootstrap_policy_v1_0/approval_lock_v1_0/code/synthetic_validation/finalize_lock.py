"""합성/독립 QC 통과 후에만 D13 LOCK v1.0을 등록한다."""
import copy,json
from datetime import datetime,timezone
from common import OUT,CAND,ROOT,PHASE1,load,sha,write

def main():
    policy=load(OUT/'logs/D13_APPROVED_CONTENT_PRE_QC.json')
    synth=load(OUT/'qc/D13_LOCK_SYNTHETIC_RESULTS.json')
    independent=load(OUT/'qc/D13_LOCK_INDEPENDENT_QC.json')
    inputs=load(OUT/'qc/D13_LOCK_INPUT_MANIFEST.json')
    candidate=load(CAND/'policy/D13_LOCK_CANDIDATE.json')
    changed=[p for p,v in inputs['protected_files'].items() if not (ROOT/p).is_file() or sha(ROOT/p)!=v['sha256']]
    checks={'사용자최종승인근거기록':bool(inputs['approval_authority']),
        '후보세부규칙완전보존':policy['approved_execution_rules']==candidate['candidate_rules'],
        'MBB구현원본바이트동일':sha(CAND/'code/bootstrap_candidate.py')==sha(OUT/'code/synthetic_validation/bootstrap_locked.py'),
        '기존D08승계':policy['inherited_inference_reference']==candidate['inherited_inference'],
        'A01승인_Type7':policy['A01']['status']=='APPROVED' and policy['A01']['Hyndman_Fan_type']==7,
        'A02승인_B안_family5':policy['A02']['status']=='APPROVED' and policy['A02']['option']=='B' and policy['A02']['family_size']==5,
        '구현오류대체금지':all(c['result']['internal_Holm_vector'] is None for c in synth['A02_cases'] if c['expect_implementation_error']),
        'Ridge보호':next(c for c in synth['A02_cases'] if c['case']=='Ridge_missing')['result']['primary_status']=='PRIMARY_RIDGE_INFERENCE_UNAVAILABLE',
        '합성QC_PASS':synth['status']=='PASS',
        '독립QC_PASS':independent['status']=='PASS',
        'Bootstrap_p미도입':not policy['bootstrap_p_value_enabled'],
        '기존22_7보존':policy['prior_tests_preserved']=={'synthetic_cases':22,'boundary_guards':7,'status':'PASS'},
        '보호파일해시불변':not changed,
        '실증실행권한없음':policy['execution_restrictions']['empirical_inference_authorized'] is False,
        'Phase3미승인':policy['execution_restrictions']['phase3_authorized'] is False,
        '시험성과밀봉':policy['execution_restrictions']['phase4_performance']=='SEALED'}
    passed=all(checks.values())
    if not passed:
        write('qc/D13_LOCK_QC.json',{'status':'BLOCKED_REVIEW_REQUIRED','checks':checks,'changed':changed})
        raise RuntimeError('BLOCKED_REVIEW_REQUIRED: no final LOCK written')
    policy['status']='LOCKED_v1_0'
    operative=copy.deepcopy(policy['inherited_inference_reference'])
    operative['MBB'].update({'resample_detail_status':'LOCKED_v1_0','minimum_valid_resample_n':'max(52, ceil(0.80*N_grid))',
        'insufficient_resample_action':'reject with recorded reason; redraw unchanged distribution',
        'empty_resample_action':'reject with recorded reason; redraw unchanged distribution',
        'max_total_attempts':10000,'redraw_failure_action':'BOOTSTRAP_INFERENCE_UNAVAILABLE; no CI/p',
        'confidence_quantiles':[.025,.975],'quantile_method':'linear','Hyndman_Fan_type':7,
        'execution_rules_reference':'approved_execution_rules'})
    # Supersede ambiguous old placeholder name; this limit counts ALL draws, not extra retries.
    operative['MBB'].pop('max_redraw_attempts')
    operative['Holm']['missing_p_decision_reference']='A02'
    policy['operational_inference']=operative
    policy['inherited_reference_note']='inherited_inference_referenceは既存LOCKの履歴参照であり、DEFERRED/nullは新承認の未確定を意味しない。'
    policy['inherited_reference_note']='inherited_inference_reference는 원본 Phase1의 역사 참조다. 그 안의 DEFERRED/null은 새 정책의 미확정을 뜻하지 않는다. 현재 유효 상세는 operational_inference와 approved_execution_rules 및 A01/A02다.'
    policy['locked_at_utc']=datetime.now(timezone.utc).isoformat()
    policy['code_hashes']={p.relative_to(OUT).as_posix():sha(p) for p in sorted((OUT/'code').rglob('*.py'))}
    write('D13_LOCKED_POLICY_v1_0.json',policy)
    decisions={'approval_authority':inputs['approval_authority'],'approved_on_kst':'2026-10-18','decisions':[
        {'decision_id':'D13_EXECUTION_RULES_v1_0','status':'APPROVED','definition':'후보 min_n/RNG/paired 결측/비순환MBB/5000유효/10000총시도 규칙 그대로 채택'},
        policy['A01'],policy['A02']]}
    write('D13_APPROVED_DECISIONS.json',decisions)
    gates={'D10_GATE':'IMPLEMENTATION_PASS','PHASE2B_DATASET_QC':'PASS','D13_POLICY':'APPROVED',
        'D13_A01':'APPROVED','D13_A02':'APPROVED','D13_LOCK_QC':'PASS','D13_LOCK_STATUS':'LOCKED_v1_0',
        'PHASE3_EXECUTION':'NOT_AUTHORIZED','PHASE4_TEST_PERFORMANCE':'SEALED',
        'empirical_statistical_significance_evaluated':False,'updates_prior_gate_files':False}
    write('D13_GATE_STATUS.json',gates)
    write('D13_LOCKED_POLICY_v1_0.md','''# 연구 C D13 최종 승인 정책 LOCK v1.0

정책 ID: **C_D13_CALENDAR_GRID_MBB_v1_0**. 상태 **LOCKED_v1_0**. 승인2026-10-18 KST. 현재 사용자의 명시적 승인에 따라 후보 및 A01/A02를 동결한다.

## 효력과 참조

후보 `../policy/D13_LOCK_CANDIDATE.json`은 당시 상태로 보존한다. 기존 Phase1 LOCK도 수정하지 않는다. 이 신규승인버전이 D13의 운영상 세부규칙을 확정한다. JSON의 inherited_inference_reference는 과거 설계의 정확한 참조 사본이므로 그 안의 DEFERRED/null과 현재 승인상태를 혼동하지 않는다. 현재 적용명세는 operational_inference,approved_execution_rules,A01,A02다.

## Bootstrap 운영규칙

최소표본=max(52,ceil(.80*N_grid)). 분모는 사전에 정한 연속 미국 달력 주 전체격자이며 유효주만으로 축소하지 않는다. 원본paired손실 미달이면 추출전중단. 비순환MBB8주(민감도4·12),시작점0..N−L 균등복원추출,ceil(N/L)개 블록연결 후N슬롯절단. M0/M1손실·결측·주날짜 공동추출. 빈주 압축·보간 금지. n_valid는 복원추출 중복도 세는 슬롯 수다.

재표본 n하한 미달은 기록 후 동일분포 재추출. 유효5000회목표,총10000시도한도이며10001번째추출없음. 미달이면 BOOTSTRAP_INFERENCE_UNAVAILABLE,CI/p산출금지. 원본/재표본분산0·비유한·연산오류는임의epsilon/p0으로처리하지않는다. 기존결측·거절규칙/RNG는변경없다.

seed20261016. YYYY-MM-DD 주격자를LF로연결(마지막LF없음),ASCII SHA256의32byte를little-endian uint32 8개로분할한다. SeedSequence([20261016,L,*words])→PCG64→Generator. 동일격자/L/시도번호의알고리즘은공통시작인덱스. mask차이로채택번호가달라질수있으며 결과에따라seed/한도/하한을변경하지않는다. 장애주입 forced_start는합성QC에서만허용한다.

## A01 — APPROVED

`D13_A01_PERCENTILE_LINEAR_TYPE7`. 양측95% percentile CI의 q=.025,.975를linear/Hyndman–Fan Type7로계산한다. 정렬x에 h=(n−1)q,j=floor(h),g=h−j,Q=(1−g)x[j]+g*x[min(j+1,n−1)]이다. NumPy는 `np.quantile(x,[.025,.975],method="linear")`를사용하고실제버전을JSON/환경기록에남긴다. BCa/basic/studentized로변경하지않는다.

## A02 — APPROVED, B안

`D13_A02_HOLM_FAMILY5_CONSERVATIVE_MISSING_P`. family는OLS,Ridge,Elastic Net,Random Forest,HistGradientBoosting의5개다. 기존HAC 단측p를기본으로사용한다.

구현오류·정렬오류·잘못된입력·재현불능수치오류·미승인규칙은 IMPLEMENTATION_ERROR_REVIEW_REQUIRED이며 **전체 해당 Holm절차를중단**한다. p=1대체금지. 원인수정과검증전보정결론없음.

적법한통계적미산출(최소paired표본부족,분산0,승인규칙의명시적추론불가)은 raw_p=null,status=NOT_COMPUTABLE,구체적사유를기록한다. **Holm 내부벡터에서만1**을사용한다. 전체5개에step-down을수행하며계산가능항목의raw/보정p를보고한다. 미산출항목의보고용보정p는null이고 REJECTION_NOT_SUPPORTED다. 내부1은실제측정p가아니다.

정렬p_(j)에 `adj_(j)=min(1,max_{i<=j}[(5−i+1)*p_(i)])`를적용한다. 동률표시순서는family목록순으로고정하며보정값은동률일관성을유지한다. 누락을이유로family4/3축소금지. 일부미산출이면 PARTIALLY_EVALUATED_FAMILY,전부미산출이면 FAMILY_INFERENCE_UNAVAILABLE. 계산가능항목의결과만부분평가임을밝혀보고한다.

Ridge미산출이면 PRIMARY_RIDGE_INFERENCE_UNAVAILABLE. 다른알고리즘의유의한결과로주력결론을대체하지않고 예측정보가치없음의증거로해석하지않는다. 실제미산출사유와구현오류를먼저분류/검증해야한다. 원인불명은적법한미산출로승격하지않는다.

## 기존 D08 불변

MAE(%p),Delta=MAE(M0)−MAE(M1),양수FGI유리. HAC Bartlett lag4 **원래달력주거리**,민감도2·8,소표본보정없음. u=d−mean(d),Omega=[sum(u²)+2sum_{i<j,1<=gap<=q}(1−gap/(q+1))u_i*u_j]/n,SE=sqrt(Omega/n),z=mean(d)/SE,단측p=1−Phi(z),alpha=.05,양측CI=mean(d)±1.95996398454*SE. 분산0/비유한/음수오류중단. 실제적법한분산0과구현오류는A02로구분한다. Bootstrap는양측percentile95%CI만유지하며새p검정없음. 주력Ridge와5종Holm유지.

## 범위·한계

정책QC는실제통계적유의성검증이아니다. 52/80% 및조건부재추출은검정력/coverage보장이아니다. 비무작위결측·구조변화·모형선정불확실성·과거게시/빈티지UNVERIFIED한계를유지한다. 보조모형은자체격자/가용성검증을거쳐야하며818주자동승계금지.

D10_GATE=IMPLEMENTATION_PASS,PHASE2B_DATASET_QC=PASS,D13_POLICY/A01/A02=APPROVED,D13_LOCK_QC=PASS,D13_LOCK_STATUS=LOCKED_v1_0. Phase3=NOT_AUTHORIZED,Phase4성과=SEALED. 이번승인으로실제학습/성과/검정실행은허가되지않는다.
''')
    write('D13_LOCK_CHANGELOG.md','''# D13 LOCK 변경기록

후보 v1.0→승인 LOCK v1.0. 원본후보파일/코드/검증22사례7경계/Phase1/Phase2B수정없음.

|항목|후보|현재|
|---|---|---|
|정책상태|LOCK_CANDIDATE_REVIEW_REQUIRED|LOCKED_v1_0|
|최소표본/RNG/재추출/5000·10000|후보|동일내용승인|
|A01보간|추가결정필요|linear Type7 승인|
|A02미산출p|추가결정필요/당시결론보류권고|B안승인: 적법한미산출만내부1,보고null,m5유지|
|구현오류|미산출과구분필요|p1대체금지/절차중단명시|
|주력Ridge미산출|주력보호원칙|전용상태/대체금지명시|
|Bootstrap p|추가하지않음|동일|
|Phase3|미승인|미승인|

운영JSON의구 max_redraw_attempts(null)는 max_total_attempts=10000으로명확화했다. 이는초회포함한총시도한도이며10000추가재시도가아니다. 역사참조JSON은원문그대로유지했다. 후보MBB코드사본은SHA256동일하다.
''')
    qc={'status':'PASS','checks':checks,'count':len(checks),'protected_count':len(inputs['protected_files']),
        'protected_changed':changed,'synthetic_checks':synth['check_count'],'independent_checks':independent['count'],
        'actual_execution_counts':{'models_fit':0,'tuning':0,'predictions':0,'performance':0,'actual_loss_inference':0,'test_Y_parse':0,'phase3':0},
        'gates':gates}
    write('qc/D13_LOCK_QC.json',qc)
    write('reports/D13_LOCK_REPORT.md',f'''# 연구 C D13 최종 승인·LOCK v1.0 보고서

작성2026-10-18 KST. 정책 **C_D13_CALENDAR_GRID_MBB_v1_0**,상태 **LOCKED_v1_0**.
사용자의최종승인에따라문서·구현명세·합성QC를동결했다. 실제모델성과/통계유의성을검증한것은아니다.

## 승인 내용

A01 D13_A01_PERCENTILE_LINEAR_TYPE7=APPROVED. q=.025/.975,linear,Hyndman–Fan Type7의양측95%percentileCI. NumPy버전 **{policy['A01']['numpy_version']}**. h=(n−1)q를정렬자료사이선형보간한다. 기존CI종류를바꾸지않았다.

A02 D13_A02_HOLM_FAMILY5_CONSERVATIVE_MISSING_P=APPROVED,**B안**. 통계적으로적법한미산출만raw/보고보정p=null,구체적사유/status를유지하고Holm내부에서1을쓴다. family5개유지,일부미산출시부분평가명시. 구현오류/정렬오류/미승인규칙은p1대체금지및절차중단이다. Ridge미산출시 PRIMARY_RIDGE_INFERENCE_UNAVAILABLE,다른모형으로주력대체금지.

min_n=max(52,ceil(.80N_grid)),비순환MBB8(4·12),paired/원래격자,5000유효/10000총시도,seed20261016+격자SHA/L파생을후보그대로보존했다. 기존MBB코드는바이트동일사본으로보존했다. HAC Bartlett4(2·8),단측alpha.05,양측95%CI,5종Holm,Ridge,Delta=M0−M1,정규z/p/분산식/소표본보정미사용은불변이다. Bootstrap p검정을추가하지않았다.

## QC

기존합성22사례/7경계검사및모든파일해시보존. 신규A01 **9개**데이터사례,A02 **22개**사례와추가guard/smoke를포함한합성검사 **{synth['check_count']}/{synth['check_count']} PASS**. 별도구현독립QC **{independent['count']}/{independent['count']} PASS**,최종LOCK QC **{len(checks)}/{len(checks)} PASS**.

A01은Decimal60자리독립계산으로순위일치/보간/중복/음양혼합을확인했다. A02는주step-down코드를호출하지않고31개비공집합Bonferroni폐쇄검정과대조했다. 정상/1개·여러개·Ridge만·전부미산출,p0/1,동률,단조성,보고null,m5유지,구현오류중단을검사했다. MBB사본으로합성52주5000회smoke를통과했다. 모두합성입력이며실제손실/p/CI는계산하지않았다.

동일Codex작업내별도코드검증이며외부독립심사가아니다. 합성검사는실제검정력/coverage의증명이아니다. 예기치않은테스트실패0이며음성사례의중단은의도한PASS다. 규칙이나검정값을결과에맞춰변경하지않았다.

## 보호 및 접근

기존보호 **{len(inputs['protected_files'])}개 SHA256 일치**,변경0. 기존Phase1 LOCK/Phase2B/후보폴더/RAW/freeze불변. 시험자료는바이너리해시만확인했고디코딩/CSV파싱/Y열람0. 시험성과/실제오차추론0,모델학습/튜닝/예측0,Phase3실행0.

입력참조경로·해시는qc/D13_LOCK_INPUT_MANIFEST.json,산출물은qc/D13_LOCK_OUTPUT_MANIFEST.json와별도sha256이다. 기존후보를참조하는별도승인버전이며과거파일을수정하거나이전게이트상태를지우지않았다. 역사참조의DEFERRED/null과현재운영명세를구별했다.

## 최종 게이트

|항목|상태|
|---|---|
|D10_GATE|IMPLEMENTATION_PASS|
|PHASE2B_DATASET_QC|PASS|
|D13_POLICY/A01/A02|APPROVED|
|D13_LOCK_QC|PASS|
|D13_LOCK_STATUS|LOCKED_v1_0|
|PHASE3_EXECUTION|NOT_AUTHORIZED|
|PHASE4_TEST_PERFORMANCE|SEALED|

D13정책승인은완료됐다. 이문서로실제연구결과의통계유의성/정보가치가확인됐다고해석하지않는다. 연구가정·빈티지·조건부재추출·결측선택한계를유지한다. 후속모델학습/시험은별도승인전금지. LOCK등록에서작업종료.
''')
    write('reports/D13_LOCK_HANDOFF.md','''# D13 LOCK 인수인계

정책 C_D13_CALENDAR_GRID_MBB_v1_0,상태 LOCKED_v1_0. D10구현/Phase2B데이터QC PASS,D13/A01/A02 APPROVED. 정책QC PASS. Phase3=NOT_AUTHORIZED,Phase4시험성과=SEALED.

현재효력은 D13_LOCKED_POLICY_v1_0.json의approved_execution_rules,operational_inference,A01,A02다. inherited_inference_reference는변경하지않은과거Phase1원문이다. 후보와현재승인사이관계/해시는supersedes_candidate에기록했다.

합성검증코드는 code/synthetic_validation/. MBB는후보코드의바이트동일사본이다. approved_inference_details.py는Type7와5종Holm의승인규칙을구현한다. 실제연구데이터로아직실행하지않았다. 실제손실계산·HAC구현·모델학습은추가승인단계의별도코드와QC가필요하다.

Ridge p미산출은주력추론불가이지FGI무가치의증거가아니다. 버그를적법한통계미산출로재분류해내부p1처리하지않는다. 전체family5개를유지하고미산출항목은raw/보고보정p=null이다. 부분평가를명시한다.

재현환경은qc/D13_LOCK_INPUT_MANIFEST.json. 실행순서는prepare_lock.py→synthetic_tests.py→independent_qc.py→finalize_lock.py이며각파일은기존출력덮어쓰기를거부한다. 기존폴더재실행대신검토된신규실행버전이필요하다. 마지막읽기전용검사는 independent_qc.py --sealed-check.

시험Y파싱/실제통계검정/모델성과평가/Phase3이후를자동시작하지않는다. 이전D13후보·Phase1게이트는역사기록그대로보존한다.
''')
    write('README.md','''# 연구 C D13 승인 LOCK v1.0

**C_D13_CALENDAR_GRID_MBB_v1_0 — LOCKED_v1_0**.
기존후보를참조하는별도승인버전이다. A01 Type7선형보간과A02 B안5종Holm을승인했다.

- [최종정책](D13_LOCKED_POLICY_v1_0.md)
- [결과보고서](reports/D13_LOCK_REPORT.md)
- [인수인계](reports/D13_LOCK_HANDOFF.md)
- [독립QC](qc/D13_LOCK_INDEPENDENT_QC.md)

새학습/예측/실제오차검정미실시. Phase3 NOT_AUTHORIZED,Phase4성과 SEALED. 합성QC는실제통계유의성을뜻하지않는다.
''')
    write('logs/D13_LOCK_WORK_LOG.md',f'''# D13 승인 LOCK 작업 이력

2026-10-18 사용자최종승인접수. 필수참조를실제열람하고SHA기록. 기존1569파일/후보manifest검증PASS.
후보MBB코드바이트동일복사,기존22사례/7경계기록보존. A01/A02명세및합성입력경로작성.
합성A01 9사례/A02 22사례,총32검사PASS. 별도Decimal/31부분집합폐쇄검정18검사PASS. 최종16검사PASS후LOCK문서생성.
예기치않은검사실패0. 의도한버그·잘못된입력은p1없이절차중단PASS. 테스트수치를맞추는변경없음.
새폴더밖쓰기0,기존파일변경0. 시험Y파싱0,실제p/CI/오차검정0,학습/예측/성과/Phase3실행0.
후속독립 --sealed-check로최종게이트·manifest·보호해시를읽기전용대조한다.
''')
    files=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file()]
    write('qc/D13_LOCK_OUTPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':files,'file_count':len(files),
        'excludes':['qc/D13_LOCK_OUTPUT_MANIFEST.json','qc/D13_LOCK_OUTPUT_MANIFEST.sha256'],
        'self_hash_policy':'별도sha256에manifest해시기록'})
    write('qc/D13_LOCK_OUTPUT_MANIFEST.sha256',sha(OUT/'qc/D13_LOCK_OUTPUT_MANIFEST.json')+'  D13_LOCK_OUTPUT_MANIFEST.json\n')
    print({'LOCK':'LOCKED_v1_0','policy_QC':len(checks),'synthetic_QC':synth['check_count'],'independent_QC':independent['count'],
        'protected':len(inputs['protected_files']),'hashed_outputs':len(files)})

if __name__=='__main__':main()
