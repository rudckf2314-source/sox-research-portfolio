"""필수 입력 실제 열람, 기존 후보와 보호자료 검증 및 신규 승인 내용 준비."""
import copy,platform
from datetime import datetime,timezone
import numpy as np
from common import OUT,CAND,ROOT,BUILD,PHASE1,load,sha,write

def main():
    for name in ['qc','reports','logs']:(OUT/name).mkdir(exist_ok=True)
    prior=load(CAND/'inputs/D13_INPUT_MANIFEST.json')['protected_files']
    assert all((ROOT/p).exists() and sha(ROOT/p)==v['sha256'] for p,v in prior.items())
    cm=CAND/'qc/D13_OUTPUT_MANIFEST.json'
    assert sha(cm)==(CAND/'qc/D13_OUTPUT_MANIFEST.sha256').read_text().split()[0]
    for x in load(cm)['files']:assert sha(CAND/x['path'])==x['sha256'],x['path']
    protected=dict(prior)
    for p in CAND.rglob('*'):
        if p.is_file() and OUT not in p.parents:
            protected[p.relative_to(ROOT).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    refs=[PHASE1/'PHASE1_LOCKED_SPEC_v1_1.md',PHASE1/'PHASE1_LOCKED_SPEC_v1_1.json',
        PHASE1/'PHASE1_APPROVED_DECISIONS.json',PHASE1/'PHASE1_GATE_REGISTER.json',
        PHASE1.parent/'design/PHASE1_STATISTICAL_TEST_PLAN.md',
        *[BUILD/'reports'/x for x in ['PHASE2B_REPORT.md','PHASE2B_MISSINGNESS_REPORT.md','PHASE2B_HANDOFF.md']],
        *[CAND/x for x in ['policy/D13_LOCK_CANDIDATE.md','policy/D13_LOCK_CANDIDATE.json',
            'reports/D13_POLICY_REVIEW_REPORT.md','reports/D13_APPROVAL_REQUEST.md','qc/D13_INDEPENDENT_QC.md',
            'qc/D13_SYNTHETIC_TEST_RESULTS.json','qc/D13_POLICY_QC.json','qc/D13_INDEPENDENT_QC.json']],
        BUILD/'qc/PHASE2B_D10_GATE_RESULT.json']
    read=[]
    for p in refs:
        content=p.read_text(encoding='utf-8-sig')
        if p.suffix=='.json':load(p)
        read.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size,'text_characters_read':len(content)})
    write('qc/D13_LOCK_INPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'protected_files':protected,'protected_count':len(protected),'references_read':read,
        'sealed_test_access':'바이너리 SHA-256 확인만 수행; 텍스트 디코딩/CSV 파싱/Y 조회 없음',
        'approval_authority':'현재 사용자 메시지: 연구 C D13 Bootstrap 정책 최종 승인 및 LOCK v1.0',
        'environment':{'python':platform.python_version(),'numpy':np.__version__}})
    source=CAND/'code/bootstrap_candidate.py';target=OUT/'code/synthetic_validation/bootstrap_locked.py'
    with target.open('xb') as f:f.write(source.read_bytes())
    assert sha(source)==sha(target)
    candidate=load(CAND/'policy/D13_LOCK_CANDIDATE.json')
    inherited=load(PHASE1/'PHASE1_LOCKED_SPEC_v1_1.json')['inference']
    assert candidate['inherited_inference']==inherited
    assert load(CAND/'qc/D13_POLICY_QC.json')['D13_POLICY_QC']=='PASS'
    prior_tests=load(CAND/'qc/D13_SYNTHETIC_TEST_RESULTS.json')
    assert prior_tests['status']=='PASS' and prior_tests['case_count']==22 and all(prior_tests['guards'].values())
    policy={'policy_id':'C_D13_CALENDAR_GRID_MBB_v1_0','version':'1.0','status':'APPROVED_PENDING_LOCK_QC',
        'target_lock_status':'LOCKED_v1_0','approved':True,'approved_on_kst':'2026-10-18',
        'supersedes_candidate':{'path':str((CAND/'policy/D13_LOCK_CANDIDATE.json').relative_to(ROOT)),
            'sha256':sha(CAND/'policy/D13_LOCK_CANDIDATE.json'),'policy_id':candidate['policy_id']},
        'inherited_inference_reference':copy.deepcopy(inherited),
        'approved_execution_rules':copy.deepcopy(candidate['candidate_rules']),
        'A01':{'decision_id':'D13_A01_PERCENTILE_LINEAR_TYPE7','status':'APPROVED',
            'quantiles':[0.025,0.975],'method':'linear','Hyndman_Fan_type':7,
            'definition':'sort x; h=(n-1)*q; j=floor(h); g=h-j; Q=(1-g)*x[j]+g*x[min(j+1,n-1)]',
            'numpy_expression':'np.quantile(x,[0.025,0.975],method="linear")','numpy_version':np.__version__,
            'CI':'two-sided 95% paired percentile; not BCa/basic/studentized'},
        'A02':{'decision_id':'D13_A02_HOLM_FAMILY5_CONSERVATIVE_MISSING_P','status':'APPROVED','option':'B',
            'algorithms':['OLS','Ridge','Elastic Net','Random Forest','HistGradientBoosting'],'family_size':5,
            'p_value_source':'approved HAC one-sided improvement test','alpha':0.05,
            'legitimate_not_computable':{'raw_p':None,'status':'NOT_COMPUTABLE','reason_required':True,
                'internal_Holm_input':1.0,'reported_adjusted_p':None,'decision':'REJECTION_NOT_SUPPORTED'},
            'implementation_error':'IMPLEMENTATION_ERROR_REVIEW_REQUIRED; stop entire procedure; no p=1 substitution',
            'primary_algorithm':'Ridge','primary_unavailable':'PRIMARY_RIDGE_INFERENCE_UNAVAILABLE',
            'partial_family_disclosure_required':True,'all_unavailable':'FAMILY_INFERENCE_UNAVAILABLE',
            'tie_order':'listed algorithm order for reproducible display; Holm adjusted values tie-consistent'},
        'bootstrap_p_value_enabled':False,'candidate_RNG_and_missingness_changed':False,
        'prior_tests_preserved':{'synthetic_cases':22,'boundary_guards':7,'status':'PASS'},
        'methodology_decisions_pending':[],
        'execution_restrictions':{'empirical_inference_authorized':False,'phase3_authorized':False,'phase4_performance':'SEALED'},
        'limitations':['historical posting and vintages UNVERIFIED','minimum-n conditional resampling does not prove coverage or power',
            'missingness may be nonrandom; saved losses do not capture all model-selection uncertainty']}
    write('logs/D13_APPROVED_CONTENT_PRE_QC.json',policy)
    write('logs/USER_APPROVAL_SCOPE.md','''# 사용자 승인 범위 기록

현재 사용자 직접 지시 「연구 C — D13 Bootstrap 정책 최종 승인 및 LOCK v1.0」에 따른다.
기존 후보 세부 실행규칙, A01 Type7 선형보간, A02 B안 보수적5종Holm 처리의 정책승인이다.
구현오류는 p=1 대체금지 및 절차중단. 적법한통계적 미산출만 raw/보고보정p=null, 내부벡터1 처리.
Ridge미산출시 PRIMARY_RIDGE_INFERENCE_UNAVAILABLE. 주력교체금지.
실제예측손실통계검정/학습/평가/Phase3 실행은 승인되지 않았다. 기존후보·Phase1·Phase2B 수정금지.
''')
    print({'preflight':'PASS','protected_files':len(protected),'prior_cases':22,'prior_guards':7,'copied_MBB_byte_hash_equal':True})

if __name__=='__main__':main()
