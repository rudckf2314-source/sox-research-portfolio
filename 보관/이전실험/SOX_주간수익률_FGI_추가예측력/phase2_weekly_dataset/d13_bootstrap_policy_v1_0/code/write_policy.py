"""기존 잠금 원문을 보존하는 D13 정책 후보/방법론 문서."""
from prepare import OUT, LOCK, load, save

def main():
    inherited=load(LOCK/'PHASE1_LOCKED_SPEC_v1_1.json')['inference']
    gate={'D10_GATE':'IMPLEMENTATION_PASS','PHASE2B_DATASET_QC':'PASS',
        'D13_LOCK_STATUS':'LOCK_CANDIDATE_REVIEW_REQUIRED','PHASE3_EXECUTION':'NOT_AUTHORIZED',
        'PHASE4_TEST_PERFORMANCE':'SEALED'}
    policy={'policy_id':'C_D13_CALENDAR_GRID_MBB_v1_0_CANDIDATE','status':'LOCK_CANDIDATE_REVIEW_REQUIRED',
        'approved':False,'inherited_inference':inherited,'gate_snapshot':gate,
        'candidate_rules':{'minimum_valid_n':'max(52, ceil(0.80*N_grid))','integer_equivalent':'max(52,(4*N_grid+4)//5)',
            'N_grid_basis':'사전 고정한 연속 미국 달력 주 격자','block_lengths':[8,4,12],
            'algorithm':'noncircular moving block bootstrap; uniform starts 0..N-L inclusive; concatenate ceil(N/L) blocks; truncate to N',
            'target_valid_replicates':5000,'max_total_attempts':10000,'root_seed':20261016,
            'original_insufficient':'ORIGINAL_SAMPLE_INSUFFICIENT; no draws',
            'resample_insufficient':'reject attempt; retain attempt record; redraw from same unmodified distribution',
            'failure':'BOOTSTRAP_INFERENCE_UNAVAILABLE; no CI/p; no threshold/block adjustment',
            'degenerate':'INFERENCE_UNAVAILABLE_DEGENERATE; no epsilon or p=0',
            'count_definition':'finite paired occurrences, with replacement duplicates counted; distinct original-week count not substituted',
            'missing_mask':'finite M0 loss AND finite M1 loss; carry both losses and mask through common indices',
            'rng':'PCG64(SeedSequence([20261016,L,*8_little_endian_uint32_words(SHA256(ASCII(week_dates_joined_by_LF)))]))',
            'shared_stream':'same full grid and L -> same starts per attempt across algorithms; masks do not enter seed',
            'synthetic_forced_start':'fault injection only, forbidden in empirical sampling'},
        'bootstrap_p_value_enabled':False,'CI_method_inherited':'paired percentile 2.5/97.5; no p from crossing zero',
        'quantile_interpolation_proposal':'linear (Hyndman-Fan type7); ADDITIONAL_DECISION_REQUIRED',
        'additional_decisions':[
            {'id':'A01','topic':'percentile 보간 구현','status':'ADDITIONAL_DECISION_REQUIRED',
             'recommendation':'linear type7를 사전 승인. percentile 방식 자체는 기존 설계 유지.'},
            {'id':'A02','topic':'5종 중 HAC p 산출 불가시 Holm','status':'ADDITIONAL_DECISION_REQUIRED',
             'recommendation':'family m=5 유지; 승인 전 전체 Holm 결론 보류. 이후 보수적 내부 p=1 배치 등은 별도 승인, 원래 p는 null로 유지.'},
            {'id':'A03','topic':'Bootstrap p-value 추가','status':'NOT_PLANNED_REQUIRES_SEPARATE_APPROVAL_IF_ADDED',
             'recommendation':'기존 HAC 단측 p와 percentile CI만 사용. centered null 등 추가 p 방식은 이번에 도입하지 않음.'}],
        'requires_user_approval_before_empirical_inference':True,
        'test_error_valid_count':'UNKNOWN_NOT_YET_PREDICTED','auxiliary_sample_counts':None}
    policy['candidate_rules']['N_grid_basis']='사전 고정한 연속 미국 월요일 달력 주 격자; 유효 주만으로 분모 축소 금지'
    save('policy/D13_LOCK_CANDIDATE.json',policy)
    save('policy/D13_LOCK_CANDIDATE.md','''# D13 세부 규칙 잠금 후보 v1.0

상태: **LOCK_CANDIDATE_REVIEW_REQUIRED**. 정책 ID: `C_D13_CALENDAR_GRID_MBB_v1_0_CANDIDATE`. 사용자 최종 승인 전 APPROVED/LOCKED가 아니다.

## 유지되는 D08

C-M0=B1~B10, C-M1=B1~B10+F1, SOX 비중첩 주간 부호 수익률, ΔMAE=MAE(M0)−MAE(M1), 양수는 FGI 유리. 주력 Ridge, 알고리즘 5종 family, alpha=.05 단측 개선검정과 양측95%CI를 구분한다. HAC Bartlett4달력주/민감도2·8, MBB8달력주/민감도4·12,5000회,seed20261016을 그대로 유지한다. 기존 변수·기간·학습창·모델을 바꾸지 않는다.

## 신규 후보

`min_valid_n=max(52,ceil(0.80*N_grid))`. N_grid는 사전 고정한 연속 미국 달력 주 격자 길이이다. 301→241,209→168,50→52이므로 50주 검정 불가. FGI 변수 생성의80% 관측률과 별개의 통계 운영기준이다.

원본 paired 유효 수 미달이면 추출 전 중단한다. 각 재표본도 같은 하한을 적용한다. 원래 격자 길이N을 복원추출하므로 반복 등장한 유효 원천 주도 해당 횟수만큼 n_valid에 센다. 서로 다른 원천 주 수를 n_valid와 혼동하지 않는다.

비순환 MBB로 유효5000회 확보 또는 총10000회에서 중단한다. 미달 반복은 원인과 함께 보존하고 동일 분포로 재추출한다. 최대 한도 도달시 BOOTSTRAP_INFERENCE_UNAVAILABLE, CI/p 산출 금지. 부족을 비유의로 해석하거나 조건을 완화하지 않는다.

상세 인덱스·시드·결측 정책은 동봉 문서와 JSON에 있다. 보간 규칙과 일부 검정 불능시 Holm 처리는 ADDITIONAL_DECISION_REQUIRED이다. 이번 결과는 후보의 구현 정합성 검사이며 coverage·검정력 검증이 아니다.

최신 D10=IMPLEMENTATION_PASS, Phase2B 데이터QC=PASS를 승계한다. 기존 게이트 원본은 수정하지 않는다. Phase3=NOT_AUTHORIZED, Phase4 시험성과=SEALED.
''')
    save('policy/D13_MISSINGNESS_POLICY.md','''# D13 결측 및 실패 정책 후보

## 실제 데이터 감사 범위

Phase2-B `PAIRED_COMMON_WEEK_MEMBERSHIP.csv`의 week_start,split,paired_common_valid만 파싱한다. 전체823주,공통818주,최초2011-02-07,마지막2026-10-05,초기308/개발209/시험301주. 첫5주(2011-01-03~01-31) 예열 결손 뒤 내부 결측0. 이 자료는 X/Y 가용성 플래그다. **301주가 아직 없는 모델 예측오차301건을 보장하지 않는다.** 시험Y는 파싱하지 않는다.

## 원본과 재표본

원본N_grid는 결과를 보기 전에 고정한 평가구간의 모든 연속 월요일 슬롯이다. 개발209·시험301은 따로 정의하며 초기823격자나 공통818을 시험 분모로 쓰지 않는다. 하위기간/보조모형도 자신이 사전 고정한 전체 격자를 사용한다.

원본 paired 유효 손실은 두 모형 모두 유한해야 한다. 한 모형 실패/NaN/±inf면 그 주 쌍 전체 불가, 날짜와 어느 모형의 어떤 실패인지를 공개한다. 비유한값을0으로 바꾸지 않는다. 모든 손실이 유효하면 전수사용한다. 소수 결측이라도 달력 슬롯을 남겨 시간 간격을 보존한다. 원본 paired n<max(52,ceil(.8N))이면 검정 중단이다.

재표본 인덱스는 결측 여부와 관계없이 원래N위치에서 추출한다. 동일 인덱스로 두 모형 손실과 결측표지를 함께 복제한다. 유효 반복의 평균만 계산하며 n은 반복마다 변할 수 있다. 원본N을 유효주 수로 교체하거나 결측을 제거하고 블록화하지 않는다. n미달/빈 반복은 제외하되 원래 난수분포에서 재추출하고 실패기록을 보존한다.

원본 paired 손실 차이 분산0/비유한, 최종 재표본 평균 분산0/비유한이면 추론 불가다. 유한 입력에서 수치 연산이 비유한이 된 경우도 수치오류로 중단한다. 임의 epsilon, p=0, 작은 분산으로 교체 금지. 개별 재표본이 우연히 상수인 것만으로는 표본수 기준을 통과한 반복을 추가 탈락시키지 않는다.

## 방법론적 한계

52주/80%는 운영 하한이지 검정력·유효표본 독립성·95% 포함률을 보장하지 않는다. 결측이 손실/시장상태와 관련되면 관측쌍 평균은 전체기간 평균과 다를 수 있다. 이 정책은 MNAR 편향을 해결하지 않는다.

반복을 n하한으로 거절하면 **해당 하한을 만족하는 재표본 분포에 조건부**가 된다. 연속 결손과 블록 위치 때문에 거절률이 달라지며 경계에서는5000회를10000회 안에 못 모을 수 있다. 전체 시도·거절률·유효n범위·공백·유효블록을 보고한다. 결과 유리성에 따라 하한/블록/시드를 바꾸지 않는다. 반복5000개는 정보량5000주가 아니다.

비순환 블록은 유한표본에서 양끝 관측의 포함 확률이 내부와 다르다. circular 방식으로 자동 전환하거나 가중치를 사후 수정하지 않는다. 구조변화/동적 재학습/모형선정 불확실성까지 저장된 손실의 MBB가 모두 포괄한다고 주장하지 않는다.

## 보조모형

C-M2/3, C-M4/5는 별도 가용성 검증·격자·paired 표본이 필요하다. 동일 최소표본 규칙을 적용하는 후보 방향은 가능하지만 실제 관측 수는 UNKNOWN이다. 주력818주를 자동 상속하지 않는다. 다른 결측 처리/하한이 필요하면 근거와 별도 승인을 요청한다. 승인 전에 결과를 만들어 채우지 않는다.
''')
    save('policy/D13_BOOTSTRAP_ALGORITHM_SPEC.md','''# D13 비순환 Moving Block Bootstrap 명세 후보

## 입력/출력

사전 등록한 동일 월요일 격자N, 주별 M0/M1 절대손실, paired mask, L∈{8,4,12}. d=loss0−loss1, 양수FGI유리. 실제 추론 코드는 승인 후에만 구현·실행한다. 현재 코드는 합성 손실 전용 QC이며 CI/p 기능이 없다.

1. 격자 중복·역순·7일이 아닌 간격·월요일 외 날짜·손실 음수·배열 불일치를 거부한다.
2. m=max(52,ceil(.8N)); 원본 유효쌍<m이면 시도0으로 종료한다. L>N도 불가.
3. 난수 흐름을 아래처럼 초기화하고 K=ceil(N/L)로 둔다.
4. 각 시도에서 독립 균등정수 시작점K개를0..N−L(양끝 포함)에서 복원추출한다.
5. 각 시작점s에서 s..s+L−1을 순서대로 연결하고 처음N개만 남긴다. 마지막 블록만 절단할 수 있다. 원천격자 양끝을 감지 않아 순환이 아니다.
6. 동일 인덱스에 해당하는 두 모형 손실·날짜·결측mask를 함께 사용한다. n_valid>=m일 때만 유효 반복. n은 중복 추출된 유효 슬롯의 개수다.
7. 유효한 슬롯의 d 평균을 계산한다. 빈/부족 반복은 이유를 기록하고 재추출한다. 실제 수치오류는 단순 결측처럼 무한 재추출하지 않고 중단한다.
8. 유효5000회면 종료. 총시도10000회를 포함하여 그 안에5000회를 얻지 못하면 BOOTSTRAP_INFERENCE_UNAVAILABLE. 10001번째 시도는 없다.
9. 일부 유효 반복만으로 CI/p를 계산하지 않는다. 성공하더라도 Bootstrap p는 기본 제공하지 않는다. 분산0/비유한은 추론 불가로 별도 표시한다.

## 난수 후보 규칙

root_seed=20261016. 격자 날짜 YYYY-MM-DD를 LF로 연결(끝 LF 없음)한 ASCII문자열의 SHA-256을32byte로 해석한다. 순서대로4byte씩 little-endian uint32 8개를 얻는다. `SeedSequence([20261016,L,*words])` → `PCG64` → NumPy Generator를 사용한다. Python hash()·프로세스순서·모형성능·알고리즘명·결측mask는 seed에 넣지 않는다. 라이브러리 버전과 실제 시작점도 저장한다. 이는 새 후보 세부이므로 승인 대기다.

같은 전체격자/L의 알고리즘은 같은 시도번호의 시작점 흐름을 공유한다. 각 알고리즘의 mask가 다르면 채택된 시도번호는 다를 수 있다. 타 알고리즘의 채택/종료에 따라 난수 흐름을 당기지 않는다. 같은 유효번호라고 동일 인덱스라고 주장하지 않으며 시도번호로 비교한다. 모든 모형의 결측을 전역 교집합으로 강제하지 않는다. M0/M1 쌍내 날짜는 항상 같다.

합성 `forced_start`는 빈 블록 반복의 장애 주입 전용이다. 실제 분석에서 사용하거나 균등 추출의 대안으로 선택할 수 없다.

## 기록

시도번호,L,N,원본 paired n,하한,재표본 paired n,채택여부,제외이유,블록시작점,원천인덱스 재구성규칙,seed/격자해시,최대 연속 결측슬롯,유효블록 수. 블록간 연결점은 독립 재추출 경계이지 원천에서 연속한 날짜라고 주장하지 않는다. 최대 공백은 재표본 안의 연속 결측슬롯 길이로 정의하고 블록시작점을 함께 보존해 원천주 간격을 추적한다.

## 기존 추론 승계

유효 원천주 인덱스 i,j와 n, u_i=d_i−mean(d):
`Omega=(sum(u_i^2)+2*sum_{i<j,1<=gap<=q}(1-gap/(q+1))*u_i*u_j)/n`;
`SE=sqrt(Omega/n)`, q=4달력주(민감도2,8), 소표본 보정 없음.
`z=mean(d)/SE`, 단측p=1−Phi(z), 양측95%CI=mean(d)±1.95996398454*SE. 분산0/음수/비유한 중단. 필터된 행 번호 lag 사용 금지.

Bootstrap CI는 기존안의 재표본 평균 분포2.5/97.5 percentile이다. CI보간의 `linear` type7 선택은 추가 승인 후보다. percentile CI의0포함 여부를 p로 변환하지 않는다. Bootstrap p를 요청하면 centered-null 등 정확한 방식·family를 시험 열람 전에 추가 승인해야 한다.

HAC 단측p 5개에 고정m=5 Holm을 적용한다: 정렬p_(j), adjusted p_(j)=min(1,max_{i<=j}[(5−i+1)p_(i)]). 누락p시 family축소 금지, 처리법 승인 전 전체 보정판정 보류. Ridge 주력과 전체family를 구분한다.

## 구현 참고자료

[arch MovingBlockBootstrap](https://bashtage.github.io/arch/bootstrap/generated/arch.bootstrap.MovingBlockBootstrap.html)는 동일 길이의 비순환 블록을 정의한다. [NumPy SeedSequence](https://numpy.org/doc/stable/reference/random/parallel.html)는 재현 가능한 난수 스트림 구성 참고다. [NumPy quantile](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html)는 보간 방법 명시의 근거다. 확인2026-10-18 KST. 이 문서들은52/80% 하한을 통계적으로 보장하는 근거가 아니다. 기존 LOCK의 details_source를 우선하며 라이브러리 기본값으로 설계를 변경하지 않았다.
''')
    save('policy/D13_OPEN_METHODOLOGY_ITEMS.md','''# D13 방법론 감사 및 추가 결정

## 이미 정의되어 있어 바꾸지 않는 것

Phase1 LOCK JSON inference.HAC.details_source가 참조하는 `design/PHASE1_STATISTICAL_TEST_PLAN.md`에는 원래 달력 gap 기반 HAC Ω/SE/z, 정규 단측p, 양측95%CI, 소표본 보정 미사용, percentile Bootstrap CI 및 Holm 수식이 명시되어 있다. 초안의 민감도1·8/4·13만 최신 LOCK의2·8/4·12로 대체한다. 기본 추론 방식을 새로 고르지 않는다.

## ADDITIONAL_DECISION_REQUIRED

|ID|미정 사항|선택지|권고 후보 및 현재 처리|
|---|---|---|---|
|A01|유한5000개 percentile 보간|linear type7 / 역경험CDF(order statistic) 등|기존 percentile 유지 + linear type7 명시 승인 권고. 승인 전 실제 CI 미실행.|
|A02|5개 중 HAC p가 미산출일 때 Holm|전체family판정 보류 / 미산출에 보수적 내부1 배치 후m5 유지|현재 전체family판정 보류. 사용자 승인 없이 p=1을 실제 산출p로 기록하거나 family를 축소하지 않음.|

A01은 CI 종류 변경이 아닌 수치 구현 명세의 빈칸이다. A02는 실제 결측이 없더라도 분산0·모델실패 가능성 때문에 사전에 필요하다. 보수적 내부1 처리 승인시에도 원래 raw p=null, 가정상 보정 입력임을 별도 표시해야 한다.

## 별도 요청이 있을 때만 필요한 항목

A03 Bootstrap p는 기존안에서 필수 아님. 권고는 HAC 단측검정+percentile CI 유지다. Bootstrap p 추가시 귀무하 중심화, 단측꼬리, Monte Carlo 보정, 다중검정family를 추가 승인해야 한다. 비중심화 Bootstrap 비율이나 CI0-crossing을 유의확률로 쓰지 않는다.

보조모형별 실제 가용성·격자·표본은 미확정이다. 현재818주를 이식하지 않으며 별도 검토한다. 같은 격자에서 알고리즘별 paired 결측mask가 달라지면 평가 대상 집합도 달라짐을 보고해야 한다. 주력의 기존 쌍내 동일표본 원칙은 유지하며 결과를 본 뒤 공통교집합을 골라 바꾸지 않는다.

## 설명 가능한 한계

80%하한/재추출은 표본 부족을 감지하는 후보 정책이다. 결측mask와 손실을 함께 뽑아도 비무작위 결측의 전체격자 추정 편향은 해결되지 않는다. 하한 조건으로 채택한 분포는 무조건부 MBB와 다르며, 이를 숨기지 않는다. 합성 QC는 코딩 규칙을 검사할 뿐 실제 검정 크기·검정력·CI coverage를 추정하지 않는다. 이 한계를 전제로 후보 정합성 PASS와 정책승인 대기를 구분한다.
''')
    save('inputs/METHODOLOGY_SOURCES.json',{'checked_on_kst':'2026-10-18','sources':[
        {'url':'https://bashtage.github.io/arch/bootstrap/generated/arch.bootstrap.MovingBlockBootstrap.html','scope':'비순환 동일길이 블록 정의'},
        {'url':'https://numpy.org/doc/stable/reference/random/parallel.html','scope':'SeedSequence 재현성'},
        {'url':'https://numpy.org/doc/stable/reference/generated/numpy.quantile.html','scope':'percentile 보간 방법 명시'}],
        'threshold_is_user_candidate_not_external_theorem':True})
    print('D13 policy candidate written; approval false')

if __name__=='__main__':main()
