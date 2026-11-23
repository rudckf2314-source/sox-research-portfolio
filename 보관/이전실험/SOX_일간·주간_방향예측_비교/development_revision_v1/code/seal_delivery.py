"""Readable completion report and SHA-256 seal after all writers have stopped."""
from pathlib import Path
import json,hashlib
import pandas as pd
H=Path(__file__).resolve().parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
qc=json.loads((H/'qc/FINAL_STATUS.json').read_text(encoding='utf-8'))
assert qc['status']=='PASS_WITH_TIMING_ARCHIVE_LIMITATIONS',qc
r=pd.read_csv(H/'MODEL_RESULTS.csv');pooled=r[r.period=='ALL'];m=pooled[pooled.group!='BASELINE'].sort_values(['Accuracy','BalancedAccuracy','MCC'],ascending=False);b=m.iloc[0]
config={'A_old_annual_expanding':'기존 지연 · 연간 갱신 · 전체 과거','B_latest_annual_expanding':'직전 종가 반영 · 연간 갱신 · 전체 과거','C_latest_monthly_expanding':'직전 종가 반영 · 월간 갱신 · 전체 과거','D_latest_monthly_3years':'직전 종가 반영 · 월간 갱신 · 최근 3년'}
s='''# 당일 방향 예측 개선 비교 결과

예측 대상은 **오늘 종가가 직전 미국 거래일 종가보다 높은가**이며, 예측시점은 미국 거래일 오전 09:00입니다. 2017~2020년의 동일한 1,007개 날짜에서 비교했습니다. 2021년 이후 성능은 평가하지 않았습니다.

미국 직전 종가 등 완료된 시장가격 정보를 더 빨리 반영하고, 재학습 주기와 학습기간을 바꿨으며, 분류와 회귀를 비교했습니다. 설정은 결과 평가 전에 고정했고 기존 연구 D 결과는 보존했습니다.

## 설정별 개발 최고 적중률

|설정|개발 최고 적중률|모델|변수군|
|---|---:|---|---|
'''
for name,label in config.items():
    a=m[m.scenario==name].iloc[0];s+=f'|{label}|{100*a.Accuracy:.2f}%|{a.algorithm}|{a.group}|\n'
s+=f'\n항상 상승을 예측하는 기준의 적중률은 **{100*b.baseline_accuracy:.2f}%**입니다. 설정별 최고값은 여러 후보 중 개발 성적이 가장 좋은 모델을 고른 것이므로, 최종 시험 성능이나 설정 자체의 순수한 효과로 해석할 수 없습니다. 같은 모델끼리 비교한 결과는 CONTROLLED_PAIRED_COMPARISONS.csv에 있습니다.\n'
s+='\n## 분류와 회귀\n\n|방식|최고 개발 적중률|모델|\n|---|---:|---|\n'
for algo,label in [('LogisticClassifier','분류'),('XGBClassifier','분류'),('RidgeRegressor','회귀'),('XGBRegressor','회귀')]:
    a=m[m.algorithm==algo].iloc[0];s+=f'|{label}|{100*a.Accuracy:.2f}%|{algo}|\n'
