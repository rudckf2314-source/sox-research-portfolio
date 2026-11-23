"""개발 실행/독립 QC 완료 후 보고서와 Phase4 실험사양 후보를 작성."""
from common import *
def mdtable(rows,fields,labels=None):
    def fmt(x):
        if x is None:return '미정의'
        if isinstance(x,float):return f'{x:.6f}'
        return str(x)
    return '| '+' | '.join(labels or fields)+' |\n|'+ '|'.join(['---']*len(fields))+'|\n'+'\n'.join('| '+' | '.join(fmt(r.get(f)) for f in fields)+' |' for r in rows)

def main():
    completion=load(OUT/'logs/WALKFORWARD_COMPLETION.json')
    independent=load(OUT/'qc/PHASE3_INDEPENDENT_QC.json')
    register=load(OUT/'selection/PHASE3_SELECTION_REGISTER.json');selected=register['selected']
    g=load(OUT/'qc/GATE_A.json');inputs=load(OUT/'inputs/PHASE3_INPUT_MANIFEST.json')
    predictions=pd.read_csv(OUT/'predictions/PHASE3_ALL_CANDIDATE_PREDICTIONS.csv')
    pair=pd.read_csv(OUT/'metrics/PHASE3_MODEL_PAIR_COMPARISON.csv').to_dict('records')
    windows=pd.read_csv(OUT/'metrics/PHASE3_WINDOW_COMPARISON.csv').to_dict('records')
    baselines=pd.read_csv(OUT/'metrics/PHASE3_BASELINE_METRICS.csv').to_dict('records')
    metricsrows=pd.read_csv(OUT/'metrics/PHASE3_CANDIDATE_METRICS.csv').to_dict('records')
    grid=load(OUT/'config/PHASE3_APPROVED_SEARCH_GRID.json');df=read_data()
    prep=load(OUT/'logs/PREPROCESSING_FIT_AUDIT.json')
    changed=[r for r,v in inputs['protected_files'].items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    ic=independent['checks'];checks={}
    def add(name,result,evidence):checks[name]={'PASS':bool(result),'evidence':evidence}
    add('01_Phase2B입력해시',sha(DATA)==inputs['data_sha256'],'DATA SHA-256 재확인')
    add('02_공통517주',len(df)==517,'train_dev paired_common_valid')
    add('03_개발209원점',(df.split=='development').sum()==209,'Gate A와 독립 CSV 검사')
    add('04_주간중복0',not df.week_start.duplicated().any(),'주 식별자 전수')
    add('05_훈련Y엄격성숙',ic['라벨성숙_자체X원점과거_현재Y유입0'],'418개 원점·창 독립 재선택')
    add('06_자체X역사가용성',ic['5687개자체역사원점가용성'],'5687개 lineage; 실제공개 UNVERIFIED 유지')
    add('07_현재Y학습유입0',ic['라벨성숙_자체X원점과거_현재Y유입0'],'대상주 제외와 label_available_at<origin')
    add('08_미래자료교란',load(OUT/'qc/SMOKE_AND_PERTURBATION_QC.json')['status']=='PASS','첫원점5알고리즘 M0: 현재Y/미래X,Y 교란 후 동일')
    add('09_train_only전처리',ic['전적합train_only스케일러검증'],'전체 선형 fit의 학습 평균/분산/n 전수 대조')
    add('10_시험CSV파싱0',ic['시험CSV파싱0_개발만'],'읽기경로 allowlist와 날짜prefix 차단')
    add('11_5개알고리즘',len(grid['algorithms'])==5,'승인 grid 동일')
    add('12_18개후보',sum(map(len,grid['algorithms'].values()))==18,'1+5+4+4+4')
    add('13_후보조합불변',ic['승인5알고리즘18후보동일'],'원본 LOCK JSON 비교')
    add('14_Expanding_Rolling5년',ic['260행강제확장없이5달력년'],'origin기준5달력년, cutoff포함, 만료라벨 제외')
    add('15_최소156주',all(x['n']>=156 for x in g['counts']),'418개 학습창 전수')
    add('16_fit_누락_실패계수',completion['candidate_fits_completed']==15048 and completion['failed_fits']==0,'본실험15048; 기술13/독립36은 별도')
    add('17_seed_worker',grid['seed']==20261016 and grid['workers']==1,'설정/모형 전체 get_params 및 threadpool_limits')
    add('18_기준예측',ic['0및학습평균836예측독립일치'],'창별0%/origin훈련평균')
    add('19_음수예측보존',bool((predictions.prediction<0).any()),'raw signed predictions; clipping 없음')
    add('20_탐색예산동등',all(len(x)==7524 for _,x in predictions.groupby('information_set')),'정보집합별 18*2*209')
    add('21_MAE독립계산',ic['72개후보조합지표전수독립재집계'],'math.fsum으로 72조합 전수')
    add('22_RMSE_OOSR2_방향',ic['72개후보조합지표전수독립재집계'],'origin훈련평균 분모/sign(0)=0')
    add('23_동일209주paired',ic['전후보209날짜_Y동일'],'모든 후보·정보집합·창 날짜/Y')
    add('24_Ridge_M0창선택',ic['주력Ridge선택재현'],'Ridge M0 창별 최적후보 MAE 비교')
    add('25_알고리즘별창선택',ic['알고리즘별M0창선택_표현별후보독립확인'],'각 알고리즘 M0 선택, 자기 M1에 공유')
    add('26_창동점Expanding',ic['동점규칙경계테스트'],'합성 동점 경계')
    add('27_후보동점ID',ic['동점규칙경계테스트'],'합성 ID 동점 경계')
    add('28_시험기반선택0',not register['test_data_used'],'2017~2020 예측 CSV만 집계')
    add('29_D13해시불변',not changed,'입력 manifest의 모든 D13 파일 포함')
    add('30_시험통계검정0',completion['phase4_executed'] is False,'HAC/Bootstrap/Holm 실제값 미계산')
    add('31_독립재적합',ic['첫중간마지막_60개독립재적합'],'첫·중간·끝60개: 선형폐쇄형24/estimator36')
    add('32_OLS_rank_자유도',ic['OLS_rank_자유도'],'모든 OLS 적합 검사')
    add('33_보호1594파일불변',not changed and len(inputs['protected_files'])==1594,'SHA-256 재확인')
    add('34_독립QC_PASS',independent['status']=='PASS',f"별도 구현 {independent['count']}개 검사")
    add('35_합성시점경계8검사',load(OUT/'qc/PHASE3_BOUNDARY_SYNTHETIC_QC.json')['status']=='PASS','동시각/직전/5년경계/위조성숙미래라벨 검사')
    passed=all(v['PASS'] for v in checks.values())
    state='PASS' if passed else 'BLOCKED_REVIEW_REQUIRED'
    save('qc/PHASE3_QC.json',{'PHASE3_DEVELOPMENT_QC':state,'PHASE3_INDEPENDENT_QC':independent['status'],
        'checks':checks,'count':len(checks),'changed_protected':changed,'protected_count':len(inputs['protected_files']),
        'fit_counts':{'development_candidate_estimator_fits':15048,'technical_smoke_success_fits':10,
            'initial_aborted_smoke_fits':3,'independent_estimator_fits':36,'independent_closed_form_solves':24,
            'total_estimator_fits':15097,'candidate_estimator_failures':0,'initial_diagnostic_pipeline_failures':1},
        'PHASE4_EXECUTION':'NOT_AUTHORIZED','PHASE4_TEST_PERFORMANCE':'SEALED'})
    if not passed:raise RuntimeError('BLOCKED_REVIEW_REQUIRED; no experiment candidate frozen')
    lock_candidate={'status':'LOCK_CANDIDATE_REVIEW_REQUIRED','FINAL_LOCKED':False,
        'study':'C','version':'phase3_development_v1_0','primary_algorithm':'Ridge',
        'dataset':{'path':str(DATA.relative_to(ROOT)),'sha256':sha(DATA),'phase2b_version':'build_v1_1',
            'target':'100*(SOX_last_Close[w]/SOX_last_Close[w-1]-1)','signed':True,'frequency':'nonoverlapping_US_calendar_week'},
        'features':{'C-M0':FEATURES[:10],'C-M1':FEATURES},'selected_algorithms':selected,
        'selection':load(OUT/'config/PHASE3_EXPERIMENT_CONFIG.json'),
        'label_maturity':'strict UTC label_assumed_available_at < origin; target week strictly past; own historical X eligible',
        'publication_and_vintage':'UNVERIFIED; approved assumptions only',
        'environment_lock_sha256':sha(OUT/'config/PHASE3_ENVIRONMENT_LOCK.json'),
        'preprocessing':'origin train-only StandardScaler+intercept OLS/Ridge/ElasticNet; native tree scales; no imputation/PCA/clipping',
        'baselines':['0%','origin/window eligible training Y mean'],
        'future_phase4':{'authorized':False,'test_period_plan':'2021-01-04..2026-10-05 Mondays; raw label limit2026-10-09',
            'procedure':'after separate approval, weekly refit fixed selected configuration using only past matured labels; no adaptive search/selection from test losses',
            'D13_policy_id':'C_D13_CALENDAR_GRID_MBB_v1_0','D13_lock_sha256':sha(D13/'D13_LOCKED_POLICY_v1_0.json'),
            'test_XY_parsing_authorized_now':False,'new_tuning_allowed':False,
            'failure':'stop/review on implementation/estimator error; insufficient eligible sample record paired nonprediction; no candidate substitution'},
        'limitations':['development selection bias','prior D1/W1 period exposure','unknown original posting and vintages','current revised/adjusted source files']}
    save('selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.json',lock_candidate)
    parameterrows=[]
    for algo,r in selected.items():
        for info,m in r['models'].items():parameterrows.append({'algorithm':algo,'information_set':info,'window':r['selected_window'],
            'candidate_id':m['candidate_id'],'parameters':json.dumps(m['hyperparameters'],ensure_ascii=False,separators=(',',':'))})
    paramtable=mdtable(parameterrows,['algorithm','information_set','window','candidate_id','parameters'])
    pairtable=mdtable(pair,['algorithm','selected_window','M0_candidate_id','M1_candidate_id','M0_MAE','M1_MAE','Delta_MAE_dev','M0_RMSE','M1_RMSE','M0_OOS_R2_training_mean','M1_OOS_R2_training_mean','M0_direction_accuracy','M1_direction_accuracy'])
    windowtable=mdtable(windows,['algorithm','information_set','window_type','candidate_id','MAE','RMSE','OOS_R2_training_mean','direction_accuracy'])
    basetable=mdtable(baselines,['window_type','baseline','n','MAE','RMSE','OOS_R2_training_mean','direction_accuracy'])
    ridge=next(r for r in pair if r['algorithm']=='Ridge')
    ridge_mean=next(r for r in baselines if r['window_type']==ridge['selected_window'] and r['baseline']=='training_mean')
    improved=sum(r['Delta_MAE_dev']>0 for r in pair)
    save('selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.md','''# 연구 C Phase4 적용 실험사양 LOCK 후보

상태 **LOCK_CANDIDATE_REVIEW_REQUIRED**. FINAL_LOCKED가 아니다. 사용자의 별도 최종 승인 전 Phase4 미실행.
데이터/변수/라벨/원점/환경/성숙조건/기준모형/실패처리/모델별 고정후보는 동명JSON에 기록한다.

'''+paramtable+'''

주력 Ridge 유지. 알고리즘별 M0의 개발 최적MAE로 창을 선택하고 쌍에 공유했다. 하이퍼파라미터는 정보집합별 같은 후보/규칙/209주로 별도 선택했다. 이 방식은 Phase1 learning.candidate_selection의 per representation에 따른다.

예측원점은 첫 미국 거래일09:00 America/New_York. 과거 행 자신의 역사적 X 가용성과 label_available_at<origin을 UTC 엄격비교한다. Rolling은 원점에서5달력년,260행강제확장없음. 최소156주. StandardScaler는 학습행만,트리는원척도,PCA/보간/clipping없음. origin별 새로 성숙한 Y의 재학습은 가능하지만 시험손실로 설정변경 금지.

별도승인 후 Phase4에서는 기존2021~마지막완료주를 사용하고 D13정책 C_D13_CALENDAR_GRID_MBB_v1_0를 적용한다. 이번에는 시험Y/예측/오차/성과/HAC/Bootstrap/Holm을 열람·계산하지 않았다. 모델실패를 후보대체로 숨기지않으며 오류는중단/검토한다. 부족표본은쌍공동미예측으로기록한다.
''')
    report=f'''# 연구 C Phase3 머신러닝 개발 검증 보고서

**PHASE3_DEVELOPMENT_QC=PASS**, **PHASE3_INDEPENDENT_QC=PASS**, **PHASE3_MODEL_SELECTION=COMPLETED**.
**PHASE3_EXPERIMENT_SPEC=LOCK_CANDIDATE_REVIEW_REQUIRED**. D10=IMPLEMENTATION_PASS,D13=LOCKED_v1_0.
**PHASE4_EXECUTION=NOT_AUTHORIZED**, **PHASE4_TEST_PERFORMANCE=SEALED**.

## 데이터·범위

Y는 SOX 비중첩 미국 달력 주 부호수익률(%)이다. 주 마지막 Close/직전 주 마지막 Close 비율을 사용하며 절댓값으로 바꾸지 않았다. 현재 예측 대상 주 Y는 예측함수에 전달하지 않고 예측 반환 후에만 개발손실을 계산했다.

Phase2B train_dev의 초기308주+개발209주=517개 공통 유효행을 확인했다. 초기 유효시작2011-02-07, 개발2017-01-02~2020-12-28주 209개 원점이다. 첫 원점 실제 예측시각은2017-01-03 09:00 ET다. 입력의 11개 X(B1~B10,F1),SOURCE/시차/라벨성숙/실제게시·빈티지 UNVERIFIED를 유지했다. 원본 X/Y를 재생성하지 않았다.

Expanding 학습308~516주, 최근5달력년 Rolling260~261주다. Rolling은현재 원점의 America/New_York 달력시각에서5년을빼고 학습행자신의예측원점>=경계를적용한다. 여기에 엄격한라벨성숙조건을함께적용한다.260개를맞추려고창을늘리지않았다. 모든418개 원점·창에서최소156주를통과했다. 고정5행purge는사용하지않았다.

## 실행·환경

OLS1,Ridge5,ElasticNet4,RandomForest4,HistGradientBoosting4=18개를C-M0/C-M1,두창,209원점에동등적용했다. **본실험 estimator fit15,048회 완료**, 실패0,미예측0. 모델별72개후보조합의각209개 예측을전부보존했다.

추가 기술smoke10회,최초진단오류전적합3회,독립표본estimator36회는본예산과별도다. 실제estimator총15,097회이며독립OLS/Ridge폐쇄형선형해24개를별도검증했다. 유리한후보만남기는재탐색은없다.

실행환경은기존 .venv_W1의Python/scikit-learn을읽기전용재사용했고패키지변경0이다. 이가상환경이름은이전연구산출물을변경했다는뜻이아니다. Python/NumPy/pandas/SciPy/scikit-learn/threadpoolctl버전과모든명시·기본생성자설정을config/PHASE3_ENVIRONMENT_LOCK.json에기록했다. seed20261016,RF n_jobs1,BLAS/OpenMP1thread, HGB early_stopping=False를유지했다. 선형train-only표준화,트리원척도,intercept,OLS fullrank/n>p+20,비유한검사를적용했다. 음수예측은보존했다.

## 선택 결과와 FGI 개발 추가가치

각창/정보집합에서후보를pooledMAE로고르고각알고리즘M0의최적후보MAE로창을선정했다. 선택창은M0/M1에공유했다. 창동점Expanding,후보동점ID오름차순이다. v1.1 JSON이per representation을명시하므로M0/M1후보를별도선택하는방식에미해결충돌은없다. 기존초안/역사게이트는후속승인과적용범위를구분했다.

MAE/RMSE는%p,방향정확도는0~1비율이다. OOS R²분모는해당origin/창의훈련Y평균예측오차제곱합이다. ΔMAE_dev=M0−M1로양수면FGI추가가개발MAE에유리하다.

{pairtable}

주력Ridge는 **{ridge['selected_window']}**,M0 **{ridge['M0_candidate_id']}**,M1 **{ridge['M1_candidate_id']}**다. MAE {ridge['M0_MAE']:.6f}→{ridge['M1_MAE']:.6f}%p,ΔMAE_dev={ridge['Delta_MAE_dev']:.6f}%p이다. 이결과로주력모형을다른알고리즘으로교체하지않는다.

FGI 추가로 개발 MAE가 낮아진 알고리즘은 {improved}/5개이고, 나머지는 악화됐다. 개선의 일관성이 확인된 결과는 아니다. Ridge M1의 MAE는 같은 Rolling 창의 훈련평균 기준예측({ridge_mean['MAE']:.6f}%p)보다 높고, OOS R²도 {ridge['M1_OOS_R2_training_mean']:.6f}로 음수다. FGI 추가 전후의 작은 차이와 단순 기준예측 대비 성능을 구분해 해석해야 한다. 통계적 유의성은 이번 단계에서 계산하지 않았다.

### 선택한 하이퍼파라미터

{paramtable}

### 두 학습창의 개발 결과

아래는각창/정보집합내최저MAE후보이고,전체72개조합은metrics/PHASE3_CANDIDATE_METRICS.csv에있다.

{windowtable}

### 기준모형

{basetable}

훈련평균은각원점의적격과거Y만사용했다. sign(pred)==sign(Y),sign(0)=0이며0을상승으로임의분류하지않았다. 실제0/예측0개수와비0실제의방향정확도도각메트릭CSV에있다. 기준모형은Holm5종family에추가하지않는다.

## QC·오류 이력

자동QC **{len(checks)}/{len(checks)} PASS**,별도구현독립QC **{independent['count']}/{independent['count']} PASS**. 독립검사는전수418개학습경계/라벨성숙,5687개특징가용성,72개후보지표,모든선형fit스케일러상태,기준예측,paired날짜와선택을재계산했다. 첫·중간·마지막원점60개조합만모형예측을재현했고전15048개를재적합했다고주장하지않는다. OLS/Ridge는독립선형대수,나머지는같은라이브러리별도경로다. 같은Codex작업내독립구현이며외부독립심사가아니다.

첫smoke의Ridge.n_iter_=None 진단값을int로변환하는오류1건이발생했다. 원본코드/원인/3회추가적합이력을logs/INITIAL_*에보존했다. 로그직렬화만수정했고모델/데이터/파라미터변경0이다. 수정후기술smoke10회와미래현재Y/미래X,Y교란5알고리즘검사를통과한뒤전체실행했다. 본실험중후보실패0이며오류를누락하지않았다.

기존보호 **{len(inputs['protected_files'])}개 SHA-256 불변**,RAW/freeze/Phase1/Phase2B/D10/D13변경0. 시험CSV는파싱0이며바이너리해시만검사했다. 전체가용성파일은2021첫행의날짜10byte prefix에서중단하고그행의나머지내용을디코딩/파싱하지않았다. 시험Y값/분포/상관/예측성과를조회하지않았다.

## 해석 및 다음 승인

이209개원점의예측은과거만쓴Walk-forward이나,개발MAE가후보/창선택에쓰였으므로선택모형의성능은독립최종시험성과가아니다. 모든알고리즘·비개선·두창·후보를보존했다. 통계유의성이나연구가설확정을주장하지않는다. 실제HAC/BootstrapCI/Holmp미계산이다.

역사게시시각/최초빈티지UNVERIFIED,현재수정·조정원자료,기존D1/W1의동일시장기간노출한계를유지한다. 보조C-M2~M5나61개후보실험은하지않았다.

선정10개정보집합별설정과Phase4동적재적합절차는selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.json에사용자검토용으로저장했다. 별도최종승인전FINAL_LOCKED/Phase4실행으로전환하지않는다. 연구설계변경이필요한미해결선택규칙은없다. Phase3완료에서중단한다.
'''
    save('reports/PHASE3_REPORT.md',report)
    save('reports/PHASE3_MODEL_COMPARISON_REPORT.md','# Phase3 개발모형 비교\n\n개발209주. MAE/RMSE %p, 방향정확도0~1. 독립최종시험성과아님.\n\n'+pairtable+'\n\n## 두창 전체선택전비교\n\n'+windowtable+'\n\n## 기준예측\n\n'+basetable+'\n\n전72개후보메트릭은metrics/PHASE3_CANDIDATE_METRICS.csv,전15048예측은predictions/PHASE3_ALL_CANDIDATE_PREDICTIONS.csv에보존했다.\n')
    save('reports/PHASE3_SELECTION_REPORT.md','# Phase3 모델 선택 보고\n\n선택완료. Phase4사양은LOCK_CANDIDATE_REVIEW_REQUIRED.\n\n'+paramtable+'\n\n각알고리즘M0최적MAE로창을선택해쌍에공유. 동일창안의후보는정보집합별동등탐색으로선택했다. 미해결충돌없음. 주력Ridge유지. 시험기반선택없음.\n')
    save('reports/PHASE3_HANDOFF.md','''# Phase3 인수인계

개발검증/QC PASS,모델선택COMPLETED,실험사양LOCK_CANDIDATE_REVIEW_REQUIRED. D10 IMPLEMENTATION_PASS,D13 LOCKED_v1_0.
**PHASE4_EXECUTION=NOT_AUTHORIZED, PHASE4_TEST_PERFORMANCE=SEALED**.

우선selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.md와json,PHASE3_SELECTION_REGISTER.json,config의환경·검색·실험설정을검토한다. 사용자최종승인전에시험자료를열거나예측하지않는다. D13정책은수정하지않는다.

예측원점별학습라벨의엄격한성숙조건과학습X의자체역사가용성을유지한다. Phase4가후속승인되면고정된창/후보/전처리로주마다성숙한과거Y를써재적합하는절차이며,이번에하나의전체517주모델을만들어시험예측한것은아니다. 시험오차를보고모델·변수·창·시드를변경하지않는다.

재현코드순서preflight.py→run_walkforward.py→aggregate_select.py→independent_qc.py→finalize.py. 중단재개는run_walkforward.py가원점체크포인트해시·입력/설정/실행코드서명을확인한경우에만허용한다. 최종완료후같은출력을덮어쓰지않는다. 읽기전용봉인검사는independent_qc.py --sealed-check.

기존환경 .venv_W1을패키지변경없이사용했고-B -X utf8을적용했다. 새코드/체크포인트/실행로그/오류기록/지표/예측은이번신규폴더에만있다. 외부심사로독립성을과장하지않는다.
''')
    save('qc/PHASE3_NO_LEAKAGE_AUDIT.md','''# 시점 누출 감사

418개원점·창에서주간과거조건/과거origin/label_available_at<origin을UTC로엄격비교했다. 동시각은제외한다. 원래KRX5행purge승계없음. Rolling5달력년경계를독립계산했다.
5687개학습·개발Xlineage가각행자신의예측원점전에가정/실제이용가능해야한다. publication/vintage UNVERIFIED는그대로이며실제PIT가증명됐다는주장아님.
기술검사에서첫원점5알고리즘의현재Y및미래X/Y교란후예측불변을확인했다. 주실행fit함수에현재Y를전달하지않았다. 전체선형fit의스케일러평균/분산/n은각학습행으로전수검증했다. 트리원척도,HGB early_stopping=False,공통표본규칙우회없음,PCA/보간/clipping없음.
최종시험X/Y/손실/성과/HAC/Bootstrap/Holm접근0. 독립검사는전수경계/지표와표본60조합재추정범위를구별한다.
''')
    save('qc/PHASE3_TEST_SEAL_AUDIT.md','''# 최종 시험 봉인 감사

data/sealed_test/*.csv는바이너리SHA-256만계산했고CSV파싱/문자열내용조회/모델fit/예측/기술통계/성과계산0이다.
실제주력X/Y는data/train_dev/WEEKLY_CORE_COMBINED.csv만읽었다. 원천가용성혼합로그는binary날짜prefix를검사해2021-01-04부터나머지내용을디코딩/파싱하지않았다. 새lineage사본에는2011~2020만있다.
입출력해시와접근범위는inputs/PHASE3_INPUT_MANIFEST.json 및 PHASE3_DATA_ACCESS_AUDIT.json에기록한다. 이는애플리케이션경로제한/감사이며OS권한차단이나암호화보장을뜻하지않는다. Phase4는NOT_AUTHORIZED,시험성과는SEALED다.
''')
    save('README.md','''# 연구 C Phase3 개발 Walk-forward v1.0

개발2017~2020년209개원점,5알고리즘18후보,2정보집합2창,15048본실험fit완료.
결과보고서: [PHASE3_REPORT.md](reports/PHASE3_REPORT.md)
모형비교: [PHASE3_MODEL_COMPARISON_REPORT.md](reports/PHASE3_MODEL_COMPARISON_REPORT.md)
사양후보: [PHASE3_EXPERIMENT_LOCK_CANDIDATE.md](selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.md)
독립QC: [PHASE3_INDEPENDENT_QC.md](qc/PHASE3_INDEPENDENT_QC.md)

설정은사용자검토대기 LOCK_CANDIDATE_REVIEW_REQUIRED. Phase4시험실행미승인/시험성과SEALED.
''')
    save('logs/PHASE3_WORK_LOG.md','''# Phase3 작업 이력

필수문서열람/보호해시/GateA/라이브러리기본설정확인후실행. 기존 .venv_W1 패키지변경없음.
첫smoke진단직렬화오류1건을기록하고None보존으로수정. 원본실패코드/3추가적합이력보존. 후보·시드·모델설정변경없음.
기술smoke10회/미래교란통과후209원점72적합씩실행. 원점마다해시·코드/입력서명포함체크포인트기록. 본실험15048회완료,후보실패0.
72개조합메트릭/창·후보선정/기준예측/paired결과보존. 첫중간마지막60개독립수치검증(36estimator+24선형해),전수경계/스케일러/지표재검사.
입력보호1594개해시불변. 시험내용파싱0. 실제HAC/Bootstrap/Holm미실행. 후속Phase4미승인에서종료.
''')
    files=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file()]
    save('qc/PHASE3_OUTPUT_MANIFEST.json',{'files':files,'file_count':len(files),'created_at_utc':datetime.now(UTC).isoformat(),
        'excludes':['qc/PHASE3_OUTPUT_MANIFEST.json','qc/PHASE3_OUTPUT_MANIFEST.sha256']})
    save('qc/PHASE3_OUTPUT_MANIFEST.sha256',sha(OUT/'qc/PHASE3_OUTPUT_MANIFEST.json')+'  PHASE3_OUTPUT_MANIFEST.json\n')
    print({'phase3':'PASS','candidate_fits':15048,'QC':len(checks),'independent_QC':independent['count'],
        'model_selection':'COMPLETED','experiment_spec':'LOCK_CANDIDATE_REVIEW_REQUIRED','protected':len(inputs['protected_files']),'hashed_outputs':len(files)})

if __name__=='__main__':main()
