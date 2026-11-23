"""연구 C Phase3 개발 전용. 시험 CSV 내용 읽기 금지."""
import os
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[name]='1'
import csv,hashlib,json,sys,math
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from sklearn.linear_model import LinearRegression,Ridge,ElasticNet
from sklearn.ensemble import RandomForestRegressor,HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2]
BUILD=ROOT/'research_C/phase2_weekly_dataset/build_v1_1'
LOCK=ROOT/'research_C/phase1_research_design/approval_lock_v1_1'
D13=ROOT/'research_C/phase2_weekly_dataset/d13_bootstrap_policy_v1_0/approval_lock_v1_0'
DATA=BUILD/'data/train_dev/WEEKLY_CORE_COMBINED.csv'
FEATURES=[f'B{i}' for i in range(1,11)]+['F1']
UTC=timezone.utc;NY=ZoneInfo('America/New_York')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(rel,x):
    p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:f.write(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def csvsave(rel,rows):
    p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def read_data():
    assert DATA.relative_to(BUILD).parts[1]=='train_dev'
    df=pd.read_csv(DATA)
    assert (df.week_start<'2021-01-01').all()
    df=df[df.paired_common_valid].copy().sort_values('week_start').reset_index(drop=True)
    df['origin_utc']=pd.to_datetime(df.prediction_origin,utc=True)
    df['label_utc']=pd.to_datetime(df.label_assumed_available_at,utc=True)
    assert len(df)==517 and int((df.split=='development').sum())==209
    return df
def training_indices(df,index,window):
    row=df.iloc[index];origin=row.origin_utc
    mask=(df.week_start<row.week_start)&(df.label_utc<origin)&(df.origin_utc<origin)
    cutoff=None
    if window=='rolling_5_calendar_years':
        cutoff=origin.to_pydatetime().astimezone(NY)-relativedelta(years=5)
        mask &= df.origin_utc>=pd.Timestamp(cutoff.astimezone(UTC))
    return np.flatnonzero(mask.to_numpy()),cutoff
def estimator(algo,params):
    kw={k:v for k,v in params.items() if k!='candidate_id'}
    if algo=='OLS':return LinearRegression(n_jobs=1,**kw)
    if algo=='Ridge':return Ridge(**kw)
    if algo=='ElasticNet':return ElasticNet(random_state=20261016,**kw)
    if algo=='RandomForest':return RandomForestRegressor(**kw)
    if algo=='HistGradientBoosting':return HistGradientBoostingRegressor(**kw)
    raise ValueError(algo)
def fit_predict(algo,params,X,y,current):
    scaled=algo in ['OLS','Ridge','ElasticNet'];scaler=StandardScaler() if scaled else None
    if scaled:
        x=scaler.fit_transform(X);z=scaler.transform(current)
    else:x=X;z=current
    rank=int(np.linalg.matrix_rank(np.column_stack([np.ones(len(x)),x])))
    if algo=='OLS' and (rank!=x.shape[1]+1 or len(x)<=x.shape[1]+20):raise ValueError('OLS_RANK_OR_DOF_FAILURE')
    model=estimator(algo,params)
    with threadpool_limits(limits=1):model.fit(x,y);prediction=float(model.predict(z)[0])
    assert np.isfinite(prediction)
    return prediction,{'rank':rank,'p_with_intercept':x.shape[1]+1,
        'scaler_n_samples':int(scaler.n_samples_seen_) if scaler else 0,
        'scaler_mean':scaler.mean_.tolist() if scaler else None,
        'scaler_var':scaler.var_.tolist() if scaler else None,
        'input_columns':FEATURES[:X.shape[1]],'estimator_n_iter':int(model.n_iter_) if getattr(model,'n_iter_',None) is not None else None}
def metrics(y,p,mean):
    y=np.asarray(y,float);p=np.asarray(p,float);mean=np.asarray(mean,float)
    d=y-p;den=float(np.sum((y-mean)**2))
    return {'n':len(y),'MAE':float(np.mean(np.abs(d))),'RMSE':float(np.sqrt(np.mean(d*d))),
        'OOS_R2_training_mean':1-float(np.sum(d*d))/den if den>0 else None,
        'direction_accuracy':float(np.mean(np.sign(y)==np.sign(p))),
        'actual_zero_n':int(np.count_nonzero(y==0)),'prediction_zero_n':int(np.count_nonzero(p==0)),
        'nonzero_actual_direction_accuracy':float(np.mean(np.sign(y[y!=0])==np.sign(p[y!=0]))) if (y!=0).any() else None}
