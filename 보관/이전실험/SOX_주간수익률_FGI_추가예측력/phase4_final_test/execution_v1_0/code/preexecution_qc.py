"""실제 시험내용 접근 전: 합성모형/시점/HAC/MBB/Type7/Holm 검증."""
import ast,importlib.util
from datetime import date,timedelta
from common import *
from phase3_model_core import fit_predict
from statistics_core import hac,mbb,holm_family5,percentile_type7
from d13_rng_core import simulate

def main():
    checks={};config=load(OUT/'config/PHASE4_LOCKED_EXECUTION_CONFIG.json')
    for p in (OUT/'code').glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    checks['all_code_syntax']=True
    for name in ['run_test','evaluate_infer','independent_qc','finalize']:
        module=importlib.util.module_from_spec(importlib.util.spec_from_file_location(name,OUT/'code'/f'{name}.py'))
        importlib.util.spec_from_file_location(name,OUT/'code'/f'{name}.py').loader.exec_module(module)
    checks['all_imports_no_test_IO']=True
    rng=np.random.Generator(np.random.PCG64(20261016));X=rng.normal(size=(180,11));Y=.2*X[:,0]+rng.normal(size=180);current=rng.normal(size=(1,11))
    smoke=[]
    for algo,v in config['phase3_lock']['selected_algorithms'].items():
        for info,width in [('C-M0',10),('C-M1',11)]:
            p,a=fit_predict(algo,v['models'][info]['hyperparameters'],X[:,:width],Y,current[:,:width])
            q,_=fit_predict(algo,v['models'][info]['hyperparameters'],X[:,:width],Y,current[:,:width])
            checks['model_'+algo+'_'+info]=p==q and math.isfinite(p) and (a['scaler_n_samples']==180 if algo in ['OLS','Ridge','ElasticNet'] else a['scaler_n_samples']==0)
            smoke.append({'algorithm':algo,'information_set':info,'prediction':p,'reproducible':p==q})
    from run_test import OutcomeVault
    O=pd.Timestamp('2025-01-06T14:00Z');df=pd.DataFrame({'week_start':['2024-12-23','2024-12-30','2025-01-06','2025-01-13'],
        'origin_utc':[O-pd.Timedelta(weeks=2),O-pd.Timedelta(weeks=1),O,O+pd.Timedelta(weeks=1)],
        'label_utc':[O,O-pd.Timedelta(microseconds=1),O-pd.Timedelta(days=1),O-pd.Timedelta(days=1)],
        'Y_valid':[True]*4,'split':['sealed_test']*4})
    vault=OutcomeVault(np.array([1.,2.,3.,4.]),df,np.ones(4,dtype=bool));ids,y,_=vault.training(2,'expanding')
    checks['strict_maturity_no_target_future']=ids.tolist()==[1] and y.tolist()==[2.]
    try:vault.evaluate();checks['outcome_access_guard_before_predictions']=False
    except AssertionError:checks['outcome_access_guard_before_predictions']=True
    boundary=df.copy();cut=O.to_pydatetime().astimezone(NY).replace(year=2020)
    boundary.loc[0,'week_start']='2019-12-30';boundary.loc[1,'week_start']='2019-12-30'
    boundary.loc[0,'origin_utc']=pd.Timestamp(cut).tz_convert('UTC');boundary.loc[1,'origin_utc']=pd.Timestamp(cut).tz_convert('UTC')-pd.Timedelta(microseconds=1)
    boundary.loc[:1,'label_utc']=O-pd.Timedelta(days=7)
    ids,_,_=OutcomeVault(np.arange(4.),boundary,np.ones(4,dtype=bool)).training(2,'rolling_5_calendar_years')
    checks['five_calendar_year_cutoff_no_extend']=ids.tolist()==[0]
    grid=[str(date(2000,1,3)+timedelta(weeks=i)) for i in range(64)]
    t=np.arange(64);a=2+np.sin(t/4);b=1+.3*np.cos(t/7);d=a-b;d[[5,6,20]]=np.nan
    for lag in [4,2,8]:
        r=hac(grid,d,lag);idx=np.flatnonzero(np.isfinite(d));v=d[idx];u=v-v.mean()
        W=np.maximum(0.,1-np.abs(idx[:,None]-idx[None,:])/(lag+1));omega=float(u@W@u/len(v));se=math.sqrt(omega/len(v))
        p=.5*math.erfc((float(v.mean())/se)/math.sqrt(2))
        checks[f'HAC_gap_matrix_lag{lag}']=math.isclose(r['Omega'],omega,abs_tol=1e-12) and math.isclose(r['raw_p'],p,abs_tol=1e-12)
    for L in [8,4,12]:
        result,means,records,starts=mbb(grid,a,b,L)
        legacy,oldrecords,oldstarts,oldmeans=simulate(grid,a,b,L)
        # Independent direct Type7 (rather than np.quantile).
        s=sorted(means);quant=[]
        for q in [.025,.975]:
            h=(len(s)-1)*q;j=int(math.floor(h));g=h-j;quant.append((1-g)*s[j]+g*s[min(j+1,len(s)-1)])
        checks[f'MBB_L{L}_approved_RNG_full_replay']=starts==oldstarts and means==oldmeans and len(means)==5000
        checks[f'Type7_L{L}_direct_formula']=math.isclose(result['CI_low'],quant[0],abs_tol=1e-12) and math.isclose(result['CI_high'],quant[1],abs_tol=1e-12)
    checks['Type7_two_points']=percentile_type7([-10,30])==[-9.,29.]
    checks['zero_variance_legal']=hac(grid,np.ones(64),4)['reason']=='ZERO_VARIANCE'
    checks['minimum_n_abort']=hac(grid,[np.nan]*14+[1.]*50,4)['reason']=='INSUFFICIENT_PAIRED_SAMPLE'
    records={NAME[a]:{'status':'COMPUTABLE','raw_p':p,'reason':None} for a,p in zip(FAMILY,[.001,.01,.02,.2,.9])}
    h=holm_family5(records);checks['Holm_family5_full']=[r['reported_adjusted_p'] for r in h['rows']]==[.005,.04,.06,.4,.9]
    records['Ridge']={'status':'NOT_COMPUTABLE','raw_p':None,'reason':'ZERO_VARIANCE','reason_detail':'synthetic'}
    h=holm_family5(records);ridge=next(r for r in h['rows'] if r['algorithm']=='Ridge')
    checks['A02_legal_internal1_reportnull']=ridge['reported_adjusted_p'] is None and ridge['internal_Holm_input']==1 and h['primary_status']=='PRIMARY_RIDGE_INFERENCE_UNAVAILABLE'
    records['OLS']={'status':'IMPLEMENTATION_ERROR','raw_p':None};h=holm_family5(records)
    checks['A02_bug_stops_no_substitute']=h['family_status']=='IMPLEMENTATION_ERROR_REVIEW_REQUIRED' and h['internal_Holm_vector'] is None
    checks['no_actual_test_unsealed']=not (OUT/'inputs/PHASE4_UNSEAL_AUDIT.json').exists()
    status='PASS' if all(checks.values()) else 'BLOCKED_REVIEW_REQUIRED'
    save('qc/PHASE4_PREEXECUTION_SYNTHETIC_QC.json',{'status':status,'checks':checks,'count':len(checks),'synthetic_model_fits':20,
        'smoke':smoke,'test_data_contents_used':False,'MBB_synthetic_repetitions':15000,'legacy_MBB_comparison_repetitions':15000})
    if status!='PASS':raise RuntimeError('PREEXECUTION_SYNTHETIC_QC_FAILED')
    save('config/PHASE4_EXECUTION_AUTHORIZATION.json',{'PHASE4_EXECUTION_AUTHORIZATION':'USER_APPROVED','PHASE4_PREEXECUTION_GATE':'PASS',
        'approval_source':'inputs/USER_PHASE4_AUTHORIZATION.txt','approval_sha256':sha(OUT/'inputs/USER_PHASE4_AUTHORIZATION.txt'),
        'code_hashes':code_hashes(),'config_sha256':sha(OUT/'config/PHASE4_LOCKED_EXECUTION_CONFIG.json'),
        'environment_sha256':sha(OUT/'config/PHASE4_ENVIRONMENT.json'),'created_at_utc':datetime.now(UTC).isoformat(),
        'supersedes_historical_NOT_AUTHORIZED_for_phase4_only':True,'phase5_authorized':False})
    event('PREEXECUTION_SYNTHETIC_GATE_PASS_BEFORE_UNSEAL',checks=len(checks))
    print({'preexecution_gate':status,'checks':len(checks),'test_content_read':0,'code_frozen':True})

if __name__=='__main__':main()
