"""Execute the frozen Korean-only timing policy. No tuning or Taiwan execution."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import sys,json,hashlib,shutil,warnings,platform
from pathlib import Path
import numpy as np,pandas as pd,joblib,sklearn
from sklearn.base import clone
from sklearn.metrics import accuracy_score,recall_score,balanced_accuracy_score,matthews_corrcoef,roc_auc_score,brier_score_loss,log_loss
from threadpoolctl import threadpool_limits

O=Path(__file__).resolve().parent;P=O.parent;A=P.parent;D=A.parent;ROOT=D.parent;V=D/'development_revision_v1';SEED=20261019
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def js(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def csv(n,x):pd.DataFrame(x).to_csv(O/n,index=False,encoding='utf-8-sig')
def canonical(x):return json.dumps(x,sort_keys=True,default=str)
def hashframe(x):return hashlib.sha256(pd.util.hash_pandas_object(x,index=True).values.tobytes()).hexdigest()
def snapshot():
    rows=[]
    for b,ds,fs in os.walk(ROOT,followlinks=False):
        ds[:]=[n for n in ds if n not in {'.git','.venv','.venv_W1'} and not (Path(b)/n).resolve().is_relative_to(O)]
        for n in fs:
            p=Path(b)/n
            assert not p.is_symlink(),str(p)
            rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return rows
CHECKS=[]
def ck(n,ok,detail=''):
    CHECKS.append(dict(check=n,PASS=bool(ok),detail=str(detail)))
    if not ok:csv('QC.csv',CHECKS);raise RuntimeError(n+': '+str(detail))
def metrics(y,p,pred,q):
    return dict(n=len(y),correct=int((y==pred).sum()),accuracy=accuracy_score(y,pred),recall_nonup=recall_score(y,pred,pos_label=0,zero_division=0),recall_up=recall_score(y,pred,pos_label=1,zero_division=0),BA=balanced_accuracy_score(y,pred),MCC=matthews_corrcoef(y,pred),AUC=roc_auc_score(y,p) if len(set(y))==2 else np.nan,Brier=brier_score_loss(y,p),Log_loss=log_loss(y,p,labels=[0,1]),q_Brier=brier_score_loss(y,q),q_Log_loss=log_loss(y,q,labels=[0,1]),predicted_up_rate=float(pred.mean()))

def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1)
    assert not (O/'PROTECTED_BEFORE.csv').exists(),'Do not rerun or overwrite an execution'
    for n in ['inputs','data','models','logs','predictions']:(O/n).mkdir(exist_ok=True)
    before=snapshot();csv('PROTECTED_BEFORE.csv',before);print('Snapshot complete:',len(before),'protected files',flush=True)
    seals=[]
    for base in [D,V,A,A/'execution_v1',P]:
        man=base/'OUTPUT_MANIFEST.csv';ck('manifest_own_'+str(base.relative_to(ROOT)),sha(man)==(base/'OUTPUT_MANIFEST.sha256').read_text().split()[0])
        for r in pd.read_csv(man).itertuples():
            p=base/r.path;ok=p.is_file() and p.stat().st_size==r.bytes and sha(p)==r.sha256
            seals.append(dict(manifest=str(man.relative_to(ROOT)),path=r.path,PASS=ok))
    csv('EXISTING_SEAL_CHECK.csv',seals);ck('all_existing_study_seals',all(r['PASS'] for r in seals))
    for src,dst in [(P/'REVISED_EXPERIMENT_PLAN.md','inputs/REVISED_EXPERIMENT_PLAN_ORIGINAL.md'),(P/'REVIEW_SCOPE.md','inputs/REVIEW_SCOPE_ORIGINAL.md'),(P/'PUBLIC_EVIDENCE.json','inputs/PUBLIC_EVIDENCE_ORIGINAL.json')]:shutil.copy2(src,O/dst)
    plan_summary=json.loads((P/'AUDIT_SUMMARY.json').read_text());rawpath=ROOT/plan_summary['raw_paths']['01']['path']
    ck('RAW01_hash_unchanged',sha(rawpath)==plan_summary['raw_paths']['01']['sha256'])
    ck('mask_scope_hash',sha(P/'REVIEW_SCOPE.md')==plan_summary['evidence_policy_sha256'])
    frozen=pd.read_csv(P/'A1_PARTIAL_ROW_REVIEW.csv',dtype={'source':str},parse_dates=['date']);frozen=frozen[frozen.source=='01'].copy();csv('inputs/FROZEN_KR_MASK.csv',frozen)
    cols=json.loads((V/'config/INFORMATION_SETS.json').read_text())['M1'];krcols=[c for c in cols if c.startswith('s01_')];others=[c for c in cols if c not in krcols]
    ck('5_KR_48_other_features',len(krcols)==5 and len(others)==48)
    data=pd.read_csv(V/'data/LATEST_EOD_1D.csv',parse_dates=['date','label_end']).set_index('date').sort_index();baseX=data[cols].copy();newX=baseX.copy()
    raw=pd.read_csv(rawpath,comment='#');raw=raw[raw.Date<='2020-12-31'].copy();raw.index=pd.to_datetime(raw.Date);raw=raw.sort_index();close=raw.Close.astype(float)
    ck('RAW_native_dates_unique',raw.index.is_unique)
    vals={f'ret{k}':100*(close/close.shift(k)-1) for k in [1,5,20]};vals.update(vol20=100*(close/close.shift(1)-1).rolling(20,min_periods=20).std(ddof=1),ma20_gap=100*(close/close.rolling(20,min_periods=20).mean()-1))
    first=set(raw.groupby(raw.index.year).apply(lambda z:z.index.min()).tolist());maskcheck=[];frozen=frozen.set_index(['date','feature']).sort_index()
    ck('mask_12475_unique_rows',len(frozen)==2495*5 and frozen.index.is_unique)
    for date,r in data.iterrows():
        present=date in raw.index;pos=raw.index.get_loc(date) if present else -1;reason='';clock=None;evidence=''
        if not present:reason='own_same_day_observation_absent_not_assumed_holiday'
        elif date in first:reason='first_native_session_of_year_quarantine_exact_special_time_unverified'
        elif date.month==11 and date!=pd.Timestamp('2019-11-14'):reason='predeclared_November_quarantine_special_calendar_incomplete'
        elif date.year==2020 and date.month==12:reason='predeclared_2020_December_quarantine_special_calendar_incomplete'
        elif date.weekday()>=5:reason='own_unverified_weekend_session'
        else:
            special=date==pd.Timestamp('2019-11-14');clock='16:30' if special else ('15:00' if date<pd.Timestamp('2016-08-01') else '15:30');evidence='KR_SPECIAL_2019' if special else 'KR_REGULAR'
        local=pd.Timestamp(str(date.date())+' '+clock,tz='Asia/Seoul') if clock else None
        available=(local+pd.Timedelta(hours=2)).tz_convert('America/New_York') if local is not None else None
        origin=pd.Timestamp(r.origin_et)
        if available is not None and available>origin:reason='conditional_availability_after_origin'
        for f in krcols:
            fr=reason;key=f.split('_',1)[1];offsets=[0,1] if key=='ret1' else [0,5] if key=='ret5' else [0,20] if key=='ret20' else list(range(20)) if key=='ma20_gap' else list(range(21))
            inputs=[raw.index[pos-j] for j in offsets] if present and pos>=max(offsets) else []
            if not fr and len(inputs)!=len(offsets):fr='insufficient_native_calculation_history'
            if not fr and any(not np.isfinite(close.loc[d]) or close.loc[d]<=0 for d in inputs):fr='own_required_input_nonpositive_or_nonfinite'
            value=float(vals[key].loc[date]) if present else np.nan
            if not fr and not np.isfinite(value):fr='derived_feature_not_finite'
            applied=not fr;old=frozen.loc[(date,f)];expected_reason=fr or 'conditional_market_close_plus_2h_accepted'
            ok=(bool(old.proposed_same_day_applied)==applied and bool(old.fallback)==(not applied) and old.reason==expected_reason and np.isclose(old.baseline_value,baseX.loc[date,f],rtol=1e-10,atol=1e-10,equal_nan=True) and pd.Timestamp(old.origin_ET)==origin)
            if clock:ok=ok and pd.Timestamp(old.close_at_local)==local and pd.Timestamp(old.conditional_available_at_ET)==available and old.evidence==evidence
            if applied:
                ok=ok and np.isclose(value,old.proposed_native_value,rtol=1e-10,atol=1e-10) and available<=origin
                newX.loc[date,f]=value
            maskcheck.append(dict(date=str(date.date()),feature=f,applied=applied,fallback=not applied,reason=expected_reason,close_at_local=str(local) if local is not None else '',conditional_available_at_ET=str(available) if available is not None else '',origin_ET=str(origin),recomputed_value=value if applied else np.nan,mask_matches=ok))
    maskcheck=pd.DataFrame(maskcheck);csv('MASK_INDEPENDENT_RECHECK.csv',maskcheck);ck('frozen_mask_matches_independent_reconstruction',maskcheck.mask_matches.all())
    ck('other48_identical',newX[others].equals(baseX[others]))
    application=maskcheck.pivot(index='date',columns='feature',values='applied');application.index=pd.to_datetime(application.index);application=application.reindex(data.index)
    ck('fixed_training_eval_application_counts',int(application.loc[application.index.year<2017].to_numpy().sum())==6450 and int(application.loc[application.index.year>=2017].to_numpy().sum())==4230)
    ck('fallback_original_values_preserved',all(newX.loc[~application[f],f].equals(baseX.loc[~application[f],f]) for f in krcols))
    ck('same_2495_rows_1007_evaluation',len(data)==2495 and data.index.is_unique and len(data[data.index.year>=2017])==1007 and data.index.max()<=pd.Timestamp('2020-12-31'))
    sox=pd.read_csv(ROOT/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv',comment='#',usecols=['Date','Close']);sox=sox[sox.Date<='2020-12-31'].set_index('Date').sort_index();y=(sox.Close>sox.Close.shift()).astype(int).reindex(data.index.strftime('%Y-%m-%d')).to_numpy()
    ck('Y_matches_actual_previous_US_close',np.array_equal(y,data.Y));ck('origins_09_ET',data.origin_et.str.contains('09:00:00').all())
    dev=data[data.index.year>=2017];saved=pd.read_csv(V/'predictions/ALL_PREDICTIONS_WITH_BENCHMARKS.csv',parse_dates=['date'])
    def reference(sc,g):
        z=saved[(saved.scenario==sc)&(saved.group==g)&(saved.algorithm=='LogisticClassifier')].set_index('date').sort_index();ck(sc+g+'_dates_Y',z.index.equals(dev.index) and np.array_equal(z.Y,dev.Y));return z
    r0=reference('C_latest_monthly_expanding','M1');best=reference('D_latest_monthly_3years','M0');refs={'always_up':np.ones(len(dev),dtype=int),'R0':r0.prediction.to_numpy(),'old_best':best.prediction.to_numpy()}
    ck('reference_correct_563_549_567',[int((r==dev.Y.to_numpy()).sum()) for r in refs.values()]==[563,549,567])
    meta={f['fold']:f for f in json.loads((V/'logs/FOLD_DETAILS.json').read_text()) if f['scenario']=='C_latest_monthly_expanding' and f['group']=='M1' and f['algorithm']=='LogisticClassifier'}
    labels=pd.to_datetime(data.label_available_et,utc=True);folds=[];cached=[];template=None;params=None
    for month in pd.period_range('2017-01','2020-12',freq='M'):
        test=data[data.index.to_period('M')==month];origin=pd.to_datetime(test.iloc[0].origin_et,utc=True);tr=data[(data.index<test.index[0])&(labels<origin)];f=meta[str(month)]
        ck('fold_training_'+str(month),len(tr)==f['train_n'] and str(tr.index[0].date())==f['train_start'] and str(tr.index[-1].date())==f['train_end'] and str(tr.label_end.max().date())==f['max_train_label_end'] and len(tr)>=500 and tr.Y.nunique()==2 and (pd.to_datetime(tr.label_available_et,utc=True)<origin).all())
        oldmodel=joblib.load(V/f['model_path']);pp=oldmodel.predict_proba(test[cols])[:,1]
        now={s:oldmodel.named_steps[s].get_params(deep=False) for s in ['impute','scale','model']}
        if params is None:params=now;template=oldmodel
        ck('R0_cache_'+str(month),canonical(now)==canonical(params) and list(oldmodel.classes_)==[0,1] and list(oldmodel.feature_names_in_)==cols and np.allclose(pp,r0.loc[test.index].probability,rtol=0,atol=1e-9) and np.array_equal((pp>=.5).astype(int),r0.loc[test.index].prediction))
        med=np.nan_to_num(np.nanmedian(baseX.loc[tr.index],axis=0),nan=0);filled=np.where(np.isnan(baseX.loc[tr.index]),med,baseX.loc[tr.index])
        ck('R0_preprocessing_'+str(month),np.allclose(oldmodel.named_steps['impute'].statistics_,med,rtol=1e-10,atol=1e-10) and np.allclose(oldmodel.named_steps['scale'].mean_,filled.mean(axis=0),rtol=1e-10,atol=1e-10) and np.allclose(oldmodel.named_steps['scale'].var_,filled.var(axis=0),rtol=1e-10,atol=1e-10))
        cached.append(dict(month=str(month),model_path=f['model_path'],sha256=sha(V/f['model_path']),max_probability_error=float(np.max(abs(pp-r0.loc[test.index].probability.to_numpy())))))
        folds.append(dict(month=str(month),origin=str(origin),train_n=len(tr),train_start=str(tr.index[0].date()),train_end=str(tr.index[-1].date()),max_train_label_available=str(pd.to_datetime(tr.label_available_et,utc=True).max()),test_n=len(test),training_hash=hashframe(pd.concat([newX.loc[tr.index],tr.Y],axis=1)),training_applied_cells=int(application.loc[tr.index].to_numpy().sum()),training_target_cells=len(tr)*5,test_applied_days=int(application.loc[test.index].any(axis=1).sum())))
    ck('template_fixed_parameters',params['model']['C']==1 and params['model']['class_weight'] is None and params['model']['random_state']==SEED and params['model']['max_iter']==2000)
    js('R0_CACHE_AUDIT.json',cached);js('ESTIMATOR_PARAMETERS.json',params);csv('logs/FOLD_PREFLIGHT.csv',folds)
    env=dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__,joblib=joblib.__version__,platform=platform.platform(),threads=1,seed=SEED);js('ENVIRONMENT.json',env)
    newdata=data.copy();newdata[cols]=newX;newdata.to_csv(O/'data/KR_ONLY_1D.csv',encoding='utf-8-sig')
    js('PREFLIGHT.json',dict(status='PASS',mask_source_sha256=sha(P/'A1_PARTIAL_ROW_REVIEW.csv'),frozen_KR_mask_sha256=sha(O/'inputs/FROZEN_KR_MASK.csv'),scope_sha256=sha(P/'REVIEW_SCOPE.md'),RAW01_sha256=sha(rawpath),source_plan_sha256=sha(P/'REVISED_EXPERIMENT_PLAN.md'),execution_spec_sha256=sha(O/'EXECUTION_SPEC.md'),baseline_X_sha256=hashframe(baseX),new_X_sha256=hashframe(newX),other48_sha256=hashframe(newX[others]),initial_training_n=1488,evaluation_n=1007,fixed_training_application_days=1290,fixed_eval_application_days=846,source13_changed=False,source23_changed=False,new_fits_before_preflight=0,all_checks_passed=len(CHECKS),conditional_market_information_only=True))
    csv('QC.csv',CHECKS);print('PREFLIGHT PASS: frozen mask, clocks, RAW, all48 R0 models and folds. Starting KR only, cap48.',flush=True)
    attempts=[];preds=[]
    for f in folds:
        month=f['month'];test=data[data.index.to_period('M').astype(str)==month];origin=pd.Timestamp(f['origin']);tr=data[(data.index<test.index[0])&(labels<origin)]
        assert len(attempts)<48
        row={**f,'attempt':len(attempts)+1,'status':'STARTED','policy':'A1_KR_ONLY'};attempts.append(row);csv('logs/FIT_ATTEMPTS.csv',attempts)
        m=clone(template)
        try:
            with warnings.catch_warnings(record=True) as ws:
                warnings.simplefilter('always');m.fit(newX.loc[tr.index],tr.Y)
            row['warnings']=' | '.join(str(w.message) for w in ws)
            assert m.named_steps['model'].n_iter_.max()<m.named_steps['model'].max_iter,'Convergence limit'
            assert canonical({s:m.named_steps[s].get_params(deep=False) for s in ['impute','scale','model']})==canonical(params),'Model settings changed'
            path=O/f'models/A1_KR_ONLY_{month}.joblib';joblib.dump(m,path);row['model_path']=str(path.relative_to(O));row['sha256']=sha(path);row['status']='PASS';p=m.predict_proba(newX.loc[test.index])[:,1]
        except Exception as e:
            row['status']='FAIL';row['error']=repr(e);csv('logs/FIT_ATTEMPTS.csv',attempts);raise
        csv('logs/FIT_ATTEMPTS.csv',attempts)
        for date,prob in zip(test.index,p):preds.append(dict(policy='A1_KR_ONLY',date=str(date.date()),year=date.year,month=month,Y=int(data.loc[date,'Y']),probability=float(prob),prediction=int(prob>=.5),threshold=.5,C=1,training_up_probability=float(tr.Y.mean()),same_day_applied=bool(application.loc[date].any()),applied_feature_count=int(application.loc[date].sum()),R0_probability=float(r0.loc[date].probability),R0_prediction=int(r0.loc[date].prediction),old_best_prediction=int(best.loc[date].prediction),always_up_prediction=1))
        csv('predictions/EXTERNAL_PREDICTIONS.csv',preds);print('KR fit',len(attempts),month,'PASS',flush=True)
    ck('48_successful_fits',len(attempts)==48 and all(r['status']=='PASS' for r in attempts))
    pr=pd.DataFrame(preds);ck('all1007_predictions',pr.date.tolist()==dev.index.strftime('%Y-%m-%d').tolist() and np.array_equal(pr.Y,dev.Y));ck('threshold_fixed',np.array_equal(pr.prediction,(pr.probability>=.5).astype(int)))
    metricrows=[];cis=[];dist=[];aux=[]
    for policy,probs,pred in [('A1_KR_ONLY',pr.probability.to_numpy(),pr.prediction.to_numpy()),('R0',r0.probability.to_numpy(),r0.prediction.to_numpy())]:
        for year in ['ALL',2017,2018,2019,2020]:
            mask=np.ones(len(dev),bool) if year=='ALL' else dev.index.year==year;y=pr.Y.to_numpy()[mask];p=probs[mask];q=pr.training_up_probability.to_numpy()[mask];c=pred[mask];row=dict(policy=policy,period=year,**metrics(y,p,c,q))
            n=len(y);rng=np.random.default_rng(SEED);starts=rng.integers(0,n-20+1,size=(2000,int(np.ceil(n/20))));idx=(starts[:,:,None]+np.arange(20)).reshape(2000,-1)[:,:n]
            for name,ref in refs.items():
                b=ref[mask];delta=(c==y).astype(int)-(b==y).astype(int);lo,hi=np.quantile(delta[idx].mean(axis=1)*100,[.025,.975]);row[name+'_correct']=int((b==y).sum());row[name+'_accuracy']=float((b==y).mean());row[name+'_delta_correct']=int(delta.sum());row[name+'_delta_pp']=float(delta.mean()*100);row['beats_'+name]=bool(delta.sum()>0)
                cis.append(dict(policy=policy,period=year,reference=name,n=n,delta_correct=int(delta.sum()),delta_pp=float(delta.mean()*100),CI95_low_pp=float(lo),CI95_high_pp=float(hi),block=20,replicates=2000,seed=SEED))
            metricrows.append(row)
            for cl in [0,1]:
                pp=p[y==cl];dist.append(dict(policy=policy,period=year,actual_class=cl,n=len(pp),mean=pp.mean(),std=pp.std(),q05=np.quantile(pp,.05),q25=np.quantile(pp,.25),median=np.median(pp),q75=np.quantile(pp,.75),q95=np.quantile(pp,.95),fraction045_055=((pp>=.45)&(pp<=.55)).mean()))
            for subset,selected in [('fixed_applied_days',pr.same_day_applied.to_numpy()[mask]),('fixed_fallback_days',~pr.same_day_applied.to_numpy()[mask])]:
                yy=y[selected];cp=p[selected];cc=c[selected];qq=q[selected];ar=dict(policy=policy,period=year,subset=subset,analysis='AUXILIARY_ONLY_NOT_PRIMARY',**metrics(yy,cp,cc,qq))
                for name,ref in refs.items():
                    bb=ref[mask][selected];ar[name+'_correct']=int((bb==yy).sum());ar[name+'_delta_correct']=int((cc==yy).sum()-(bb==yy).sum());ar[name+'_delta_pp']=float(((cc==yy).mean()-(bb==yy).mean())*100)
                aux.append(ar)
    csv('METRICS.csv',metricrows);csv('PAIRED_BLOCK_BOOTSTRAP.csv',cis);csv('PROBABILITY_DISTRIBUTIONS.csv',dist);csv('FIXED_MASK_SUBSET_AUXILIARY.csv',aux)
    app=maskcheck.copy();app['year']=pd.to_datetime(app.date).dt.year;app['scope']=np.where(app.year<2017,'initial_training_2011_2016','evaluation_2017_2020')
    for name,keys in [('APPLICATION_RATES.csv',['scope','feature']),('APPLICATION_RATES_BY_YEAR.csv',['year','feature']),('FALLBACK_REASONS.csv',['scope','year','feature','reason'])]:
        z=app.groupby(keys).agg(feature_cells=('applied','size'),applied_cells=('applied','sum'),fallback_cells=('fallback','sum')).reset_index();z['application_pct']=100*z.applied_cells/z.feature_cells;z['fallback_pct']=100*z.fallback_cells/z.feature_cells;csv(name,z)
    daily=app.groupby(['scope','year','date']).applied.any().reset_index();dr=daily.groupby(['scope','year']).agg(days=('date','size'),applied_days=('applied','sum')).reset_index();dr['fallback_days']=dr.days-dr.applied_days;dr['application_pct']=100*dr.applied_days/dr.days;dr['fallback_pct']=100*dr.fallback_days/dr.days;csv('APPLICATION_DAYS_BY_YEAR.csv',dr)
    csv('QC.csv',CHECKS);js('RUN_SUMMARY.json',dict(status='EXECUTED_PENDING_INDEPENDENT_REVIEW',new_fit_attempts=len(attempts),fit_failures=0,budget=48,candidate='A1_KR_ONLY',TW23_executed=False,additional_tuning=False,mask_changed=False,evaluation_n=1007,new_model_files=len(list((O/'models').glob('*.joblib'))),protected_before=len(before)))
    print('KR48 complete; all1007 predictions saved; independent review pending.',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:
        js('EXECUTION_FAILURE.json',dict(status='FAIL',error=repr(e),retry=False));raise
