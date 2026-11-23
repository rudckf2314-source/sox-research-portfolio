"""Write diagnosis and a bounded, unexecuted experiment plan from stored diagnostics."""
from pathlib import Path
import json,hashlib,ast
import pandas as pd,numpy as np
O=Path(__file__).resolve().parent;D=O.parent;ROOT=D.parent
def write(n,s):(O/n).write_text(s,encoding='utf-8')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
s=json.loads((O/'DIAGNOSTIC_SUMMARY.json').read_text(encoding='utf-8'));assert not s['failed'],s['failed']
p=pd.read_csv(O/'PREDICTION_DIAGNOSTICS.csv');pooled=p[(p.period=='ALL')&(p.group!='BASELINE')&(~p.is_M3_alias)];b=s['best_1D_accuracy']

# Date discrepancies are evidence of disagreement, not proof of holidays or vendor error.
date_sets={}
for code in ['13','23']:
    path=next((ROOT/'data/raw').glob(f'{code}_*/*RAW*.csv'));x=pd.read_csv(path,comment='#');date_sets[code]=set(x.loc[x.Date.between('2011-01-01','2020-12-31'),'Date'])
date_rows=[{'date':date,'TWII_13_present':date in date_sets['13'],'TWSE_sector_23_present':date in date_sets['23'],'cause':'UNRESOLVED; check native session/calendar/vendor transformation','is_weekend':pd.Timestamp(date).dayofweek>=5} for date in sorted(date_sets['13']^date_sets['23'])]
pd.DataFrame(date_rows).to_csv(O/'ASIA_SESSION_DISCREPANCIES.csv',index=False,encoding='utf-8-sig')

write('CURRENT_STATE.md','''# 연구 D 현재 상태
## 이번 범위

실제 `C:\\fgi_pilot\\research_D` 존재를 확인했다. 새 폴더 `research_D/accuracy_improvement_v1`은 기존에 없었으며, 이번 결과는 이 폴더에만 작성했다. 범위는 **기존 예측 진단과 개선 실험계획**이다. 모델 학습·새 예측 생성·임곗값 탐색·2021년 이후 성능평가는 0회다. 과거 지시문은 근거로만 읽었다.

## 변하지 않는 Y와 예측시점

- 1D: `100*(오늘 SOX Close/직전 실제 미국 거래일 Close-1)>0`이면 1, 아니면 0. 해당 미국 실제 거래일 09:00 America/New_York.
- 1W: `100*(이번 주 마지막 실제 미국 거래일 Close/이전 완료 주 마지막 Close-1)>0`이면 1, 아니면 0. 이번 주 첫 실제 미국 거래일 09:00 America/New_York.
- 1W는 미국 달력주별 비중첩이다. 휴장 주의 월요일을 가짜 origin으로 만들지 않는다. 오늘 정규장 시가는 09:30이므로 09:00 X에 넣을 수 없다.
- SOX Close로 1D·1W Y를 직접 재계산해 저장 라벨과 전수 대조했다. 보합은 0이다.
- 이번 개선계획은 1D 우선, 1W 실행계획은 보류·별도다.

## 이미 끝난 실험

|실험|설계|실제 수행|
|---|---|---|
|최초 Phase 0~2|RAW47종/CSV48개 감사. 조건부 적격22종→86특징. M0 5/M1 53/M2 86/M3=M2/M4 학습 내부 선택/산업대리 제거68. 2011~2016 초기, 2017~2020 개발. 연간 expanding.|Logistic/Ridge Classifier/RF/XGBoost/LightGBM. 200 외부 모델, 내부 기록998개. 내부 C·복잡도 일부 2설정과 threshold .45/.5/.55 선택. CatBoost 미설치.|
|development_revision_v1|1D 동일1,007일. M0/M1/M2. A 기존지연·연간·확장, B 직전종가·연간·확장, C 직전종가·월간·확장, D 직전종가·월간·최근3년.|Logistic C1, Ridge 회귀 alpha100, XGB 분류/회귀 고정. 1,248 외부 모델. 분류 threshold .5, 회귀 예측수익률>0.|

최근 실험은 시장가격 11종 53특징만 1세션 정렬로 바꿨고, 위험·심리33특징은 2세션 가정을 유지했다. 아시아 **같은 날짜** 종가를 쓰지는 않았다. 최초 실험과 최근 비교는 튜닝·threshold 규칙이 달라 같은 설정이라고 합쳐서는 안 된다. M3은 중복 alias이며 독립 모델 증거가 아니다.

최초 개발 최고: 1D 56.01%(기준55.91%), 1W 62.68%(기준61.72%). 최근 1D 최고: 최근3년·월별·M0 Logistic 56.31%(+0.3972%p). 모두 개발 후보선정 성적이다.

## 이번에 직접 읽고 대조한 근거

- 최초: `code/prepare.py`, `code/experiment.py`, `PHASE2_EXPERIMENT_PLAN.md`, `TARGET_SPEC_1D_1W.md`, `FEATURE_DICTIONARY.csv`, 기존 완료·QC 보고서, 저장 예측·fold 기록.
- 수정 비교: `development_revision_v1/code/run_comparison.py`, `code/review_comparison.py`, 설계·config·성과·저장 예측·fold 기록.
- 저장 예측으로 전체128시리즈(기준·alias 포함), pooled와4개 연도별640행을 독립 재계산했다. M3 alias를 제외한 모델 후보는 1D 분류49·회귀24, 1W 분류25개다.
- 실제 상승비율 기준 q는 각 외부 fold의 실제 성숙 학습 Y로 다시 계산했다. 저장 Majority 확률과 일치했다.
- 기존 모델은 classes_ 메타데이터만 읽었다. 새 학습이나 predict 호출은 하지 않았다.
- 기존 완료 스크립트의 main, fit, 평가 실행을 재실행하지 않았다.

## 기존 QC와 이번 직접 확인을 구별

기존 QC 기록은 최초634/634, 수정3,926/3,926 PASS이며 역사적 정보가용성 한계가 명시돼 있다. 이번에는 라벨·저장예측·기준확률·날짜·성숙라벨·classes_를 별도 확인했다. 상세는 DIRECT_AUDIT_CHECKS.json, TRAIN_LABEL_MATURITY_AUDIT.csv, POSITIVE_CLASS_METADATA.csv에 있다. 과거 실제 벤더 전달시각까지 이번에 입증한 것은 아니다.

기존 연구 C 백업은 FAIL 상태이며 이를 바꾸지 않는다. D1/W1/C/공통RAW/기존D/매니페스트/archives 수정·삭제 금지. 패키지 설치·신규 금융자료 수집·Phase3·최종 시험은 미실행이다. 기존 봉인 이후 추가된 HANDOFF와 새 하위 폴더가 기존 snapshot manifest에 없다는 사실만으로 오류라고 판단하지 않는다.
''')

