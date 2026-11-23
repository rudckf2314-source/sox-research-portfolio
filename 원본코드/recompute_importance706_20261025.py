"""Recompute October as one 17-day month; retain exact unaffected monthly contributions.
No fits, tuning, or forecast changes. Restore the original RNG stream before October.
"""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import json,hashlib,copy,sys
import numpy as np,pandas as pd,joblib
from threadpoolctl import threadpool_limits
W=Path(__file__).resolve().parents[1];D=Path('C:/Users/rudck/Desktop/SOX_논문_연구');O=W/'outputs/importance706_20261025';O.mkdir(exist_ok=True)
C=W/'outputs/crossed_feature_algorithm_v1_20261023';R=W/'outputs/sox_return_regression16_v1_20261024';F=W/'outputs/frozen_extension_all_tasks_20261023_v1_20261024';I=W/'outputs/importance_classification_20261024';J=W/'outputs/importance_price_xgb_20261024'
M=D/'06_RAW와변수/05_실제모델입력_월별'
CASES=[('BINARY_BEST_OBSERVED','G001100_MONTH2_FIRST','BINARY','LGBM'),('BINARY_REFERENCE','G110000_NONE','BINARY','LR'),('FOUR_BEST_OBSERVED','G001100_MONTH2_FIRST','FOUR','LR')]
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def js(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(x,name):pd.DataFrame(x).to_csv(O/name,index=False,encoding='utf-8-sig')
def arrays(month,train=False):
 with np.load(M/month/'X_train_X_eval(학습과 평가 입력배열).npz')as z:
  a=z['X_eval'];names=z['feature_names'].astype(str).tolist();dates=z['eval_dates'].astype(str)
  t=z['X_train']if train else None
 return a,names,dates,t
def main():
 threadpool_limits(1)
 protected=[I/'ALL_CLASSIFICATION_IMPORTANCE.csv',J/'FEATURE_IMPORTANCE_ALL55.csv',J/'MONTHLY_PERMUTATION_DETAIL.csv',F/'FULL706_CLASSIFICATION_DAILY.csv',F/'FULL706_REGRESSION_DAILY.csv',C/'audit_models/late_2026-10.joblib',R/'windows/2026-10/MODELS.joblib']
 hashes={str(p):sha(p)for p in protected};js(O/'PROTECTED_SOURCE_HASHES.json',hashes)
 schedule=pd.read_csv(M/'월별학습평가기간.csv');assert len(schedule)==34
 rngc=np.random.default_rng(20261024);rngr=np.random.default_rng(20261024);advance=[]
 # Advance only random draws; the first 33 months of inputs, models and labels are unchanged.
 for row in schedule.iloc[:-1].itertuples():
  mo=row.month;xx,names,dates,_=arrays(mo);assert len(dates)==row.eval_rows
  masks=load(C/f'windows/late_{mo}/FEATURE_MASKS.json')
  for case,mask,task,algo in CASES:
   ix=[names.index(c)for c in masks[mask]];bt=xx[:,ix]
   for j in range(len(ix)):
    varies=np.ptp(bt[:,j])>1e-10
    for repeat in range(5):
     if varies:rngc.permutation(len(bt))
     rngc.integers(max(0,row.train_rows-252),row.train_rows,size=len(bt))
  cols=load(R/f'windows/{mo}/FEATURES.json')['G000000_NONE']
  for c in cols:
   for repeat in range(5):rngr.permutation(len(dates))
  advance.append(dict(month=mo,eval_rows=len(dates),train_rows=row.train_rows,input_npz_sha256=sha(M/mo/'X_train_X_eval(학습과 평가 입력배열).npz')))
 print('Original RNG streams restored through September; 33 unchanged months verified',flush=True)
 xx,names,dates,train=arrays('2026-10',True);assert len(dates)==17 and dates[-1]=='2026-10-23'
 masks=load(C/'windows/late_2026-10/FEATURE_MASKS.json');models=joblib.load(C/'audit_models/late_2026-10.joblib')
 with np.load(C/'windows/late_2026-10/PREDICTIONS_NO_Y.npz')as z:order=list(zip(z['mask'].astype(str),z['task'].astype(str),z['algo'].astype(str)));old_saved=z['probabilities']
 full=pd.read_csv(F/'FULL706_CLASSIFICATION_DAILY.csv');cold=pd.read_csv(I/'ALL_CLASSIFICATION_IMPORTANCE.csv');records=[];parts=[];baselines=[]
 def calculate_class(n,rng):
  result={}
  for case,mask,task,algo in CASES:
   key=order.index((mask,task,algo));model=models[str(key)];cols=masks[mask];ix=[names.index(c)for c in cols];bt=xx[:n,ix];at=train[:,ix]
   g=full[(full['mask']==mask)&(full.task==task)&(full.algo==algo)].set_index('date').loc[dates[:n]];yy=g.Y.to_numpy(int)
   pp=model.predict_proba(bt);k=pp.shape[1];assert np.allclose(pp,g[[f'p{i}'for i in range(k)]],rtol=1e-8,atol=1e-9)
   if n==5:assert np.allclose(pp,old_saved[key,:,:k],rtol=1e-8,atol=1e-9)
   def loss(p):return -np.log(np.clip(p[np.arange(n),yy],1e-15,1))
   def pred(p):return(p[:,1]>=.5).astype(int)if k==2 else p.argmax(1)
   base=loss(pp);pr=pred(pp);correct=int((pr==yy).sum());tn=int(((pr==0)&(yy==0)).sum())if k==2 else 0
   result[case]={}
   for j,c in enumerate(cols):
    vals={k:np.zeros(5)for k in ['within_loss','within_correct_drop','within_TN_drop','past_loss']};varies=np.ptp(bt[:,j])>1e-10
    for repeat in range(5):
     if varies:
      changed=bt.copy();changed[:,j]=changed[rng.permutation(n),j];p=model.predict_proba(changed);q=pred(p);vals['within_loss'][repeat]=float((loss(p)-base).sum());vals['within_correct_drop'][repeat]=correct-int((q==yy).sum())
      if k==2:vals['within_TN_drop'][repeat]=tn-int(((q==0)&(yy==0)).sum())
     changed=bt.copy();changed[:,j]=at[rng.integers(max(0,len(at)-252),len(at),size=n),j];p=model.predict_proba(changed);vals['past_loss'][repeat]=float((loss(p)-base).sum())
    vals['varies']=bool(varies);result[case][c]=vals
   print('October permutation',n,'days',case,'complete',flush=True)
  return result
 oldpart=calculate_class(5,copy.deepcopy(rngc));newpart=calculate_class(17,copy.deepcopy(rngc))
 for case,mask,task,algo in CASES:
  g=full[(full['mask']==mask)&(full.task==task)&(full.algo==algo)];assert len(g)==706
  nn=int((g.Y==0).sum())if task=='BINARY'else 0
  oldnn=297
  for r in cold[cold['case']==case].to_dict('records'):
   c=r['feature'];a=oldpart[case].get(c);b=newpart[case].get(c)
   for column,key,den0,den1,factor in [('within_month_delta_logloss','within_loss',694,706,1),('within_month_accuracy_drop_pp','within_correct_drop',694,706,100),('past252_replacement_delta_logloss','past_loss',694,706,1)]:
    oldnum=r[column]*den0/factor;remove=float(a[key].mean())if a else 0.;add=float(b[key].mean())if b else 0.;r[column]=(oldnum-remove+add)/den1*factor
   if task=='BINARY':r['within_month_nonup_recall_drop_pp']=(r['within_month_nonup_recall_drop_pp']*oldnn/100-(float(a['within_TN_drop'].mean())if a else 0)+(float(b['within_TN_drop'].mean())if b else 0))/nn*100
   r['varying_eval_months']=int(r['varying_eval_months'])-int(a['varies']if a else False)+int(b['varies']if b else False);r['within_month_assessable']=r['varying_eval_months']>0;r.update(evaluation_start='2024-01-02',evaluation_end='2026-10-23',evaluation_days=706,repeats=5)
   records.append(r)
   if a:
    for repeat in range(5):parts.append(dict(case=case,feature=c,repeat=repeat,October_days=17,delta_logloss_sum=float(b['within_loss'][repeat]),correct_drop=float(b['within_correct_drop'][repeat]),TN_drop=float(b['within_TN_drop'][repeat]),past252_delta_logloss_sum=float(b['past_loss'][repeat])))
  k=2 if task=='BINARY'else 4;p=g[[f'p{i}'for i in range(k)]].to_numpy();y=g.Y.to_numpy(int);baselines.append(dict(case=case,mask=mask,task=task,algo=algo,n=706,accuracy=float((g.prediction==g.Y).mean()),logloss=float(-np.log(np.clip(p[np.arange(706),y],1e-15,1)).mean()),nonup_recall=float(((g.prediction==0)&(g.Y==0)).sum()/nn)if nn else None))
 save(records,'ALL_CLASSIFICATION_IMPORTANCE_706.csv');save(parts,'OCTOBER_CLASSIFICATION_PERMUTATION_DETAIL.csv');save(baselines,'CLASSIFICATION_MODEL_BASELINES.csv')
 # Regression retains exact per-repeat monthly SSE, and verifies old October reconstruction.
 bank=load(C/'BANK16.json');mask='G000000_NONE';key=str(bank.index(mask)*6+4);regmodels=joblib.load(R/'windows/2026-10/MODELS.joblib');model=regmodels[key];cols=load(R/'windows/2026-10/FEATURES.json')[mask];ix=[names.index(c)for c in cols]
 fullr=pd.read_csv(F/'FULL706_REGRESSION_DAILY.csv');g=fullr[(fullr['mask']==mask)&(fullr.algo=='XGB')];october=g.set_index('date').loc[dates];yy=october.Y.to_numpy();pp=model.predict(xx[:,ix]);assert np.allclose(pp,october.prediction,atol=1e-9,rtol=1e-8)
 detail=pd.read_csv(J/'MONTHLY_PERMUTATION_DETAIL.csv');old_detail=detail[detail.month=='2026-10'];newrows=[];maxerr=0.
 for n in [5,17]:
  rng=copy.deepcopy(rngr);bt=xx[:n,ix];y=yy[:n];p0=pp[:n];base=float(((y-p0)**2).sum());imp=model.feature_importances_
  for j,c in enumerate(cols):
   for repeat in range(5):
    change=bt.copy();change[:,j]=change[rng.permutation(n),j];p=model.predict(change);delta=float(((y-p)**2).sum()-base)
    if n==5:
     old=old_detail[(old_detail.feature==c)&(old_detail['repeat']==repeat)];assert len(old)==1;err=abs(delta-old.delta_SSE.iloc[0]);maxerr=max(maxerr,err);assert np.isclose(delta,old.delta_SSE.iloc[0],atol=1e-8,rtol=1e-8),(c,repeat,delta,old.delta_SSE.iloc[0])
    else:newrows.append(dict(month='2026-10',feature=c,repeat=repeat,delta_SSE=delta,normalized_training_gain=float(imp[j]),eval_n=17))
 detail=pd.concat([detail[detail.month!='2026-10'],pd.DataFrame(newrows)],ignore_index=True);save(detail,'REGRESSION_MONTHLY_PERMUTATION_DETAIL.csv');base_sse=float(((g.Y-g.prediction)**2).sum());base_rmse=float(np.sqrt(base_sse/706));oldreg=pd.read_csv(J/'FEATURE_IMPORTANCE_ALL55.csv');regrows=[]
 for r in oldreg.to_dict('records'):
  sub=detail[detail.feature==r['feature']];deltas=sub.groupby('repeat').delta_SSE.sum().reindex(range(5),fill_value=0).to_numpy();change=np.sqrt((base_sse+deltas)/706)-base_rmse
  gains=sub.drop_duplicates('month');r.update(mean_delta_RMSE=float(change.mean()),min_repeat_delta_RMSE=float(change.min()),max_repeat_delta_RMSE=float(change.max()),normalized_gain_weighted=float((gains.normalized_training_gain*gains.eval_n).sum()/706),evaluation_start='2024-01-02',evaluation_end='2026-10-23',evaluation_days=706)
  regrows.append(r)
 df=pd.DataFrame(regrows).sort_values('mean_delta_RMSE',ascending=False);save(df,'REGRESSION_FEATURE_IMPORTANCE_706.csv')
 assert all(sha(Path(p))==h for p,h in hashes.items());save(advance,'UNCHANGED_MONTH_REUSE_AUDIT.csv')
 js(O/'VERIFIED.json',dict(status='PASS',evaluation_start='2024-01-02',evaluation_end='2026-10-23',evaluation_days=706,months=34,October_days=17,repeats=5,method='monthly within-month permutation; October jointly recomputed on all17days',classifier_cases=3,regression_cases=1,new_model_fits=0,forecast_changes=0,old_October_regression_per_repeat_maximum_replay_error=maxerr,regression_base_RMSE=base_rmse,prior33months_inputs_unchanged=True,original_sources_unchanged=True,random_seed=20261024,SHAP=False))
 print('COMPLETE 706-day permutation importance; no model fits or forecast changes',flush=True)
 for case,_,_,_ in CASES:
  t=pd.DataFrame(records);print(case,t[(t['case']==case)&t.within_month_assessable].nlargest(7,'within_month_delta_logloss')[['feature','within_month_delta_logloss']].to_json(orient='records'),flush=True)
 print('REGRESSION',df.head(7)[['feature','mean_delta_RMSE']].to_json(orient='records'),flush=True)
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
