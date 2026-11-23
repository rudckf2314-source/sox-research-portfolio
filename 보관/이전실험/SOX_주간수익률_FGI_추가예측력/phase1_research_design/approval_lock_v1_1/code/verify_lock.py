"""Automatic approval/schema/protection QC. Does not execute data or model pipelines."""
from pathlib import Path
import hashlib,json,ast
L=Path(__file__).resolve().parents[1];O=L.parent;ROOT=O.parents[1]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    checks={}
    def ck(name,value):checks[name]=bool(value)
    s=load(L/'PHASE1_LOCKED_SPEC_v1_1.json');a=load(L/'PHASE1_APPROVED_DECISIONS.json');g=load(L/'PHASE1_GATE_REGISTER.json')
    decisions={r['decision_id']:r for r in a['decisions']}
    search=load(L/'PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json');oldsearch=load(O/'design/PHASE1_SEARCH_BUDGET_DRAFT.json')
    refs=load(L/'PHASE1_FORMULA_AND_SOURCE_REFERENCES_v1_1.json')
    required=['README.md','PHASE1_APPROVED_DECISIONS.json','PHASE1_LOCKED_SPEC_v1_1.json','PHASE1_LOCKED_SPEC_v1_1.md',
      'PHASE1_GATE_REGISTER.json','PHASE1_CHANGELOG_v1_1.md','reports/PHASE1_LOCK_REPORT.md','reports/PHASE1_LOCK_HANDOFF.md']
    ck('required_design_and_reports_exist',all((L/p).is_file() for p in required))
    ck('all_JSON_parse',all(isinstance(load(p),(dict,list)) for p in L.rglob('*.json')))
    ck('D01_D14_all_present',set(decisions)=={f'D{i:02}' for i in range(1,15)})
    ck('approval_date_KST',a['approval_date_kst']=='2026-10-17' and s['approved_on_kst']=='2026-10-17')
    ck('D04_A_explicit_approved',decisions['D04']['approval_status']=='APPROVED' and decisions['D04']['option']=='A')
    ck('FGI_UNVERIFIED_preserved',s['fgi']['actual_historical_posting_status']=='UNVERIFIED' and s['fgi']['vintage_status']=='UNVERIFIED' and not s['information_availability']['first_vintage_or_publication_verified_by_lag'])
    fields=s['information_availability']['time_fields']
    ck('actual_assumed_and_vintage_fields_separate',all(f in fields for f in ['actual_release_at','actual_available_at','assumed_available_at','availability_basis','vintage_status','assumption_policy_id']))
    ck('approved_origin_strict_boundary',s['origin']['time']=='09:00:00' and s['origin']['timezone']=='America/New_York' and s['origin']['strict_comparator']=='<')
    ck('weekly_signed_Y_unchanged',s['target']['formula']=='100*(P_sox[w]/P_sox[w-1]-1)' and s['target']['frequency']=='NONOVERLAPPING_US_CALENDAR_WEEK' and s['target']['price_source']=='02_sox Yahoo ^SOX Close')
    oldcore={r['variable_id']:r for r in refs['original_formula_records'] if r['variable_id'] in {f'B{i}' for i in range(1,11)}}
    ck('B10_original_formulas_prices_and_units_preserved',len(s['core_variables'])==10 and all(s['core_variables'][i]['formula']==r['formula'] and s['core_variables'][i]['source_columns']==r['source_columns'] and s['core_variables'][i]['unit']==r['unit'] for i,r in oldcore.items()))
    m=s['information_sets'];ck('M0_M1_exact_FGI_addition',m['C-M1']['features']==m['C-M0']['features']+['F1'] and len(m['C-M0']['features'])==10)
    ck('FGI_80_100_and_no_fill',s['fgi']['minimum_valid_fraction']==.8 and s['fgi']['complete_case_sensitivity_fraction']==1 and not any(s['fgi'][f] for f in ['auto_LOCF','interpolation','future_substitution']))
    ck('FGI_base_and_extra_source_lag_separate',s['information_availability']['base_fgi_source_shift_sessions']==0 and s['information_availability']['sensitivity_fgi_source_shift_sessions']==1)
    ck('split_2011_2016_2017_2020_2021_onward',s['split']['initial_years']==[2011,2016] and s['split']['development_years']==[2017,2020] and s['split']['test_years']==[2021,2026] and not s['split']['test_results_for_selection'])
    learn=s['learning'];ck('expanding_calendar5_min156',learn['windows']==['expanding','rolling_5_calendar_years'] and learn['minimum_valid_training_weeks']==156 and not learn['extend_rolling_until_260_rows'])
    ck('Ridge_primary_same_window_tie',learn['primary_algorithm']=='Ridge' and 'Ridge C-M0' in learn['primary_window_selector'] and 'Ridge C-M1' in learn['primary_window_selector'] and learn['window_exact_tie']=='expanding')
    ck('five_algorithms_existing18_exact_candidates',search['algorithms']==oldsearch['algorithms'] and {k:len(v) for k,v in search['algorithms'].items()}=={'OLS':1,'Ridge':5,'ElasticNet':4,'RandomForest':4,'HistGradientBoosting':4} and sum(map(len,search['algorithms'].values()))==18)
    ck('seed_and_budget_meaning_preserved',search['seed']==20261016 and search['candidate_count_per_representation_window']==18 and search['workers']==1 and 'PER information representation' in search['interpretation'])
    inf=s['inference'];ck('HAC_and_sensitivity_approved',inf['HAC']['primary_lag']==4 and inf['HAC']['sensitivity_lags']==[2,8] and inf['alpha']==.05 and inf['confidence_interval']=='two-sided95%')
    ck('bootstrap_and_sensitivity_approved',inf['MBB']['primary_block_weeks']==8 and inf['MBB']['sensitivity_block_weeks']==[4,12] and inf['MBB']['replicates']==5000)
    ck('Holm5_and_conditional_CW',inf['Holm']['m']==5 and not inf['Clark_West']['automatic_MAE_or_nonlinear_application'])
    ck('D10_conditional_gate_pending',decisions['D10']['approval_status']=='APPROVED_CONDITIONAL' and decisions['D10']['validation_status']=='GATE_PENDING' and g['D10_GATE_STATUS']=='PENDING_PHASE2_PREBUILD_AUDIT' and not g['gates']['D10']['passed'] and not g['gates']['D10']['audit_executed'])
    ck('D10_blocks_weekly_prebuild',set(g['gates']['D10']['blocks'])=={'substantive_weekly_XY_build','B10_build','core_common_weekly_sample_build'} and not g['gates']['D10']['generic_D04_assumption_exemption'] and 'B10' in s['information_availability']['not_automatically_applicable_to'])
    ck('D13_deferred_not_passed',decisions['D13']['detail_status']=='DEFERRED_LOCK' and g['D13_GATE_STATUS']=='PENDING_WEEKLY_MISSINGNESS_AUDIT' and not g['gates']['D13']['passed'] and all(v is None for v in g['gates']['D13']['unresolved'].values()))
    ck('D13_before_final_test_errors',g['gates']['D13']['must_lock_before']=='Any access to Phase4 final-test prediction errors or performance results' and inf['MBB']['resample_detail_status']=='DEFERRED_LOCK')
    ck('overall_conditional_not_full_lock',s['status']=='PHASE1_DESIGN_LOCKED_WITH_GATES' and not s['all_gates_passed'] and not g['all_gates_passed'])
    ck('no_Phase2_authorization_or_execution',not s['phase2_execution_approved'] and all(v==0 for v in s['execution_counts'].values()) and not any(p.is_dir() and p.name.startswith(('phase2_','phase3_','phase4_','phase5_')) for p in O.parent.iterdir()))
    snapshot=load(L/'inputs/PHASE1_LOCK_INPUT_MANIFEST.json');changed=[];authorized=[]
    for path,record in snapshot['protected_files'].items():
        p=ROOT/path
        if not p.is_file():changed.append(path);continue
        h=sha(p)
        if h!=record['sha256']:
            if path=='RESEARCH_PROJECT_INDEX.md' and hashlib.sha256(p.read_bytes()[:record['bytes']]).hexdigest()==record['sha256']:authorized.append({'path':path,'original_sha256':record['sha256'],'current_sha256':h,'operation':'authorized append only'})
            else:changed.append(path)
    ck('protected_RAW_freeze_Phase0_Phase1_original_unchanged',not changed)
    ck('approval_verbatim_source_hash',(L/'inputs/USER_APPROVAL_INSTRUCTION.txt').is_file() and sha(L/'inputs/USER_APPROVAL_INSTRUCTION.txt')==snapshot['approval_source_sha256'])
    forbidden=[]
    for p in (L/'code').glob('*.py'):
        for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('fit','predict','fit_transform','pct_change','ewm','rolling','corr','download','history','merge_asof'):forbidden.append((p.name,node.func.attr))
            if isinstance(node,ast.Import):forbidden.extend((p.name,a.name) for a in node.names if a.name.split('.')[0] in ('pandas','numpy','sklearn','statsmodels','yfinance','requests','xgboost','lightgbm'))
    ck('documentation_only_code_calls',not forbidden)
    failures=[k for k,v in checks.items() if not v]
    result={'qc_status':'QC_PASS' if not failures else 'QC_FAIL','overall_status':s['status'],'checks':checks,'test_count':len(checks),'failures':failures,
      'protected_files_checked':len(snapshot['protected_files']),'protected_raw_files_checked':sum(k.startswith('data/raw/') for k in snapshot['protected_files']),
      'protected_original_phase1_files_checked':sum(k.startswith('research_C/phase1_research_design/') for k in snapshot['protected_files']),
      'unauthorized_changes':changed,'authorized_index_append':authorized,'phase2_executed':False,'gate_validation_performed':False,
      'limits':'Approval-document/schema/hash checks; not D10 availability audit, D13 missingness audit, actual weekly data or predictive-performance validation.'}
    if not (L/'qc/LOCK_FINALIZATION.json').exists():
        (L/'qc/PHASE1_LOCK_QC.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'qc':result['qc_status'],'checks':len(checks),'failures':failures,'protected':len(snapshot['protected_files']),'changes':changed,'authorized_index_append':len(authorized)}))
    assert not failures,failures
if __name__=='__main__':main()