s+='\n회귀는 예측 수익률이 0보다 크면 상승으로 판정했습니다. 회귀의 수익률 예측값을 확률로 바꾸어 표시하지 않았습니다. 이번 고정 설정 비교에서는 회귀 전환이 분류보다 좋은 결과를 만들지 못했습니다. 회귀모델 일반이 효과가 없다는 결론은 아닙니다.\n'
s+=f'''\n## 최고 후보를 어떻게 해석해야 하나

- 모델: {b.algorithm}, {b.group}, {config[b.scenario]}
- 적중률: **{100*b.Accuracy:.2f}%**, 기준 대비 **{b.gain_pp:+.2f}%p**. 1,007개 중 기준보다 {round(b.gain_pp*1007/100)}개 더 맞혔습니다.
- Balanced Accuracy: **{100*b.BalancedAccuracy:.2f}%**, MCC: **{b.MCC:.4f}**
- 비상승 Recall: **{100*b.recall_nonup:.2f}%**, 상승 예측 비중: **{100*b.predicted_up_fraction:.2f}%**
- ROC-AUC: **{b.ROC_AUC:.4f}**
- 기준 대비 개선폭의 20세션 block-bootstrap 95% 구간: **[{b.CI95_gain_lower_pp:.2f}, {b.CI95_gain_upper_pp:.2f}]%p**. 여러 후보 중 최고를 고른 편향은 보정하지 않았습니다.

|검증연도|최고 후보 적중률|기준 대비 개선폭|
|---|---:|---:|
'''
annual=r[(r.scenario==b.scenario)&(r.group==b.group)&(r.algorithm==b.algorithm)&(r.period!='ALL')]
for a in annual.itertuples():s+=f'|{a.period}|{100*a.Accuracy:.2f}%|{a.gain_pp:+.2f}%p|\n'
s+='''
**이번 변경만으로 안정적인 상승·하락 판별력을 확보했다고 판단하기 어렵습니다.** 여전히 상승 예측에 크게 치우쳤고, 개선이 연도 전반에 일관되게 나타나지 않았습니다. 입력 지연이나 회귀·분류 선택 하나만을 원인으로 단정할 수 없습니다.

## 정보가용성과 다음 판단

시장가격 11종의 53개 특징은 원천일 이후 첫 미국 거래세션 08:00에 이용 가능하다고 모델링했습니다. 나머지 위험·심리 특징 33개는 기존 2세션 가정을 유지했습니다. FGI와 발표·수정 이력이 불명확한 거시·월간 자료는 추가하지 않았습니다.

시장 종가가 결정된 시점과 과거 벤더 CSV의 실제 도착 시점은 다릅니다. 실제 과거 전송·정정 로그가 없는 조건부 역사 실험이며, 완전한 point-in-time 인증은 아닙니다. 또한 당일 아시아 종가나 미국 장전·야간 정보까지 모두 활용한 정보집합은 아닙니다.

후속 우선순위는 **오전 09:00 전에 확정된 당일 아시아 시장 정보와 장전·야간 정보의 시각·품질 검증**, 그리고 **상승·비상승 오류를 어떻게 평가할지 사전에 정한 비교**입니다. 이번 결과를 보고 탐색을 계속 늘리거나 미래 최종 시험을 반복하지 않았습니다.

## 보존과 검증

'''
s+=f'- 1,248개 모델 학습 완료, 모델 학습 실패 0건. 준비 단계의 지수 컬럼 매핑 오류 1건은 수정하고 원래 오류 로그를 보존했습니다.\n- 구현 QC **{qc["passed"]}/{qc["checks"]} PASS**. 저장 모델 예측 재현, 원천 Y·특징 재계산, 입력시점, 동일 평가일, 학습 라벨 성숙 여부를 검사했습니다.\n- 기존 연구 D와 RAW·백업 기록 등 보호 대상의 변경은 0개입니다. 연구 C 전체 10,515개 파일도 재해시 대조에서 변경 0개였습니다.\n- 새 자료 수집·패키지 설치·기존 연구 삭제는 수행하지 않았습니다. Phase 3와 최종 시험은 실행하지 않았습니다.\n'
(H/'RESULTS_KO.md').write_text(s,encoding='utf-8')
paths=[p for p in sorted(H.rglob('*')) if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256']]
rows=[{'path':p.relative_to(H).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths]
pd.DataFrame(rows).to_csv(H/'OUTPUT_MANIFEST.csv',index=False,encoding='utf-8-sig')
(H/'OUTPUT_MANIFEST.sha256').write_text(sha(H/'OUTPUT_MANIFEST.csv')+'  OUTPUT_MANIFEST.csv\n',encoding='utf-8')
for row in rows:assert sha(H/row['path'])==row['sha256'],row['path']
print('PASS: sealed and re-read',len(rows),'files; manifest SHA256',sha(H/'OUTPUT_MANIFEST.csv'))
