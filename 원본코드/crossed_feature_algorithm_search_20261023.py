"""Same feature masks crossed with every estimator and target; resumable."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,hashlib,itertools,time,warnings,traceback
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np,pandas as pd,joblib
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
import staged_multi_algorithm_search_v2_20261023 as parent
W=parent.W;O=W/'outputs/crossed_feature_algorithm_v1_20261023';SEED=20261023;ALGOS=parent.ALGOS;TASKS=parent.TASKS;WORKERS=4
def sha(p):return parent.sha(p)
def js(p,x):return parent.js(p,x)
def load(p):return parent.load(p)
def csv(p,x):return parent.csv(p,x)
def verify():assert all(sha(p)==h for p,h in load(O/'INPUT_SEAL.json').items())
def estimator(algo,task):
    m=parent.model(algo,task)
    # Fixed computational budget, declared before any crossed-search score.
    if algo in ['RF','ET']:m.set_params(n_estimators=48)
    elif algo=='HGB':m.set_params(max_iter=60)
    elif algo in ['XGB','LGBM']:m.set_params(n_estimators=64)
    return m
def prepare():
    O.mkdir(exist_ok=False);(O/'windows').mkdir();(O/'audit_models').mkdir();parent.verify()
    x,y,fs=parent.inputdata();groups=load(parent.O/'GROUPS.json');source=load(parent.O/'COMBINATIONS.json');masks=[];rng=np.random.default_rng(SEED)
    for c in source:
        cols=sum([groups[g] for g in c['groups']],[])
        if c['french']!='NONE':cols +=[c['french']+'_PC'+str(k+1) for k in range(10)]
        masks.append(dict(mask=c['combo'],kind='GROUP',groups=c['groups'],french=c['french'],features=cols))
    rawcols=list(fs['NEXT20'].columns)
    def add(cols,lag,description):
        masks.append(dict(mask=f'I{len([m for m in masks if m["kind"]=="INDIVIDUAL"]):03}',kind='INDIVIDUAL',groups=[],french=lag,features=list(cols),design=description))
    # Guarantee every one of the216 nonFrench variables and420 raw French
    # variables in each lag scenario appears somewhere in the candidate bank.
    for chunk in np.array_split(np.array(x.columns,dtype=object),2):add(chunk.tolist(),'NONE','coverage partition; no price mandatory')
    for lag in ['NEXT20','MONTH2_FIRST']:
        for chunk in np.array_split(np.array(rawcols,dtype=object),5):
            base=rng.choice(x.columns,8,replace=False).tolist();add(base+[lag+'::'+c for c in chunk],lag,'all420 raw French coverage partition+8 mixed nonFrench')
    sizes=[8,16,24,32,48,64,96,128]
    while len(masks)<256:
        j=len(masks)-192;lag=['NONE','NEXT20','MONTH2_FIRST'][j%3];pool=list(x.columns)+([] if lag=='NONE' else [lag+'::'+c for c in rawcols]);n=sizes[j%len(sizes)]
        if j%2==0:cols=rng.choice(pool,n,replace=False).tolist()
        else:
            # Group-balanced random sets, then individual draw; no Y ranking.
            buckets=[groups[g] for g in groups]+([] if lag=='NONE' else [[lag+'::'+c for c in rawcols]])
            cols=[]
            while len(cols)<n:
                bucket=buckets[int(rng.integers(len(buckets)))];c=str(rng.choice(bucket))
                if c not in cols:cols.append(c)
        add(cols,lag,'fixed-seed individual subset, cardinality'+str(n))
    assert len(masks)==256 and len({m['mask'] for m in masks})==256
    individual=[m for m in masks if m['kind']=='INDIVIDUAL'];union=set(sum([m['features'] for m in individual],[]));assert set(x.columns)<=union
    for lag in fs:assert {lag+'::'+c for c in rawcols}<=union
    csv(O/'VARIABLE_MASKS.csv',[dict(mask=m['mask'],kind=m['kind'],french=m['french'],count=len(m['features']),features='|'.join(m['features'])) for m in masks]);js(O/'MASKS.json',masks)
    plan=dict(seed=SEED,workers=WORKERS,masks=256,group_masks=192,individual_masks=64,algorithms=ALGOS,targets=TASKS,screen='all256 x all6 x both2 x3annual folds2016/2018/2020=9216fits; no LR prefilter',bank='union of best mask for each algorithm-target; baseline; ensure3 individual masks; pooled normalized rank fill to16; all pre2021; same16 for every algorithm and bothtargets',confirmation='all16 x6 x2 x36monthly2021..2023=6912fits; train2011..previousmonth',final='all16 x6 x2 x34monthly2024..2026-10=6528fits;694sameevaluationdays; no late reselection',fit_cap=22656,feature_rules='same fixed mask for all algorithms/targets; train-only coverage80%,nonconstant,median,scaling,directPearsonabs.95greedy; no supervised ANOVA or algorithm-specific subset',French='group masks may PCA420->10; individual masks may use rawderived420 directly; assumed prior release lags retained; no mixed lag versions within one mask',algorithms_parameters={a:estimator(a,'BINARY').get_params() for a in ALGOS},targets_rule='same SOX1d binary and previouscalendar-year absreturn median4class labels; label availability cutoff retained',decision='freeze best algorithm-mask per target using monthly2021..2023 only; candidate must improve accuracy and TN(binary) or macroF1(four) vs baselineLR; else baselineLR',storage='all forecasts and feature logs retained; audit estimators retained for2021Jan/2023Dec/2024Jan/2026Oct',revision_risk_remains=True,independent_test=False,API_calls=0,automatic_adoption=False)
    js(O/'FROZEN_PLAN.json',plan)
    inputs=[Path(__file__),W/'work/staged_multi_algorithm_search_v2_20261023.py',parent.O/'INPUT_SEAL.json',parent.O/'X216_WITHOUT_FRENCH_COMPONENTS_NO_Y.csv',parent.O/'LABELS_FOR_TRAINING_ONLY.csv',parent.O/'GROUPS.json',parent.O/'COMBINATIONS.json']+[parent.F/f'{p}_FRENCH420_ALIGNED_NO_Y.csv' for p in fs]+[O/'FROZEN_PLAN.json',O/'MASKS.json']
    js(O/'INPUT_SEAL.json',{str(p):sha(p) for p in inputs});js(O/'CURRENT_STATE.json',dict(stage='PREPARED',fits_completed=0,fit_cap=22656));print('PREPARED256 masks,64individual; FULL CROSS6algorithms x2targets;22656fit cap',flush=True)
def bundle(x,y,fs,cutoff,end):
    b=parent.bundle(x,y,fs,cutoff,end)
    aa=[b['a']];bb=[b['b']];names=list(b['names']);raw_scopes={}
    for lag in fs:
        imp,sc,pc=b['stats']['PCA'][lag];a=sc.transform(imp.transform(fs[lag].loc[b['td']]));e=sc.transform(imp.transform(fs[lag].loc[b['ed']]));aa.append(a);bb.append(e);names.extend(lag+'::'+c for c in fs[lag].columns)
    a=np.column_stack(aa);e=np.column_stack(bb);keep=np.std(a,axis=0)>1e-12
    a=a[:,keep];e=e[:,keep];names=[n for n,k in zip(names,keep) if k]
    b['stats']['cross_nonconstant_mask']=keep;b['stats']['cross_feature_names']=names
    corr=np.abs(np.corrcoef(a,rowvar=False));assert np.isfinite(a).all() and np.isfinite(e).all() and np.isfinite(corr).all();b.update(a=a,b=e,names=names,corr=corr);return b
def mask_indices(b,mask):
    wanted=set(mask['features']);ix=[]
    for i,n in enumerate(b['names']):
        if n in wanted and not any(b['corr'][i,j]>=.95 for j in ix):ix.append(i)
    assert ix,mask['mask'];return ix
def run_one(b,mask,task,algo,ix):
    model=estimator(algo,task);model.fit(b['a'][:,ix],b['y'][task]);p=model.predict_proba(b['b'][:,ix]);k=2 if task=='BINARY' else 4
    assert np.array_equal(model.classes_,np.arange(k)) and p.shape==(len(b['ed']),k) and np.isfinite(p).all() and (p>=0).all() and np.allclose(p.sum(1),1,atol=1e-6)
    return mask['mask'],task,algo,p,model
def phase(stage):
    verify();assert stage in ['screen','confirm','late'];done=O/f'{stage}_COMPLETE.json';assert not done.exists();masks=load(O/'MASKS.json')
    if stage!='screen':
        assert sha(O/'BANK16.json')==load(O/'BANK_SEAL.json')['sha256'];bank=load(O/'BANK16.json');masks=[m for m in masks if m['mask'] in bank];assert len(masks)==16
    if stage=='late':assert sha(O/'DECISION_PRE2024.json')==load(O/'DECISION_SEAL.json')['sha256']
    windows=[(str(yr),f'{yr}-01-01',f'{yr+1}-01-01') for yr in [2016,2018,2020]] if stage=='screen' else [(str(m),str(m)+'-01',str(m+1)+'-01') for m in pd.period_range('2021-01' if stage=='confirm' else '2024-01','2023-12' if stage=='confirm' else '2026-10',freq='M')]
    x,y,fs=parent.inputdata();summaries=[];totalfits=0
    warnings.filterwarnings('error',category=ConvergenceWarning);warnings.filterwarnings('ignore',message='X does not have valid feature names')
    for window,cutoff,end in windows:
        root=O/'windows'/f'{stage}_{window}';root.mkdir(exist_ok=True);seal=root/'COMPLETE.json'
        if seal.exists():
            d=load(seal);assert sha(root/'PREDICTIONS_NO_Y.npz')==d['prediction_sha256'];summaries.append(d);totalfits+=d['fits'];print('REUSE',stage,window,d['fits'],'fits',flush=True);continue
        b=bundle(x,y,fs,cutoff,end);indices={m['mask']:mask_indices(b,m) for m in masks};order=list(itertools.product([m['mask'] for m in masks],TASKS,ALGOS));by={m['mask']:m for m in masks};position={k:i for i,k in enumerate(order)};pred=np.full((len(order),len(b['ed']),4),np.nan);fitlog=[];audit={};start=time.monotonic();audit_this=window in ['2021-01','2023-12','2024-01','2026-10']
        joblib.dump(b['stats'],root/'TRAIN_TRANSFORM.joblib',compress=3);js(root/'FEATURE_MASKS.json',{m['mask']:[b['names'][i] for i in indices[m['mask']]] for m in masks})
        executor=ThreadPoolExecutor(max_workers=WORKERS);futures={}
        try:
            for mask,task,algo in order:
                f=executor.submit(run_one,b,by[mask],task,algo,indices[mask]);futures[f]=(mask,task,algo)
            n=0
            for future in as_completed(futures):
                mask,task,algo,p,model=future.result();i=position[mask,task,algo];pred[i,:,:p.shape[1]]=p;n+=1
                prior=np.bincount(b['y'][task],minlength=p.shape[1])/len(b['td']);fitlog.append(dict(mask=mask,task=task,algo=algo,n_features=len(indices[mask]),train_start=str(b['td'][0]),train_end=str(b['td'][-1]),n_train=len(b['td']),prior=prior.tolist(),fit_success=True))
                if audit_this:audit[str(i)]=model
                if n%96==0 or n==len(order):
                    js(O/'CURRENT_STATE.json',dict(stage=stage,window=window,window_fits=n,window_total=len(order),phase_fits=totalfits+n,elapsed_seconds=round(time.monotonic()-start,1),fit_cap=22656));print(stage,window,n,'/',len(order),'fits',round(time.monotonic()-start,1),'sec',flush=True)
        except BaseException:
            for f in futures:f.cancel()
            executor.shutdown(wait=True,cancel_futures=True);js(root/'FAILURE.json',dict(error=traceback.format_exc(),completed=len(fitlog)));raise
        executor.shutdown(wait=True)
        np.savez_compressed(root/'PREDICTIONS_NO_Y.npz',dates=b['ed'].astype(str),probabilities=pred,mask=np.array([k[0] for k in order]),task=np.array([k[1] for k in order]),algo=np.array([k[2] for k in order]));js(root/'FIT_LOG.json',fitlog)
        if audit_this:joblib.dump(audit,O/'audit_models'/f'{stage}_{window}.joblib',compress=3)
        d=dict(stage=stage,window=window,fits=len(order),eval_start=str(b['ed'][0]),eval_end=str(b['ed'][-1]),train_end=str(b['td'][-1]),prediction_sha256=sha(root/'PREDICTIONS_NO_Y.npz'),features_sha256=sha(root/'FEATURE_MASKS.json'),transform_sha256=sha(root/'TRAIN_TRANSFORM.joblib'),fitlog_sha256=sha(root/'FIT_LOG.json'),window_root=str(root),eval_Y_used_for_fit=False,audit_models=audit_this)
        js(seal,d);summaries.append(d);totalfits+=len(order)
    verify();js(done,dict(stage=stage,fits=totalfits,windows=summaries,selection_uses_post2023=False));print(stage,'COMPLETE',totalfits,'fits',flush=True)
def phase_scores(stage):
    complete=load(O/f'{stage}_COMPLETE.json');x,y,fs=parent.inputdata();cache={};baselines={};bywindow=[]
    for row in complete['windows']:
        root=Path(row['window_root']);assert sha(root/'PREDICTIONS_NO_Y.npz')==row['prediction_sha256'];fitlog={(r['mask'],r['task'],r['algo']):r for r in load(root/'FIT_LOG.json')}
        with np.load(root/'PREDICTIONS_NO_Y.npz') as z:dates=z['dates'].astype(str);prob=z['probabilities'];masks=z['mask'];tasks=z['task'];algos=z['algo']
        if stage!='late':assert dates[-1]<'2024-01-01'
        for i,(mask,task,algo) in enumerate(zip(masks,tasks,algos)):
            key=(str(mask),str(task),str(algo));p=prob[i,:,:2 if task=='BINARY' else 4];yy=y.loc[dates,'Y' if task=='BINARY' else 'class4'].to_numpy(int);cache.setdefault(key,[]).append((dates,p,yy));bywindow.append(dict(mask=mask,task=task,algo=algo,window=row['window'],**parent.metric(yy,p,task)))
    results=[]
    for (mask,task,algo),entries in cache.items():
        dates=np.concatenate([v[0] for v in entries]);p=np.concatenate([v[1] for v in entries]);yy=np.concatenate([v[2] for v in entries]);results.append(dict(mask=mask,task=task,algo=algo,candidate=mask,**parent.metric(yy,p,task)))
    csv(O/f'{stage}_METRICS.csv',results);csv(O/f'{stage}_WINDOW_METRICS.csv',bywindow);return results,cache
def bank():
    verify();assert not (O/'BANK16.json').exists();rows,_=phase_scores('screen');base=load(parent.O/'FROZEN_PLAN.json')['baseline_combo'];masks=load(O/'MASKS.json');kind={m['mask']:m['kind'] for m in masks};bank=[];ranks={m['mask']:[] for m in masks};algorithm_winners=[]
    for task,algo in itertools.product(TASKS,ALGOS):
        rr=[r for r in rows if r['task']==task and r['algo']==algo];b=next(r for r in rr if r['mask']==base);rank=parent.rank(rr,task,b);algorithm_winners.append(dict(task=task,algo=algo,mask=rank[0]['mask']))
        if rank[0]['mask'] not in bank:bank.append(rank[0]['mask'])
        for j,r in enumerate(rank):ranks[r['mask']].append(j/255)
    if base not in bank:bank.append(base)
    pooled=sorted(ranks,key=lambda m:(np.mean(ranks[m]),m));individuals=[m for m in pooled if kind[m]=='INDIVIDUAL']
    while sum(kind[m]=='INDIVIDUAL' for m in bank)<3:
        bank.append(next(m for m in individuals if m not in bank))
    assert len(bank)<=16
    for m in pooled:
        if len(bank)==16:break
        if m not in bank:bank.append(m)
    assert len(bank)==16 and base in bank;js(O/'BANK16.json',bank);js(O/'BANK_SELECTION_DETAIL.json',dict(algorithm_winners=algorithm_winners,pooled_rank=[dict(mask=m,mean_rank=float(np.mean(ranks[m]))) for m in pooled],selected=bank,all_algorithms_all_tasks_get_same_bank=True));js(O/'BANK_SEAL.json',dict(sha256=sha(O/'BANK16.json')));print('COMMON BANK16 FROZEN',bank,flush=True)
def select():
    verify();assert not (O/'DECISION_PRE2024.json').exists();rows,_=phase_scores('confirm');base=load(parent.O/'FROZEN_PLAN.json')['baseline_combo'];decision={}
    for task in TASKS:
        b=next(r for r in rows if r['task']==task and r['mask']==base and r['algo']=='LR');eligible=[]
        for r in rows:
            if r['task']!=task:continue
            if r['accuracy']>b['accuracy'] and (r['TN']>=b['TN'] if task=='BINARY' else r['macro_F1']>b['macro_F1']):eligible.append({**r,'candidate':r['mask']+'__'+r['algo']})
        best=parent.rank(eligible,task,b)[0] if eligible else b;decision[task]=dict(mask=best['mask'],algo=best['algo'])
    js(O/'DECISION_PRE2024.json',dict(selected=decision,selection_end='2023-12-29',no_late_reselection=True,automatic_adoption=False));js(O/'DECISION_SEAL.json',dict(sha256=sha(O/'DECISION_PRE2024.json')));print('DECISION FROZEN',decision,flush=True)
def score():
    verify();assert sha(O/'DECISION_PRE2024.json')==load(O/'DECISION_SEAL.json')['sha256'];rows,cache=phase_scores('late');yearly=[];daily=[];cmrows=[];comparisons=[];base=load(parent.O/'FROZEN_PLAN.json')['baseline_combo'];rng=np.random.default_rng(SEED);n=694;ix=(rng.integers(0,n-19,size=(1000,int(np.ceil(n/20))))[:,:,None]+np.arange(20)).reshape(1000,-1)[:,:n]
    for (mask,task,algo),entries in cache.items():
        dates=np.concatenate([r[0] for r in entries]);p=np.concatenate([r[1] for r in entries]);yy=np.concatenate([r[2] for r in entries]);pred=(p[:,1]>=.5).astype(int) if task=='BINARY' else p.argmax(1);assert len(dates)==694
        for year in [2024,2025,2026]:
            take=np.char.startswith(dates,str(year));yearly.append(dict(mask=mask,task=task,algo=algo,year=year,**parent.metric(yy[take],p[take],task)))
        for day,pr,target,pp in zip(dates,pred,yy,p):daily.append(dict(mask=mask,task=task,algo=algo,date=str(day),prediction=int(pr),Y=int(target),correct=bool(pr==target),**{f'p{k}':float(v) for k,v in enumerate(pp)}))
        cm=parent.confusion_matrix(yy,pred,labels=range(p.shape[1]));cmrows.extend(dict(mask=mask,task=task,algo=algo,actual=i,predicted=j,n=int(cm[i,j])) for i in range(len(cm)) for j in range(len(cm)))
        be=cache[base,task,'LR'];bp=np.concatenate([r[1] for r in be]);bpred=(bp[:,1]>=.5).astype(int) if task=='BINARY' else bp.argmax(1);delta=(pred==yy).astype(float)-(bpred==yy).astype(float);values=delta[ix].mean(1)*100;comparisons.append(dict(mask=mask,task=task,algo=algo,delta_correct=int(delta.sum()),delta_pp=float(delta.mean()*100),lo95=float(np.quantile(values,.025)),hi95=float(np.quantile(values,.975)),exploratory_after_large_search=True))
    csv(O/'LATE_YEARLY_METRICS.csv',yearly);csv(O/'LATE_DAILY_RESULTS.csv',daily);csv(O/'CONFUSION_MATRICES.csv',cmrows);csv(O/'PAIRED_BLOCK_BOOTSTRAP.csv',comparisons);js(O/'SCORING_COMPLETE.json',dict(status='PASS',policies=len(rows),same16_masks_for_all6algorithms_and_both2targets=True,late_days=694,decision_sha256=sha(O/'DECISION_PRE2024.json'),independent_test=False));print('SCORED192 crossed policies;694same days;frozen choice preserved',flush=True)
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1);warnings.filterwarnings('ignore',message='The y_prob values do not sum to one');{'prepare':prepare,'screen':lambda:phase('screen'),'bank':bank,'confirm':lambda:phase('confirm'),'select':select,'late':lambda:phase('late'),'score':score}[sys.argv[1]]()
