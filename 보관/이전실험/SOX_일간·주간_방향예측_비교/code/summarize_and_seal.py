"""Deliver A-D Korean completion report and seal all finished research_D files."""
from pathlib import Path
import json,hashlib
import pandas as pd
O=Path(__file__).resolve().parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(n,s):(O/n).write_text(s,encoding='utf-8')
s=json.loads((O/'PHASE2_SUMMARY.json').read_text(encoding='utf-8'))
r=pd.read_csv(O/'PHASE2_MODEL_RESULTS.csv');raw=pd.read_csv(O/'RAW_INVENTORY.csv');counts=json.loads((O/'qc/DATASET_COUNTS.json').read_text(encoding='utf-8'))
q=json.loads((O/'qc/FINAL_STATUS.json').read_text(encoding='utf-8'));assert q['status']=='PASS_WITH_POINT_IN_TIME_LIMITATIONS'
report='''# 연구 D Phase0~2 완료 보고

**개발 실험과 구현 QC를 완료했지만, 기준모형보다 반복 가능하게 나은 예측력을 확보했다고 판단할 근거는 부족합니다.** 완전한 역사적 실시간 정보가용성 검증은 아니며, 시장 EOD2세션 지연을 가정한 조건부 연구입니다. Phase3와 최종 시험은 실행하지 않았습니다.

## A. 데이터 현황

- 실제 RAW: 47종 / canonical CSV48개. 전수 조사·해시·기간·품질·가용성 기록 완료.
- 이번 조건부 시장 EOD 설계에 활용한 원천:22종, 파생변수86개. 엄밀한 과거 전송시각을 전수 입증했다는 뜻은 아닙니다.
- 제외·보류:25종. FGI, AAII, FRED 환율/금리, 수정 가능한 거시통계·월간 산업자료·French·FOMC 등.42번 ESOX는2021시작으로 개발기간 부재. 자세한 목록은 RAW_INVENTORY와 POINT_IN_TIME_AUDIT 참조.
- 24번 세관자료:10,035행, 날짜 중복9,846건이지만 Date+HS_Code 중복0건, 품목107개입니다. 정상 다중품목 관측을 단순 날짜중복 오류로 처리하지 않았습니다. 분류 합산·공표시점 문제로 모델에는 사용하지 않았습니다.
- 1D: 초기학습1,488개 / 개발검증1,007개. 1W: 초기학습308개 / 개발검증209개.
- SOX 원천: 보존 Yahoo 다운로드와 모든 값 및 기록해시 일치.2011~2020 달력2,517세션 일치. 다른 공급원 확인을 수행한 것은 아닙니다.
- 기존 C 백업은 여전히 FAIL입니다. 연구 D에서 과거 매니페스트를 고치거나 백업을 재판정하지 않았습니다.

## B. 예측 성능 — 2017~2020 개발검증

|지평|다수 기준 Accuracy|최고 개발 Accuracy|개선폭|Balanced Accuracy|MCC|모델·정보집합|변수 수|
|---|---:|---:|---:|---:|---:|---|---:|
'''
for a in s:
 report+=f"|{a['horizon']}|{100*a['baseline_accuracy']:.2f}%|{100*a['accuracy']:.2f}%|{a['gain_pp']:+.2f}%p|{100*a['balanced_accuracy']:.2f}%|{a['MCC']:.4f}|{a['best_algorithm']} · {a['best_group']}|{a['features_min']}~{a['features_max']}|\n"
report+='\n1D 최고값은1,007개 중 기준보다1개, 1W는209개 중2개 더 맞힌 결과입니다. **개발 최고 모델을 고른 성적이며 최종 시험 성적이 아닙니다.**\n\n'
for a in s:
 rr=r[(r.horizon==a['horizon'])&(r.group==a['best_group'])&(r.algorithm==a['best_algorithm'])]
 allrow=rr[rr.period=='ALL'].iloc[0]
 report+=f"- {a['horizon']} 개선폭95% block-bootstrap 구간: [{a['CI95_lower_pp']:.2f}, {a['CI95_upper_pp']:.2f}]%p. 0을 포함하며 모델선택 편향은 미보정입니다.\n"
 report+=f"- {a['horizon']} 상승예측 비중 {100*allrow.predicted_up_fraction:.2f}%, 상승 recall {100*allrow.recall_up:.2f}%, 비상승 recall {100*allrow.recall_nonup:.2f}%, ROC-AUC {allrow.ROC_AUC:.4f}. 높은 Accuracy 대부분이 상승 클래스 비중과 관련됩니다.\n"
 report+=f"- {a['horizon']} 연도별 적중률/기준 대비: "+'; '.join(f"{v.period}: {100*v.accuracy:.2f}% / {v.improvement_pp:+.2f}%p" for v in rr[rr.period!='ALL'].itertuples())+'\n'
