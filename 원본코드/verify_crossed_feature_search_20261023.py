import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import itertools,warnings
from pathlib import Path
import numpy as np,pandas as pd,joblib
from sklearn.base import clone
from threadpoolctl import threadpool_limits
import crossed_feature_algorithm_search_20261023 as s
def transform(x,fs,stats,cutoff,dates):
    td=x.index[x.index<cutoff];raw=stats['raw_features'];imp=stats['imputer'];scale=stats['scaler'];assert stats['train_end']==td[-1] and stats['n_train']==len(td)
    eligible=x.loc[td].columns[x.loc[td].notna().mean()>=.8].tolist();eligible=[c for c in eligible if x.loc[td,c].nunique(dropna=True)>1];assert raw==eligible;assert np.allclose(imp.statistics_,x.loc[td,raw].median())
    ta=imp.transform(x.loc[td,raw]);assert np.allclose(scale.mean_,ta.mean(0)) and np.allclose(scale.var_,ta.var(0));a=scale.transform(ta);b=scale.transform(imp.transform(x.loc[dates,raw]));names=list(raw);rawa=[];rawb=[]
    for lag in ['NEXT20','MONTH2_FIRST']:
        fi,ss,pc=stats['PCA'][lag];ft=fs[lag].loc[td];fe=fs[lag].loc[dates];assert np.allclose(fi.statistics_,ft.median());tt=fi.transform(ft);assert np.allclose(ss.mean_,tt.mean(0)) and np.allclose(ss.var_,tt.var(0));assert pc.n_samples_==len(td)
        aa=ss.transform(tt);bb=ss.transform(fi.transform(fe));again=clone(pc);scores=again.fit_transform(aa);assert np.allclose(again.components_,pc.components_,atol=1e-10);a=np.column_stack([a,scores]);b=np.column_stack([b,pc.transform(bb)]);names.extend(lag+'_PC'+str(k+1) for k in range(10));rawa.append(aa);rawb.append(bb)
    post=stats['post_scaler'];assert np.allclose(post.mean_,a.mean(0),atol=1e-10) and np.allclose(post.var_,a.var(0));a=post.transform(a);b=post.transform(b);a=np.column_stack([a]+rawa);b=np.column_stack([b]+rawb)
    for lag in ['NEXT20','MONTH2_FIRST']:names.extend(lag+'::'+c for c in fs[lag].columns)
    keep=np.std(a,axis=0)>1e-12;assert np.array_equal(keep,stats['cross_nonconstant_mask']);names=[n for n,k in zip(names,keep) if k];assert names==stats['cross_feature_names'];return a[:,keep],b[:,keep],names,td
