"""Render v1.1 approval and gate policies as review documents without touching v1.0."""
from pathlib import Path
import json
L=Path(__file__).resolve().parents[1];O=L.parent
def load(n):return json.loads((L/n).read_text(encoding='utf-8'))
def write(n,t):(L/n).write_text(t.strip()+'\n',encoding='utf-8')
def main():
    if (L/'qc/LOCK_FINALIZATION.json').exists():raise RuntimeError('v1.1 is sealed; do not overwrite approved documents')
    s=load('PHASE1_LOCKED_SPEC_v1_1.json');d=load('PHASE1_APPROVED_DECISIONS.json')
    rows='\n'.join(f"|{r['decision_id']}|{r['approval_status']}|{r['decision']}|" for r in d['decisions'])
    formulas='\n'.join(f"|{fid}|{r['variable_name']}|`{r['formula']}`|{r['unit']}|" for fid,r in s['core_variables'].items())
    write('PHASE1_LOCKED_SPEC_v1_1.md',f'''# 연구 C Phase1 승인 설계 v1.1

승인일: **2026-10-17 KST**. 승인 근거는 사용자 첨부 지시문 전체이며 원문 사본·경로·SHA-256은 inputs와 승인결정 JSON에 기록했다.

전체 상태: **PHASE1_DESIGN_LOCKED_WITH_GATES**. 승인된 설계 부분은 고정하지만 D10·D13 게이트가 통과한 완전한 최종 LOCK 또는 Phase2 실행 승인은 아니다. 원본 v1.0 초안·계획서·보고서는 변경하지 않았다.

## 승인결정 D01~D14

|ID|승인 상태|고정 내용 및 조건|
|---|---|---|
{rows}

D04는 APPROVED다. D02·D08·D09·D10은 조건부 승인이다. D13은 기본 방향을 승인했지만 상세는 DEFERRED_LOCK이다. 데이터의 UNVERIFIED는 연구설계 승인과 별개이며 그대로 유지한다.

## 주력 목표와 원점

`Y_w=100*(P_sox[w]/P_sox[w-1]-1)`은 미국 현지 월~일 비중첩 달력 주의 부호수익률이다. P는 02번 Yahoo ^SOX의 마지막 실제 거래세션 Close다. Adj Close/절댓값/한국 ETF/일별 rolling5일로 바꾸지 않는다. 주 식별자는 현지 월요일 week_start이며 연말 주를 분할하지 않는다. 다른 주 가격으로 기준주 결손을 채우지 않는다. 무거래주·가격결손·미완성 라벨 사유를 보존한다.

원점은 대상 주 첫 실제 미국 주식시장 세션 **09:00 America/New_York**다. DST·휴장·조기마감은 실제 거래일정으로 처리한다. 실제 이용 가능시각의 비교는 `<`다. 동시각 값은 별도 이전수신 증거가 없으면 제외한다. 현재 RAW의 마지막 Y 완료 주 후보는2026-10-05주/10-09종료다. 주간 표본 수는 아직 계산하지 않았다.

## B10 산식 보존

|ID|이름|원래 산식|단위|
|---|---|---|---|
{formulas}

각 원천 경로·가격열·결측·예열·중복정보·빈티지 주의는 PHASE1_FORMULA_AND_SOURCE_REFERENCES_v1_1.json에서 원래 변수사전과 연결된다. B4는 14개 유효 가격변화의 SMA로 상승·하락 평균을 초기화한다. 이후 `(13*이전평균+현재변화)/14`의 Wilder 평활이다. 평균손실0/상승양수이면100, 평균상승0/손실양수이면0, 둘 다0이면50이다. 거래일 가격이 결손이면 임의 건너뛰지 않고 state를 재시작해 14개 변화를 다시 확보한다. 실제 SOX2010 예열자료는 없으며 현재 RSI 값을 계산하지 않았다.

B3는 일간 **부호수익률(%)**의 표본표준편차(ddof1), 단위%p, 비연율화다. B9는 HYG Adj Close다. B10은 DGS10 퍼센트포인트 차이에100을 곱한 bp이며 금리 수익률이 아니다. B10 정의 채택은 H15 시점 문제 해결을 뜻하지 않는다.

## FGI 주력·민감도

F1은 직전 완료 미국 달력 주의 **관측일표지가 있는 적격 일별 점수** 평균이다. 원척도0~100, `n_valid>=ceil(0.8*N_expected)`를 적용한다. 분모 N_expected는 실제 미국 세션 수이며 결손을 빼서 축소하지 않는다. 민감도는100% 완전관측 주간이다. N_expected=0 또는 n_valid=0이면 이용 불가다. 보간·미래대체·자동LOCF·가까운 과거값 자동탐색은 금지한다.

현재11 CSV의2026-03-12=21.15 존재 사실과 과거 결손기록을 구별한다. 2026-10-06 local/GitHub 충돌 및 canonical 로컬 우선 이력은 유지한다. 원래 역사값을 부정하거나 수정하지 않는다. 관측값의 정확성, 실제 최초 CNN 게시시각, 과거 최초 빈티지는 별개다.

### D04 A안 — 고정된 운용 가정

기본 정책 ID: **C_DAILY_EOD_NEXT_US_SESSION_0800_ET_v1_1**.

완료된 일별 원천 세션 d의 값은 **d 다음 실제 미국 주식시장 거래일 08:00 ET**부터 이용 가능하다고 가정한다. 이것은 확인된 CNN/제공처 게시시각이 아니라, 익일 장전 및 주말·휴장 지연을 두는 연구용 운용 가정이다. 그보다 더 늦게 게시되었을 가능성은 여전히 남는다. 원점09:00 이전이라는 조건만을 기계적으로 검사할 수 있으며 진짜 과거 공개를 입증하지 않는다.

기본 F1의 점수 원천 이동은0세션이다. 전주 금요일 관측점수의 assumed_available_at이 다음 월요일08:00(월요일 휴장시 다음 개장일08:00)이 될 수 있다. 따라서 F1을 **전주 관측점수 평균**이라 기록하고, 모든 점수가 실제로 전주에 게시됐다고 주장하지 않는다. 이 차이는 기존 초안의 ‘전주 공개’ 문구를 가정 기반 구현에서 명확하게 한 부분이다.

실제 이용시각이 확인되면 actual_available_at을 우선 사용한다. 일부 실제 발표증거가 가정보다 늦으면 알려진 늦은 경계를 무시하지 않는다. 예를 들어 실제 embargo가 원점 이후이면 가정시각이 원점 이전이어도 제외한다. 정확히 원점 시각의 발표도 별도 이전수신 근거가 없으면 제외한다. 제공처 준비시각까지 입증되지 않으면 VERIFIED_ACTUAL로 올리지 않는다.

필드: actual_release_at / actual_available_at / assumed_available_at / availability_basis / publication_status / vintage_status / assumption_policy_id. 실제 미확인 시각은 null이다. assumed_available_at을 actual 열에 복사하지 않는다. availability_basis는 VERIFIED_ACTUAL / ASSUMED_CONSERVATIVE / UNAVAILABLE를 구분한다. 가정으로 적격이어도 publication_status와 vintage_status의 UNVERIFIED는 유지한다.

추가1세션 민감도는 전주 대상 세션 d마다 `source=previous_US_session(d,1)`로 한 번 이동한 실제 원천점수를 사용한다. 그 실제 원천일의 가용성 규칙을 다시 적용한다. 같은 N_expected/관측률을 유지한다. 단순 달력일−1, 금요일 제거, 유효값을 찾을 때까지 반복 이동하는 처리는 금지한다. 전주 월요일 대상이 전전주 금요일 점수로 바뀌는 등 원천 주가 달라질 수 있으므로 target_session_date와 source_observation_date를 모두 보존한다.

US 휴장일은 예상 거래세션에서 제외한다. 휴일·주말 표지의 추가 점수는 거래일 점수로 몰래 옮기지 않고 별도 감사한다. 기대 세션에 점수가 없거나 알려진 실제 공개가 늦으면 분모를 유지한 결측으로 센다. 시각 미확인이나 일정 부재를 가짜 실제 시각으로 채우지 않는다. 실제/가정 일자가 다른 주에 속하는지도 lineage에 기록한다.

이 일별 가정은 승인 범위의 금융시장 EOD와 FGI에 적용하는 운용 명세다. **H15/B10, H10, NFCI, AAII, 월간자료, French, FOMC 일정에 자동 적용하지 않는다.** B10은 D10 사전감사에서 별도 판정 방법을 정해야 한다. 라벨도 완료된 주만 쓰고 실제 가용시각 또는 별도 C_LABEL_EOD_NEXT_US_SESSION_0800_ET_v1_1 가정을 표시한다. 이번에 시각 매핑표나 라벨을 생성하지 않았다.

## 정보집합과 비교

C-M0=B10, C-M1=B10+F1이 주력이다. C-M2=B10+AAIIspread+EquityPut/Call+NYSE신고저, C-M3=C-M2+F1, C-M4=B10+SOXX+TSM+대만반도체, C-M5=C-M4+F1은 시점가용성 조건부 보조그룹이다. 정확한 산식은 기존 사전 그대로다. 나머지 French·월간·거시 후보는 별도 탐색으로 남기고 한 모형에 자동 추가하지 않는다.

동일 쌍의 Y·예측원점·학습 공통주·평가주·알고리즘·전처리 원칙·창·탐색예산을 맞춘다. 확장자료 때문에 주력 표본을 전역 교집합으로 줄이지 않는다. 모든 사전 결과와 비개선 결과를 보고한다. 연구 C 기본 정보집합에는 PCA가 없다.

## 시간 분할·창·학습 규칙

주 월요일 기준2011~2016 초기학습,2017~2020 개발검증,2021~2026 마지막 완료주 시험이다. Expanding과 최근5달력년 Rolling을 비교한다. 결손 때문에260유효행까지 과거 창을 늘리지 않는다. 최소156유효 학습주를 확보하지 못하면 미예측 플래그를 남기고 동일 쌍에서 제외·건수를 공개한다. OLS의 원래 rank 및 n>p+20 진단도 유지한다.

**Ridge가 사전 주력 알고리즘**이다. Ridge C-M0의 개발 pooled MAE로 창을 선택해 Ridge M0/M1에 공유하며 창 동점은Expanding이다. 다른 알고리즘은 원래 각 알고리즘 C-M0 개발 MAE 기준을 유지해 해당 M0/M1에 공유한다. Ridge 창을 다른 알고리즘에 조용히 강제하거나 시험 최저모델로 주력 Ridge를 바꾸지 않는다. 후보 동점은candidate_id 오름차순이다.

원점마다 성숙한 과거 라벨만 추가해 재학습할 수 있다. 시험기간에 이미 성숙한 과거 Y를 다음 원점 학습에 쓰는 것과, 시험 오차로 설정을 바꾸는 것은 구분한다. 전처리는 해당 학습구간에서만 fit한다. 이전 중첩5일 연구의 고정5행 purge를 승계하지 않는다. 음수예측을0으로 자르지 않는다.

## 탐색 후보 예산

OLS1+Ridge5+ElasticNet4+RandomForest4+HistGradientBoosting4=**합계18개의 고유 후보**다. 이는 정보집합별·학습창별·개발원점별 적용 목록이며 18개/알고리즘 또는 총18회 학습이라는 뜻이 아니다. 주력 개발 fit 예산 산식은 `18*2정보집합*2창*N_dev`다. 실제 N_dev와 fit 횟수는 아직0회 실행/미산출이다. 조건부 확장쌍에도 같은 원래 후보를 동등하게 적용하되 후보조합 추가는 승인하지 않았다. 정확한18조합은 PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json이다. seed20261016, workers1, 0% 및 origin별 학습평균 기준을 유지한다.

## 평가·통계검정

주지표MAE(%p), 보조RMSE(%p), origin별 학습평균 기준OOS R², 방향정확도다. `ΔMAE=MAE(C-M0)-MAE(C-M1)`로 양수가FGI 유리다. 음수수익률/실제Y는 변경하지 않는다.

단측 개선검정alpha.05와 양측95%CI를 병기한다. HAC Bartlett 기본4 **원래 달력주 거리**, 민감도2·8주다. MBB 기본8달력주, 민감도4·12주,5000회,seed20261016이다. 원래 초안의HAC1·8 및block4·13은 v1.1에서 각각2·8과4·12로 명시 변경했다. 소표본 보정 미사용, HAC 비유한/분산 오류 중단, 원래 gap 기반 계산식 등 나머지 원칙은 유지한다.

Holm family는 사전5알고리즘의 C-M0/M1 대비이며 raw/보정p를 모두 보고한다. 주력 Ridge와 전체5종 family 결과를 구분한다. Clark–West는 전제가 성립하는 동일 표본의 중첩 선형 OLS 모형 제곱오차 보조검정만 허용한다. MAE/임의 비선형 ML에 자동 적용하지 않는다. 2021~2022와2023~완료주 안정성도 사전 보조분석으로 구별한다. 통계 결과는 아직 없다.

## D10·D13 게이트

**D10_GATE_STATUS=PENDING_PHASE2_PREBUILD_AUDIT**. Phase2 명시 승인 후 첫 작업으로 H15 실제/가정 공표 판정, 기준주·전전주 유효관측, 결측/미확인, 공통표본 영향, 기존B10 유지 가능성과 정책변경 필요를 감사한다. 주간X/Y 본격 생성보다 선행한다. 기존정의를 유지할 수 없으면 B10/핵심 공통표본 생성을 중단하고 별도 승인을 받아야 한다. D04 일반가정으로 이 검사를 면제하지 않는다. 이번 작업에서 감사 또는 통과 선언을 하지 않았다.

**D13_GATE_STATUS=PENDING_WEEKLY_MISSINGNESS_AUDIT**. 원래 달력주 격자,8주블록,paired오차 공동추출,매회 유효n 기록 방향만 승인했다. 최소유효n,부족/빈반복 처리,최대재추출 횟수,실패 처리는 전부null/DEFERRED_LOCK이다. Phase2의 실제 결손 감사 뒤 별도 문서로 정하고 **Phase4 최종 시험오차·성능을 보기 전에** 잠가야 한다. 이 세부가 미잠금이면 bootstrap 추론 및 시험오차/성과 열람 단계로 넘어가지 않는다.

## 효력과 다음 단계

승인 설계 부분은 고정했지만 Phase2 실행은 승인되지 않았다. 이번에는 RAW·freeze·Phase0·기존Phase1를 변경하지 않고 승인 문서만 생성했다. 실제 X/Y·as-of·학습·예측·성과0회, Phase2 디렉터리 미생성이다. 가정 기반 연구라는 점, 과거 빈티지 미검증 및 동일 시장기간의 이전 연구 노출 한계를 논문에 유지한다.
''')
    write('PHASE1_CHANGELOG_v1_1.md','''# v1.0 초안 → 승인 LOCK v1.1 변경이력

승인일2026-10-17 KST. 원본 초안 version=phase1-draft-20261016. 원본 경로/해시는 inputs와 PHASE1_LOCKED_SPEC_v1_1.json에 기록했다. 기존 파일은 덮어쓰지 않았다.

|항목|원본|v1.1|근거|
|---|---|---|---|
|전체 상태|REQUIRES_APPROVAL|PHASE1_DESIGN_LOCKED_WITH_GATES|최신 명시 승인|
|D01/D14|09:00/< 권고|첫 미국세션09:00 ET 및 실제 strict-before 승인|D01/D14|
|B10/RSI|산식 제안|산식 채택; DGS10 가용성 조건부|D02/D10|
|FGI|평균/80%/100% 권고|채택; 무보간·자동LOCF 금지|D03|
|역사 게시시각|가정 허용 미승인|A안 승인, 실제/가정 분리,UNVERIFIED 유지|D04|
|가정 구현시각|미상세|다음 실제 US세션08:00 ET 운용가정; 실제시각 아님|D04 구현정책 고정 요구|
|FGI 주간 표현|전주에 공개된 점수 문구|전주 관측일표지와 실제/가정 공개주 분리; 기본원천이동0/민감도1세션|D03/D04 정합화|
|분할/창|권고|2011~16/2017~20/2021이후,Expanding/5달력년,최소156주 승인|D05/D06|
|대표모형|Ridge 권고|Ridge 사전 지정,해당M0 개발MAE 창선정/공유/동점Expanding|D11|
|다른 알고리즘 창|각M0 기준|기존 각알고리즘M0 기준 유지,전체보고|D11의 다른 모형 기존설계 승계|
|후보|합계18 제안|기존18조합 그대로 승인;1/5/4/4/4|D07|
|HAC 민감도|1·8주|2·8주;기본4주 유지|D08 최신지시 우선|
|MBB 민감도|4·13주|4·12주;기본8주/5000회 유지|D08 최신지시 우선|
|심리/업종 그룹|소수그룹 제안|해당C-M2~5 조건부 채택,나머지 탐색 보류|D09|
|D10|미결정|조건부 승인 + GATE_PENDING,사전감사 미실시|통과아님|
|D13|미결정|기본방향 승인,상세 DEFERRED_LOCK|통과아님|
|기존 원천·수식·Y|원본 보존|그대로 유지|수치 변경0|
|Phase2|미승인/미실행|여전히 미승인/미실행|종료조건|

새 운영 가정은 공식 공표시각을 새로 검증한 결과가 아니다. 원래 일반 발표규칙과 가정에 따른 적격성은 구별한다. D10과 D13의후속 감사에서는 본 승인사항을 임의 변경하지 않고 필요한 경우 별도 승인받는다. 원본 계획서의과거 미승인 문구와초안은역사 기록으로 그대로 남기며 최신v1.1이 승인 범위에서 우선한다.
''')
    write('README.md','''# 연구 C Phase1 승인 LOCK v1.1

상태 **PHASE1_DESIGN_LOCKED_WITH_GATES**, 승인일2026-10-17 KST.

사용자가 D01~D14를 승인한 내용을 별도 버전으로 보존했다. 전체 게이트가 해결된 최종 무조건 LOCK 또는 Phase2 실행 승인은 아니다.

- 승인 결정: PHASE1_APPROVED_DECISIONS.json
- 실행 사양: PHASE1_LOCKED_SPEC_v1_1.json / .md
- 정확한18후보: PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json
- 기존 산식·출처·미검증 상태: PHASE1_FORMULA_AND_SOURCE_REFERENCES_v1_1.json
- 미통과 게이트: PHASE1_GATE_REGISTER.json
- 변경 이력: PHASE1_CHANGELOG_v1_1.md
- 승인원문·보호해시: inputs/
- 자동·독립 QC 및 산출물해시: qc/
- 최종 보고·인수인계: reports/
- 문서작성/검증코드: code/

D10은 Phase2 승인 후 주간X/Y 본격 생성 전 H15 사전감사가 필요하다. D13은 실제주간 결손 감사 후 Phase4 시험오차·성과 열람 전에 상세를 잠가야 한다. 두 게이트 모두 미통과다.

기존 Phase1 루트의 초안/보고서는 역사 기록이며 수정하지 않았다. 이 버전의 명시 변경만 최신이다. 원본 연구계획서/RAW/freeze/Phase0/이전연구·아카이브도 그대로다. 과거생성코드를재실행하면원본Phase1문서를변경할수있으므로 이번작업은그코드를재실행하지않았다.

Python표준라이브러리만사용했다. prepare_lock.py는초기입력manifest덮어쓰기를거부한다. 실제데이터셋/모형실험재현코드는이번산출물이아니다. Phase2폴더생성및실행은별도명시지시전까지금지한다.

qc/LOCK_FINALIZATION.json이 생성되면 이 버전의 문서 생성기는 덮어쓰기를 거부한다. 이는 승인 문서의 보존 장치이며 D10·D13의 통과를 뜻하지 않는다. 변경이 필요하면 사용자 지시에 따라 별도 버전을 작성한다.
''')
    print('Locked Markdown, changelog and README saved.')
if __name__=='__main__':main()