diag='''# 1단계 예측 진단

## ① 확인된 문제와 직접 확인한 정상 항목

Accuracy 자체의 산출 오류·Y 반전·확률 열 반전이 원인이라는 증거는 발견되지 않았다. 저장된 검증 예측을 사용했고, threshold를 사후 최적화하지 않았다.

'''
diag+=f'- 전체 {s["candidate_series_including_baselines_aliases"]}개 예측 시리즈, {s["diagnostic_rows"]}개 pooled/연도별 행을 재계산했다. 기존 모델 {s["model_class_metadata_checked"]}개 classes_가 `[0,1]`이므로 코드의 `predict_proba[:,1]`은 상승 확률 열이다. 직접 검사 {s["direct_checks"]}건 모두 PASS.\n'
diag+='''- 각 후보를 해당 실험·설정·지평의 Majority와 **날짜로 일치시켜** 비교했고, 정렬 후 라벨도 일치했다. 회귀와 TrainingMeanReturn/ZeroReturn의 수익률 score에는 Brier/Log loss/확률 분포를 계산하지 않았다. 회귀 AUC는 별도 `regression_score_auc`다.
- fold 기록을 실제 데이터의 가용 라벨로 재구성했다. 학습 수·마지막 학습일·마지막 라벨 종료·origin 이전 성숙을 확인했다. 실제 벤더 시각이나 과거 빈티지까지 검증한 것은 아니다.
- 기존 평가지표와 이번 재계산은 Accuracy 정의가 같다. 기존 수정 평가에는 Log loss가 빠져 있어 이번에 새로 계산했다. 최초 코드에는 LogLoss가 있었다.

### 최고 Accuracy 후보도 약한 판별력

'''
diag+=f'''최근 D/M0 Logistic: Accuracy {100*b['accuracy']:.2f}% 대 기준 {100*b['same_date_majority_accuracy']:.2f}%, 개선 {b['accuracy_gain_pp']:+.4f}%p. 비상승444개 중22개, 상승563개 중545개를 맞혔다. 상승예측 비중 {100*b['predicted_up_fraction']:.2f}%, 비상승 Recall {100*b['recall_nonup']:.2f}%, BA {100*b['balanced_accuracy']:.2f}%, MCC {b['MCC']:.4f}다. 기준보다4개 더 맞혔지만 잘 구분하는 모델로 보기 어렵다.

|기간|Accuracy|기준 대비 %p|AUC|Brier / 학습비율기준|Log loss / 학습비율기준|
|---|---:|---:|---:|---:|---:|
'''
bestrows=p[(p.study==b['study'])&(p.scenario==b['scenario'])&(p.group==b['group'])&(p.algorithm==b['algorithm'])]
for r in bestrows.itertuples():diag+=f'|{r.period}|{100*r.accuracy:.2f}%|{r.accuracy_gain_pp:+.2f}|{r.probability_auc:.4f}|{r.brier:.6f} / {r.training_frequency_brier:.6f}|{r.log_loss:.6f} / {r.training_frequency_log_loss:.6f}|\n'
diag+='''
연도 AUC는 그 해 안의 순위이고 pooled AUC는 서로 다른 연도 간 확률 순위까지 포함한다. 후보를 섞어 AUC를 계산하지 않았다. pooled에만 의존하지 않도록 같은 연도 양성·음성 pair 수로 가중한 `year_stratified_auc_pair_weighted`도 제공했다. 이는 단순 연도 평균이나 pooled AUC와 다르다. 월별 학습비율 q도 변하므로 기준 AUC를 무조건0.5로 가정하지 않았다.

### 확률 성능과 실제 클래스별 분포

'''
diag+=f'''M3 중복을 제외한 1D 분류49후보 중 pooled Brier가 q보다 좋은 후보는{s['classifiers_1D_brier_better_than_train_frequency']}개, Log loss도{s['classifiers_1D_logloss_better_than_train_frequency']}개였다. 둘 다 최근 C/M0 Logistic으로 Accuracy56.01%, AUC0.4881, Brier0.246532 대 q0.246874, Log loss0.686186 대 q0.686885다. 확률 손실 개선이 곧 순위·Accuracy의 확실한 개선은 아니다.

1D 분류49후보 중 pooled AUC>0.5는{s['classifiers_1D_auc_above_05']}개였다. AUC 최고는 최근 B/M1 Logistic 0.5344이지만 Accuracy54.52%, Brier0.254182 대 q0.246906이었다. **모든 후보가 같은 문제를 보인다고 일반화하지 않는다.** 높은 Accuracy 후보와 상대적으로 높은 AUC 후보가 다르며 둘 다 재검증이 필요하다.

최고 Accuracy 후보의 실제 비상승/상승 확률 평균은 각각 {b['actual_0_p_mean']:.6f}/{b['actual_1_p_mean']:.6f}로 거의 같다. 비상승 확률의 중앙값 {b['actual_0_p_q50']:.6f}, 상승 중앙값 {b['actual_1_p_q50']:.6f}다. 전체의 {100*b['probability_04_to_06_fraction']:.2f}%가0.4~0.6에 있고, 0.5±0.05에는 {100*b['probability_near_05_fraction']:.2f}%가 있다. 좁고 겹치는 분포에서0.5 판정이 거의 상승으로 이어진다.

'''
diag+='''PREDICTION_DIAGNOSTICS.csv에는 모든 후보·연도별 n, 혼동행렬, 두 Recall, BA/MCC, Accuracy와 동일 날짜 기준 대비 %p, 확률 AUC/Brier/Log loss, q 대비 확률 손실 차이, 실제 클래스별 평균·표준편차·5/25/50/75/95% quantile, 확률 집중률이 있다. PROBABILITY_DISTRIBUTIONS.csv에는 고정 bin별 실제 클래스 조건부 분포가 있다. q는 `RECOMPUTED_TRAINING_BASELINES.csv`에서 원점별로 확인할 수 있다.

### 아시아 자료의 별도 확인 사항

1D 검증일1,007개 중 당일 원천 행은 한국01 951개, 대만13 943개, 대만23 944개다. 나머지를 모두 휴장이라고 단정할 수 없다. 대만13/23은 2011~2020 날짜 집합도 다르다. 13에만 있는2014-07-23/2016-07-08, 23에만 있는여러 보충 토요일과2019-09-09 등을 ASIA_SESSION_DISCREPANCIES.csv에 기록했다. 이것은 **일자 불일치의 확인**이며 특정 공급원 오류·휴장 원인을 확정한 것은 아니다. 달력 gate를 먼저 통과해야 한다.

## ② 아직 검증되지 않은 원인 가설

1. **새 정보 부족:** 당일 아시아 관측을 제외한 X가 미국09시 이전의 밤사이 정보를 충분히 반영하지 못했을 수 있다. 실제로 당일 정렬이 Accuracy를 높이는지는 미실험이다.
2. **약한 신호 대비 과도한 적합 또는 확률 과장:** 대부분 후보의 확률 손실이 학습비율 기준보다 나쁘다. 이 사실만으로 과적합이 원인이라고 확정할 수는 없지만 더 강한 규제를 제한적으로 시험할 이유가 된다.
3. **결정경계와 순위의 불일치:** M1 Logistic은 최고 Accuracy 모델보다 AUC가 높다. 학습 내부 threshold 선택이 도움이 될 수 있으나, 실제 signal이 약하면 threshold 조정만으로 해결되지 않는다.
4. **시기별 관계 변화:** 최고 Accuracy 모델의 개선은2020년에 집중된다. 시장상태·재학습창이 원인이라는 인과 증거는 아니며, 특정 연도에만 맞춘 선택 위험을 고려해야 한다.
5. **표현의 한계:** 트리에서 상대강도·제한된 상호작용이 약한 관계를 표현하기 쉬울 수 있다. 새 원천정보가 생기는 것은 아니며 유리한 결과를 보장하지 않는다.

## 1W 분리

최초1W 최고는 산업대리 제거 XGBoost62.68%, 기준61.72%, AUC0.4911, Brier0.241826 대 q0.238887이다.209주라 불확실성이 크다. 저장된1W 전체 후보·연도도 이번 CSV에 포함했지만, 최근 수정 비교는1D뿐이며 이번1D 실행계획과 학습 예산을 공유하지 않는다.

## 문헌의 역할

추가로 원문 세 편의 관련 구간을 확인했다(SOURCES.md). 기술적 표현은 월간 미국 주식 프리미엄 연구와의 차이를 명시했고, cost-sensitive 이론은 Recall과Accuracy 목표의 차이를 설명하는 근거로만 사용했다. 반복 탐색 문헌은 후보수·실패 보존과 선택편향 경고에 연결했다. 논문의 적중률을 SOX 기대값으로 가져오거나 CSCV를 시간순 검증의 대체로 실행하지 않았다.
'''
write('DIAGNOSIS.md',diag)