def main():
    threadpool_limits(1);warnings.filterwarnings('ignore',message='X does not have valid feature names');s.verify();assert s.load(s.O/'SCORING_COMPLETE.json')['status']=='PASS';x,y,fs=s.parent.inputdata();masks=s.load(s.O/'MASKS.json');by={m['mask']:m for m in masks};bank=s.load(s.O/'BANK16.json');checks={};replayed=0;fits=0;maxerr=0.
    assert len(masks)==256 and len(bank)==16 and sum(by[m]['kind']=='INDIVIDUAL' for m in bank)>=3;assert s.sha(s.O/'BANK16.json')==s.load(s.O/'BANK_SEAL.json')['sha256'];assert s.sha(s.O/'DECISION_PRE2024.json')==s.load(s.O/'DECISION_SEAL.json')['sha256']
    # A future-data perturbation must leave training features and labels unchanged.
    first=s.bundle(x,y,fs,'2016-01-01','2017-01-01');xx=x.copy();yy=y.copy();ff={p:f.copy() for p,f in fs.items()};xx.loc[xx.index>='2016-01-01']=123456;yy.loc[yy.index>='2016-01-01','Y']=1-yy.loc[yy.index>='2016-01-01','Y'];yy.loc[yy.index>='2016-01-01','class4']=3-yy.loc[yy.index>='2016-01-01','class4']
    for f in ff.values():f.loc[f.index>='2016-01-01']=123456
    second=s.bundle(xx,yy,ff,'2016-01-01','2017-01-01');assert first['names']==second['names'] and np.array_equal(first['a'],second['a']) and all(np.array_equal(first['y'][t],second['y'][t]) for t in s.TASKS);checks['future_X_Y_mutation_training_invariant']=True
    for stage in ['screen','confirm','late']:
        complete=s.load(s.O/f'{stage}_COMPLETE.json');fits+=complete['fits'];expected=set(itertools.product([m['mask'] for m in masks] if stage=='screen' else bank,s.TASKS,s.ALGOS))
        for window in complete['windows']:
            root=Path(window['window_root']);seal=s.load(root/'COMPLETE.json')
            for file,key in [('PREDICTIONS_NO_Y.npz','prediction_sha256'),('FEATURE_MASKS.json','features_sha256'),('TRAIN_TRANSFORM.joblib','transform_sha256'),('FIT_LOG.json','fitlog_sha256')]:assert s.sha(root/file)==seal[key]
            with np.load(root/'PREDICTIONS_NO_Y.npz') as z:dates=z['dates'].astype(str);p=z['probabilities'];order=list(zip(z['mask'].astype(str),z['task'].astype(str),z['algo'].astype(str)))
            assert len(order)==len(expected) and set(order)==expected and dates[0]>seal['train_end'];assert stage=='late' or dates[-1]<'2024-01-01';stats=joblib.load(root/'TRAIN_TRANSFORM.joblib');cutoff=(window['window']+'-01-01') if stage=='screen' else (window['window']+'-01');a,b,names,td=transform(x,fs,stats,cutoff,dates);corr=np.abs(np.corrcoef(a,rowvar=False));actual=s.load(root/'FEATURE_MASKS.json');log=s.load(root/'FIT_LOG.json');look={(r['mask'],r['task'],r['algo']):r for r in log};assert len(look)==len(expected) and set(look)==expected
            for mask in {v[0] for v in order}:
                wanted=set(by[mask]['features']);ix=[]
                for i,n in enumerate(names):
                    if n in wanted and not any(corr[i,j]>=.95 for j in ix):ix.append(i)
                assert actual[mask]==[names[i] for i in ix]
            audit=s.load(root/'COMPLETE.json')['audit_models'];models=joblib.load(s.O/'audit_models'/f"{stage}_{window['window']}.joblib") if audit else {}
            for i,(mask,task,algo) in enumerate(order):
                k=2 if task=='BINARY' else 4;pp=p[i,:,:k];assert np.isfinite(pp).all() and (pp>=0).all() and (pp<=1).all();err=float(np.max(np.abs(pp.sum(1)-1)));maxerr=max(maxerr,err);assert err<1e-6
                r=look[mask,task,algo];assert r['n_train']==len(td) and r['train_end']==td[-1] and r['n_features']==len(actual[mask]);target=y.loc[td,'Y' if task=='BINARY' else 'class4'].to_numpy();assert np.allclose(r['prior'],np.bincount(target,minlength=k)/len(td))
                if audit:
                    model=models[str(i)];ix=[names.index(n) for n in actual[mask]];prob=model.predict_proba(b[:,ix]);assert np.allclose(prob,pp,atol=1e-9,rtol=1e-8);assert model.n_features_in_==len(ix);assert np.array_equal(model.classes_,np.arange(k));replayed+=1
            print('VERIFIED',stage,window['window'],len(order),'crossed policies',flush=True)
    checks.update(same_masks_crossed_with_all6algorithms_and2targets=True,train_only_preprocessing_and_masks_verified=True,all_window_hashes_verified=True,audit768_models_replayed=replayed==768,fit_cap=fits==22656)
    # Recompute the frozen pre2024 winner from internal monthly scores.
    confirm=pd.read_csv(s.O/'confirm_METRICS.csv');base=s.load(s.parent.O/'FROZEN_PLAN.json')['baseline_combo'];decision=s.load(s.O/'DECISION_PRE2024.json')['selected']
    for task in s.TASKS:
        rows=confirm[confirm.task==task].to_dict('records');base_row=next(r for r in rows if r['mask']==base and r['algo']=='LR');eligible=[{**r,'candidate':r['mask']+'__'+r['algo']} for r in rows if r['accuracy']>base_row['accuracy'] and (r['TN']>=base_row['TN'] if task=='BINARY' else r['macro_F1']>base_row['macro_F1'])];best=s.parent.rank(eligible,task,base_row)[0] if eligible else base_row;assert decision[task]==dict(mask=best['mask'],algo=best['algo'])
    checks['winner_fixed_before2024']=True
    # Bank selection pools all algorithms and both goals; no LR gatekeeper.
    screen=pd.read_csv(s.O/'screen_METRICS.csv');ranklists={m['mask']:[] for m in masks};rebuilt=[]
    for task,algo in itertools.product(s.TASKS,s.ALGOS):
        rows=screen[(screen.task==task)&(screen.algo==algo)].to_dict('records');base_row=next(r for r in rows if r['mask']==base);rr=s.parent.rank(rows,task,base_row)
        if rr[0]['mask'] not in rebuilt:rebuilt.append(rr[0]['mask'])
        for i,r in enumerate(rr):ranklists[r['mask']].append(i/255)
    if base not in rebuilt:rebuilt.append(base)
    pooled=sorted(ranklists,key=lambda m:(np.mean(ranklists[m]),m));individual=[m for m in pooled if by[m]['kind']=='INDIVIDUAL']
    while sum(by[m]['kind']=='INDIVIDUAL' for m in rebuilt)<3:rebuilt.append(next(m for m in individual if m not in rebuilt))
    for m in pooled:
        if len(rebuilt)==16:break
        if m not in rebuilt:rebuilt.append(m)
    assert rebuilt==bank;checks['common16_selection_all_algorithm_pool_recomputed']=True
    daily=pd.read_csv(s.O/'LATE_DAILY_RESULTS.csv');metrics=pd.read_csv(s.O/'late_METRICS.csv');assert len(daily.groupby(['mask','task','algo']))==192
    for (mask,task,algo),g in daily.groupby(['mask','task','algo']):
        assert len(g)==694 and g.date.is_unique;target=y.loc[g.date,'Y' if task=='BINARY' else 'class4'].to_numpy(int);assert np.array_equal(g.Y,target);p=g[['p'+str(k) for k in range(2 if task=='BINARY' else 4)]].to_numpy();pred=(p[:,1]>=.5).astype(int) if task=='BINARY' else p.argmax(1);assert np.array_equal(pred,g.prediction);row=metrics[(metrics['mask']==mask)&(metrics.task==task)&(metrics.algo==algo)].iloc[0];assert row.correct==int((pred==target).sum())
    reference=pd.read_csv(s.parent.O/'LATE_DAILY_RESULTS.csv')
    for task in s.TASKS:
        old=reference[(reference.task==task)&(reference.name=='BASELINE')].set_index('date').sort_index();new=daily[(daily.task==task)&(daily['mask']==base)&(daily.algo=='LR')].set_index('date').sort_index();assert old.index.tolist()==new.index.tolist() and np.array_equal(old.prediction,new.prediction)
        cols=['p'+str(k) for k in range(2 if task=='BINARY' else 4)];assert np.allclose(old[cols],new[cols],atol=1e-9,rtol=1e-8)
    checks['fixedC_baseline_reproduces_previous_framework']=True;checks['all192policies_same694days_scores_verified']=True;checks['past_year_fourclass_boundaries']=bool((y.reference_year==pd.to_datetime(y.index).year-1).all());assert all(checks.values());s.verify();s.js(s.O/'FINAL_VERIFICATION.json',dict(status='PASS_CONDITIONAL_FULL_CROSS',checks=checks,training_fits=fits,models_replayed=replayed,max_probability_sum_error=maxerr,independent_test=False,release_assumptions_remain=True,API_calls=0));print('PASS',fits,'fits;',replayed,'auditmodels;',192,'finalpolicies',flush=True)
if __name__=='__main__':main()
