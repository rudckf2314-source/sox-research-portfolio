"""Fit only corrected R0 and corrected fixed-mask KR, after preflight PASS."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import sys,warnings,platform
import numpy as np,pandas as pd,joblib,sklearn
from sklearn.base import clone
from sklearn.metrics import accuracy_score,recall_score,balanced_accuracy_score,matthews_corrcoef,roc_auc_score,brier_score_loss,log_loss
from threadpoolctl import threadpool_limits
from common import *
def score(y,p,c,q):
    tn=int(((y==0)&(c==0)).sum());tp=int(((y==1)&(c==1)).sum())
    return dict(n=len(y),TN=tn,FP=int((y==0).sum())-tn,FN=int((y==1).sum())-tp,TP=tp,correct=tn+tp,accuracy=accuracy_score(y,c),recall_nonup=recall_score(y,c,pos_label=0,zero_division=0),recall_up=recall_score(y,c,pos_label=1,zero_division=0),BA=balanced_accuracy_score(y,c),MCC=matthews_corrcoef(y,c),AUC=roc_auc_score(y,p) if len(set(y))==2 else np.nan,Brier=brier_score_loss(y,p),Log_loss=log_loss(y,p,labels=[0,1]),q_Brier=brier_score_loss(y,q),q_Log_loss=log_loss(y,q,labels=[0,1]),predicted_up_rate=float(c.mean()))
def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1);pre=json.loads((O/'PREFLIGHT_RESULT.json').read_text());assert pre['status']=='PASS';assert not (O/'logs/FIT_ATTEMPTS.csv').exists(),'Never rerun/overwrite fitting'
    for key,file in [('corrected_R0_file_sha256','data/CORRECTED_R0_1D.csv'),('corrected_KR_file_sha256','data/CORRECTED_A1_KR_ONLY_1D.csv')]:assert sha(O/file)==pre[key]
    assert sha(P/'A1_PARTIAL_ROW_REVIEW.csv')==pre['input_mask_sha256']
    for r in pre['RAW_hashes']:assert sha(ROOT/r['path'])==r['sha256']
    cols=json.loads((V/'config/INFORMATION_SETS.json').read_text())['M1'];data={p:pd.read_csv(O/f'data/{p}_1D.csv',parse_dates=['date','label_end']).set_index('date') for p in ['CORRECTED_R0','CORRECTED_A1_KR_ONLY']};base=data['CORRECTED_R0'];dev=base[base.index.year>=2017]
    template=joblib.load(V/'models/C_latest_monthly_expanding_M1_LogisticClassifier_2017-01.joblib');params={s:template.named_steps[s].get_params(deep=False) for s in ['impute','scale','model']};assert canonical(params)==canonical(json.loads((K/'ESTIMATOR_PARAMETERS.json').read_text()));js('ESTIMATOR_PARAMETERS.json',params)
    js('ENVIRONMENT.json',dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__,joblib=joblib.__version__,platform=platform.platform(),seed=SEED,threads=1))
    folds=pd.read_csv(O/'FOLD_PREFLIGHT.csv');attempts=[];preds=[]
    mask=pd.read_csv(O/'KR_FROZEN_MASK_APPLICATION.csv');app=mask.groupby('date').applied.any()
    print('Preflight hashes stable; starting two fixed policies, maximum96 fits.',flush=True)
    for f in folds.itertuples():
        month=f.month;origin=pd.Timestamp(f.origin)
        for policy,z in data.items():
            assert len(attempts)<96 and sum(a['policy']==policy for a in attempts)<48
            te=z[z.index.strftime('%Y-%m')==month];tr=z[(z.index<te.index[0])&(pd.to_datetime(z.label_available_et,utc=True)<origin)];assert len(tr)==f.train_n
            row=dict(attempt=len(attempts)+1,policy=policy,month=month,status='STARTED',train_n=len(tr),train_start=str(tr.index[0].date()),train_end=str(tr.index[-1].date()),max_label_available=str(pd.to_datetime(tr.label_available_et,utc=True).max()),origin=str(origin),test_n=len(te),training_XY_sha256=framehash(tr[cols+['Y']]),C=1,threshold=.5,seed=SEED)
            attempts.append(row);csv('logs/FIT_ATTEMPTS.csv',attempts);m=clone(template)
            try:
                with warnings.catch_warnings(record=True) as ws:
                    warnings.simplefilter('always');m.fit(tr[cols],tr.Y)
                row['warnings']=' | '.join(str(w.message) for w in ws);assert m.named_steps['model'].n_iter_.max()<m.named_steps['model'].max_iter,'Convergence limit'
                assert canonical({s:m.named_steps[s].get_params(deep=False) for s in ['impute','scale','model']})==canonical(params)
                path=O/f'models/{policy}_{month}.joblib';joblib.dump(m,path);row['model_path']=path.relative_to(O).as_posix();row['sha256']=sha(path);row['status']='PASS';prob=m.predict_proba(te[cols])[:,1]
                assert np.isfinite(prob).all() and list(m.classes_)==[0,1]
            except Exception as e:
                row['status']='FAIL';row['error']=repr(e);csv('logs/FIT_ATTEMPTS.csv',attempts);raise
            csv('logs/FIT_ATTEMPTS.csv',attempts)
            for date,p in zip(te.index,prob):preds.append(dict(policy=policy,date=str(date.date()),year=date.year,month=month,Y=int(te.loc[date,'Y']),probability=float(p),prediction=int(p>=.5),threshold=.5,C=1,training_up_probability=float(tr.Y.mean()),KR_fixed_mask_day=bool(app.loc[str(date.date())])))
            csv('predictions/EXTERNAL_PREDICTIONS.csv',preds);print('Fit',len(attempts),policy,month,'PASS',flush=True)
    assert len(attempts)==96 and all(a['status']=='PASS' for a in attempts)
    pr=pd.DataFrame(preds);old=pd.read_csv(V/'predictions/ALL_PREDICTIONS_WITH_BENCHMARKS.csv',parse_dates=['date']);oldkr=pd.read_csv(K/'predictions/EXTERNAL_PREDICTIONS.csv',parse_dates=['date']).set_index('date').sort_index()
    def saved(sc,g):
        z=old[(old.scenario==sc)&(old.group==g)&(old.algorithm=='LogisticClassifier')].set_index('date').sort_index();assert z.index.equals(dev.index) and np.array_equal(z.Y,dev.Y);return z
    legacyR0=saved('C_latest_monthly_expanding','M1');best=saved('D_latest_monthly_3years','M0');r0=pr[pr.policy=='CORRECTED_R0'].sort_values('date');refs={'always_up':np.ones(len(dev),dtype=int),'corrected_R0':r0.prediction.to_numpy(),'SOX_best_567':best.prediction.to_numpy(),'legacy_KR_591':oldkr.prediction.to_numpy(),'legacy_R0_549':legacyR0.prediction.to_numpy()}
    assert np.array_equal(oldkr.Y,dev.Y) and oldkr.index.equals(dev.index) and [int((refs[k]==dev.Y.to_numpy()).sum()) for k in ['always_up','SOX_best_567','legacy_KR_591','legacy_R0_549']]==[563,567,591,549]
    pd.DataFrame(dict(date=dev.index,Y=dev.Y.to_numpy(),**refs)).to_csv(O/'inputs/REFERENCE_PREDICTIONS.csv',index=False,encoding='utf-8-sig')
    metrics=[];intervals=[];dist=[];subset=[];aucrows=[]
    for policy,w in pr.groupby('policy',sort=False):
        w=w.sort_values('date');assert w.date.tolist()==dev.index.strftime('%Y-%m-%d').tolist();assert np.array_equal(w.Y,dev.Y)
        pair_weight=0.;totalpairs=0
        for year in ['ALL',2017,2018,2019,2020]:
            keep=np.ones(len(w),bool) if year=='ALL' else dev.index.year==year;v=w.loc[keep];y=v.Y.to_numpy();p=v.probability.to_numpy();c=v.prediction.to_numpy();q=v.training_up_probability.to_numpy();row=dict(policy=policy,period=year,**score(y,p,c,q));n=len(v);rng=np.random.default_rng(SEED);start=rng.integers(0,n-19,size=(2000,int(np.ceil(n/20))));idx=(start[:,:,None]+np.arange(20)).reshape(2000,-1)[:,:n]
            if year!='ALL':pairs=int((y==1).sum()*(y==0).sum());pair_weight+=row['AUC']*pairs;totalpairs+=pairs
            for name,b in refs.items():
                ref=b[keep];delta=(c==y).astype(int)-(ref==y).astype(int);lo,hi=np.quantile(delta[idx].mean(axis=1)*100,[.025,.975]);tn=int(((ref==0)&(y==0)).sum());tp=int(((ref==1)&(y==1)).sum());row[name+'_delta_correct']=int(delta.sum());row[name+'_delta_pp']=float(delta.mean()*100);row[name+'_delta_TN']=row['TN']-tn;row[name+'_delta_TP']=row['TP']-tp;row['beats_'+name]=bool(delta.sum()>0)
                intervals.append(dict(policy=policy,period=year,reference=name,n=n,delta_correct=int(delta.sum()),delta_TN=row['TN']-tn,delta_TP=row['TP']-tp,delta_pp=float(delta.mean()*100),CI95_low_pp=float(lo),CI95_high_pp=float(hi),block=20,replicates=2000,seed=SEED))
            metrics.append(row)
            for cl in [0,1]:
                pp=p[y==cl];dist.append(dict(policy=policy,period=year,actual_class=cl,n=len(pp),mean=pp.mean(),std=pp.std(),q05=np.quantile(pp,.05),q25=np.quantile(pp,.25),median=np.median(pp),q75=np.quantile(pp,.75),q95=np.quantile(pp,.95),fraction045_055=((pp>=.45)&(pp<=.55)).mean()))
            for label,ss in [('fixed_KR_applied_days',v.KR_fixed_mask_day.to_numpy()),('fixed_KR_fallback_days',~v.KR_fixed_mask_day.to_numpy())]:
                yy=y[ss];cc=c[ss];r=dict(policy=policy,period=year,subset=label,analysis='AUXILIARY_ONLY',**score(yy,p[ss],cc,q[ss]))
                for name,b in refs.items():r[name+'_delta_correct']=int((cc==yy).sum()-(b[keep][ss]==yy).sum())
                subset.append(r)
        aucrows.append(dict(policy=policy,pooled_AUC=roc_auc_score(w.Y,w.probability),within_year_pair_weighted_AUC=pair_weight/totalpairs))
    csv('METRICS.csv',metrics);csv('PAIRED_BLOCK_BOOTSTRAP.csv',intervals);csv('PROBABILITY_DISTRIBUTIONS.csv',dist);csv('FIXED_MASK_SUBSET_AUXILIARY.csv',subset);csv('POOLED_VS_WITHIN_YEAR_AUC.csv',aucrows)
    impact=[]
    for r in metrics:
        ref='legacy_KR_591' if r['policy']=='CORRECTED_A1_KR_ONLY' else 'legacy_R0_549';impact.append(dict(policy=r['policy'],period=r['period'],legacy_reference=ref,correct=r['correct'],accuracy=r['accuracy'],delta_correct=r[ref+'_delta_correct'],delta_pp=r[ref+'_delta_pp'],delta_TN=r[ref+'_delta_TN'],delta_TP=r[ref+'_delta_TP']))
    csv('CORRECTION_IMPACT.csv',impact)
    ap=mask.copy();ap['year']=pd.to_datetime(ap.date).dt.year;ap['scope']=np.where(ap.year<2017,'initial_training','evaluation')
    for name,keys in [('APPLICATION_RATES.csv',['scope','feature']),('APPLICATION_RATES_BY_YEAR.csv',['year','feature']),('FALLBACK_REASONS.csv',['scope','year','feature','reason'])]:
        z=ap.groupby(keys).agg(feature_cells=('applied','size'),applied_cells=('applied','sum'),fallback_cells=('fallback','sum')).reset_index();z['application_pct']=100*z.applied_cells/z.feature_cells;z['fallback_pct']=100*z.fallback_cells/z.feature_cells;csv(name,z)
    js('RUN_SUMMARY.json',dict(status='FITTED_PENDING_REVIEW',new_fit_attempts=len(attempts),fit_failures=0,budget=96,per_policy_fits={p:sum(r['policy']==p for r in attempts) for p in data},legacy_cache_reused=0,TW_comparison_executed=False,tuning=False,mask_changed=False,primary_dates=1007))
    print('Completed96 fits, two policies, all1007 days each. Review pending.',flush=True)
if __name__=='__main__':
    try:main()
    except Exception as e:js('TRAIN_FAILURE.json',dict(status='FAIL',error=repr(e),action='STOP no retry or budget increase'));raise
