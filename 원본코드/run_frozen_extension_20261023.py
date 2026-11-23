"""Reuse sealed October models; seal forecasts before separate truth/scoring stage."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import sys,json,hashlib,warnings
import numpy as np,pandas as pd,joblib
from sklearn.metrics import accuracy_score,balanced_accuracy_score,f1_score,log_loss,roc_auc_score,confusion_matrix,mean_absolute_error,mean_squared_error,r2_score
from threadpoolctl import threadpool_limits
W=Path(__file__).resolve().parents[1];O=W/'outputs/frozen_extension_all_tasks_20261023_v1_20261024';S=W/'outputs/crossed_feature_algorithm_v1_20261023';R=W/'outputs/sox_return_regression16_v1_20261024';P=W/'outputs/evaluation_extension_20261023_consistent_v5_20261024';O.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def js(name,x):(O/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def save(df,name):pd.DataFrame(df).to_csv(O/name,index=False,encoding='utf-8-sig')
def transform_fixed(x,fs,stats):
 a=stats['scaler'].transform(stats['imputer'].transform(x[stats['raw_features']]));pcs=[];raw=[];names=list(stats['raw_features'])
 for lag in ['NEXT20','MONTH2_FIRST']:
  fi,sc,pc=stats['PCA'][lag];b=sc.transform(fi.transform(fs[lag]));raw.append(b);pcs.append(pc.transform(b));names.extend(lag+'_PC'+str(i+1) for i in range(10))
 a=stats['post_scaler'].transform(np.column_stack([a]+pcs));a=np.column_stack([a]+raw)
 for lag in ['NEXT20','MONTH2_FIRST']:names.extend(lag+'::'+c for c in fs[lag].columns)
 keep=stats['cross_nonconstant_mask'];a=a[:,keep];names=[n for n,k in zip(names,keep) if k];assert names==stats['cross_feature_names'] and np.isfinite(a).all();return a,names
def infer():
 assert not (O/'FORECAST_SEAL.json').exists(),'Forecasts already sealed; do not overwrite'
 check=load(P/'동일규칙_최종검증.json');assert check['status']=='PASS_SAME_RULES_INPUT_PREPARATION_CONDITIONAL_HISTORY'
 inputs=[P/'동일규칙_최종검증.json',P/'기존10월전처리_모든조합입력_NO_Y.npz',S/'audit_models/late_2026-10.joblib',S/'windows/late_2026-10/COMPLETE.json',S/'windows/late_2026-10/FEATURE_MASKS.json',S/'windows/late_2026-10/PREDICTIONS_NO_Y.npz',R/'windows/2026-10/COMPLETE.json',R/'windows/2026-10/MODELS.joblib',R/'windows/2026-10/FORECASTS_NO_Y.npz',S/'BANK16.json',S/'DECISION_PRE2024.json',Path(__file__)]
 original={str(p):sha(p) for p in inputs};bank=load(S/'BANK16.json');masks=load(S/'windows/late_2026-10/FEATURE_MASKS.json');assert set(masks)==set(bank) and len(bank)==16
 cs=load(S/'windows/late_2026-10/COMPLETE.json');rs=load(R/'windows/2026-10/COMPLETE.json');assert cs['train_end']==rs['train_end']=='2026-09-30'
 assert sha(S/'windows/late_2026-10/PREDICTIONS_NO_Y.npz')==cs['prediction_sha256'] and sha(S/'windows/late_2026-10/FEATURE_MASKS.json')==cs['features_sha256']
 for name,h in rs['hashes'].items():assert sha(R/'windows/2026-10'/name)==h
 with np.load(P/'기존10월전처리_모든조합입력_NO_Y.npz') as z:dates=z['dates'].astype(str);names=z['feature_names'].astype(str).tolist();x=z['values']
 assert len(dates)==12 and dates[0]=='2026-10-08' and dates[-1]=='2026-10-23' and np.isfinite(x).all()
 ix={m:[names.index(c) for c in masks[m]] for m in bank}
 with np.load(S/'windows/late_2026-10/PREDICTIONS_NO_Y.npz') as z:cdates=z['dates'].astype(str);cprobs=z['probabilities'];cmask=z['mask'].astype(str);ctask=z['task'].astype(str);calgo=z['algo'].astype(str)
 with np.load(R/'windows/2026-10/FORECASTS_NO_Y.npz') as z:rdates=z['dates'].astype(str);rpred=z['predictions'];rmask=z['mask'].astype(str);ralgo=z['algo'].astype(str);baseline=z['baseline_values']
 assert np.array_equal(cdates,rdates) and len(cdates)==5
 # Reproduce all saved October1-7 forecasts from saved X-only preprocessing before extending.
 statsfile=S/'windows/late_2026-10/TRAIN_TRANSFORM.joblib';assert sha(statsfile)==cs['transform_sha256'];stats=joblib.load(statsfile)
 oldx=pd.read_csv(W/'outputs/staged_multi_algorithm_v2_20261023/X216_WITHOUT_FRENCH_COMPONENTS_NO_Y.csv',index_col=0,float_precision='round_trip').loc[cdates]
 fs={lag:pd.read_csv(W/f'outputs/french_release_scenarios_v1_20261023/{lag}_FRENCH420_ALIGNED_NO_Y.csv',index_col=0,float_precision='round_trip').loc[cdates] for lag in ['NEXT20','MONTH2_FIRST']};oldtrans,oldnames=transform_fixed(oldx,fs,stats);assert oldnames==names
 classifiers=joblib.load(S/'audit_models/late_2026-10.joblib');regressors=joblib.load(R/'windows/2026-10/MODELS.joblib');assert len(classifiers)==192 and len(regressors)==96
 out=np.full((192,12,4),np.nan);regout=np.full((96,12),np.nan);maxerr=0.;logs=[]
 for i,(mask,task,algo) in enumerate(zip(cmask,ctask,calgo)):
  m=classifiers[str(i)];k=2 if task=='BINARY' else 4;assert m.n_features_in_==len(ix[mask]) and np.array_equal(m.classes_,np.arange(k))
  replay=m.predict_proba(oldtrans[:,ix[mask]]);assert np.allclose(replay,cprobs[i,:,:k],atol=1e-9,rtol=1e-8);maxerr=max(maxerr,float(np.max(np.abs(replay-cprobs[i,:,:k]))))
  p=m.predict_proba(x[:,ix[mask]]);assert p.shape==(12,k) and np.isfinite(p).all() and np.allclose(p.sum(1),1);out[i,:,:k]=p
  logs.append(dict(task=task,mask=mask,algo=algo,n_features=len(ix[mask]),training_end='2026-09-30',replay_original_5_days=True,new_fit=False))
 for i,(mask,algo) in enumerate(zip(rmask,ralgo)):
  m=regressors[str(i)];assert m.n_features_in_==len(ix[mask]);replay=m.predict(oldtrans[:,ix[mask]]);assert np.allclose(replay,rpred[i],atol=1e-9,rtol=1e-8);maxerr=max(maxerr,float(np.max(np.abs(replay-rpred[i]))))
  p=m.predict(x[:,ix[mask]]);assert p.shape==(12,) and np.isfinite(p).all();regout[i]=p;logs.append(dict(task='REGRESSION',mask=mask,algo=algo,n_features=len(ix[mask]),training_end='2026-09-30',replay_original_5_days=True,new_fit=False))
 np.savez_compressed(O/'CLASSIFICATION_FORECASTS_NO_Y.npz',dates=dates,mask=cmask,task=ctask,algo=calgo,probabilities=out)
 np.savez_compressed(O/'REGRESSION_FORECASTS_NO_Y.npz',dates=dates,mask=rmask,algo=ralgo,predictions=regout,baseline_values=baseline)
 save(logs,'SAVED_MODEL_REPLAY_AND_INFERENCE_LOG.csv');assert all(sha(p)==h for p,h in original.items());js('PROTECTED_INPUT_HASHES.json',original)
 js('FORECAST_SEAL.json',dict(status='288_POLICIES_FORECASTS_SEALED_BEFORE_Y',training_cutoff='2026-09-30',new_fit=0,original_forecast_replays=288,original_replay_days=5,maximum_replay_error=maxerr,additional_days=12,source32_existing_rules_preserved=True,new_selection=False,Y_read_for_inference=False,forecast_hashes={name:sha(O/name) for name in ['CLASSIFICATION_FORECASTS_NO_Y.npz','REGRESSION_FORECASTS_NO_Y.npz','SAVED_MODEL_REPLAY_AND_INFERENCE_LOG.csv']}));print('REPLAYED288 original policies; EXTENDED12days; FORECASTS SEALED before labels',flush=True)
def classmetric(y,p,task):
 k=p.shape[1];pred=(p[:,1]>=.5).astype(int) if task=='BINARY' else p.argmax(1);cm=confusion_matrix(y,pred,labels=np.arange(k));r=dict(n=len(y),correct=int((pred==y).sum()),accuracy=accuracy_score(y,pred),BA=balanced_accuracy_score(y,pred),macro_F1=f1_score(y,pred,average='macro',zero_division=0),logloss=log_loss(y,p,labels=np.arange(k)))
 if task=='BINARY':
  tn,fp,fn,tp=cm.ravel();r.update(TN=int(tn),FP=int(fp),FN=int(fn),TP=int(tp),nonup_recall=float(tn/(tn+fp)) if tn+fp else None,up_recall=float(tp/(tp+fn)) if tp+fn else None,up_precision=float(tp/(tp+fp)) if tp+fp else None,up_prediction=float(pred.mean()),AUC=roc_auc_score(y,p[:,1]) if len(np.unique(y))==2 else None)
 else:r.update(direction_accuracy=float(((p[:,2]+p[:,3]>=.5)==(y>=2)).mean()),predicted_classes=np.bincount(pred,minlength=4).tolist(),actual_classes=np.bincount(y,minlength=4).tolist())
 return r
def regmetric(y,p,mean):
 mse=mean_squared_error(y,p);true=y>0;pred=p>0;cm=confusion_matrix(true,pred,labels=[False,True]);tn,fp,fn,tp=cm.ravel();den=np.sum((y-mean)**2)
 return dict(n=len(y),MAE=mean_absolute_error(y,p),RMSE=float(np.sqrt(mse)),R2=r2_score(y,p),R2_OOS_vs_train_mean=float(1-np.sum((y-p)**2)/den) if den else None,direction_accuracy=float((true==pred).mean()),nonup_recall=float(tn/(tn+fp)) if tn+fp else None,TN=int(tn),FP=int(fp),FN=int(fn),TP=int(tp))
def score():
 seal=load(O/'FORECAST_SEAL.json');assert all(sha(O/n)==h for n,h in seal['forecast_hashes'].items());assert all(sha(p)==h for p,h in load(O/'PROTECTED_INPUT_HASHES.json').items());assert not (O/'FINAL_VERIFICATION.json').exists()
 # First label access is after the forecast hash seal has been checked.
 oldy=pd.read_csv(W/'outputs/staged_multi_algorithm_v2_20261023/LABELS_FOR_TRAINING_ONLY.csv',index_col=0,float_precision='round_trip');assert len(oldy)==3942
 raw=pd.read_csv(BYRAW,index_col=0,float_precision='round_trip');raw.index=pd.to_datetime(raw.index);s=raw.Close.sort_index();returns=100*(s/s.shift()-1)
 with np.load(O/'CLASSIFICATION_FORECASTS_NO_Y.npz') as z:dates=z['dates'].astype(str);cprobs=z['probabilities'];cmask=z['mask'].astype(str);ctask=z['task'].astype(str);calgo=z['algo'].astype(str)
 c=float(oldy.loc['2026-10-07','threshold_pct']);assert oldy.loc[oldy.reference_year==2025,'threshold_pct'].nunique()==1
 # Verify threshold uses only2025 realized history and matches the sealed original labels.
 assert np.isclose(c,returns.loc['2025'].abs().median(),atol=1e-10,rtol=1e-10)
 yy=returns.reindex(pd.to_datetime(dates)).to_numpy(float);assert np.isfinite(yy).all();truth=pd.DataFrame(dict(date=dates,return_pct=yy,threshold_pct=c,reference_year=2025,class4=np.select([yy<=-c,yy<=0,yy<c],[0,1,2],default=3),Y=(yy>0).astype(int)))
 save(truth,'ADDED12_SCORING_TRUTH.csv');prior_truth=pd.DataFrame(dict(date=oldy.index,Y=oldy.Y,class4=oldy.class4,return_pct=oldy.return_pct));truthall=pd.concat([prior_truth,truth],ignore_index=True).set_index('date');save(pd.DataFrame(dict(date=oldy.loc['2026-10-01':'2026-10-07'].index,original_return=oldy.loc['2026-10-01':'2026-10-07'].return_pct,fresh_return=returns.reindex(pd.to_datetime(oldy.loc['2026-10-01':'2026-10-07'].index)).to_numpy())),'ORIGINAL_OCTOBER_TARGET_OVERLAP_AUDIT.csv')
 daily=[]
 for i,(mask,task,algo) in enumerate(zip(cmask,ctask,calgo)):
  k=2 if task=='BINARY' else 4;p=cprobs[i,:,:k];pred=(p[:,1]>=.5).astype(int) if k==2 else p.argmax(1);y=truth.Y.to_numpy() if k==2 else truth.class4.to_numpy()
  for j,d in enumerate(dates):daily.append(dict(mask=mask,task=task,algo=algo,date=d,prediction=int(pred[j]),Y=int(y[j]),correct=bool(pred[j]==y[j]),**{f'p{q}':float(p[j,q]) for q in range(k)}))
 newc=pd.DataFrame(daily);oldc=pd.read_csv(S/'LATE_DAILY_RESULTS.csv',float_precision='round_trip');fullc=pd.concat([oldc,newc],ignore_index=True);save(newc,'ADDED12_CLASSIFICATION_DAILY.csv');save(fullc,'FULL706_CLASSIFICATION_DAILY.csv')
 with np.load(O/'REGRESSION_FORECASTS_NO_Y.npz') as z:rp=z['predictions'];rmask=z['mask'].astype(str);ralgo=z['algo'].astype(str);base=z['baseline_values']
 newreg=[]
 for (mask,algo),pp in zip(zip(rmask,ralgo),rp):newreg.extend(dict(mask=mask,algo=algo,date=d,Y=float(y),prediction=float(p),train_mean=float(base[1]),train_end='2026-09-30') for d,y,p in zip(dates,yy,pp))
 for algo,value in zip(['ZERO','TRAIN_MEAN','TRAIN_MEDIAN'],base):newreg.extend(dict(mask='BASELINE',algo=algo,date=d,Y=float(y),prediction=float(value),train_mean=float(base[1]),train_end='2026-09-30') for d,y in zip(dates,yy))
 oldreg=pd.read_csv(R/'DAILY_RESULTS.csv',float_precision='round_trip');newreg=pd.DataFrame(newreg);fullreg=pd.concat([oldreg,newreg],ignore_index=True);save(newreg,'ADDED12_REGRESSION_DAILY.csv');save(fullreg,'FULL706_REGRESSION_DAILY.csv')
 metrics=[];yearly=[];regmetrics=[];regyear=[]
 for (mask,task,algo),g in fullc.groupby(['mask','task','algo'],sort=False):
  g=g.sort_values('date');assert len(g)==706 and g.date.is_unique;k=2 if task=='BINARY' else 4
  for scope,sub in [('ORIGINAL694',g[g.date<='2026-10-07']),('ADDED12',g[g.date>'2026-10-07']),('FULL706',g)]:metrics.append(dict(scope=scope,mask=mask,task=task,algo=algo,**classmetric(sub.Y.to_numpy(),sub[[f'p{i}' for i in range(k)]].to_numpy(),task)))
  for year,sub in g.groupby(g.date.str[:4]):yearly.append(dict(year=year,mask=mask,task=task,algo=algo,**classmetric(sub.Y.to_numpy(),sub[[f'p{i}' for i in range(k)]].to_numpy(),task)))
 for (mask,algo),g in fullreg.groupby(['mask','algo'],sort=False):
  g=g.sort_values('date');assert len(g)==706 and g.date.is_unique
  for scope,sub in [('ORIGINAL694',g[g.date<='2026-10-07']),('ADDED12',g[g.date>'2026-10-07']),('FULL706',g)]:regmetrics.append(dict(scope=scope,mask=mask,task='REGRESSION',algo=algo,**regmetric(sub.Y.to_numpy(),sub.prediction.to_numpy(),sub.train_mean.to_numpy())))
  for year,sub in g.groupby(g.date.str[:4]):regyear.append(dict(year=year,mask=mask,algo=algo,**regmetric(sub.Y.to_numpy(),sub.prediction.to_numpy(),sub.train_mean.to_numpy())))
 m=pd.DataFrame(metrics);r=pd.DataFrame(regmetrics);save(m,'CLASSIFICATION_ALL192_THREE_PERIODS.csv');save(yearly,'CLASSIFICATION_YEARLY.csv');save(r,'REGRESSION_ALL96_AND_BASELINES_THREE_PERIODS.csv');save(regyear,'REGRESSION_YEARLY.csv')
 # Reconcile all original scores to existing reports; extension never rewrites historical predictions.
 oldmetrics=pd.read_csv(S/'LATE_METRICS.csv');oldrm=pd.read_csv(R/'ALL96_AND_BASELINES_METRICS.csv')
 for row in oldmetrics.to_dict('records'):
  cur=m[(m.scope=='ORIGINAL694')&(m['mask']==row['mask'])&(m.task==row['task'])&(m.algo==row['algo'])].iloc[0];assert cur.correct==row['correct'] and np.isclose(cur.accuracy,row['accuracy'],atol=1e-12)
 for row in oldrm.to_dict('records'):
  cur=r[(r.scope=='ORIGINAL694')&(r['mask']==row['mask'])&(r.algo==row['algo'])].iloc[0];assert np.isclose(cur.RMSE,row['RMSE'],atol=1e-12) and np.isclose(cur.MAE,row['MAE'],atol=1e-12)
 # Freeze each mask's previously observed winner, rather than choose from the12new days.
 table=[];bank=load(S/'BANK16.json');specs={z['mask']:z for z in load(S/'MASKS.json')}
 for no,mask in enumerate(bank,1):
  row=dict(number=no,mask=mask,groups='+'.join(specs[mask]['groups']) or 'INDIVIDUAL',French=specs[mask]['french'],October_features=len(load(S/'windows/late_2026-10/FEATURE_MASKS.json')[mask]))
  for task in ['BINARY','FOUR']:
   best=m[(m.scope=='ORIGINAL694')&(m['mask']==mask)&(m.task==task)].sort_values(['accuracy','algo'],ascending=[False,True]).iloc[0];row[task+'_fixed_old_best_algo']=best.algo
   for scope in ['ORIGINAL694','ADDED12','FULL706']:
    cur=m[(m.scope==scope)&(m['mask']==mask)&(m.task==task)&(m.algo==best.algo)].iloc[0];row[task+'_'+scope+'_accuracy']=cur.accuracy
    if task=='BINARY':row[task+'_'+scope+'_nonup_recall']=cur.nonup_recall
  best=r[(r.scope=='ORIGINAL694')&(r['mask']==mask)].sort_values(['RMSE','MAE','algo']).iloc[0];row['REG_fixed_old_best_algo']=best.algo
  for scope in ['ORIGINAL694','ADDED12','FULL706']:
   cur=r[(r.scope==scope)&(r['mask']==mask)&(r.algo==best.algo)].iloc[0];row['REG_'+scope+'_RMSE']=cur.RMSE;row['REG_'+scope+'_MAE']=cur.MAE;row['REG_'+scope+'_R2']=cur.R2
  table.append(row)
 save(table,'MASK16_FIXED_OLD_WINNERS_COMPARISON.csv')
 # Main fixed representative models: original reference, pre2024selection, old observed champion.
 selected=load(S/'DECISION_PRE2024.json')['selected'];represent=[('기준모형','G110000_NONE','BINARY','LR'),('2024년이전선정',selected['BINARY']['mask'],'BINARY',selected['BINARY']['algo'])]
 for task in ['BINARY','FOUR']:
  best=m[(m.scope=='ORIGINAL694')&(m.task==task)].sort_values(['accuracy','mask','algo'],ascending=[False,True,True]).iloc[0];represent.append(('기존기간최고_'+task,best['mask'],task,best.algo))
 represent.append(('4등급기준','G110000_NONE','FOUR','LR'));rb=r[(r.scope=='ORIGINAL694')&(r['mask']!='BASELINE')].sort_values(['RMSE','MAE','mask','algo']).iloc[0]
 summaryrows=[]
 for label,mask,task,algo in represent:
  for scope in ['ORIGINAL694','ADDED12','FULL706']:
   cur=m[(m.scope==scope)&(m['mask']==mask)&(m.task==task)&(m.algo==algo)].iloc[0].to_dict();cur['label']=label;summaryrows.append(cur)
 for scope in ['ORIGINAL694','ADDED12','FULL706']:
  cur=r[(r.scope==scope)&(r['mask']==rb['mask'])&(r.algo==rb.algo)].iloc[0].to_dict();cur['label']='기존기간최고_회귀';summaryrows.append(cur)
  ds=truthall.index[(truthall.index>='2024-01-02')&(truthall.index<=('2026-10-07' if scope=='ORIGINAL694' else '2026-10-23'))];ds=ds[ds>'2026-10-07'] if scope=='ADDED12' else ds;up=truthall.loc[ds,'Y'].to_numpy();summaryrows.append(dict(label='항상상승',scope=scope,task='BINARY',mask='BASELINE',algo='ALWAYS_UP',n=len(up),correct=int(up.sum()),accuracy=float(up.mean()),nonup_recall=0.))
 save(summaryrows,'대표모형_기존_추가_전체_비교.csv');js('SUMMARY_DATA.json',summaryrows)
 assert all(sha(O/n)==h for n,h in seal['forecast_hashes'].items()) and all(sha(p)==h for p,h in load(O/'PROTECTED_INPUT_HASHES.json').items())
 final=dict(status='PASS_FROZEN_288_POLICIES_EXTENDED',binary_policies=96,four_policies=96,regression_policies=96,regression_baselines=3,original_evaluation_days=694,additional_days=12,total_evaluation_days=706,evaluation_end='2026-10-23',new_fit=0,training_cutoff='2026-09-30',replayed_original_models=288,original_scores_reconciled=True,forecasts_sealed_before_Y=True,four_threshold_reference_year=2025,four_threshold_pct=c,all_original_artifacts_unchanged=True,independent_unseen_test=False,source_time_and_vintage_assumptions_remain=True,no_automatic_model_adoption=True)
 js('FINAL_VERIFICATION.json',final);print(json.dumps(final,ensure_ascii=False,indent=2),flush=True);print('REPRESENTATIVES',pd.DataFrame(summaryrows)[['label','scope','accuracy','RMSE']].to_string(index=False),flush=True)
BYRAW=W/'outputs/evaluation_extension_20261023_v1/prepared/raw_snapshots/02_merged_RAW.csv'
if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1);warnings.filterwarnings('ignore',message='X does not have valid feature names');warnings.filterwarnings('ignore',message='y_pred contains classes not in y_true');{'infer':infer,'score':score}[sys.argv[1]]()
