"""Design completeness checks; no model or weekly dataset calculations."""
from pathlib import Path
import csv,hashlib,json
P=Path(__file__).resolve().parents[1];ROOT=P.parents[1]
REQUIRED=['README.md','inputs/PHASE1_INPUT_MANIFEST.json','inputs/RAW_INVENTORY.json',
 'design/PHASE1_RESEARCH_SPEC_DRAFT.json','design/PHASE1_FEATURE_DICTIONARY.csv','design/PHASE1_AVAILABILITY_MATRIX.csv',
 'design/PHASE1_Y_DEFINITION.md','design/PHASE1_FGI_POLICY.md','design/PHASE1_WALKFORWARD_PROTOCOL.md',
 'design/PHASE1_MODEL_COMPARISON_SPEC.md','design/PHASE1_STATISTICAL_TEST_PLAN.md','design/PHASE1_OPEN_DECISIONS.md',
 'design/CONFLICT_REGISTER.md','design/PHASE1_POINT_IN_TIME_PROTOCOL.md','reports/PHASE1_REPORT.md','reports/PHASE1_HANDOFF.md','logs/PHASE1_WORK_LOG.md']
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read_csv(n):
    with (P/n).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
    tests={}; failures=[]
    def check(name,condition):tests[name]=bool(condition);failures.extend([] if condition else [name])
    check('required_outputs_exist',all((P/n).is_file() for n in REQUIRED))
    jsons={f.relative_to(P).as_posix():json.loads(f.read_text(encoding='utf-8')) for f in P.rglob('*.json')}
    check('all_json_valid',bool(jsons))
    spec=jsons['design/PHASE1_RESEARCH_SPEC_DRAFT.json'];manifest=jsons['inputs/PHASE1_INPUT_MANIFEST.json']
    check('phase_requires_approval',spec['phase_status']=='REQUIRES_APPROVAL')
    check('confirmed_target_and_source',spec['confirmed']['target']=='100*(P_sox[w]/P_sox[w-1]-1)' and spec['confirmed']['price']=='02_sox Close')
    check('origin_proposed_timezone',spec['proposed']['origin']['status']=='PROPOSED' and spec['proposed']['origin']['timezone']=='America/New_York')
    dictionary=read_csv('design/PHASE1_FEATURE_DICTIONARY.csv')
    mandatory=['variable_id','economic_rationale','literature_ids','raw_ids','raw_paths','source_columns','original_frequency','unit','formula','weekly_policy','availability_rule','missing_holiday_policy','warmup','vintage_price_adjustment_risk','information_overlap','recommendation','approval_status','open_decisions']
    check('feature_required_fields',all(all(r.get(k) for k in mandatory) for r in dictionary))
    ids=[r['variable_id'] for r in dictionary]
    check('feature_unique_ids',len(ids)==len(set(ids)))
    check('core_exact_B10',set(r['variable_id'] for r in dictionary if r['recommendation']=='PROPOSED_CORE')=={f'B{i}' for i in range(1,11)})
    check('feature_paths_exist',all((ROOT/path).is_file() for r in dictionary for path in r['raw_paths'].split(';')))
    inventory=jsons['inputs/RAW_INVENTORY.json'];rawids={r['dataset_id'] for r in inventory}
    check('raw_ids_resolve',all(x=='FROZEN_PROXY7' or x in rawids for r in dictionary for x in r['raw_ids'].split(';')))
    check('actual_raw47_csv48',len(rawids)==47 and len(inventory)==48)
    availability=read_csv('design/PHASE1_AVAILABILITY_MATRIX.csv')
    check('all_raw_in_availability_matrix',rawids.issubset({r['raw_id'] for r in availability}))
    check('availability_status_vocab',all(r['availability_status'] in ('VERIFIED','CONDITIONAL','UNVERIFIED','NOT_APPLICABLE') for r in availability))
    check('no_unknown_posting_promoted_verified',not any(r['availability_status']=='VERIFIED' for r in availability))
    m0=spec['information_sets']['C-M0'];m1=spec['information_sets']['C-M1']
    check('M0_M1_only_FGI_difference',m1==m0+['F1'] and len(m0)==10)
    check('paired_comparison_conditions',all(spec['comparability'].values()))
    split=spec['proposed']['split']
    check('chronological_split',split['initial'][1]<split['development'][0]<=split['development'][1]<split['test'][0]<=split['test'][1])
    check('split_proposed_not_executed',split['status']=='PROPOSED_NOT_EXECUTED')
    check('no_research_execution',all(v==0 for v in spec['execution_counts'].values()))
    check('future_phase_folders_absent',all(not (P.parent/n).exists() for n in spec['prohibited_future_phase_paths']))
    search=jsons['design/PHASE1_SEARCH_BUDGET_DRAFT.json']
    counts={k:len(v) for k,v in search['algorithms'].items()}
    check('search_candidates_handlisted_budget',counts=={'OLS':1,'Ridge':5,'ElasticNet':4,'RandomForest':4,'HistGradientBoosting':4} and sum(counts.values())==18)
    changes=[];authorized=[]
    for relative,record in manifest['protected_files'].items():
        path=ROOT/relative
        if not path.is_file():changes.append({'file':relative,'reason':'missing'});continue
        current=sha(path)
        if current!=record['sha256']:
            if relative=='RESEARCH_PROJECT_INDEX.md' and hashlib.sha256(path.read_bytes()[:record['bytes']]).hexdigest()==record['sha256']:
                authorized.append({'file':relative,'before':record['sha256'],'after':current,'reason':'authorized append only'})
            else:changes.append({'file':relative,'reason':'unexpected hash change'})
    check('protected_files_unchanged_except_authorized_index_append',not changes)
    result={'phase':1,'design_qc':'QC_PASS' if not failures else 'QC_FAIL','overall_phase_state':'REQUIRES_APPROVAL',
      'test_count':len(tests),'tests':tests,'failures':failures,'feature_definition_candidates':len(dictionary),'core_features':10,'primary_FGI_features':1,
      'availability_rows':len(availability),'protected_files_checked':len(manifest['protected_files']),
      'protected_raw_files_checked':sum(r.startswith('data/raw/') for r in manifest['protected_files']),
      'unexpected_changes':changes,'authorized_index_changes':authorized,'execution_counts':spec['execution_counts'],
      'limits':'Checks design completeness only. No factual historical PIT/weekly sample size/predictive performance validation.'}
    (P/'qc/PHASE1_QC.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'design_qc':result['design_qc'],'tests':len(tests),'failures':failures,'protected':result['protected_files_checked'],'index_append':len(authorized)}))
    assert not failures,failures
if __name__=='__main__':main()