report+='''
Logistic Regression, Ridge Classifier(시간순 calibration 포함), Random Forest, XGBoost, LightGBM을 비교했습니다. CatBoost는 미설치로 실행하지 않았습니다. 외부 fold 모델200개, 내부 시도기록998개, 실행 실패0건입니다. 다수 기준·직전방향 모멘텀 기준과 모든 모델의 F1/AUC/Brier/LogLoss·연도·클래스별 성능을 PHASE2_MODEL_RESULTS.csv에 보존했습니다.

## C. 변수 확대 효과

다음은 같은 XGBoost 알고리즘끼리의 비교입니다. 모든 지평 내부에서 평가 날짜가 같습니다. 다만 설정과 분류 임곗값은 각각 학습 내부에서 선택하므로 순수한 변수의 인과적 효과는 아닙니다.

|정보집합|후보/선택 수|1D Accuracy|1W Accuracy|
|---|---:|---:|---:|
'''
for g,label,n in [('M0','SOX 과거 정보','5'),('M1','주요 시장·채권·산업 대리지표','53'),('M2','추가 위험·심리·시장 내부지표','86'),('M4','학습 내부 변수선택','25'),('M2_no_sector_proxy','SOX와 중복성이 큰 산업대리지표 제거','68')]:
 row=r[(r.period=='ALL')&(r.algorithm=='XGBoost')&(r.group==g)].set_index('horizon')
 report+=f"|{g}: {label}|{n}|{100*row.loc['1D','accuracy']:.2f}%|{100*row.loc['1W','accuracy']:.2f}%|\n"
report+='''
전체 RAW 확대가 일관된 성능 향상으로 이어지지 않았습니다. 1W에서는M1이M0보다 낫지만M2 전체 확대는 악화됐고, 산업 대리지표를 제거한68개 후보가 가장 높았습니다. 이 차이를 특정 지표의 안정적인 기여로 확정하지 않습니다. M4 변수선택도 최고 적중률을 개선하지 못했습니다. M3에 새로 넣을 수 있는 발표시점·빈티지 검증 거시/월간 산업자료가 없어M2와 동일합니다. 해당 자료군의 실효성은 이번 실험에서 검증하지 못했습니다.

## D. 최종 판단

- 1W가 기준 대비 개선폭·BA/MCC 면에서는 상대적으로 더 유망하지만 표본이209개뿐이고 연도별 성과가 엇갈립니다. 현재 단계에서 반복 가능한 우위를 확보했다고 판단하지 않습니다.
- 1D 최고 후보는 거의 항상 상승을 예측하며 비상승 recall이1% 미만입니다. 실용적인 상승·하락 판별모형을 확보한 것으로 볼 수 없습니다.
- 모든 전처리·선택·튜닝·threshold 결정은 외부 검증연도 이전 자료로만 했습니다. 여러 개발모형 중 최고를 고른 편향, 작은 주간표본, 시장자료 정정본/전송시각 한계는 남습니다.
- 추가로 필요한 것은 당시 최초 발표값과 실제 공표시각이 보존된 거시·산업 데이터, FGI 변경의 구체적 계보·승인 근거, 시장자료 수정 이력입니다. 이번 단계에서 새 수집을 하지 않았습니다.
- 논문 후보 질문은 정보군 확대와 변수선택의 실제 개선 여부, 지평별 안정성입니다. 최종 주제·제목·최종 검증정책은 확정하지 않았습니다.
- 구현 QC634/634 PASS. 실제 과거 정보가용성에 대한 무조건 PASS가 아닙니다. 기존 보호범위2,829개 파일 및 연구C 전체10,515개(내부환경 포함) 해시 변경0개.
- 모든 신규 산출물은 research_D 아래입니다. 기존C·RAW·archives는 수정·삭제하지 않았으며 연구C Phase5도 실행하지 않았습니다.

최종 상태: **Phase0~2 조건부 역사 개발실험 완료 / 안정적 예측력 개선 미확보 / Phase3·최종 시험 미실행**.
'''
write('PHASE2_COMPLETION_REPORT.md',report)
notes='''

## 해석상 핵심

최고1D 모델은 기준보다1개, 최고1W 모델은2개 더 맞힌 정도입니다. 두 개선폭의95% block-bootstrap 구간은0을 포함합니다. 높은 상승예측 비중과 낮은 비상승 recall, ROC-AUC를 함께 보면 안정적인 방향 판별력을 확보했다고 보기 어렵습니다. 이 부분은 PHASE2_COMPLETION_REPORT.md의 A~D 표와 클래스별 지표를 함께 확인하십시오.
'''
for n in ['PHASE2_IMPROVEMENT_REPORT.md','PHASE2_1D_VS_1W_REPORT.md']:
 content=(O/n).read_text(encoding='utf-8').split('\n\n## 해석상 핵심')[0];write(n,content+notes)
