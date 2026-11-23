"""Gate A: 내용열람 범위를 제한한 시점/후보/해시 사전 검증."""
import io,platform,importlib.metadata,time
from common import *
def main():
    for d in ['inputs','config','predictions','metrics','selection','qc','reports','logs/checkpoints']:(OUT/d).mkdir(parents=True,exist_ok=True)
    prior=load(D13/'qc/D13_LOCK_INPUT_MANIFEST.json')['protected_files'];protected=dict(prior)
    seal=D13/'qc/D13_LOCK_OUTPUT_MANIFEST.json'
    assert sha(seal)==(D13/'qc/D13_LOCK_OUTPUT_MANIFEST.sha256').read_text().split()[0]
    for x in load(seal)['files']:assert sha(D13/x['path'])==x['sha256']
    for p in D13.rglob('*'):
        if p.is_file():protected[p.relative_to(ROOT).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    changed=[p for p,v in protected.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=v['sha256']]
    assert not changed,changed
    refs=[ROOT/'Research_C_Study_Plan_v1_20261016.md',
        *[LOCK/x for x in ['PHASE1_LOCKED_SPEC_v1_1.md','PHASE1_LOCKED_SPEC_v1_1.json','PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json',
            'PHASE1_APPROVED_DECISIONS.json','PHASE1_GATE_REGISTER.json','PHASE1_FORMULA_AND_SOURCE_REFERENCES_v1_1.json']],
        *[LOCK.parent/'design'/x for x in ['PHASE1_WALKFORWARD_PROTOCOL.md','PHASE1_MODEL_COMPARISON_SPEC.md']],
        *[BUILD/x for x in ['reports/PHASE2B_REPORT.md','reports/PHASE2B_HANDOFF.md','data/WEEKLY_DATA_DICTIONARY.md','qc/PHASE2B_OUTPUT_MANIFEST.json']],
        D13/'D13_LOCKED_POLICY_v1_0.md',D13/'D13_LOCKED_POLICY_v1_0.json',D13/'D13_GATE_STATUS.json']
    read=[]
    for p in refs:
        t=p.read_text(encoding='utf-8-sig');read.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'text_characters_read':len(t)})
        if p.suffix=='.json':load(p)
    save('inputs/PHASE3_INPUT_MANIFEST.json',{'protected_files':protected,'protected_count':len(protected),'changed':changed,
        'references_read':read,'data_sha256':sha(DATA),'created_at_utc':datetime.now(UTC).isoformat()})
    spec=load(LOCK/'PHASE1_LOCKED_SPEC_v1_1.json');grid=load(LOCK/'PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json')
    assert {a:len(v) for a,v in grid['algorithms'].items()}=={'OLS':1,'Ridge':5,'ElasticNet':4,'RandomForest':4,'HistGradientBoosting':4}
    assert sum(map(len,grid['algorithms'].values()))==18
    assert spec['learning']['candidate_selection']=='same frozen candidate set and pooled development MAE per representation; no test-driven selection'
    assert load(D13/'D13_GATE_STATUS.json')['D13_LOCK_STATUS']=='LOCKED_v1_0'
    save('config/PHASE3_APPROVED_SEARCH_GRID.json',grid)
    defaults={a:{c['candidate_id']:estimator(a,c).get_params(deep=False) for c in candidates} for a,candidates in grid['algorithms'].items()}
    save('config/PHASE3_ENVIRONMENT_LOCK.json',{'python':sys.version,'executable':sys.executable,
        'packages':{p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','scikit-learn','threadpoolctl','python-dateutil']},
        'explicit_and_default_estimator_params':defaults,'thread_environment':{k:os.environ[k] for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']},
        'existing_environment_modified':False,'default_semantics':'Phase1はバージョン未固定、現行引数既定を実行前記録'})
    df=read_data();assert not df.week_start.duplicated().any() and np.isfinite(df[FEATURES+['Y']].to_numpy()).all()
    assert set(df.split)=={'initial_train','development'} and (df.Y<0).any() and (df.Y>0).any()
    # Read only permitted historical records of mixed availability file. At first test date,
    # stop after date prefix BEFORE decoding or parsing the remaining test row.
    avail=BUILD/'availability/FEATURE_AVAILABILITY_LOG.csv';lines=[];first_test_prefix=None
    with avail.open('rb') as f:
        header=f.readline().decode('utf-8-sig');lines.append(header)
        while True:
            prefix=f.read(10)
            if not prefix:break
            if prefix>=b'2021-01-01':first_test_prefix=prefix.decode('ascii');break
            lines.append((prefix+f.readline()).decode('utf-8'))
    logs=list(csv.DictReader(io.StringIO(''.join(lines))));valid=set(df.week_start)
    logs=[r for r in logs if r['week_start'] in valid]
    assert len(logs)==517*11
    violation=[]
    for r in logs:
        origin=pd.Timestamp(r['prediction_origin']).tz_convert('UTC')
        actual=r['actual_available_at']
        effective=actual if actual not in ('null','','None') else r['latest_assumed_available_at']
        if not (r['valid']=='True' and pd.Timestamp(effective).tz_convert('UTC')<origin and r['source_period_complete']=='True'):
            violation.append([r['week_start'],r['feature_id']])
        assert r['publication_status']=='UNVERIFIED' and r['vintage_status']=='UNVERIFIED'
    assert not violation,violation[:10]
    # Exact historical X lineage for independent checks, no test records.
    csvsave('inputs/TRAIN_DEV_FEATURE_AVAILABILITY.csv',logs)
    counts=[]
    for i in np.flatnonzero((df.split=='development').to_numpy()):
        for window in spec['learning']['windows']:
            ids,cutoff=training_indices(df,i,window)
            assert len(ids)>=156 and i not in ids and (df.iloc[ids].label_utc<df.iloc[i].origin_utc).all()
            counts.append({'week_start':df.iloc[i].week_start,'window':window,'n':len(ids),
                'train_start':df.iloc[ids[0]].week_start,'train_end':df.iloc[ids[-1]].week_start,
                'cutoff':cutoff.isoformat() if cutoff else None})
    save('qc/GATE_A.json',{'status':'PASS','initial_valid':308,'development_valid':209,'combined':517,
        'lineage_records_checked':len(logs),'availability_violations':violation,'counts':counts,
        'actual_publication_and_vintage':'UNVERIFIED; only approved assumptions verified'})
    save('inputs/PHASE3_DATA_ACCESS_AUDIT.json',{'parsed_CSV':[str(DATA.relative_to(ROOT)),str(avail.relative_to(ROOT))],
        'availability_read_policy':'mixed log binary 10-byte week prefix gate; first test row date prefix only, remaining content not decoded/parsed',
        'first_excluded_date_prefix':first_test_prefix,'parsed_week_range':['2011-01-03','2020-12-28'],
        'sealed_test_CSV_parsed':0,'test_Y_values_read':0,'test_files_binary_hash_only':True})
    save('config/PHASE3_EXPERIMENT_CONFIG.json',{'stage':'PHASE3_DEVELOPMENT_ONLY','seed':20261016,'workers':1,
        'features':{'C-M0':FEATURES[:10],'C-M1':FEATURES},'planned_estimator_fits':15048,
        'windows':spec['learning']['windows'],'minimum_train_n':156,
        'rolling_cutoff':'training row prediction_origin >= current origin minus 5 calendar years in America/New_York; strict label_available_at < origin',
        'candidate_selection':'per algorithm / information_set / window pooled MAE; exact candidate_id tie ascending',
        'window_selection':'minimum candidate C-M0 pooled MAE per window; tie expanding; pair shares window',
        'resolution':'v1.1 learning.candidate_selection explicitly per representation; no same-parameter restriction. Old gate timestamps retain history; latest D10/D13 and current user authorize Phase3 only.',
        'direction':'sign(prediction)==sign(Y); sign(0)=0','phase4_authorized':False,
        'linear_preprocessing':'train-only StandardScaler with intercept','tree_preprocessing':'native scale; no imputation; no PCA'})
    print({'GATE_A':'PASS','rows':517,'origins':209,'lineage':len(logs),'protected':len(protected),
        'train_n_range':{w:[min(r['n'] for r in counts if r['window']==w),max(r['n'] for r in counts if r['window']==w)] for w in spec['learning']['windows']}})

if __name__=='__main__':main()