write('CHANGE_PLAN.md','''# 개선 후보와 중복 제거

## 고정 목표와 대조

주목표는 **동일 날짜 학습 다수클래스 기준 대비 Accuracy 개선폭(%p)**이다. 1D Y와 미국 실제 거래일09:00 origin을 유지한다. 하락 Recall·BA를 높이는 것만으로 성공이라 하지 않는다. 기본 대조 R0는 최근 C/M1 Logistic(C1, weight없음, threshold0.5), 월별 expanding,53컬럼이다. 최근 최고 모델을 다시 고른 것이 아니라 아시아 원천과 SOX/NDX/SPX가 이미 있어 변화 요인을 나누기 쉬운 고정 대조를 택했다. 이 선택도 개발자료 노출 이후의 연구자 선택임을 명시한다.

## A. 기존 아시아 RAW 당일 정렬: 우선, 조건부

01 KODEX 반도체 ETF,13 TWII,23 TWSE 반도체지수의 기존13특징(5+5+3)을 **추가하지 않고** 원천 event 정렬만 바꾼다. 미국의 당일 가격은 넣지 않는다. TSM ADR14는 미국 시장 종목이므로 아시아 당일 규칙을 적용하지 않는다.

|시장|정규 마감 현지시각|미 동부 여름/겨울|확인 범위|
|---|---|---|---|
|한국|15:30 Asia/Seoul|02:30 EDT / 01:30 EST|KRX 공식 가이드. 2016-08-01 거래시간30분 연장 사실은 정부 자료 확인. 전기간 특수일 전체는 미확인.|
|대만|13:30 Asia/Taipei|01:30 EDT / 00:30 EST|TWSE 공식 가이드. 일부 지수 산출 종료는 주식시장 마감과 다를 수 있어 원천별 확인 필요.|

한국의2016-08-01 이전은 정규15:00 정책 이력을 확인해야 하며, 현재시각15:30을2011년부터 소급하지 않는다. 한국 수능일·연초특례, 대만 태풍·보충토요일 등 예외를 확인한다. 전기간 실제 전달기록이 없다는 한계는 별도다. 시장 마감시각상 미국09시 전인 것과 벤더가 당시 값을 공급했다는 것은 다르다. 근거는 SOURCES.md.

### 실제 RAW를 이용한 예시

- 한국2017-07-10: 현재 규칙은2017-07-07까지. 제안은7/10 15:30 KST 종가(02:30 EDT), 보수적2시간 buffer 후04:30 EDT부터 이용 가능하다고 가정한다.09시 전이다.
- 한국2017-12-04: 현재12/01. 제안12/04 15:30 KST=01:30 EST, buffer 후03:30 EST.
- 대만2017-07-10: 당일13:30 Taipei=01:30 EDT, buffer 후03:30 EDT. 현재 원천일 이전 날짜를 쓰는 규칙과 구별한다.
- 대만2018-10-10: 공식 휴장 공지가 확인된다. 오늘 종가를 만들지 않고 이전 적격 관측을 유지하며 source_date·age·fallback을 기록한다.
- 나머지 상세 예시는 ASIA_ALIGNMENT_EXAMPLES.csv에 있다.2020-12-03 한국16:30 예시는 **특수일 시각의 원문 추가 확인이 필요한 가정 예시**이며 검증 완료 사실로 쓰지 않는다.

### 학습 전에 통과해야 할 gate

1. 현지 세션·휴장/결측·마감/지수 확정시각·timezone을 원천별로 대조한다. 관측일 부재만으로 휴장이라고 하지 않는다. 미국 BDay나 월~금 가정으로 대만 보충 토요일을 삭제하지 않는다.
2. TWII13과 공식 관측23의 일자 불일치를 날짜별로 검토한다. 기존 RAW는 고치지 않는다. 최신행뿐 아니라 ret5/ret20/vol20/MA20 계산창에 들어가는 원천 관측도 확인한다. 불일치 원인을 입증하지 못한 계산창의 same-day 특징은 채택하지 않고 원래 대조의 과거값으로 fallback한다. 불명 날짜를 몰래 삭제해 native rolling 정의까지 바꾸지 않는다.
3. event의 실제 시각 또는 명시한 `현지 마감+2시간` 조건부 시각이 origin 이하인지 확인한다. source_observation_date, close_at_local, available_at_ET, origin_ET, 실제/가정 구분을 저장한다.
4. 휴장·검증 불가에는 기존 정책으로 fallback,10달력일 staleness 초과는 결측. 추가 missing flag를 이 단독 비교에서 넣지 않는다. 평가일1,007개를 임의 교집합으로 줄이지 않는다.
5. 한국의 전기간 특수일 및 대만 모든 지수 확정시각은 아직 전수 입증하지 못했다. 이 gate를 학습 전에 문서화할 수 없으면 A1을 **미실행**으로 남긴다. 핵심 Y에 문제는 발견되지 않았으므로 나머지 대조까지 자동 중단할 이유는 아니다.

## B. 기존과 다른 소수 표현: 후순위 별도 비교

특징 사전86개와 두 생성 코드를 대조했다. 아래 조합 컬럼은 없지만 구성 요소는 M1 안에 이미 있다. 따라서 새 정보 원천이 아니라 **표현 변경**이다.

|후보|산식·컬럼|판정|
|---|---|---|
|SOX/SPX 상대강도5|`100*((1+s02_ret5/100)/(1+s04_ret5/100)-1)`|파생 비율 표현 신규. 같은 as-of 미국 종가일로 맞춘다.|
|SOX-NDX 상대수익률5|`s02_ret5-s12_ret5`|컬럼은 신규지만 선형결합. 선형모델에 독립정보를 추가했다고 해석하면 안 된다.|
|추세방향×변동성|`sign(s02_ma20_gap)*s02_vol20`|새 상호작용 표현. 상태 경계0을 고정하고 별도 최적화하지 않는다.|
|NYSE 신고가/신저가 정규화|`(high-low)/(high+low)` = s05_level|이미 있음. 신규 후보 제외.|
|상승/하락 거래량 정규화|`(adv-dec)/(adv+dec)` = s06_level|이미 있음. 신규 후보 제외.|
|1/5/20일 모멘텀,20일 변동성,MA20 괴리|사전의 ret/vol20/ma20_gap|이미 있음. 그대로 다시 신규 실험이라고 부르지 않는다.|

B1은 상대강도2개만 M1에 추가(55개), B2는 상호작용1개만 추가(54개). 둘을 합치지 않고 A1 당일 정렬도 섞지 않는다. 부모는 기존 C/M1 XGBClassifier의100trees/depth2 고정이다. 선형모델에 중복 차분을 추가해 얻은 결과를 새 시장정보 효과라 하지 않는다. 기술적 표현의 일반적 동기는 Neely 등 원문에서 확인했으나 이 정확한 산식의 SOX 일간 효과를 입증한 논문으로 인용하지 않는다.

## C. 학습·분류 기준

- **C1 규제:** 기존 월간 C1 Logistic에서 C={0.01,0.1,1}만 비교. 확률 손실이 q보다 나쁜 후보가 많아 더 강한 규제가 도움이 되는지 확인할 이유가 있다. C를 낮추면 규제가 강해진다. 최초 연간 C0.1/1 선택과 달리 월간 내부 선택 정책의 비교이며 완전한 신규 아이디어라고 하지 않는다.
- **T1 threshold:** 기존 월간 M1 Logistic의 C1·weight없음을 고정하고 {.45,.50,.55}만 내부 선택. 최초 연간 실험에서도 쓴 grid지만 최근 월간은0.5 고정이므로 동일한 월간 정책은 아직 비교하지 않았다. 회귀 threshold는 이번에 변경하지 않는다.
- **클래스 가중치:** 이번 우선 실행안에서는 보류.56/44 비율만으로 severe imbalance라고 단정할 수 없고, balanced weighting은 Recall/BA와Accuracy의 목적을 바꿀 수 있다. Elkan의 cost-sensitive 이론도 Accuracy 향상을 보장하지 않는다.
- **트리 복잡도:** 우선안에서 보류. 최초에depth1/2 등 제한적 변경을 이미 일부 했고, 현재 약한 확률 성능만으로 더 깊은 트리를 우선할 근거가 부족하다. B1/B2에서는depth2를 고정해 표현만 바꾼다.

분류 Calibration은 손실 진단상 후속 검토할 수 있으나, 지금은 임곗값·규제와 동시에 새 학습 축으로 추가하지 않는다. 확률 손실 개선 자체를 Accuracy 개선으로 오인하지 않는다.
''')