# Supplement the historic anomaly chronology without changing any old audit.
phase0=(O/'PHASE0_RAW_AUDIT.md').read_text(encoding='utf-8').split('\n\n## 역사적 매니페스트 시점 대조')[0]
phase0+='''

## 역사적 매니페스트 시점 대조

qc/HISTORICAL_MANIFEST_CHRONOLOGY.json에서2026-10-16 Phase1,10-17 승인LOCK,10-19 Phase4의 시점을 비교했습니다. 인덱스의 과거 기록 길이1,283/1,685바이트 prefix 해시가 현재 파일 앞부분과 일치해 append 계보와 부합하며, 승인된 append 기록은 기존 Phase1 작업로그/QC에 있습니다. 현재 전체해시는Phase4 기준과 일치합니다.

FGI 현재해시는 이미Phase1 초기 입력과 승인LOCK 및Phase4 입력에서 동일하게 보호돼 있었습니다. 따라서 연구D 작업에서 발생한 변경은 아닙니다. 그러나 더 이른refresh 보고의다른 해시에서 현재본으로 바뀐 구체적 변환·승인 근거와 실제 역사적 공개시각을 전수 입증하지 못해 기본실험 제외를 유지합니다. 옛 기록을 새해시로 바꾸지 않았습니다.26번FRED누락도 해소된 것으로 가정하지 않습니다.
'''
write('PHASE0_RAW_AUDIT.md',phase0)
build=(O/'PHASE2_EXPERIMENT_PLAN.md').read_text(encoding='utf-8')
# Do not change the pre-execution plan; calibration union detail is a separate implementation note.
write('config/CALIBRATION_IMPLEMENTATION_NOTE.md','Ridge calibration은 estimator 내부에 선택·대치·스케일을 포함한 pipeline을 두어 각 TimeSeriesSplit의 학습부분에만 fit합니다. M4는 submodel당 최대25개이며 ensemble 실제 입력 보고는 세 submodel 선택컬럼의 union(최대75)입니다. 각 컬럼과 submodel 구성은 logs/FOLD_DETAILS.json에 보존했습니다.\n')
readme=(O/'README.md').read_text(encoding='utf-8')
readme+='\n주 완료 보고서는 PHASE2_COMPLETION_REPORT.md입니다. finalize.py 후 summarize_and_seal.py가 해석 보고서와 최종 SHA-256 매니페스트를 생성합니다. 최종 매니페스트는 모든 일반 산출물을 포함하고 자기 자신과 seal 파일만 제외합니다.\n'
write('README.md',readme)
delivery={'phase0_2':'COMPLETED_CONDITIONAL_HISTORICAL_DEVELOPMENT','independent_implementation_checks':634,'checks_passed':634,'reliable_baseline_outperformance_established':False,'all_post2020_performance_evaluations':0,'source_data_writes':0,'phase3_executed':False,'catboost_installed':False,'all_attempts_and_predictions_preserved':True}
write('qc/DELIVERY_CHECKS.json',json.dumps(delivery,indent=2)+'\n')
files=[]
for p in sorted(O.rglob('*')):
 if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256']:
  files.append({'path':p.relative_to(O).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
pd.DataFrame(files).to_csv(O/'OUTPUT_MANIFEST.csv',index=False,encoding='utf-8-sig')
write('OUTPUT_MANIFEST.sha256',sha(O/'OUTPUT_MANIFEST.csv')+'  OUTPUT_MANIFEST.csv\n')
for row in files:
 assert sha(O/row['path'])==row['sha256'],row['path']
assert len(files)==sum(1 for p in O.rglob('*') if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256'])
print('Delivery sealed and independently re-read:',len(files),'files; manifest SHA256',sha(O/'OUTPUT_MANIFEST.csv'))
