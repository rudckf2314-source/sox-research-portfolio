"""전수 개발 로그 재집계, 선택재현, 보호/봉인/코드 경로 감사."""
import ast,math,platform
from datetime import datetime,timezone
from common import *
FAMILY=['OLS','Ridge','ElasticNet','RandomForest','HistGradientBoosting']
def main():
    for d in ['inputs','lock','audit','qc','reports','logs']:(OUT/d).mkdir(exist_ok=True)
    protected=dict(load(DEV/'inputs/PHASE3_INPUT_MANIFEST.json')['protected_files'])
    m=load(DEV/'qc/PHASE3_OUTPUT_MANIFEST.json')
    assert sha(DEV/'qc/PHASE3_OUTPUT_MANIFEST.json')==(DEV/'qc/PHASE3_OUTPUT_MANIFEST.sha256').read_text().split()[0]
    for x in m['files']:assert sha(DEV/x['path'])==x['sha256'],x['path']
    for p in DEV.rglob('*'):
        if p.is_file():protected[p.relative_to(ROOT).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    changed=[r for r,v in protected.items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    assert not changed,changed
    refs=[ROOT/'Research_C_Study_Plan_v1_20261016.md',
        *[P1/x for x in ['PHASE1_LOCKED_SPEC_v1_1.md','PHASE1_LOCKED_SPEC_v1_1.json','PHASE1_APPROVED_DECISIONS.json','PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json','PHASE1_GATE_REGISTER.json']],
        P1.parent/'design/PHASE1_STATISTICAL_TEST_PLAN.md',
        *[BUILD/x for x in ['reports/PHASE2B_REPORT.md','reports/PHASE2B_HANDOFF.md','qc/PHASE2B_OUTPUT_MANIFEST.json','data/WEEKLY_SAMPLE_COUNTS.json','qc/PHASE2B_D10_GATE_RESULT.json']],
        *[D13/x for x in ['D13_LOCKED_POLICY_v1_0.md','D13_LOCKED_POLICY_v1_0.json','qc/D13_LOCK_QC.json','D13_GATE_STATUS.json']],
        *[DEV/x for x in ['reports/PHASE3_REPORT.md','reports/PHASE3_SELECTION_REPORT.md','qc/PHASE3_INDEPENDENT_QC.md','qc/PHASE3_QC.json',
            'selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.md','selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.json','selection/PHASE3_SELECTION_REGISTER.json',
            'logs/WALKFORWARD_COMPLETION.json','inputs/PHASE3_DATA_ACCESS_AUDIT.json','config/PHASE3_ENVIRONMENT_LOCK.json']]]
    read=[]
    for p in refs:
        s=p.read_text(encoding='utf-8-sig');read.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'characters_read':len(s)})
        if p.suffix=='.json':load(p)
    write('qc/INPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'protected_files':protected,
        'protected_count':len(protected),'changed':changed,'references_read':read,'python':platform.python_version(),
        'authority':'현재 사용자 직접 지시: 연구 C Phase3 최종 실험사양 LOCK 및 Phase4 시험 직전 감사',
        'access_rule':'개발자료/정책/기존코드는읽기; sealed_test는파일명/크기/바이너리SHA256만'})
    candidate=load(DEV/'selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.json')
    grid=load(P1/'PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json')
    assert grid==load(DEV/'config/PHASE3_APPROVED_SEARCH_GRID.json')
    assert sum(map(len,grid['algorithms'].values()))==18
    # Independent count and MAE aggregation directly from saved predictions.
    logs=csvread(DEV/'predictions/PHASE3_ALL_CANDIDATE_PREDICTIONS.csv');groups={}
    for r in logs:
        assert r['week_start']<'2021-01-01'
        key=tuple(r[k] for k in ['algorithm','information_set','window_type','candidate_id'])
        groups.setdefault(key,[]).append(r)
    assert len(logs)==15048 and len(groups)==72
    weeks={r['week_start'] for r in logs};assert len(weeks)==209
    scores={}
    for k,rs in groups.items():
        assert len(rs)==209 and {r['week_start'] for r in rs}==weeks
        assert len({r['week_start'] for r in rs})==209
        scores[k]=math.fsum(abs(float(r['development_actual_y'])-float(r['prediction'])) for r in rs)/len(rs)
    published=csvread(DEV/'metrics/PHASE3_CANDIDATE_METRICS.csv')
    assert all(math.isclose(scores[tuple(r[k] for k in ['algorithm','information_set','window_type','candidate_id'])],float(r['MAE']),abs_tol=1e-12,rel_tol=1e-12) for r in published)
    chosen={};rows=[]
    expected={'OLS':('expanding','OLS01','OLS01'),'Ridge':('rolling_5_calendar_years','R05','R05'),
        'ElasticNet':('expanding','E04','E04'),'RandomForest':('rolling_5_calendar_years','RF04','RF04'),
        'HistGradientBoosting':('expanding','GB02','GB01')}
    rounded={'OLS':[2.852482,2.842873],'Ridge':[2.783198,2.781478],'ElasticNet':[2.813001,2.814829],
        'RandomForest':[2.755656,2.754715],'HistGradientBoosting':[2.894729,2.923378]}
    for algo in FAMILY:
        best={}
        for info in ['C-M0','C-M1']:
            for window in ['expanding','rolling_5_calendar_years']:
                keys=[k for k in groups if k[:3]==(algo,info,window)]
                best[info,window]=min(keys,key=lambda k:(scores[k],k[3]))
        window=min(['expanding','rolling_5_calendar_years'],key=lambda w:(scores[best['C-M0',w]],w!='expanding'))
        ids=tuple(best[info,window][3] for info in ['C-M0','C-M1'])
        assert (window,*ids)==expected[algo]
        chosen[algo]={'selected_window':window,'models':{}}
        for j,info in enumerate(['C-M0','C-M1']):
            k=best[info,window];actual=scores[k]
            params=next(c for c in grid['algorithms'][algo] if c['candidate_id']==k[3])
            old=candidate['selected_algorithms'][algo]
            assert old['selected_window']==window and old['models'][info]['candidate_id']==k[3]
            assert old['models'][info]['hyperparameters']==params
            assert abs(actual-rounded[algo][j])<=0.500001e-6
            assert math.isclose(actual,old['models'][info]['development_metrics']['MAE'],abs_tol=1e-12)
            chosen[algo]['models'][info]={'candidate_id':k[3],'hyperparameters':params,'verified_development_MAE':actual}
            rows.append({'algorithm':algo,'information_set':info,'window':window,'candidate_id':k[3],
                'parameters':params,'MAE_recalculated':actual,'MAE_user_rounded':rounded[algo][j],
                'within_rounding_tolerance':True})
    # Verify actual execution counts via 209 hash-verified origin checkpoints.
    cpcount=0;cpfits=0
    for p in sorted((DEV/'logs/checkpoints').glob('*.json')):
        assert sha(p)==p.with_suffix('.sha256').read_text().strip()
        cp=load(p);assert len(cp['predictions'])==72
        assert all(sha(ROOT/r)==h for r,h in cp['signature'].items())
        cpcount+=1;cpfits+=len(cp['predictions'])
    assert cpcount==209 and cpfits==15048
    failure=load(DEV/'metrics/PHASE3_FAILURE_COUNTS.json')
    assert failure['candidate_estimator_fit_failures']==failure['excluded_origins']==0
    data=csvread(BUILD/'data/train_dev/WEEKLY_CORE_COMBINED.csv')
    valid=[r for r in data if r['paired_common_valid']=='True']
    assert len(valid)==517 and sum(r['split']=='initial_train' for r in valid)==308 and sum(r['split']=='development' for r in valid)==209
    verification={'status':'PASS','selected':chosen,'models':rows,'counts':{'initial':308,'development':209,'common':517,
        'origins':209,'algorithms':5,'unique_candidates':18,'representation_windows':4,'candidate_fits':cpfits,
        'candidate_fit_failures':0,'nonpredicted_origins':0},'all72_MAE':[
            {'algorithm':k[0],'information_set':k[1],'window':k[2],'candidate_id':k[3],'MAE':v} for k,v in sorted(scores.items())],
        'fit_count_scope':'15048 is main experiment only; smoke13 and prior independent estimator36/linear24 excluded',
        'primary_algorithm':'Ridge','source_prediction_sha256':sha(DEV/'predictions/PHASE3_ALL_CANDIDATE_PREDICTIONS.csv')}
    write('lock/PHASE3_SELECTION_VERIFICATION.json',verification)
    sealed=[];bm=load(BUILD/'qc/PHASE2B_OUTPUT_MANIFEST.json')
    for x in bm['files']:
        if x['path'].startswith('data/sealed_test/'):
            p=BUILD/x['path'];assert p.is_file() and sha(p)==x['sha256'] and p.stat().st_size==x['bytes']
            sealed.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p),'matches_frozen_hash':True})
    assert len(sealed)==3
    codeaudit=[]
    for p in sorted((DEV/'code').glob('*.py')):
        source=p.read_text(encoding='utf-8');tree=ast.parse(source)
        calls=[{'line':n.lineno,'function':ast.unparse(n.func),'arguments':ast.unparse(n)} for n in ast.walk(tree)
            if isinstance(n,ast.Call) and ('read_csv' in ast.unparse(n.func) or ast.unparse(n.func).endswith('open'))]
        codeaudit.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'read_calls':calls})
    write('audit/DEVELOPMENT_CODE_ACCESS_REVIEW.json',{'files':codeaudit,
        'finding':'주 CSV DATA는 train_dev다. 혼합 availability는 날짜 10byte prefix에서 시험 내용 전에 중단한다. 예측 함수는 현재 Y를 받지 않는다.',
        'limitation':'저장 코드·서명·로그 감사이며 OS 전체 접근 이력을 소급 증명하는 검사가 아니다.'})
    access=load(DEV/'inputs/PHASE3_DATA_ACCESS_AUDIT.json')
    assert access['sealed_test_CSV_parsed']==0 and access['test_Y_values_read']==0
    assert candidate['dataset']['sha256']==sha(BUILD/'data/train_dev/WEEKLY_CORE_COMBINED.csv')
    write('audit/PHASE4_DATA_SEAL_AUDIT.json',{'status':'PASS','sealed_files':sealed,'files':3,
        'Y_content_decoded_or_parsed':False,'test_statistics_calculated':False,'development_access_record':access,
        'dataset_version_consistent':True,'changed_protected':changed,
        'audit_limit':'저장 코드·입력·체크포인트 서명과 로그의 정합성 검사다. OS 이력 전체를 감시한 증거는 아니다.'})
    write('inputs/APPROVAL_SCOPE.md','''# 최종 승인 범위

현재 사용자는 Phase3의 기존 선택 결과를 최종 LOCK v1.0으로 등록하고 시험 직전 감사만 수행하도록 승인했다.
새 후보·변수·학습창·데이터 변경 및 Phase4/5 실행은 승인되지 않았다. 실제 시험 Y/손실/예측/통계검정을 열람하거나 계산하지 않는다.
''')
    print({'Gate_A':'PASS','predictions':len(logs),'selected_models':len(rows),'checkpoints':cpcount,'protected':len(protected),'sealed_metadata_only':len(sealed)})

if __name__=='__main__':main()