write('EXPERIMENT_PLAN.md','''# Accuracy 개선 실험계획 — 미실행

**상태: PLAN_ONLY / 새 모델 학습0회 / 현재 요청 종료 시 실행하지 않음.** 계획을 보고한 뒤 멈춘다. 이번 문서는 Phase3나 최종 시험 승인·설계 잠금이 아니다.

## 목표·날짜·대조 고정

- 1D 주목표: `100*(후보 Accuracy − 동일 날짜·해당 외부 학습구간 Majority Accuracy)` %p.
- 수정 비교와 같은2017~2020년1,007일을 외부 개발 평가로 유지. 초기2011~2016. Y와09:00 ET origin 불변.2021년 이후는 평가하지 않는다.
- R0: 기존 C_latest_monthly_expanding / M1 / LogisticClassifier.53특징, expanding, 월별48외부 fold, C1·class_weight=None·threshold0.5. 기존48개 외부모델과 저장 확률·클래스를 재사용한다.
- 학습 상승비율 q를 확률로 내는 기준의 Brier/Log loss와, 직전 완료 방향 Momentum도 보조 대조로 유지한다. 실제 검증기간 상승비율을 미리 학습확률로 쓰지 않는다.
- 기존 전체73개 1D 모델 후보(분류49·회귀24)의 재학습은 하지 않는다. 최종 최고값·확률 지표에 맞춰 날짜를 바꾸거나 후보를 계속 늘리지 않는다.

## 시간순 내부 검증

외부는2017-01~2020-12의48개월이다. 각 외부 월 첫 실제 미국 거래일09:00 이전에 성숙한 과거라벨만 학습한다. 학습창은expanding으로 고정해 최근3년창 변경을 또 섞지 않는다.

각 월의 달력상 첫날을 T라 할 때, 내부 검증블록 두 개를 `[T-12개월,T-6개월)`, `[T-6개월,T)`로 고정한다. 각 블록 첫 실제 거래일09시 이전에 성숙한 라벨로만 그 내부모델을 학습하고, 해당6개월을 예측한다. 내부 검증 끝부분도 외부origin 전에 라벨이 성숙한 행만 사용한다. 첫2017-01 fold의 내부는2016년 상·하반기다. 단일 미래검증으로 shuffle하지 않는다.

대치·스케일·상호작용에 필요한 학습 파라미터는 해당 내부 학습부분에만 fit한다. 이번 후보의sign 경계0과 상대강도 산식은 고정이며 전체자료 PCA·변수선택·전체기간quantile은 사용하지 않는다. 내부 최소 학습500일·두 클래스, 블록별 최소80성숙 라벨을 요구한다. 미달 시 설정 선택을 중단하고 R0로 fallback·건수를 보고한다.

선정 기준은 두 내부블록 pooled Accuracy(표본수 가중)다. 동률은 원래 설정(C1 또는 threshold0.5), 그 다음 강한 규제/0.5에 가까운 threshold, 마지막 작은 수치 순이다. 각 후보는 외부 Y를 보지 않고 확정한 뒤 외부 월 전체를 예측한다. 별도6개월모델이므로 기존 외부 **월간** 예측을 내부6개월모델 예측이라고 대체하지 않는다.

## 우선 실행 패키지: 원인 축을 분리한3개 후보 정책

|ID|바꾸는 것|고정하는 것|내부 선택|새 학습 상한|
|---|---|---|---|---:|
|R0|없음; 기존 외부 결과 재사용|M1·C1·weight없음·threshold0.5·월별expanding|내부96블록에 필요한 고유54모델 중42개 재사용|12|
|A1|아시아13특징의 event 정렬만 교체|53컬럼·C1·threshold0.5·학습창/갱신 불변|공표시각/세션 gate와 고정표현 점검; 하이퍼파라미터 선택 없음|내부·외부 공통모델 캐시:60|
|C1|Logistic 규제 C만 선택|기존 M1 정렬·weight없음·threshold0.5|C={.01,.1,1}; C1 내부는R0 재사용|2대안×54내부모델 +최대6추가외부 =114|
|T1|분류 threshold만 선택|기존 M1 정렬·C1·weight없음|{.45,.50,.55}; R0 내부확률 재사용|0|
|합계|3개 후보 정책+R0 대조|정보/표현/학습 설정 동시 변경 없음||**최대186회**|

### 재활용과 학습 횟수 산식

내부 검증은96블록이지만 학습 origin은2016-01~2020-06의 **54개 고유 월**이다. 같은 학습범위·X·Y·모델이면 내부와 외부에서 다시 fit하지 않는다. R0는2017-01~2020-06의42개 기존 월간 모델을 재사용하고2016년12개만 새로 학습한다. 기존 모델로 새6개월 블록을 예측할 수 있으므로 기존 **월별 예측값**을6개월 고정모델의 예측인 것처럼 이어붙이지 않는다.

A1은54내부 origin과48외부 origin의 합집합이2016-01~2020-12,60개월이라60fit이다. C의두 대안은54개 내부 origin마다각1회로108fit이다.42개 외부 origin의 해당 모델은 내부·외부 공통 캐시로 해결되며,2020-07~12의최대6개 선택된외부모델만 추가해114fit이다. 다른 C 후보를 외부월에서도 모두 새로 fit하는 일은 하지 않는다. T1은R0 내부확률에서 threshold를 선택하고 기존외부 확률에 적용하므로 추가fit0회다. 현재 이 선택·예측은 모두 미실행이다.

캐시 key는 원점·실제 성숙 학습행/라벨·특징정렬정책·입력버전·전처리·전체모델파라미터·seed·환경을 포함한다. 기존 모델의 학습범위/파라미터/입력계보와 재사용 적합성을 먼저 대조한다. 저장 CSV의 float 직렬화 오차는 기존 재현QC의 수치허용 범위를 명시해서 확인한다. 미래라벨을 학습한 모델이나 다른 특징정렬 모델을 대조로 재사용하지 않는다. 캐시 일치성을 입증하지 못하면186회를 넘어 자동 재학습하지 않고 중단해 예산을 다시 보고한다.

A1은 CHANGE_PLAN의 시각·원천 gate가 먼저다. gate를 못 통과하면 A1은0회로 보류, R0/C1/T1만 **최대126회**다. 정보 부족을 q나 Y에서 역으로 추정해 당일자료를 채택하지 않는다.

A1 결과를 보고 C1/T1에 자동 결합하지 않는다. C1과T1도 결합한 최종 최적모형을 이번 패키지에서 만들지 않는다. 각 선택정책의 전체 외부 성적을 보고하며, 가장 잘 나온 정책만 남기지 않는다.

## 후순위 표현 비교: 이번 우선 실행과 별도 검토

부모 R0_X는 기존 C/M1 XGBClassifier(depth2 등 기존값 고정)다. 외부48모델은 재사용한다. B1은 상대강도2개만 추가, B2는추세×변동성1개만 추가한다. 두 표현을 합치거나 A1/C1/T1을 함께 적용하지 않는다.

|항목|새 내부 fit|새 외부 fit|합계 상한|
|---|---:|---:|---:|
|R0_X 내부 대조|기존42개 재사용, 부족한12개만 새 fit|기존48개 재사용|12|
|B1 상대강도2개|54고유 내부모델|이와 공통42개 재사용+6추가|60|
|B2 상호작용1개|54고유 내부모델|이와 공통42개 재사용+6추가|60|
|합계|||**132회**|

이 패키지는 현재 우선186회에 자동 추가하지 않는다. 두 패키지를 모두 별도 실행하기로 정하면 합계상한318회다. 동일 캐시 검증 규칙을 적용한다. 클래스 가중·트리깊이·추가모델·신규수집은 이번 계획의 학습 예산에 넣지 않았으며 자동 실행하지 않는다.

## 보고와 중단 규칙

1. 원본 hash/기존seal 불일치, Y·확률 열·날짜·라벨 성숙 오류, X 가용시점 위반이 발견되면 관련 비교를 학습 전에 중단한다. 기존 RAW/연구를 고치지 않는다.
2. A1 달력·마감/전달 가정이 확인되지 않은 행은 원래 과거정보로 fallback한다. 같은 날짜 정보로 바뀐 행·fallback 비율을 보고한다. 적격 same-day가 없어 대조와 동일하면 A1을 미실행 중복으로 종료한다.
3. 각 fit 시도와 실패·미예측을 보존한다. 외부1,007일이 완비되지 않으면 성공 판정을 하지 않으며, 공통날짜 부가표와 누락사유를 별도로 공개한다. 전역 교집합으로 주평가 날짜를 조용히 바꾸지 않는다.
4. 외부 Accuracy 개선이0이하인 결과도 보존하고 이 계획의 후보를 추가하지 않는다. Recall/BA만 좋아진 결과를 주목표 성공으로 판정하지 않는다.
5. 후보별 pooled·연도별 Accuracy/기준대비%p, 양쪽Recall/BA/MCC, AUC/Brier/Log loss/q비교, 확률분포, 상승예측비중을 함께 보고한다.
6. 동일날짜 정오차 차이에20세션 moving-block bootstrap2,000회·seed20261019·percentile95% CI를 사전에 고정한다. Majority 대비와 R0 대비를 모두 공개하고 선택 편향이 보정된 최종 검정으로 부르지 않는다.
7. 2017~2020은 이미 반복 노출된 개발자료다. 내부 시계열 검증으로 외부월 Y의 직접 누출을 막아도 연구자·다수후보 선택편향은 남는다. 후보수·모든 실패를 기록하고 사후최고값을 독립 검증 성능으로 보고하지 않는다.

## 1W 별도 계획 — 이번 학습 예산0회

저장된209주 진단만 제공했다. 주 첫 실제 미국 거래일09:00의 아시아 당일정보, 비중첩 라벨, 주간 성숙시점과 충분한 내부표본을 따로 설계해야 한다.1D 특징·threshold·월간분할을 그대로 복제하지 않는다.1W 내부 fold 수·후보수·fit 예산은 후속 별도 계획에서 정하며 현재 실행할 모델은0개다.

## 종료 선언

이번 요청은 진단·계획 작성까지만 완료한다. **새 fit0회, 새 예측0회, threshold 탐색0회, Phase3/최종 시험0회, 신규 금융자료 수집/설치0회**. 이 문서를 보고한 뒤 학습을 시작하지 않는다.
''')

