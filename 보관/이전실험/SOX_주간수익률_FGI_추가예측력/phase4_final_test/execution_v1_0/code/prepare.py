"""필수문서/환경/원본 해시 확인. 시험 CSV는 바이너리 해시만."""
import importlib.metadata,sys
from common import *
ATTACH=Path(r'C:\Users\rudck\.codex\attachments\bae9a6e6-c68b-4307-abc7-a8796cfda4db\Pasted text.txt')
def main():
    for d in ['inputs','config','predictions','metrics','inference','qc','reports','logs/checkpoints']:(OUT/d).mkdir(parents=True,exist_ok=True)
    previous=load(FINAL/'qc/INPUT_MANIFEST.json')['protected_files'];protected=dict(previous)
    manifest=FINAL/'qc/OUTPUT_MANIFEST.json'
    assert sha(manifest)==(FINAL/'qc/OUTPUT_MANIFEST.sha256').read_text().split()[0]
    for x in load(manifest)['files']:assert sha(FINAL/x['path'])==x['sha256']
    for p in FINAL.rglob('*'):
        if p.is_file():protected[p.relative_to(ROOT).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    bad=[r for r,v in protected.items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    assert not bad,bad
    refs=[P1/'PHASE1_LOCKED_SPEC_v1_1.md',P1/'PHASE1_LOCKED_SPEC_v1_1.json',P1/'PHASE1_APPROVED_DECISIONS.json',
        *[BUILD/x for x in ['reports/PHASE2B_REPORT.md','reports/PHASE2B_HANDOFF.md','qc/PHASE2B_OUTPUT_MANIFEST.json']],
        *[D13/x for x in ['D13_LOCKED_POLICY_v1_0.md','D13_LOCKED_POLICY_v1_0.json']],
        *[FINAL/x for x in ['lock/PHASE3_FINAL_LOCK_v1_0.md','lock/PHASE3_FINAL_LOCK_v1_0.json','audit/PHASE4_EXECUTION_SPEC.md','audit/PHASE4_READY_GATE.json']],
        DEV/'config/PHASE3_ENVIRONMENT_LOCK.json',DEV/'inputs/PHASE3_INPUT_MANIFEST.json',DEV/'code/common.py']
    read=[]
    for p in refs:
        t=p.read_text(encoding='utf-8-sig');read.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'characters_read':len(t)})
    save('inputs/USER_PHASE4_AUTHORIZATION.txt',ATTACH.read_text(encoding='utf-8-sig'))
    sealed=load(FINAL/'audit/PHASE4_DATA_SEAL_AUDIT.json')['sealed_files']
    assert len(sealed)==3
    for r in sealed:assert sha(ROOT/r['path'])==r['sha256'] and (ROOT/r['path']).stat().st_size==r['bytes']
    save('inputs/PHASE4_INPUT_MANIFEST.json',{'protected_files':protected,'protected_count':len(protected),'changed':bad,
        'references_read':read,'sealed_files':sealed,'user_authorization_path':str(ATTACH),'user_authorization_sha256':sha(ATTACH),
        'pre_content_access_checked_at_utc':datetime.now(UTC).isoformat(),'test_content_opened':False})
    cp=[(DEV/'code/common.py','phase3_model_core.py'),(D13/'code/synthetic_validation/bootstrap_locked.py','d13_rng_core.py'),
        (D13/'code/synthetic_validation/approved_inference_details.py','d13_approved_details.py')]
    inherited=[]
    for src,name in cp:
        dest=OUT/'code'/name
        with dest.open('xb') as f:f.write(src.read_bytes())
        assert sha(src)==sha(dest);inherited.append({'source':src.relative_to(ROOT).as_posix(),'copy':name,'sha256':sha(src)})
    from phase3_model_core import estimator
    locked=load(FINAL/'lock/PHASE3_FINAL_LOCK_v1_0.json');d13=load(D13/'D13_LOCKED_POLICY_v1_0.json');gate=load(FINAL/'audit/PHASE4_READY_GATE.json')
    assert locked['policy_id']=='C_PHASE3_FINAL_EXPERIMENT_LOCK_v1_0' and locked['status']=='LOCKED_v1_0'
    assert d13['policy_id']=='C_D13_CALENDAR_GRID_MBB_v1_0' and d13['status']=='LOCKED_v1_0'
    assert gate['D10_GATE']=='IMPLEMENTATION_PASS' and gate['PHASE4_PRETEST_AUDIT']=='PASS' and gate['PHASE4_TEST_PERFORMANCE']=='SEALED'
    oldenv=load(DEV/'config/PHASE3_ENVIRONMENT_LOCK.json')
    versions={p:importlib.metadata.version(p) for p in oldenv['packages']};assert versions==oldenv['packages']
    params={}
    for a,v in locked['selected_algorithms'].items():
        params[a]={}
        for info,m in v['models'].items():
            actual=estimator(a,m['hyperparameters']).get_params(deep=False)
            assert actual==locked['estimator_full_parameters'][a][info]
            params[a][info]=actual
    save('config/PHASE4_ENVIRONMENT.json',{'python':sys.version,'executable':sys.executable,'packages':versions,
        'full_estimator_parameters':params,'inherited_code_copies':inherited,'packages_changed':False,'seed':20261016,'workers':1})
    save('config/PHASE4_LOCKED_EXECUTION_CONFIG.json',{'phase3_lock':locked,'D13':d13,
        'phase3_lock_sha256':sha(FINAL/'lock/PHASE3_FINAL_LOCK_v1_0.json'),'D13_lock_sha256':sha(D13/'D13_LOCKED_POLICY_v1_0.json'),
        'approval':'USER_EXPLICIT_PHASE4_EXECUTION','test_files_from_manifest':sealed,
        'stage_order':['preexecution_synthetic_gate','unseal','predict_all_origins','join_outcomes','metrics_and_inference','independent_QC','report'],
        'phase5_authorized':False})
    event('PREPARE_PROTECTED_HASHES_PASSED',protected=len(protected),test_contents_parsed=0)
    print({'pre_integrity':'PASS','protected':len(protected),'model_settings':10,'packages_identical':True,'test_contents_parsed':0})

if __name__=='__main__':main()
