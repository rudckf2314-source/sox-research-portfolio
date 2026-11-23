"""모든 감사 통과 뒤에만 최종 LOCK/사전감사 PASS 등록. 시험 실행기 없음."""
import copy
from datetime import datetime,timezone
from common import *
def main():
    verify=load(OUT/'lock/PHASE3_SELECTION_VERIFICATION.json')
    indep=load(OUT/'qc/PHASE3_FINAL_LOCK_INDEPENDENT_QC.json')
    synth=load(OUT/'qc/SYNTHETIC_PRETEST_PLANNER_QC.json')
    seal=load(OUT/'audit/PHASE4_DATA_SEAL_AUDIT.json')
    inputs=load(OUT/'qc/INPUT_MANIFEST.json')
    candidate=load(DEV/'selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.json')
    d13=load(D13/'D13_LOCKED_POLICY_v1_0.json');dg=load(D13/'D13_GATE_STATUS.json')
    oldqc=load(DEV/'qc/PHASE3_QC.json')
    counts=load(BUILD/'data/WEEKLY_SAMPLE_COUNTS.json')
    changed=[r for r,v in inputs['protected_files'].items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    checks={
        '개발209원점15048본실험재현':verify['counts']['origins']==209 and verify['counts']['candidate_fits']==15048,
        '기본517주_308초기_209개발':verify['counts']['common']==517 and verify['counts']['initial']==308 and verify['counts']['development']==209,
        '선택10개_반올림MAE일치':len(verify['models'])==10 and all(m['within_rounding_tolerance'] for m in verify['models']),
        '독립20개QC통과':indep['status']=='PASS' and indep['count']==20,
        '합성13사례22경계통과':synth['status']=='PASS' and synth['count']==22,
        '기존Phase3_QC_PASS':oldqc['PHASE3_DEVELOPMENT_QC']=='PASS' and oldqc['PHASE3_INDEPENDENT_QC']=='PASS',
        'Ridge주력고정':candidate['primary_algorithm']=='Ridge' and verify['primary_algorithm']=='Ridge',
        'D13정책ID_해시불변':d13['policy_id']=='C_D13_CALENDAR_GRID_MBB_v1_0' and candidate['future_phase4']['D13_lock_sha256']==sha(D13/'D13_LOCKED_POLICY_v1_0.json'),
        'D13_A01_A02승인':dg['D13_A01']==dg['D13_A02']=='APPROVED' and dg['D13_LOCK_STATUS']=='LOCKED_v1_0',
        'D10구현PASS':load(BUILD/'qc/PHASE2B_D10_GATE_RESULT.json')['D10_GATE']=='IMPLEMENTATION_PASS',
        '미산출p_B안_구현오류중단':d13['A02']['option']=='B' and d13['A02']['family_size']==5 and 'no p=1 substitution' in d13['A02']['implementation_error'],
        '시험메타데이터301주':counts['splits']['sealed_test']['paired_common_valid']==301 and counts['splits']['sealed_test']['weeks']==301,
        '시험3CSV봉인해시':seal['status']=='PASS' and seal['files']==3 and not seal['Y_content_decoded_or_parsed'],
        '보호2059파일불변':not changed and inputs['protected_count']==2059,
        '학습_시험_검정새실행0':synth['model_fits']==synth['predictions']==0 and indep['new_estimator_fits']==0,
        '선택실패0_미예측0':verify['counts']['candidate_fit_failures']==verify['counts']['nonpredicted_origins']==0,
        'Bootstrap_p신규미도입':d13['bootstrap_p_value_enabled'] is False,
        '기존후보데이터버전일치':candidate['dataset']['sha256']==sha(BUILD/'data/train_dev/WEEKLY_CORE_COMBINED.csv')}
    passed=all(checks.values());status='PASS' if passed else 'BLOCKED_REVIEW_REQUIRED'
    write('qc/PHASE3_FINAL_LOCK_QC.json',{'status':status,'checks':checks,'count':len(checks),'independent_checks':20,
        'synthetic_checks':22,'protected_count':2059,'protected_changed':changed,
        'new_execution_counts':{'model_fits':0,'predictions':0,'test_loss':0,'test_Y_parse':0,'test_HAC_MBB_Holm':0,'phase4':0,'phase5':0}})
    if not passed:
        write('audit/PHASE4_READY_GATE.json',{'PHASE4_PRETEST_AUDIT':'BLOCKED_REVIEW_REQUIRED','PHASE4_EXECUTION':'NOT_AUTHORIZED','PHASE4_TEST_PERFORMANCE':'SEALED'})
        raise RuntimeError('BLOCKED_REVIEW_REQUIRED; final LOCK not written')
    env=load(DEV/'config/PHASE3_ENVIRONMENT_LOCK.json')
    defaults={}
    for a,v in candidate['selected_algorithms'].items():
        defaults[a]={info:env['explicit_and_default_estimator_params'][a][m['candidate_id']] for info,m in v['models'].items()}
    locked={'policy_id':'C_PHASE3_FINAL_EXPERIMENT_LOCK_v1_0','status':'LOCKED_v1_0','approved_on_kst':'2026-10-18',
        'locked_at_utc':datetime.now(timezone.utc).isoformat(),
        'authority':'현재 사용자 직접 지시로 최종 사양 등록 승인. Phase4 실행은 승인되지 않음.',
        'supersedes_candidate':{'path':(DEV/'selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.json').relative_to(ROOT).as_posix(),
            'sha256':sha(DEV/'selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.json')},
        'dataset':copy.deepcopy(candidate['dataset']),'features':copy.deepcopy(candidate['features']),
        'selected_algorithms':copy.deepcopy(candidate['selected_algorithms']),'primary_algorithm':'Ridge',
        'estimator_full_parameters':defaults,'environment':env,'environment_source_sha256':sha(DEV/'config/PHASE3_ENVIRONMENT_LOCK.json'),
        'origin':{'day':'first actual US equity session of Monday-based target calendar week','local_time':'09:00','timezone':'America/New_York'},
        'training':{'label_condition':'label_assumed_available_at UTC < prediction_origin UTC; verified actual timestamp overrides assumption when available',
            'week_condition':'training target week strictly before target week; training row own X eligible at own historical origin',
            'rolling':'own training prediction origin >= (current prediction origin in America/New_York minus 5 calendar years); calendar clamp leap day',
            'minimum_train_n':156,'OLS':'full rank with intercept and n>p+20',
            'linear_preprocessing':'train-only StandardScaler + intercept for OLS/Ridge/ElasticNet',
            'tree_preprocessing':'native scale; HGB early_stopping=False; no imputation bypass',
            'weekly_refit_with_newly_matured_labels':True,'fixed_5row_purge':False,'PCA':False,'negative_prediction_clipping':False},
        'seed':20261016,'workers':1,'test_grid':{'first_week':'2021-01-04','last_week':'2026-10-05','expected_paired_XY_weeks':301,
            'count_basis':'Phase2B report and WEEKLY_SAMPLE_COUNTS.json metadata; no test CSV parsed',
            'expected_predictions_not_guaranteed':True,'planned_model_fits_if_all_eligible':3010},
        'baselines':['0%','origin/window eligible training Y mean'],
        'metrics':{'primary':'MAE(%p)','secondary':['RMSE(%p)','OOS_R2_vs_origin_training_mean','direction accuracy'],
            'direction_rule':'sign(pred)==sign(Y); sign(0)=0','delta_MAE':'MAE(C-M0)-MAE(C-M1); positive favors FGI'},
        'statistics':{'policy_id':d13['policy_id'],'policy_json_sha256':sha(D13/'D13_LOCKED_POLICY_v1_0.json'),
            'operational_inference':copy.deepcopy(d13['operational_inference']),
            'A01':copy.deepcopy(d13['A01']),'A02':copy.deepcopy(d13['A02']),
            'approved_execution_rules':copy.deepcopy(d13['approved_execution_rules']),
            'algorithm_name_map':{'OLS':'OLS','Ridge':'Ridge','ElasticNet':'Elastic Net','RandomForest':'Random Forest','HistGradientBoosting':'HistGradientBoosting'},
            'bootstrap_p_value_enabled':False},
        'errors':{'implementation_or_estimator_error':'stop and review; no substitution, candidate dropping, or p=1 masking',
            'insufficient_training':'paired NOT_PREDICTED_INSUFFICIENT_TRAINING; retain full grid and reasons',
            'legitimate_inference_missing':'D13 A02 only; raw/reported-adjusted p null; internal1; m5 retained',
            'Ridge_missing':'PRIMARY_RIDGE_INFERENCE_UNAVAILABLE; never substitute another primary'},
        'test_prediction_sequence':['expose only eligible current X and past matured Y to model','fit fixed selected recipe on historical eligible rows',
            'return prediction with no current Y supplied','persist/hash prediction before scoring','then access outcome for evaluation','no tuning from any test losses'],
        'phase4_execution_authorized':False,'phase5_execution_authorized':False,'test_performance_status':'SEALED',
        'limitations':copy.deepcopy(candidate['limitations'])+['code/log review is not a retrospective OS access monitor']}
    write('lock/PHASE3_FINAL_LOCK_v1_0.json',locked)
    table='| 알고리즘 | 정보집합 | 창 | 후보 | 주요 파라미터 | 개발 MAE(%p) |\n|---|---|---|---|---|---|\n'
    for r in verify['models']:
        p={k:v for k,v in r['parameters'].items() if k!='candidate_id'}
        table+=f"| {r['algorithm']} | {r['information_set']} | {r['window']} | {r['candidate_id']} | {json.dumps(p,ensure_ascii=False)} | {r['MAE_recalculated']:.6f} |\n"
    write('lock/PHASE3_FINAL_LOCK_v1_0.md','''# 연구 C Phase3 최종 실험사양 LOCK v1.0

**C_PHASE3_FINAL_EXPERIMENT_LOCK_v1_0 — LOCKED_v1_0**. 사용자 최종 사양 등록 승인에 따른다. 기존 후보·Phase1·Phase2B·D13은 수정하지 않는다. Phase4 실행 승인은 포함하지 않는다.

주력 알고리즘은 **Ridge**다. 개발 최저 MAE인 RF를 주력으로 교체하지 않는다. 아래10개 설정을 개발 로그에서 재현한 뒤 고정했다.

'''+table+'''
Y=100*(P_w/P_(w−1)−1), SOX Close의 미국 월요일~일요일 비중첩 주간 부호수익률(%). M0=B1~B10, M1=M0+F1. 원점은 해당 주 첫 실제 미국 거래세션09:00 America/New_York이다.

각 알고리즘의 M0 개발 최적 MAE로 선택한 창을 쌍에 공유한다. 같은 창의 후보는 정보집합별 동일 탐색 규칙으로 선택했다. 창 동점 Expanding, 후보 동점 candidate_id 오름차순이며 18개 고정 후보 외 추가 탐색은 없다.

미래 Phase4 실행은 audit/PHASE4_EXECUTION_SPEC.md 및 동명JSON의 training/statistics/errors/test_prediction_sequence를 따른다. 전체 생성자 기본값과 명시 설정도 JSON에 고정했다. 환경을 변경해야 하면 호환성/QC를 검토하고 조용히 새 기본값을 사용하지 않는다.

D13 정책 C_D13_CALENDAR_GRID_MBB_v1_0의 해시·운영명세·A01/A02를 참조하며 변경하지 않는다. 최소n=max(52,ceil(.8N_grid)), MBB8(4·12), 유효5000/총10000, Type7 percentile CI, HAC Bartlett4(2·8), 단측alpha.05, Holm5종과 주력Ridge를 유지한다. 새 Bootstrap p는 없다.

검토한 시험 격자는2021-01-04~2026-10-05, 예상301주이며 이는 X/Y 메타데이터 가용 주수이지 실제 예측 성공 수의 보증이 아니다. PHASE4_EXECUTION=NOT_AUTHORIZED, PHASE4_TEST_PERFORMANCE=SEALED. 별도 승인 전 시험 X/Y 내용 파싱·모델 적합·예측·성과·통계검정을 실행하지 않는다.

FGI 추가 전후 비교와 단순 기준예측 대비 성능은 별도로 해석한다. 음의 결과도 보존하며 시험 성능으로 사양·주력·연구대상을 바꾸지 않는다. 개발 선택 편향, 과거D1/W1 노출, 수정본·게시시각/빈티지 UNVERIFIED 한계를 유지한다.
''')
    write('lock/PHASE3_LOCK_CHANGELOG.md','''# Phase3 최종 LOCK 변경기록

- 기존 후보 LOCK_CANDIDATE_REVIEW_REQUIRED에서 신규 승인 버전 LOCKED_v1_0을 등록했다.
- 선정된10개 알고리즘·창·후보·파라미터·변수·Y 정의는 변경하지 않았다. 후보 원본의 경로/해시를 참조한다.
- Phase4의 동적 성숙 라벨 재학습과 시험 오차 기반 재튜닝을 구분해 실행 순서/중단조건을 문서화했다.
- Phase4 실행 권한은 계속 NOT_AUTHORIZED다. 정책 최종 등록과 실제 시험은 별개다.
- D13의 알고리즘 이름 Elastic Net/Random Forest와 코드명 ElasticNet/RandomForest의 대응표만 명시했다. family나 알고리즘 변경이 아니다.
- JSON의 5달력년 경계는 후보의 origin 기준과 동일하며 윤년 날짜 보정만 명확히 적었다. 새 학습창 선택이 아니다.
- 기존 모든 파일은 보존했다. 합성 윤년 사례의 최초 잘못된 기대 상태와 정정 이력은 logs에 남겼다.
''')
    write('audit/PHASE4_EXECUTION_SPEC.md','''# Phase4 향후 실행 명세 — 현재 실행 미승인

## 고정 과제와 원점

SOX 비중첩 미국 달력 주 부호수익률, M0=B1~B10/M1=+F1, 첫 실제 미국 세션09:00 America/New_York. 시험 주격자2021-01-04~2026-10-05, 예상301주. 실제 거래일·DST는 동결 Phase2B를 승계하고 새 데이터를 만들지 않는다.

## 매 원점의 순서

1. 최종LOCK·D13·환경·Phase2B 입력 해시를 대조한다. 별도 실행 승인 없으면 시작하지 않는다.
2. 현재 X의 적격성을 확인한다. 각 훈련 행도 자기 과거 원점에서 X가 적격했어야 한다.
3. target week가 과거이고 label_available_at<origin인 성숙 Y만 모은다. timestamp는 aware UTC로 엄격비교한다. 실제 확인값이 있으면 승인 가정보다 우선한다.
4. 선택된 Expanding 또는 원점 기준 최근5달력년의 과거 원점들을 사용한다. 경계는포함,260행을맞추려창확장금지. 최소156유효주, OLS fullrank/n>p+20를 검사한다.
5. 선형 OLS/Ridge/ElasticNet은 해당 학습행만 StandardScaler에 fit하고 절편을 둔다. 트리는원척도,HGB early_stopping=False. 결측우회·PCA·clipping·새특징/탐색금지. seed20261016/worker1 및 고정 환경 기본값을 사용한다.
6. 현재 Y를 모델 함수에 전달하지 않고 고정후보를 적합해 현재 X를 예측한다. 예측값/원점/훈련목록/설정 해시를 먼저 저장한다.
7. 예측 확정 후에만 현재 Y와 비교한다. 과거 시험주의 성숙 Y는 이후 원점의 학습에 사용할 수 있으나, 시험 오차로 후보/창/특징/전처리를 바꾸지 않는다.
8. 0% 및 같은 원점·창의 훈련Y평균을 기준예측으로 저장한다. M0/M1의 날짜/Y/공통훈련주를 맞춘다.

성숙라벨 Walk-forward 재적합은 허용 예정이나, 시험손실 기반 재튜닝은 금지다. 전기간517주로 한번 적합하는 고정모형으로 바꾸지 않는다. 이번 작업에서는 어떤 시험 원점도 실행하지 않았다.

## 오류·미예측

현재X불가/156주미달은 쌍 공동 미예측과 날짜·사유를 기록하고 원래301주 격자를 압축하지 않는다. 모델/정렬/입력/재현오류는 중단·검토한다. 실패후보 교체/임의삭제/파라미터 변경금지. OLS rank실패 등은 단순통계미산출로 둔갑시키지 않고 원인을 판정한다.

## 평가와 검정

MAE(%p),RMSE(%p),origin훈련평균 기준OOS R²,sign(pred)==sign(Y) 방향정확도(sign0=0). FGI가치를ΔMAE=MAE(M0)−MAE(M1)로정의하며양수가유리하다. FGI 추가효과와0%/훈련평균보다실제우수한지를별도로보고한다.

HAC는 유효주 원래달력 gap을 사용한다. u=d−mean(d), Omega=[sum(u²)+2sum_{i<j,1<=gap<=q}(1−gap/(q+1))u_i*u_j]/n,SE=sqrt(Omega/n),q=4(2·8민감도),소표본보정없음. z=mean(d)/SE,단측p=1−Phi(z),alpha=.05; 양측95%CI는mean(d)±1.95996398454SE. 원본/수치분산0·비유한/음수오류는 원인판정 및 D13중단규칙을따른다.

D13비순환 MBB8(4·12),원래N격자·paired mask공동추출,seed20261016+격자SHA/L파생,유효5000/총10000시도,min_n=max(52,ceil(.8N))를유지한다. Type7 linear(.025,.975) percentile95%CI이며BCa/basic/studentized로변경하지않는다. 실패시BOOTSTRAP_INFERENCE_UNAVAILABLE,부족반복으로CI산출금지. 새Bootstrap p검정없음.

5개HAC 단측p에Holm을적용한다. 적법한통계미산출만raw/보고보정p=null,내부벡터1,m5유지;부분평가명시. 구현오류는p1대체금지/전체절차중단. Ridge미산출시 PRIMARY_RIDGE_INFERENCE_UNAVAILABLE,다른알고리즘으로주력교체금지. 모든세부는D13 LOCK이권위자료다.

## 실행 승인 경계

계획상상한은10설정×301원점=3010모델적합이나 실제적격원점에따라달라질수있다. 이번적합/예측/시험손실/검정은전부0이다. Phase4와Phase5는별도승인전실행불가다.
''')
    write('audit/PHASE4_LEAKAGE_RISK_REGISTER.md','''# Phase4 정보누출 위험 등록부

|위험|확인 근거와 통제|잔여 한계/상태|
|---|---|---|
|연구C 시험Y의 개발 선택 유입|train_dev 전용경로,209개체크포인트/코드서명,동결해시,기존접근로그 일치|새로운 누출 징후 없음. 저장코드 감사는OS전체행위의소급증명이 아님|
|현재원점Y의 학습 유입|과거주/성숙시각엄격UTC비교,예측함수는현재Y미수신,예측저장후평가|Phase4 실제구현에서도필수검사|
|과거X의 소급 가용성|Phase2B역사가용성lineage와D10정책불변|실제최초게시/공급자지연/빈티지는UNVERIFIED. 가정기반연구|
|재튜닝과동적재학습 혼동|고정10설정,선정창공유,새성숙과거Y만추가|시험오차로정책/후보변경금지|
|전표본스케일러/PCA|학습전용평균·분산전수검증,연구C주력PCA없음|실제시험구현에재검증필요|
|결측격자압축/성공사례선택|301주전체격자,paired미예측사유보존,D13최소n/시도한도|301개XY가용성이301개예측성공을보장하지않음|
|과거연구A(D1)/B(W1)노출|동일·유사한시장기간분석이력명시|연구C내부봉인과별개로연구자사전지식노출. 독립최초시험이라주장하지않음|
|부정적결과폐기/주력교체|Ridge사전주력고정,전5종/비개선보존|유의성없음을자료폐기/사양변경이유로삼지않음|

현재 감사에서 미해결 구현 충돌이나 새로운 보호파일 변경은 발견되지 않았다. 위 알려진 연구상 한계는 삭제하지 않고 논문에 유지한다.
''')
    write('audit/PHASE4_PRETEST_AUDIT.md','''# Phase4 시험 직전 감사

**PASS**. 이 판정은 고정사양과저장자료/코드/로그/합성경계의정합성에대한준비판정이며, 실제시험실행승인이나성능검증이아니다.

개발15,048예측,209체크포인트,72개후보조합MAE,10개최종선택이독립재현됐다. 개발308/209/517주,본fit15,048/실패0/미예측0을확인했다. 기존smoke13회·독립estimator36/선형해24를본예산에중복합산하지않았다.

시험폴더3CSV의파일명/크기/SHA는Phase2B봉인기록과일치한다. 내용파싱·Y조회·통계량계산0. 개발코드의DATA=train_dev,가용성로그의시험날짜prefix차단,예측반환후개발Y평가를정적검토했다. 체크포인트서명과그코드해시가일치한다. 저장증거와충돌하는누출이력은발견되지않았다. OS전체실행행위를소급감시한검사가아님은명시한다.

합성13사례22경계로원점동시각제외/최소156/5달력년/윤년/DST/현재X불가/미래주위조성숙제외를검증했다. 최초윤년테스트는155주인데적격을기대한기대값오류였으며,실행로직·데이터·정책을바꾸지않고중단기대값을정정했다. 최초실패결과와코드는logs에보존했다.

D10구현PASS,D13 LOCKED_v1_0을승계하고통계방향/Type7/A02family5를변경하지않는다. 알려진게시시각/빈티지한계,기존D1/W1시장노출과개발선택편향은위험등록부에유지한다.

**PHASE4_EXECUTION=NOT_AUTHORIZED, PHASE4_TEST_PERFORMANCE=SEALED**. 별도 사용자 실행 승인 전 시험적합/예측/손실/통계검정/Phase5를 시작하지 않는다.
''')
    gate={'PHASE3_DEVELOPMENT_QC':'PASS','PHASE3_MODEL_SELECTION':'COMPLETED','PHASE3_FINAL_LOCK':'LOCKED_v1_0',
        'D10_GATE':'IMPLEMENTATION_PASS','D13_LOCK_STATUS':'LOCKED_v1_0','PHASE4_PRETEST_AUDIT':'PASS',
        'PHASE4_EXECUTION':'NOT_AUTHORIZED','PHASE4_TEST_PERFORMANCE':'SEALED','PHASE5_EXECUTION':'NOT_AUTHORIZED'}
    write('audit/PHASE4_READY_GATE.json',gate)
    write('reports/PHASE3_FINAL_LOCK_REPORT.md','''# 연구 C Phase3 최종 LOCK 결과

최종 사양 **C_PHASE3_FINAL_EXPERIMENT_LOCK_v1_0 / LOCKED_v1_0** 등록 완료. 기존 개발 결과와 선택을 재현한 뒤 승인한10설정을그대로동결했다.

'''+table+f'''
주력은 **Ridge**다. 각알고리즘M0기준창선택과쌍공유,표현별동등탐색후별도후보선택이재현됐다. 새로운튜닝/변수/모델/창변경0이다. 개발MAE는반올림허용오차5×10⁻⁷%p내에서사용자표와일치하고,원래기록과는1×10⁻¹²이내다. 개발성능을최종시험성과나유의성으로표현하지않는다.

초기308/개발209/공통517주,개발209원점,18후보×2정보집합×2창=72조합,본fit15,048회/실패0/미예측0이다. 이번에는모델을재적합하지않고저장예측을전수재집계했다. 이전기술smoke/독립재적합을본실험수에합산하지않았다.

자동QC **{len(checks)}/{len(checks)} PASS**,독립QC **20/20 PASS**,합성13사례 **22/22 PASS**. 독립검사는별도NumPy집계와datetime/calendar구현이며외부심사가아니다. 원본보호 **2059개 SHA-256 불변**,기존RAW/연구A·B·C/D10/D13/Phase1~3수정0이다.

최초합성윤년기대값오류는155주에대해적격을기대한검사작성실수였다. 올바른중단을확인하도록기대상태만고쳤고최초실패와코드를보존했다. 실제데이터/성능에맞춘설계변경은없다.

시험파일은메타데이터/바이너리해시만확인했다. 시험Y파싱/모델적합/예측/오차/성과/통계검정0이다. 실제시험실행허가는포함하지않는다.

최종설정/기본생성자/환경/데이터해시/D13해시/중단규칙은lock/PHASE3_FINAL_LOCK_v1_0.json,준비판정은audit/PHASE4_READY_GATE.json,독립검증은qc에있다. 입력/출력manifest로보호자료와신규자료를구분했다.
''')
    write('reports/PHASE4_PRETEST_READINESS_REPORT.md',f'''# Phase4 시험 준비 판정

**PHASE4_PRETEST_AUDIT=PASS**. Phase3최종사양 LOCKED_v1_0,D10 IMPLEMENTATION_PASS,D13 LOCKED_v1_0.

개발로그·모델선택·동결해시·전처리·라벨성숙·5년창·최소표본·정보누출경계를확인했다. 자동{len(checks)}개/독립20개/합성22개검사통과. 보완이필요한미해결사양충돌없음.

예상시험기간은2021-01-04~2026-10-05주,301주로Phase2B메타데이터에서만확인했다. 시험CSV3개는크기/해시일치,내용미열람이다. 실증모델fit/예측/손실/통계검정0이다.

실제승인후에는고정10설정으로매주성숙한과거Y만추가하는Walk-forward재적합을수행해야한다. 원점별train-only전처리,현재Y미수신예측/저장후평가,시험오차기반재튜닝금지,동일paired표본,0%/훈련평균기준을유지한다. FGI추가효과와단순평균대비성과는별개질문이다.

D13의HAC Bartlett4(2·8)/단측.05/양측95% Type7 CI/MBB8(4·12)/5000유효·10000시도/min_n52·80%/Holm5/A02B안/Ridge보호를유지한다. 구현오류는p1대체없이중단한다. 이번에실제검정은하지않았다.

잔여연구한계: 게시시각/빈티지UNVERIFIED,수정원자료,개발선택편향,이전D1/W1의동일시장노출. 연구C내시험봉인은이전연구노출을지우지않는다. 코드/로그검사는OS접근전체의소급증명이아니다.

**사용자의 별도 Phase4 실행 승인이 필요하다.** 현재 PHASE4_EXECUTION=NOT_AUTHORIZED,PHASE4_TEST_PERFORMANCE=SEALED,Phase5도미승인이다. 준비PASS만으로자동실행하지않는다.
''')
    write('reports/PHASE4_HANDOFF.md','''# Phase4 인수인계

현재 Phase3최종LOCK=LOCKED_v1_0,시험직전감사PASS. **Phase4 실행은 NOT_AUTHORIZED**,시험성과SEALED. 별도 사용자 지시 전 멈춘다.

후속승인시먼저 lock/PHASE3_FINAL_LOCK_v1_0.json 및 md,audit/PHASE4_EXECUTION_SPEC.md,D13 LOCK원본,입출력manifest를읽고해시대조한다. 원래Phase1/D13/Phase2B/Phase3후보는역사기록그대로보존한다.

10개선정설정/기본값/환경을고정해쌍별같은창과공통훈련주를사용한다. 성숙한과거시험Y의후속재학습만허용하고시험손실로후보/창을바꾸지않는다. 현재Y는예측함수입력이아니며예측저장후평가한다. 원점UTC엄격비교/5달력년/156주/train-only전처리를지킨다.

오류발견시중단하고원인/영향을보고한다. p=1은통계적으로적법한미산출에만Holm내부에서허용한다. 버그에사용하지않는다. Ridge미산출을다른알고리즘결론으로대체하지않는다. FGI효과와기준모형대비예측력은별도보고한다. 부정적결과도보존한다.

이번폴더 재현순서: audit_and_verify.py→synthetic_planner.py→independent_qc.py→finalize_lock.py. 기존출력덮어쓰기를거부하므로전체재실행은새검토버전이필요하다. 읽기전용최종검사: independent_qc.py --sealed-check. 합성최초실패의기대값정정기록은logs에보존했다. 이번신규작업의실증모델적합/예측은0이다.
''')
    write('README.md','''# 연구 C Phase3 최종 LOCK 및 Phase4 시험 직전 감사

**Phase3 LOCKED_v1_0 / Phase4 준비감사 PASS**. 실제 Phase4 실행은 미승인,시험성과SEALED.

- [최종LOCK](lock/PHASE3_FINAL_LOCK_v1_0.md)
- [LOCK보고서](reports/PHASE3_FINAL_LOCK_REPORT.md)
- [시험준비보고서](reports/PHASE4_PRETEST_READINESS_REPORT.md)
- [향후실행명세](audit/PHASE4_EXECUTION_SPEC.md)
- [독립QC](qc/PHASE3_FINAL_LOCK_INDEPENDENT_QC.md)

기존자료와신규산출물은qc/INPUT_MANIFEST.json 및 OUTPUT_MANIFEST.json에별도로기록한다. 모델학습/시험Y파싱/예측/성과/통계검정은수행하지않았다.
''')
    write('logs/WORK_LOG.md','''# 최종 LOCK·사전감사 작업 이력

2026-10-18 현재사용자승인범위확인. 필수문서실제열람/해시기록. 개발15048예측/209체크포인트/72메트릭/10선택을재집계했다.
기존보호2059개해시불변. 시험3CSV는파일메타데이터와바이너리SHA만검사했다. 개발코드AST/접근로그/서명과봉인기록을검토했다.
합성13사례중최초윤년사례의기대값오류1건발견(실제적격155주). 로직/자료/정책변경없이기대중단상태를정정하고최초코드/FAIL기록보존. 수정후22검사PASS.
별도NumPy/표준달력구현독립20검사PASS. 자동18검사PASS후최종LOCK과준비PASS등록. 새문구를한국어로정리했으며수치/사양변경없음.
기존RAW/동결/연구결과변경0. 새모델fit/예측/시험손실/실제통계검정/Phase4/Phase5실행0. 실제시험실행은사용자별도승인대기에서종료.
''')
    files=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file()]
    write('qc/OUTPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':files,'file_count':len(files),
        'excludes':['qc/OUTPUT_MANIFEST.json','qc/OUTPUT_MANIFEST.sha256'],'protected_file_count':2059})
    write('qc/OUTPUT_MANIFEST.sha256',sha(OUT/'qc/OUTPUT_MANIFEST.json')+'  OUTPUT_MANIFEST.json\n')
    print({'final_lock':'LOCKED_v1_0','pretest_audit':'PASS','automatic_QC':len(checks),'independent_QC':20,
        'synthetic_QC':22,'protected':2059,'hashed_outputs':len(files),'phase4':'NOT_AUTHORIZED'})

if __name__=='__main__':main()