write('SOURCES.md','''# 추가 확인 근거와 적용 한계

확인일: 2026-10-19. 연구 D 안에서 완료된 별도 문헌조사 파일은 찾지 못했으며, 인수인계서에도 연구 D의 논문 검색·원문 검토 미실행이 명시돼 있었다. 다만 기존 `Research_C_Study_Plan_v1_20261016.md`의 선행연구 부분에 Neely 등 참고문헌이 이미 있어 이 배경을 읽고 원문의 관련 방법을 다시 확인했다. 옛 지시를 실행하거나 기존 계획서의 인용만으로 효과를 검증했다고 취급하지 않았다. 아래는 이번 직접 확인 범위다. 금융 시계열을 새로 수집하지 않았다.

## 공식 시장·일정 자료

1. [KRX 공식 거래 가이드](https://global.krx.co.kr/contents/GLB/01/0109/0109000000/guide_to_trading_in_the_korean_stock_market.pdf), PDF1페이지 Trading Days and Holidays/Trading Hours. 정규09:00~15:30와 근로자의날·연말 휴장 등을 확인했다. 모든 역사적 특별일의 마감시각을 보장하는 달력은 아니다.
2. [대한민국 정책브리핑 2016 하반기 제도](https://www.korea.kr/news/issueQAView.do?newsId=148817606), 외환거래시간 연장 설명.2016-08-01부터 주식 정규거래시간도30분 연장된 사실을 확인했다. 수능일 전수 달력의 근거는 아니다.
3. [TWSE 공식 투자 가이드](https://www.twse.com.tw/en/about/company/guide.html), Trading Principles. 정규09:00~13:30, 종가 형성 전후 정보 공개와 일부 변동성 중단 가능성을 확인했다. 현재 가이드여서2011~2020 모든 날의 확정시각 증명으로 소급하지 않는다.
4. [TWSE 공식2018-10-10 휴장 공지](https://eshop.twse.com.tw/zh/news/detail/00000000648cf6e301648df180160007),2018-10-01 공지. 예시 날짜의 휴장을 직접 확인했다. 원천에 당일 행이 없는 다른 날짜도 모두 휴장이라고 확장하지 않는다.

## 원문 논문 세 편 — 높은 적중률 차용 없음

### Neely, Rapach, Tu, Zhou — Forecasting the Equity Risk Premium: The Role of Technical Indicators

- [저자 소속 St. Louis Fed 원문](https://files.stlouisfed.org/files/htdocs/wp/2010/2010-008.pdf), Working Paper2010-008H,2013-08 revised. 관련 학술지판은 Management Science2014, DOI10.1287/mnsc.2013.1838. 이 두 버전을 독립 연구로 세지 않았다.
- 읽은 부분: 원문9~10페이지 식(4)~(10), MA·모멘텀·거래량 특징과 주기 설명.
- 적용: 기술적 표현을 구체적 산식으로 검토할 일반적 동기. SOX 상대강도·상호작용의 정확한 산식을 입증한 원문으로 인용하지 않는다.
- 차이: 월간 미국 주식 프리미엄 회귀이며 SOX 당일 방향 분류가 아니다. 해당 성과 숫자를 본 연구 기대 Accuracy로 가져오지 않는다.

### Elkan — The Foundations of Cost-Sensitive Learning (IJCAI2001)

- [UCSD 저자 원문](https://cseweb.ucsd.edu/~elkan/rescale.pdf).
- 읽은 부분: Section1.3의 비용·확률에 따른 결정경계와 Section2의 재균형 설명.
- 적용: 클래스 가중·결정경계 변경과 동일 비용 Accuracy 목표가 같지 않다는 설계 근거.
- 차이: 일반적 비용민감 분류 이론이지 SOX의 실증 개선 논문이 아니다. balanced weighting으로 Accuracy가 개선된다고 주장하지 않는다.

### Bailey, Borwein, López de Prado, Zhu — The Probability of Backtest Overfitting

- [저자 원문](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf),2015-02 revised manuscript. [UC repository 학술지판 메타데이터](https://escholarship.org/uc/item/4w1110bb), DOI10.21314/jcf.2016.322,2017 표기. 버전 차이를 구분했다.
- 읽은 부분: 서론의 반복 시도 문제, Section2.3의 동기화된 trial 행렬, Section5.2의 모든 시도 공개 한계.
- 적용: 후보수·예산·실패 보존·동일날짜 비교와 개발 최고값 선택편향 기록.
- 차이: 투자전략 백테스트 선택 문제다. 이 논문의 CSCV를 원점 이전 학습만 허용하는 이번 walk-forward 대신 실행하지 않았고, PBO 수치도 산출하지 않았다.
''')

