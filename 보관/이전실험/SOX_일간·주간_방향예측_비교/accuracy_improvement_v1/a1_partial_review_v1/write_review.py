"""Write planning artifacts from the completed feature audit. No models or outcome data."""
import json,hashlib,os
from pathlib import Path
import pandas as pd
O=Path(__file__).resolve().parent;ROOT=O.parents[2]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def table(df,cols):
    z=df[cols].copy().map(lambda v:f'{v:.2f}' if isinstance(v,float) else str(v))
    return '| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(r)+' |' for r in z.to_numpy().tolist())+'\n'
def main():
    assert not (O/'FINAL_VERIFICATION.json').exists(),'Do not overwrite sealed review'
    s=json.loads((O/'AUDIT_SUMMARY.json').read_text());rates=pd.read_csv(O/'EXPECTED_RATES_SUMMARY.csv',dtype={'source':str});dates=pd.read_csv(O/'EXPECTED_DATE_COVERAGE.csv',dtype={'source':str});usage=pd.read_csv(O/'EXPECTED_OUTER_TRAINING_USAGE.csv',dtype={'source':str});rows=pd.read_csv(O/'A1_PARTIAL_ROW_REVIEW.csv',dtype={'source':str},parse_dates=['date']);budget=[]
    for source,policy in [('01','A1_KR_ONLY'),('23','A1_TW23_ONLY')]:
        for month in pd.period_range('2017-01','2020-12',freq='M'):
            first=rows.loc[rows.date.dt.to_period('M')==month,'date'].min()
            z=rows[(rows.source==source)&(rows.date<first)]
            changed=int(z.would_change_numeric_value.sum());need=changed>0
            budget.append(dict(policy=policy,month=str(month),changed_training_feature_cells=changed,new_fit_needed=need,reuse_R0_model=not need,reason='training_X_differs' if need else 'training_X_identical_require_full_cache_parameter_label_environment_checks_before_reuse'))
    pd.DataFrame(budget).to_csv(O/'EXPECTED_FIT_BUDGET.csv',index=False,encoding='utf-8-sig')
    counts=pd.DataFrame(budget).groupby('policy').agg(outer_months=('month','size'),new_fits=('new_fit_needed','sum'),reused_models=('reuse_R0_model','sum')).reset_index();counts.to_csv(O/'EXPECTED_FIT_BUDGET_SUMMARY.csv',index=False,encoding='utf-8-sig')
    # Retain the initial no-cache planning upper bound, then document the verified training-X refinement.
    s['initial_no_cache_outer_model_upper_bound']=96;s['expected_future_fits_KR']=int(counts.loc[counts.policy=='A1_KR_ONLY','new_fits'].iloc[0]);s['expected_future_fits_TW23']=int(counts.loc[counts.policy=='A1_TW23_ONLY','new_fits'].iloc[0]);s['expected_future_fits_total']=int(counts.new_fits.sum());s['cache_refinement']='feature-cell changes only; future execution must independently verify complete cache equivalence; mismatch means stop, no automatic budget increase'
    (O/'AUDIT_SUMMARY.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    disposition='''# 既存 우선 패키지의 보존 판정

R0/A1/C1/T1 우선 패키지의 최종 연구 판정은 **Accuracy 개선 실패**로 보존한다. 실행·무결성 QC의 PASS와 연구 목표 달성 여부는 다른 판단이다. C1/T1은R0보다4일 더 맞혔지만 항상 상승보다10일, 기존 개발 최고보다14일 적었다. 기존 execution_v1의 결과·미실행 A1·중단 판단·매니페스트는 변경하지 않는다.

이번 부분 적용 검토는 과거 결과를 성공으로 재해석하거나 이전 A1을 소급 실행한 것이 아니다. C1/T1 grid 확대·후보 결합·추가 알고리즘은 계획하지 않는다. 기존 결과 근거는 ../execution_v1/RESULTS_REPORT.md, METRICS.csv, FINAL_VERIFICATION.json이다. 이 판정 문서를 새 경로에 추가하며 기존 보고서는 그대로 둔다.
'''
    (O/'PREVIOUS_RESULT_DISPOSITION.md').write_text(disposition.replace('既存','기존'),encoding='utf-8')
    review=[
        dict(issue='A1全行0%',category='implementation_and_policy',direct_scope='all sources because old A1 globally NOT_EXECUTED',finding='same_day_applied=False and fallback=True were assigned unconditionally; 0% was not estimated row eligibility',revision='preserve old stop; compute source/row/input-specific conditional eligibility'),
        dict(issue='TW13/23 date mismatch',category='source_specific_warning',direct_scope='Taiwan rows; no direct KR effect',finding='other-source absence alone proves neither holiday nor bad own row',revision='retain23 if original archive/time pass; isolate13 own evidence; no KR propagation'),
        dict(issue='KR special-session history incomplete',category='general_coverage_limit',direct_scope='unverified special dates, not every ordinary date',finding='not sufficient reason for all KR dates to be unusable',revision='predeclared limited calendar scope; special quarantine; conditional regular hours elsewhere'),
        dict(issue='past special close time unknown',category='timestamp_vs_value',direct_scope='latest same-day timestamp if unverified',finding='a prior-day completed observation does not become unavailable today solely because precise prior close is unknown',revision='use established past-information basis; propagate actual invalid values/session errors only'),
        dict(issue='TW13 duplicate OHLCV',category='own_row_anomaly',direct_scope='suspected copied own observations and features actually using them',finding=','.join(s['source13_suspected_padding_dates']),revision='no row deletion; quarantine required-input windows; mark suspected padding, not proven holiday'),
        dict(issue='TW23 native archive provenance',category='direct_value_check',direct_scope='120 existing monthly files and canonical23 observations',finding=f'{s["canonical23_archive_verified"]}/{s["canonical23_rows"]} canonical values match existing stored official original files',revision='do not invalidate23 merely because Yahoo lacks that date'),
        dict(issue='TW exact historical archive delivery',category='general_provenance_limit',direct_scope='actual vendor/archive timestamps unverified',finding='2019 official dissemination manual supports operational timing; does not establish daily archive vintage identity',revision='conditional historical experiment only; start2019-04; no claim of proven delivery'),
        dict(issue='different product generated18:30',category='product_identity',direct_scope='the named constituent/EOD product only',finding='not canonical EFTRI_HIST timestamp',revision='not used to enable or exclude RAW23'),
    ];pd.DataFrame(review).to_csv(O/'A1_PARTIAL_REVIEW_TABLE.csv',index=False,encoding='utf-8-sig')
    text='''# A1 부분 적용 검토 결과 — PLAN_ONLY

기존 Accuracy 개선 실패 및 A1 미실행 판단을 보존한다. **새 학습0, 새 모델 예측0, 성능평가0, 신규 금융 시계열 수집0, 설치0**이다.

## 일괄0%의 원인과 수정 필요성

기존 execution_v1/run.py는 전역 gate에서 A1을 미실행으로 정한 뒤, 모든 행에 same_day_applied=False/fallback=True를 넣었다. 따라서0%는 모든 원천·모든 관측이 개별 검증에서 부적격이었다는 실증 결과가 아니다. 대만 불일치는 한국의 cross_source_conflict에 직접 적용되지는 않았지만, 세 원천을 함께 중단한 상위 정책이 한국까지 제외했다. **대만 원천 불일치가 한국 KODEX를 제외할 근거는 아니다.**

한국 특별일 전수 미확인도 모든 일반 거래일을 제외해야 한다는 근거는 아니다. 다만 미확인일을 무조건 일반일로 확정하지 않는다. 이번 수정계획은 사전 고정된 부분 범위와 조건부 가정을 명시한다. 원래 중단은 당시의 엄격한 전기간 gate 적용으로 보존하며, 이번 계획은 그 gate를 원천·날짜·특징의 실제 의존 입력별로 분리하는 변경이다.

## 원천별 부분 실행안

**A1_KR_ONLY:** s01의 기존5특징만 교체. 정규마감은2016-08-01 전15:00, 이후15:30. 확인한2019-11-14만16:30으로 명시한다. 모두+2시간의 조건부 가용시각을 America/New_York로 변환해09시 이전인지 확인했다. 원문 특별일 목록을 완성하지 못했으므로 연초 첫 native 관측일·매년11월·2020년12월은 당일 교체 범위에서 보수적으로 제외하며, 확인된2019-11-14만 예외로 허용한다. 월 단위 제외는 오류 판정이 아니라 미검증일 포함을 피하는 범위 제한이다. 전기간 특별일 완전 검증을 주장하지 않는다.

**A1_TW23_ONLY:** s23의 기존3특징만 교체. 기존 저장 공식 월별 원본으로 canonical 값을 전수 대조한다.2019년3월 공식 전송 매뉴얼에 지수 전송시간대·마감 통계·반도체지수 포함이 확인돼, 더 이른 기간으로 무제한 소급하지 않고2019-04-01 이후에 한정한다. 조건부 가용시각은 일반13:30+2시간인15:30 Taipei로 둔다. 당시 일별 archive의 실제 게시시각·후일 수정 여부는 입증되지 않았다. 다른 상품의18:30 생성시각을 이 파일 시각으로 전용하지 않는다.

**s13 TWII:** 부분 가능성은 별도로 집계하지만 이번 단일 대만 비교에는 포함하지 않는다. 성능을 보기 전에 공식 원본과 직접 연결되는23을 선택한 것이다. s13을 모두 오류라고 판정한 것이 아니다. s13에서 원천 자체의 OHLCV 복제 의심일을 따로 기록하고, 실제 그 값이 필요한 계산창만 격리했다. 다른 원천에 행이 없다는 사실만으로13이나23의 정상 행을 삭제하지 않았다. RAW를 고치거나 native rolling 관측을 삭제하지 않았다.

## 예상 적용률 — 분모 구분

초기 학습기간은2011~2016의1,488일, 평가기간은2017~2020의1,007일이다. 아래 적용률 분모는 해당 원천의 대상 특징 셀(한국5, TWII5, TW23 3)이다.53개 전체 특징의 비율이나 실제 전달 입증률이 아니다. source13의 application0%는 사전 미선택 때문이며 conditional_eligible_pct가 기술적 부분 가능률이다.

'''
    text+=table(rates,['scope','source','feature_cells','eligible_cells','applied_cells','application_pct','fallback_pct','conditional_eligible_pct'])
    text+='\n날짜 기준으로 하나 이상/모든 대상 특징이 적용 가능한 일수:\n\n'+table(dates,['scope','source','dates','any_feature_days','all_feature_days'])
    yr=pd.read_csv(O/'EXPECTED_APPLICATION_RATES_BY_YEAR.csv',dtype={'source':str});year=yr.groupby(['year','source'],as_index=False)[['feature_cells','applied_cells','fallback_cells']].sum();year['application_pct']=100*year.applied_cells/year.feature_cells;year['fallback_pct']=100*year.fallback_cells/year.feature_cells
    text+='\n## 연도별 예상 적용률\n\n'+table(year,['year','source','feature_cells','applied_cells','application_pct','fallback_pct'])
    text+='\n특징별 상세 분모·실제 값 변경 셀은 EXPECTED_APPLICATION_RATES.csv, 연도별은 EXPECTED_APPLICATION_RATES_BY_YEAR.csv, 각 사유는 FALLBACK_REASONS.csv에 보존했다. 월별 외부모델의 누적 학습구간 적용률은 EXPECTED_OUTER_TRAINING_USAGE.csv다. 같은 과거행이 여러 월 학습에 재사용되므로 이를 단순 합한 수를 독립 표본 수로 해석하면 안 된다.\n\n'
    text+=f'공통 수집범위의 대만 관측일 불일치는{s["cross_source_disagreement_dates"]}일이다. s13 복제 의심일은 {s["source13_suspected_padding_dates"]}이며 공식 휴장 확정으로 표현하지 않는다. canonical23 값 {s["canonical23_archive_verified"]}/{s["canonical23_rows"]}행이 기존 공식 월별 파일과 일치했다. 현재 archive 일치가 원래 실시간 vintage 입증은 아니다.\n\n'
    text+='## 확인한 것과 남은 가정\n\n정규 거래시간과2019 전송 매뉴얼은 공개 근거다. native 관측의 날짜·중복·필요 값·기존 원본 대조·타임존 변환은 이번 직접 검사다. 마감+2시간의 가용성, 현재 보관 Close의 당시 값 동일성, 실제 벤더 전달은 조건부 가정/미입증이다. 따라서 실행 가능 판정은 **조건부 역사 실험으로 제한된 부분 범위의 구현 가능**을 뜻한다. 실제 운영 시스템의 PIT 복원을 검증한 것은 아니다. 확인되지 않는 현재 관측·필요 값은 기존값 fallback이며 추가 missing flag를 넣지 않는다. 기존 과거값이 결측이면 그대로 결측을 유지하고 기존 fold 전처리를 적용한다.\n\n'
    text+='과거 특별일의 정확한 마감시각을 모른다는 이유만으로 다음 날 이후의 모든 rolling 창을 배제하지 않는다. 반면 해당 관측의 값·세션 자체가 의심되면, 그 값이 실제 필요한 특징에만 전파한다. ret5는현재와5 native 관측 전의 두 값이 직접 입력이며 vol20은21개 Close가 필요하다. 이 입력 차이도 행별 검토표에 남겼다.\n\n'
    text+='## 예상 신규 학습과 해석 범위\n\n'+table(counts,['policy','outer_months','new_fits','reused_models'])
    text+=f'\n예상 신규 학습은 합계 **{int(counts.new_fits.sum())}회**다. 시간 정렬이 바뀌지 않은 누적 학습 X는 기존R0 모델 재사용 대상으로 분류했다. 이 분류는 X의 변경 셀만으로 계산했으며 실제 실행 전 전체 파라미터·학습행/라벨 성숙·환경·입력 해시 검증이 필요하다. 캐시가 맞지 않으면 예산을 자동 확대하지 않고 중단한다. 이번 실제 학습은0회다.\n\n'
    text+='한국은 사전 제한한 일반일 중심 당일 정보의 효과, 대만은2019-04 이후 공식 반도체지수 당일 정보만 바꾸는 정책의 효과를 검증할 수 있다. 두 원천 결합 효과, 한국 제외월·특별일 전체, 대만2011~2019-03의 당일 정보 효과, TWII 효과, 실제 과거 벤더 시스템 성능은 검증할 수 없다. 대만은 초기 학습기에 당일 정렬 적용이 없고 후반에만 적용되는 정책이므로 학습/평가 정보 분포 차이가 남는다. 전체1,007일 성적에서 부분 기간 효과가 희석되며, 이 한계를 성능을 보고 기간을 다시 고르는 이유로 쓰지 않는다.\n\n상세 실행조건은 REVISED_EXPERIMENT_PLAN.md에 고정했다. 계획만 보고하고 멈춘다.\n'
    (O/'A1_PARTIAL_REVIEW.md').write_text(text,encoding='utf-8')
    plan='''# A1 원천별 부분 적용 수정 실험계획 — 미실행

## 상태와 고정 비교

PLAN_ONLY. 새 fit0회, 모델 predict0회, 성능평가0회. 기존 실행은 Accuracy 개선 실패로 보존한다. C1/T1 확대·결합을 금지한다. 아래 두 비교도 합치지 않는다.

1. A1_KR_ONLY: R0의53특징 중 s01 5개만 당일 정렬, 그 외48개는 R0와 완전히 동일.
2. A1_TW23_ONLY: R0의53특징 중 s23 3개만 당일 정렬, 그 외50개는 R0와 완전히 동일. s13은변경하지 않는다.

원천 선택과 적용 범위는 REVIEW_SCOPE.md 및 행별 적용 마스크로 사전에 고정하며 SOX 정답·성능을 사용하지 않았다. 후보의 숫자·기간·가용성 buffer·대상 특징을 결과에 따라 바꾸지 않는다. 한국과 대만을 결합한 후보를 만들지 않는다.

## 불변 조건

SOX 당일 Close>직전 실제 미국 거래일 Close이면Y1, 아니면0. 미국09:00 America/New_York origin,2017~2020의같은1,007일을 유지한다. 초기2011~2016, 이후 expanding 학습·48개월 월간 재학습을 유지한다. 해당 월 첫 실제 거래일09시 이전 성숙 라벨만 학습한다. R0 M1 Logistic C=1, class_weight=None, threshold=.5, seed20261019와 imputer/scaler/기타 전체 파라미터를 고정한다. 각 fold 학습자료만으로 전처리를 fit한다.

각 관측의 same-day 여부를 native 현지 날짜로 판단하고, REVIEW_SCOPE의 원천별 시각과 타임존 변환을 사용한다. 이벤트+2시간은 조건부 가정이며 실제 과거 전달기록이라고 표기하지 않는다. 값은 기존 RAW Close(Adj Close 사용 안 함)와 현재 native rolling 정의로 계산한다. ret1/5/20, vol20(ddof1),ma20_gap 및23 level/delta1/delta5를 새 표현 없이 그대로 유지한다. 휴장/부재/확인불가/필요 입력 이상에는 해당 특징의 원래 R0 값을 그대로 쓴다. 평가일을 줄이거나 RAW행을 삭제하지 않는다. 이전 정책의 staleness>10일 결측을 포함한 fallback 값을 그대로 보존한다.

## 학습 횟수와 캐시

후보별 외부48개월 모델이 필요하지만, 해당 월 학습 X 전체가 R0와 같으면 R0 캐시를 재사용한다. 두 후보끼리는 공유하지 않는다. 월별 예상은 EXPECTED_FIT_BUDGET.csv에 고정했다. 원래 묶음 A1의60회는 내부 고정6개월 모델까지 포함한 예산이었다. 이번 수정안은 C/threshold를 선택하지 않는 고정 정보정렬 비교라 내부 하이퍼파라미터 검증·추가 내부 모델 학습을 하지 않는다. 외부 Accuracy를 이용한 설정 선택도 하지 않는다.

'''
    plan+=table(counts,['policy','outer_months','new_fits','reused_models'])
    plan+=f'\n예상/계획 신규 상한 **{int(counts.new_fits.sum())}회**. KR48회, TW23은 학습자료가 바뀌는 월만 새 fit, 나머지는 기존R0 캐시다. 캐시 불일치나 실패가 발생하면 해당 비교를 중단하고 기록하며 자동 재시도·기간 변경·상한 확대는 하지 않는다. 두 비교 중 하나가 불가능해도 다른 비교까지 자동 폐기하지 않는다. 이번 검토의 실제 fit은0회다.\n\n'
    plan+='''## 향후 실행 전 검증과 보고

- 기존 파일/원본 매니페스트와 이번 고정 마스크·RAW 해시를 확인한다. Y·평가일·origin·학습행·라벨 성숙·기존 캐시 파라미터/전처리를 직접 검증한다.
- 각 후보는 같은 날짜의 항상 상승563/1007(55.91%),R0 549/1007(54.52%),기존 개발 최고567/1007(56.31%) 예측과 비교한다. 비교마다 Accuracy %p와 정답 수 차이, 별도의 초과 여부를 공개한다. 독립 시험이라고 표현하지 않는다.
- pooled 및2017/18/19/20 결과, 원천별 적용률/fallback/사유/변경 셀, 양 클래스Recall·BA/MCC·AUC/Brier/Log loss·학습상승비율q 대조·상승예측 비중을 보고한다. pooledAUC와 연도별AUC를 구분한다.
- 세 기준 모두 동일 날짜의 paired20세션 moving-block bootstrap2,000회 seed20261019 percentile95% CI를 유지한다. 모든 후보와 미개선을 보존하며 보조지표 개선만으로 성공이라 하지 않는다.
- 적용된 하위집합 분석이 필요해도 마스크는 성능을 보기 전 고정된 이번 파일만 사용한다. 전체1,007일 주평가를 대체하지 않는다. 결과를 보고 유리한 연도/원천/계산창을 다시 고르지 않는다.
- 비정상 원본/시간 위반/누락/캐시 불일치 발견 시 관련 비교를 중단한다. 원본을 고치지 않는다. 학습 실패·실제 fit 수·전후 보호 해시를 보존한다.

## 해석의 한계와 종료

조건부 시장정보 가용성 실험이다. 실제 vendor 전달과 원래 vintage 동일성은 미입증이며, 사전 고정된 부분 적용 범위 외로 효과를 일반화할 수 없다. 특히 TW23은 초기 학습기에는 원래 정렬, 후반에만 당일 정렬이 적용돼 cold-start 및 분포 변화가 섞인다.2017~2020의 반복 개발/다수 선택 편향은 유지된다. 이 수정계획이 과거 A1 미실행을 소급 변경하지 않는다.

현재 요청은 이 계획의 보고까지다. 추가 학습·성능평가·금융자료 수집·설치·2021년 이후 평가·1W·Phase3·최종 시험·추가 알고리즘·C1/T1 grid·후보 결합은 수행하지 않는다. 계획 보고 후 멈춘다.
'''
    (O/'REVISED_EXPERIMENT_PLAN.md').write_text(plan,encoding='utf-8')
    es=json.loads((O/'PUBLIC_EVIDENCE.json').read_text());sources='# 공개 근거와 적용 한계\n\n각 항목은 원문을 읽고 요약했다. 신규 금융 가격/API를 요청하지 않았다. 검색 결과에 우연히 포함된 가격표는 입력으로 저장하거나 사용하지 않았다.\n\n'
    for e in es:sources+=f'- **{e["id"]}** [{e["publisher"]}]({e["url"]}), {e["document_date"]}. {e["fact"]} 적용 한계: {e["scope"]}\n\n'
    sources+='Firecrawl 검색은 일부 질의에서 무관한 최신 홈페이지나 다른 연도 결과를 반환해, 공식/참여기관 원문 직접 읽기와 web 검색으로 보완했다. 뉴스·블로그·다른 연구의 주장만으로 휴장이나 오류를 확정하지 않았다.\n'
    (O/'SOURCES.md').write_text(sources,encoding='utf-8')
    # Final re-read preservation, plus all output seal entries.
    before=pd.read_csv(O/'PROTECTED_BEFORE.csv');changed=[]
    for r in before.itertuples():
        p=ROOT/r.path
        if not p.is_file() or p.stat().st_size!=r.bytes or sha(p)!=r.sha256:changed.append(r.path)
    assert not changed,changed
    final=dict(status='PASS',purpose='A1_PARTIAL_FEASIBILITY_AND_REVISED_PLAN_ONLY',protected_files=len(before),changed_existing_files=changed,new_fits=0,new_model_predictions=0,new_performance_evaluations=0,new_financial_series=0,installations=0,SOX_outcomes_used_for_adoption=False,expected_future_new_fits=int(counts.new_fits.sum()),previous_experiment_disposition='Accuracy improvement failed; preserved',old_A1_decision='NOT_EXECUTED preserved',conditional_delivery_only=True,QC_checks=len(pd.read_csv(O/'QC.csv')))
    (O/'FINAL_VERIFICATION.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files=sorted(p for p in O.rglob('*') if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256'])
    pd.DataFrame([dict(path=p.relative_to(O).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]).to_csv(O/'OUTPUT_MANIFEST.csv',index=False,encoding='utf-8-sig')
    (O/'OUTPUT_MANIFEST.sha256').write_text(sha(O/'OUTPUT_MANIFEST.csv')+'  OUTPUT_MANIFEST.csv\n',encoding='ascii')
    print(counts.to_string(index=False));print('PLAN_ONLY PASS; protected',len(before),'unchanged')
if __name__=='__main__':main()
