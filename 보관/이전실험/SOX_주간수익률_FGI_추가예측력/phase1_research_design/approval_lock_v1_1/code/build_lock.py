"""Approval documentation only. No transformations, as-of joins, fitting or inference."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,csv

L=Path(__file__).resolve().parents[1];O=L.parent;ROOT=O.parents[1]
STATE='PHASE1_DESIGN_LOCKED_WITH_GATES'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,text):(L/name).write_text(text.strip()+'\n',encoding='utf-8')
def js(name,obj):write(name,json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False))

def main():
    if (L/'qc/LOCK_FINALIZATION.json').exists():raise RuntimeError('v1.1 is sealed; create a separately approved new version instead of overwriting it')
    inputs=read(L/'inputs/PHASE1_LOCK_INPUT_MANIFEST.json')
    draft=read(O/'design/PHASE1_RESEARCH_SPEC_DRAFT.json')
    search=read(O/'design/PHASE1_SEARCH_BUDGET_DRAFT.json')
    with (O/'design/PHASE1_FEATURE_DICTIONARY.csv').open(encoding='utf-8-sig') as f:dictionary=list(csv.DictReader(f))
    with (O/'design/PHASE1_AVAILABILITY_MATRIX.csv').open(encoding='utf-8-sig') as f:availability=list(csv.DictReader(f))
    topics={r['id']:r['topic'] for r in draft['open_decisions']}
    summaries={
      'D01':'대상 주 첫 미국 주식시장 거래일09:00 America/New_York, 실제 공휴일/DST, 엄격한 이전시각 비교 승인.',
      'D02':'기존 B1~B10 구성/산식 채택. B3 ddof1 비연율화, RSI14 Wilder SMA seed와0분모 규칙, HYG Adj Close, DGS10 bp 유지. D10 미해결.',
      'D03':'F1 직전 완료 주 적격 일별 점수 평균, ceil(.8*N_expected); 완전관측100% 민감도. 무보간/미래값/자동LOCF 금지. 현재03/12=21.15 존재 유지.',
      'D04':'A안 가정 기반 역사적 표본외 연구 최종 승인. 실제 시각과 가정 시각을 분리하고 UNVERIFIED/vintage 한계 및 추가1세션 민감도 유지.',
      'D05':'대상 미국 주 월요일 기준2011~2016 초기,2017~2020 개발,2021~2026 마지막Y완료주 시험. 현행 상한10/05주/10/09종료, 실제 표본수 미산출.',
      'D06':'Expanding 대 최근5달력년 Rolling, 최소156유효주. 결손 때문에260행을 채우도록 창 연장 금지. 미달원점은 미예측/쌍별제외로 기록.',
      'D07':'OLS1,Ridge5,ElasticNet4,RF4,HistGradientBoosting4의 합계18후보, 기존 실제 조합 유지. seed20261016, 공정한 탐색 예산,0/학습평균 기준.',
      'D08':'MAE 주지표,RMSE/학습평균기준OOS R²/방향정확도. HAC4/민감도2·8,block8/민감도4·12,5000회,단측.05,양측95%CI,Holm5종. D13 상세 미잠금.',
      'D09':'C-M2/3 심리그룹 AAIIspread+CPCE+NYSE신고저, C-M4/5 업종그룹 SOXX+TSM+대만반도체 조건부 채택. 원래 산식/별도 시점검증 유지. 나머지 탐색 보류.',
      'D10':'B10 정의는 유지하되 H15 공표시점 사전감사는 아직 미실시. Phase2 승인 후 주간X/Y 본격 생성 전에 필수 감사. 유지 불가시 중단/별도승인.',
      'D11':'사전 주력 Ridge 확정. Ridge C-M0의 개발MAE로 창을 정해 Ridge M0/M1에 공유, 창동점Expanding. 다른4종도 사전 쌍비교/전부보고; 시험최저모델로 주력교체 금지.',
      'D12':'미국 월요일 주 식별,실제 첫/끝 세션/휴일/조기종료,연말주 불분할,종가 결손시 다른 주 연결 금지,미완성Y 제외.',
      'D13':'원래 미국 달력주 격자/8주블록/유효n가변 기록 방향 승인. n하한/부족·빈반복/재추출 최대횟수·실패처리는 미확정이며 시험오차 열람전 후속잠금.',
      'D14':'actual_available_at < prediction_origin. 동시각은 별도 이전수신 증거 없으면 제외. 미확인 시각은 D04 assumed필드로 분리.'}
    decisions=[]
    for i in range(1,15):
        did=f'D{i:02}';conditional=did in ['D02','D08','D09','D10','D13']
        row={'decision_id':did,'topic':topics[did],'approval_status':'APPROVED_CONDITIONAL' if conditional else 'APPROVED',
             'approved_on_kst':'2026-10-17','approved_by':'USER_EXPLICIT_ATTACHED_INSTRUCTION','decision':summaries[did],
             'source_draft_status':'REQUIRES_APPROVAL','gate_refs':(['D10'] if did in ['D02','D10'] else ['D13'] if did in ['D08','D13'] else []),
             'does_not_authorize_phase2_execution':True}
        if did=='D10':row.update(validation_status='GATE_PENDING',gate_status='PENDING_PHASE2_PREBUILD_AUDIT',passed=False)
        if did=='D13':row.update(basic_direction='APPROVED',detail_status='DEFERRED_LOCK',gate_status='PENDING_WEEKLY_MISSINGNESS_AUDIT',passed=False)
        if did=='D04':row.update(option='A',historical_posting_status='UNVERIFIED',vintage_status='UNVERIFIED')
        decisions.append(row)
    js('PHASE1_APPROVED_DECISIONS.json',{'schema_version':'1.1','overall_status':STATE,'approval_date_kst':'2026-10-17',
        'approval_evidence':{'path':inputs['approval_source_path'],'sha256':inputs['approval_source_sha256'],'verbatim_copy':'inputs/USER_APPROVAL_INSTRUCTION.txt'},
        'source_design':{'version':draft['version'],'path':str(O/'design/PHASE1_RESEARCH_SPEC_DRAFT.json'),'sha256':sha(O/'design/PHASE1_RESEARCH_SPEC_DRAFT.json')},
        'decisions':decisions,'phase2_execution_approved':False})

    gates={'D10':{'decision_status':'APPROVED_CONDITIONAL','validation_status':'GATE_PENDING',
       'gate_status':'PENDING_PHASE2_PREBUILD_AUDIT','passed':False,'audit_executed':False,
       'required_when':'First work after explicit Phase2 execution approval, before substantive weekly X/Y generation',
       'blocks':['substantive_weekly_XY_build','B10_build','core_common_weekly_sample_build'],
       'audit_deliverables':['H15 official rules and evidence','actual/assumed historical eligibility adjudication method, separately labeled',
          'valid source observations for prior and previous calendar weeks','unknown and missingness risks','common-week sample impact',
          'whether original B10 formula can be maintained','whether a policy change requires user approval'],
       'pass_requires':'Documented prebuild audit preserving original B10 definition; assumption method if used must be explicit and cannot be silently supplied by D04 generic daily policy',
       'failure_action':'Stop B10/core-common-sample build, report cause/impact, request separate approval. No automatic removal/replacement/imputation.',
       'current_B10_formula':next(r['formula'] for r in dictionary if r['variable_id']=='B10'),
       'generic_D04_assumption_exemption':False},
      'D13':{'decision_status':'APPROVED_CONDITIONAL','basic_direction':'APPROVED','detail_status':'DEFERRED_LOCK',
       'gate_status':'PENDING_WEEKLY_MISSINGNESS_AUDIT','passed':False,'audit_executed':False,
       'required_input':'Phase2 actual calendar-week missingness and valid paired sample counts',
       'must_lock_before':'Any access to Phase4 final-test prediction errors or performance results',
       'blocks':['bootstrap_inference','Phase4_final_test_error_or_performance_access_until_detail_policy_locked'],
       'unresolved':{'minimum_valid_resample_n':None,'insufficient_resample_action':None,'empty_resample_action':None,'max_redraw_attempts':None,'redraw_failure_action':None},
       'locked_direction':{'calendar_grid':'original America/New_York calendar weeks; never compress missing weeks','block_weeks':8,'variable_valid_n_per_replicate_recorded':True},
       'pass_requires':'Separate documented detail policy locked after actual Phase2 missingness audit and before Phase4 error/performance access; no result-dependent changes',
       'failure_action':'Do not run inference or inspect Phase4 errors/metrics; report unresolved detail gate.'}}
    js('PHASE1_GATE_REGISTER.json',{'overall_status':STATE,'D10_GATE_STATUS':gates['D10']['gate_status'],'D13_GATE_STATUS':gates['D13']['gate_status'],'all_gates_passed':False,'gates':gates})

    assumption={
      'research_mode':'APPROVED_ASSUMPTION_BASED_HISTORICAL_OOS_NOT_VERIFIED_REALTIME_PIT',
      'base_policy_id':'C_DAILY_EOD_NEXT_US_SESSION_0800_ET_v1_1',
      'base_fgi_source_shift_sessions':0,'sensitivity_fgi_source_shift_sessions':1,
      'assumed_available_at_rule':'For a completed daily source session d, next actual US equity session strictly after d at 08:00 America/New_York. This is an operational assumption, not evidence of publication.',
      'rationale':'Completed prior session only; at least overnight/weekend/holiday delay and one hour before 09:00 origin. Actual longer publication delays remain possible and are not disproved.',
      'applies_to':['B1','B2','B3','B4','B5','B6','B7','B8','B9','F1','F_LAST','F_DELTA','F_LAG1'],
      'not_automatically_applicable_to':['B10','H15','H10','NFCI','AAII','monthly_industry_macro','French_reconstructed_files','FOMC_schedule'],
      'B10_policy':'Gate D10 required; no assumed H15 timestamp or forced Friday inclusion established by this lock',
      'time_fields':{
         'actual_release_at':'Direct release evidence only; null if unknown',
         'actual_available_at':'Direct evidence of usable availability; null if unknown; not identical to release by default',
         'assumed_available_at':'Documented versioned assumption only; never copied into actual fields',
         'availability_basis':['VERIFIED_ACTUAL','ASSUMED_CONSERVATIVE','UNAVAILABLE'],
         'publication_status':'UNVERIFIED for unknown historical posting, even if assumed eligible',
         'vintage_status':'Independent vintage evidence flag; UNVERIFIED remains UNVERIFIED',
         'assumption_policy_id':'Required for any ASSUMED_CONSERVATIVE row; null for actual-only or unavailable row'},
      'adjudication':[
        'Require actual completed source period and correct source observation date.',
        'If actual usable availability is directly verified, use strict actual_available_at < origin; equality excluded absent separate earlier-receipt evidence.',
        'If actual usable availability is unknown and approved daily policy applies, test assumed_available_at < origin; leave actual fields null if unknown and basis ASSUMED_CONSERVATIVE.',
        'Any known actual release/embargo later than or equal to origin is a veto; never allow an earlier assumption to override known late publication.',
        'If partial actual evidence is later than the assumed time, use the later known lower bound for eligibility and keep assumed status; no claim of verified provider readiness.',
        'If calendars/source date/scheduled EOD status cannot be resolved, or no applicable approved assumption exists, mark UNAVAILABLE. No automatic nearest-date fill.'
      ],
      'source_observation_vs_publication_week':'F1 targets observation labels in the previous completed US calendar week. With this assumption Friday may be assumed usable on next Monday/next open day 08:00. Do not describe such a timestamp as actually published in the prior week.',
      'actual_evidence_does_not_prove_first_vintage':True,
      'holiday_rule':'next_US_session / previous_US_session uses actual historical US equity calendar including extraordinary closures, not weekday arithmetic. DST uses America/New_York.',
      'out_of_schedule_scores':'Scores labeled weekends/US holidays are not automatically counted as expected equity-session observations. Preserve/review separately; do not silently move to adjacent session.',
      'missed_expected_publication':'If a target source session has no valid score or known publication is too late, count missing in N_expected denominator. No carry, interpolation, or substitution.',
      'sensitivity_rule':'For every target session d in previous-week S, use source=previous_US_session(d,1), then apply that source date availability rule. Same N_expected and 80%/100% thresholds. No repeated shift until a valid value is found.',
      'required_lineage':['prediction_week_start','prediction_origin_ET','target_session_date','source_observation_date','actual_release_at','actual_available_at','assumed_available_at','availability_basis','publication_status','vintage_status','assumption_policy_id','source_shift_sessions','included_or_excluded','exclusion_reason','source_week_differs_from_target_week','assumed_available_week_differs_from_observation_week'],
      'first_vintage_or_publication_verified_by_lag':False,
      'label_maturity':'Prior target-week label must be completed and available before training origin. Direct timestamp if evidenced; otherwise separately tagged C_LABEL_EOD_NEXT_US_SESSION_0800_ET_v1_1 assumption. No actual timestamp fabrication.'}

    core={r['variable_id']:deepcopy(r) for r in dictionary if r['variable_id'] in [f'B{i}' for i in range(1,11)]}
    for fid,row in core.items():
        row['approval_status']='APPROVED_CONDITIONAL' if fid=='B10' else 'APPROVED'
        row['raw_formula_preserved_from_v1_0']=True
        row['availability_rule_v1_1']='D10 gate; actual eligible H15 releases only under audited adjudication' if fid=='B10' else 'D04 separate actual/assumed strict-before-origin adjudication'
        row['approval_note']='Old source wording retained as source annotation; current operative approval is this v1.1 record.'
    core['B3']['approved_numeric_policy']={'daily_return_unit':'percent','ddof':1,'annualized':False,'minimum_daily_returns':2}
    core['B4']['approved_numeric_policy']={'method':'Wilder','period':14,'seed':'SMA of first14 consecutive valid price changes','price_points_required':15,
       'mean_loss_zero_mean_gain_positive':100,'mean_gain_zero_mean_loss_positive':0,'both_zero':50,'internal_missing_session_price':'reset state; acquire14 new valid changes; no skip or fill'}
    core['B10']['gate_status']='PENDING_PHASE2_PREBUILD_AUDIT'
    locked_search=deepcopy(search);locked_search['status']='APPROVED';locked_search['approved_on_kst']='2026-10-17'
    locked_search['interpretation']='18 total candidate configurations summed across five algorithms, PER information representation PER learning window PER development origin; not18 per algorithm and not18 total estimator fits.'
    js('PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json',locked_search)
    info={
      'C-M0':{'features':[f'B{i}' for i in range(1,11)],'status':'APPROVED_CONDITIONAL','conditions':['D10']},
      'C-M1':{'features':[f'B{i}' for i in range(1,11)]+['F1'],'status':'APPROVED_CONDITIONAL','conditions':['D10','D04_ASSUMPTION_LABELS']},
      'C-M2':{'features':[f'B{i}' for i in range(1,11)]+['S_AAII','S_CPCE','S_HIGHLOW'],'status':'APPROVED_CONDITIONAL','conditions':['D10','group_source_availability_and_original_formula_checks']},
      'C-M3':{'features':[f'B{i}' for i in range(1,11)]+['S_AAII','S_CPCE','S_HIGHLOW','F1'],'status':'APPROVED_CONDITIONAL','conditions':['D10','group_source_availability_and_original_formula_checks','D04_ASSUMPTION_LABELS']},
      'C-M4':{'features':[f'B{i}' for i in range(1,11)]+['I_SOXX','I_TSM','I_TWSE'],'status':'APPROVED_CONDITIONAL','conditions':['D10','group_source_availability_and_original_formula_checks']},
      'C-M5':{'features':[f'B{i}' for i in range(1,11)]+['I_SOXX','I_TSM','I_TWSE','F1'],'status':'APPROVED_CONDITIONAL','conditions':['D10','group_source_availability_and_original_formula_checks','D04_ASSUMPTION_LABELS']}}
    spec={'schema_version':'1.1','study':'C','title':draft['title'],'status':STATE,'approved_on_kst':'2026-10-17',
      'approval_source':{'path':inputs['approval_source_path'],'sha256':inputs['approval_source_sha256']},
      'source_design':{'version':draft['version'],'path':inputs['source_design_path'],'sha256':sha(O/'design/PHASE1_RESEARCH_SPEC_DRAFT.json')},
      'source_plan':{'path':inputs['source_plan_path'],'sha256':sha(ROOT/'Research_C_Study_Plan_v1_20261016.md')},
      'decisions_file':'PHASE1_APPROVED_DECISIONS.json','gate_register':'PHASE1_GATE_REGISTER.json',
      'phase2_execution_approved':False,'all_gates_passed':False,'locked_approved_parts_only':True,
      'target':{'formula':draft['confirmed']['target'],'price_source':'02_sox Yahoo ^SOX Close','frequency':'NONOVERLAPPING_US_CALENDAR_WEEK',
                'week_start':'Monday America/New_York','week_end':'next Monday exclusive','year_assignment':'week_start.year','prices':'last actual session Close in each consecutive calendar week',
                'skip_missing_week':False,'label_end_session_limit':'2026-10-09','last_complete_week_candidate':'2026-10-05','actual_valid_sample_size':None},
      'origin':{'day':'first actual US equity session in target calendar week','time':'09:00:00','timezone':'America/New_York','dst':True,'strict_comparator':'<','status':'APPROVED'},
      'core_variables':core,'fgi':{'primary_id':'F1','scale':[0,100],'formula':next(r['formula'] for r in dictionary if r['variable_id']=='F1'),
          'target_observation_week':'previous completed US calendar week','minimum_valid_fraction':.8,'minimum_valid_count_rule':'ceil(0.8*N_expected)',
          'N_expected':'actual US equity sessions in previous calendar week, not calendar days or observed nonmissing rows',
          'empty_week_or_zero_valid':'N_expected<=0 or n_valid<=0 means unavailable, never divide by zero or create a synthetic observation',
          'complete_case_sensitivity_fraction':1.0,'auto_LOCF':False,'interpolation':False,'future_substitution':False,
          'actual_historical_posting_status':'UNVERIFIED','vintage_status':'UNVERIFIED','known_20260312':{'score':21.15,'status':'PRESENT_IN_CURRENT_SOURCE; not new restoration or proof of posting'},
          'source_conflict_policy':'retain existing canonical CSV and its documented 2026-10-06 local-priority history; do not modify source'},
      'information_availability':assumption,'information_sets':info,'comparability':deepcopy(draft['comparability']),
      'split':{'assignment_key':'target local Monday week_start','initial_years':[2011,2016],'development_years':[2017,2020],'test_years':[2021,2026],
               'week_start_ranges':{k:v for k,v in draft['proposed']['split'].items() if k in ['initial','development','test']},
               'test_end_rule':'last actual SOX Y-complete week within frozen raw; current candidate2026-10-05/10-09',
               'test_results_for_selection':False,'actual_sample_count_pending_Phase2':True},
      'learning':{'windows':['expanding','rolling_5_calendar_years'],'minimum_valid_training_weeks':156,'extend_rolling_until_260_rows':False,
          'insufficient_training':'record NOT_PREDICTED_INSUFFICIENT_TRAINING; omit same week from paired score; report count, never silently change model/window',
          'label_maturity_required':True,'fixed_5day_or_5row_purge':False,'weekly_refit_with_matured_labels':True,
          'primary_algorithm':'Ridge','primary_window_selector':'Ridge C-M0 pooled MAE over2017-2020 only; share chosen window with Ridge C-M1',
          'other_algorithm_window_selector':'retain original per-algorithm C-M0 development pooled-MAE rule; share with its own C-M1. Ridge window is not silently imposed on other algorithms.',
          'window_exact_tie':'expanding','candidate_exact_tie':'candidate_id ascending','candidate_selection':'same frozen candidate set and pooled development MAE per representation; no test-driven selection',
          'linear_scaling':'train-only StandardScaler + intercept for OLS/Ridge/ElasticNet','tree_scaling':'native feature scales for RF/HistGradientBoosting',
          'PCA':'not part of Research C primary specification','negative_prediction_clipping':False,'single_trial_or_test_winner_replaces_Ridge':False},
      'search':{'config_file':'PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json','source_sha256':sha(O/'design/PHASE1_SEARCH_BUDGET_DRAFT.json'),
                'algorithms':list(search['algorithms']),'candidate_counts':{k:len(v) for k,v in search['algorithms'].items()},'sum_candidates_per_representation_window':18,'seed':20261016,'workers':1,
                'primary_budget_formula':'18*2 representations*2 windows*N_development_origins','actual_fits_executed':0,
                'extension_budget':'paired equivalent original candidate configurations if extension later executed; no additional candidate combinations authorized'},
      'evaluation':{'primary':'MAE (%p)','secondary':['RMSE (%p)','OOS_R2_vs_origin_training_mean','direction_accuracy'],
          'delta_MAE':'MAE(C-M0)-MAE(C-M1)','positive_delta_favors_FGI':True,
          'OOS_R2':'1-sum((Y-forecast)^2)/sum((Y-origin_train_mean)^2)','direction':'sign(forecast)==sign(Y); sign(0)=0; disclose zero and nonzero actual counts',
          'baselines':['zero_return','origin_training_Y_mean'],'evaluation_same_weeks_for_pair':True},
      'inference':{'hypotheses':{'null':'E[d]<=0','alternative':'E[d]>0'},'loss_difference':'abs(Y-f0)-abs(Y-f1)','alpha':.05,'test_direction':'one-sided improvement','confidence_interval':'two-sided95%',
          'HAC':{'kernel':'Bartlett','lag_unit':'original calendar-week distance','primary_lag':4,'sensitivity_lags':[2,8],'small_sample_correction':False,'details_source':str(O/'design/PHASE1_STATISTICAL_TEST_PLAN.md')},
          'MBB':{'primary_block_weeks':8,'sensitivity_block_weeks':[4,12],'replicates':5000,'seed':20261016,'calendar_grid_preserved':True,
                  'paired_dates_and_errors_together':True,'variable_valid_n_recorded':True,'resample_detail_status':'DEFERRED_LOCK','detail_gate':'D13',
                  'minimum_valid_resample_n':None,'insufficient_resample_action':None,'empty_resample_action':None,'max_redraw_attempts':None,'redraw_failure_action':None},
          'Holm':{'family':'five algorithm C-M0 vs C-M1 paired comparisons at their predeclared selected windows','m':5,'alpha':.05,'report_raw_and_adjusted_p':True,'Ridge_primary_distinct_from_five_algorithm_family':True},
          'Clark_West':{'role':'conditional secondary only','models':'nested linear OLS C-M0/C-M1 on identical training samples','loss':'squared error','formula':'e0^2-(e1^2-(f0-f1)^2)',
                        'automatic_MAE_or_nonlinear_application':False,'invalid_assumptions':'NOT_APPLICABLE'},
          'subperiods':[[2021,2022],[2023,2026]],'causal_claim':False,'result_dependent_changes':False},
      'gate_status':{'D10_GATE_STATUS':'PENDING_PHASE2_PREBUILD_AUDIT','D13_GATE_STATUS':'PENDING_WEEKLY_MISSINGNESS_AUDIT'},
      'preserved_limitations':['historical original posting/vintages UNVERIFIED','current revised/adjusted source files','prior market-period research exposure','no claim of newly independent first test'],
      'execution_counts':deepcopy(draft['execution_counts']),
      'prohibited':['RAW download/change','CNN modification','weekly X/Y creation','actual as-of merge','model fit/tuning/predictions/performance','Phase2 directory creation/execution','old report overwrite','D10/D13 passed declaration']}
    js('PHASE1_LOCKED_SPEC_v1_1.json',spec)
    js('PHASE1_FORMULA_AND_SOURCE_REFERENCES_v1_1.json',{'source_feature_dictionary':{'path':str(O/'design/PHASE1_FEATURE_DICTIONARY.csv'),'sha256':sha(O/'design/PHASE1_FEATURE_DICTIONARY.csv')},
       'original_formula_records':dictionary,'approval_scope':'Core B10 and F1 approved as above; exact S_AAII/S_CPCE/S_HIGHLOW/I_SOXX/I_TSM/I_TWSE formulas conditionally adopted, other records remain separate exploratory candidates',
       'availability_reference':{'path':str(O/'design/PHASE1_AVAILABILITY_MATRIX.csv'),'sha256':sha(O/'design/PHASE1_AVAILABILITY_MATRIX.csv')},
       'historical_status_records_unchanged':availability,'v1_1_overlay':'Assumed eligibility does not change these historical verification flags. B10 remains gated.'})
    print('Approval decisions14, v1.1 spec, gates2, original18 candidates and source references written. No Phase2 execution.')
if __name__=='__main__':main()