# Add a clear companion note to the illustrative calendar CSV without rewriting old study evidence.
write('ASIA_CALENDAR_LIMITATIONS.md','''# 아시아 시각 확인 범위

일반 거래시간의 시간대 변환과2018-10-10 대만 공식 휴장은 확인했다. 한국2016년 거래시간 연장도 정부 자료와 대조했다. 모든2011~2020 특별일·휴장·지수 확정시각·벤더 전달을 전수 검증한 것은 아니다. 수능일16:30 행은 확인 대기 예시다. CSV의 시각을 실제 전달기록으로 읽지 말 것.

TWII와TWSE 반도체 원천의 일자 불일치를 별도 CSV에 보존했다. 보충 토요일은 정상 세션일 가능성이 있으므로 일괄 삭제하지 않는다. 원인 불명 행에 새 금융값을 채우지 않는다. 이 gate가 해소되지 않으면 A1은 미실행으로 남긴다.
''')

# Count only genuinely new unique model fits; this ledger is a plan, not an execution log.
external=pd.period_range('2017-01','2020-12',freq='M')
internal=sorted(set([t-12 for t in external]+[t-6 for t in external]));combined=sorted(set(internal)|set(external))
assert len(internal)==54 and len(combined)==60
existing=json.loads((D/'development_revision_v1/logs/FOLD_DETAILS.json').read_text(encoding='utf-8'))
for algo in ['LogisticClassifier','XGBClassifier']:
    origins={pd.Period(f['fold'],freq='M') for f in existing if f['scenario']=='C_latest_monthly_expanding' and f['group']=='M1' and f['algorithm']==algo}
    assert len(set(internal)&origins)==42
ledger=[]
for t in internal:
    if t.year==2016:ledger.append({'package':'primary','recipe':'R0_internal_C1','training_origin_month':str(t),'new_fit_upper':1,'condition':'not in existing outer models'})
for t in combined:ledger.append({'package':'primary','recipe':'A1_asia_C1','training_origin_month':str(t),'new_fit_upper':1,'condition':'only after Asia gate; inner/outer same-fit cache'})
for c in [.01,.1]:
    for t in internal:ledger.append({'package':'primary','recipe':f'C1_alternative_C{c}','training_origin_month':str(t),'new_fit_upper':1,'condition':'shared internal/outer model'})
for t in sorted(set(external)-set(internal)):ledger.append({'package':'primary','recipe':'C1_selected_nonparent_at_most_one','training_origin_month':str(t),'new_fit_upper':1,'condition':'only if nonparent C selected; parent outer already saved'})
for t in internal:
    if t.year==2016:ledger.append({'package':'optional_expression','recipe':'R0_X_internal','training_origin_month':str(t),'new_fit_upper':1,'condition':'not in existing outer models'})
for recipe in ['B1_relative','B2_interaction']:
    for t in combined:ledger.append({'package':'optional_expression','recipe':recipe,'training_origin_month':str(t),'new_fit_upper':1,'condition':'separate deferred package; inner/outer same-fit cache'})
budget=pd.DataFrame(ledger);assert budget.groupby('package').new_fit_upper.sum().to_dict()=={'optional_expression':132,'primary':186}
budget.to_csv(O/'PLANNED_FIT_BUDGET.csv',index=False,encoding='utf-8-sig')

# Current operation and file preservation, distinct from pre-existing QC claims.
before=pd.read_csv(O/'PROTECTED_BEFORE.csv');bad=[]
for r in before.itertuples():
    if not (ROOT/r.path).is_file() or sha(ROOT/r.path)!=r.sha256:bad.append(r.path)
asttree=ast.parse((O/'diagnose.py').read_text(encoding='utf-8'));training_calls=[n.attr for n in ast.walk(asttree) if isinstance(n,ast.Attribute) and isinstance(n.ctx,ast.Load) and n.attr in {'fit','fit_transform','partial_fit','predict','predict_proba'}]
assert not bad,bad;assert not training_calls,training_calls
required=['CURRENT_STATE.md','PREDICTION_DIAGNOSTICS.csv','DIAGNOSIS.md','CHANGE_PLAN.md','EXPERIMENT_PLAN.md'];assert all((O/n).stat().st_size>0 for n in required)
verification={'status':'DIAGNOSIS_AND_PLAN_COMPLETED_NO_TRAINING','protected_files_checked':len(before),'changed':bad,'protection_scope':'Project files excluding installed .venv/.venv_W1 and .git; only new accuracy_improvement_v1 writable by this work','direct_prediction_checks':s['direct_checks'],'direct_prediction_check_failures':s['failed'],'class_metadata_checked':s['model_class_metadata_checked'],'new_model_fits':0,'new_predict_calls':0,'threshold_searches':0,'post2020_evaluations':0,'package_installs':0,'new_financial_data_collection':0,'phase3_or_final_test':False,'expected_primary_fits_if_later_executed_max':186,'optional_representation_package_max':132,'not_executed':True}
(O/'FINAL_VERIFICATION.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
files=[p for p in sorted(O.rglob('*')) if p.is_file() and p.name not in {'OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256','reports_console.txt'}]
pd.DataFrame([{'path':p.relative_to(O).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]).to_csv(O/'OUTPUT_MANIFEST.csv',index=False,encoding='utf-8-sig')
(O/'OUTPUT_MANIFEST.sha256').write_text(sha(O/'OUTPUT_MANIFEST.csv')+'  OUTPUT_MANIFEST.csv\n',encoding='utf-8')
print(json.dumps(verification,ensure_ascii=False),flush=True)
