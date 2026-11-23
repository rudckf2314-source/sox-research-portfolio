"""Controlled development-only timing/update/classification-versus-regression study."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
import sys,json,hashlib,traceback,math,warnings
from pathlib import Path
import numpy as np,pandas as pd,joblib
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression,Ridge
from sklearn.metrics import accuracy_score,balanced_accuracy_score,matthews_corrcoef,roc_auc_score,recall_score,f1_score,mean_absolute_error,mean_squared_error,brier_score_loss
from threadpoolctl import threadpool_limits
from xgboost import XGBClassifier,XGBRegressor

HERE=Path(__file__).resolve().parents[1];D=HERE.parent;ROOT=D.parent
SEED=20261019
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def js(name,x): (HERE/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def text(name,s): (HERE/name).write_text(s,encoding='utf-8')
def csv(name,x):pd.DataFrame(x).to_csv(HERE/name,index=False,encoding='utf-8-sig')
def model(name):
    if name=='LogisticClassifier':m=LogisticRegression(C=1,max_iter=2000,random_state=SEED)
    elif name=='RidgeRegressor':m=Ridge(alpha=100)
    else:
        settings=dict(n_estimators=100,max_depth=2,learning_rate=.05,min_child_weight=10,reg_lambda=10,subsample=1,colsample_bytree=1,n_jobs=1,tree_method='hist',random_state=SEED)
        m=XGBClassifier(**settings,eval_metric='logloss') if name=='XGBClassifier' else XGBRegressor(**settings,objective='reg:squarederror')
    return Pipeline([('impute',SimpleImputer(strategy='median',keep_empty_features=True)),('scale',StandardScaler()),('model',m)])

def prepare():
    for n in ['data','inputs','config','logs','predictions','models','qc']:(HERE/n).mkdir(parents=True,exist_ok=True)
    resume='--resume-prebuild' in sys.argv
    if (HERE/'inputs/PROTECTED_BEFORE.csv').exists():
        if not resume:raise RuntimeError('Existing run found. Do not overwrite.')
        assert not (HERE/'predictions/PREDICTIONS.csv').exists() and not list((HERE/'models').glob('*')),'Only untrained prebuild failures can resume'
        for row in pd.read_csv(HERE/'inputs/PROTECTED_BEFORE.csv').itertuples():assert sha(ROOT/row.path)==row.sha256,row.path
    protected=[]
    # Protect all sealed original D outputs and original input scope, without modifying them.
    old=pd.read_csv(D/'OUTPUT_MANIFEST.csv')
    assert sha(D/'OUTPUT_MANIFEST.csv')==(D/'OUTPUT_MANIFEST.sha256').read_text().split()[0]
    for row in old.itertuples():
        assert sha(D/row.path)==row.sha256,row.path
        protected.append({'path':(D/row.path).relative_to(ROOT).as_posix(),'bytes':row.bytes,'sha256':row.sha256})
    for p in [D/'OUTPUT_MANIFEST.csv',D/'OUTPUT_MANIFEST.sha256']:
        protected.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    original=pd.read_csv(D/'inputs/PROTECTED_BEFORE.csv')
    for row in original.itertuples():
        assert (ROOT/row.path).is_file() and sha(ROOT/row.path)==row.sha256,row.path
        protected.append({'path':row.path,'bytes':row.bytes,'sha256':row.sha256})
    if not (HERE/'inputs/PROTECTED_BEFORE.csv').exists():csv('inputs/PROTECTED_BEFORE.csv',protected)
    df=pd.read_csv(D/'data/DEV_1D.csv',parse_dates=['date','label_end']).set_index('date')
    assert df.index.max()<=pd.Timestamp('2020-12-31')
    dictionary=pd.read_csv(D/'FEATURE_DICTIONARY.csv');features=dictionary.feature.tolist()
    # Previous EOD prices can be observed before next open. Delivery and correction archives remain unverified.
    fast_types={1,2,4,9,10,12,13,14,23,46,47}
    new=df.copy();audit=[];lineage=[]
    sessions=pd.DatetimeIndex(pd.read_csv(D/'inputs/US_MARKET_SESSIONS_DEV.csv').session_date)
    for source_type,part in dictionary.groupby('source_type'):
        path=ROOT/part.iloc[0].source_path
        raw=pd.read_csv(path,comment='#');raw=raw[raw.Date<='2020-12-31'].copy();raw.index=pd.to_datetime(raw.Date);raw=raw.sort_index()
        fast=source_type in fast_types
        audit.append({'source_type':int(source_type),'path':str(path),'sha256':sha(path),'new_lag_US_sessions':1 if fast else 2,'policy':'previous_completed_market_EOD_at_next_US_session_08:00_ET' if fast else 'unchanged_prior_2_session_assumption','evidence':'source canonical header and market session close; not actual historical vendor delivery archive','price_column':('Semiconductor_Industry_Index level/deltas' if source_type==23 else 'Close ratios; never Adj Close') if fast else 'original feature values unchanged','limitations':'vendor corrections/split histories and actual delivery times unverified'})
        if not fast:continue
        s=raw.Close.astype(float) if 'Close' in raw else raw.Semiconductor_Industry_Index.astype(float)
        vals={f'ret{lag}':100*(s/s.shift(lag)-1) for lag in [1,5,20]}
        vals['vol20']=100*(s/s.shift(1)-1).rolling(20,min_periods=20).std(ddof=1)
        vals['ma20_gap']=100*(s/s.rolling(20,min_periods=20).mean()-1)
        vals.update({'level':s,'delta1':s.diff(),'delta5':s.diff(5)})
        idx=sessions.searchsorted(raw.index,side='right');valid=idx<len(sessions)
        for f in part.feature:
            key=f.split('_',1)[1]
            events=pd.DataFrame({'available_date':sessions[idx[valid]],'source_date':raw.index[valid],'value':vals[key].loc[valid].to_numpy()}).sort_values('available_date').drop_duplicates('available_date',keep='last')
            joined=pd.merge_asof(pd.DataFrame({'date':df.index}),events,left_on='date',right_on='available_date',direction='backward')
            ok=(joined.date-joined.source_date).dt.days.le(10)
            new[f]=joined.value.where(ok).to_numpy()
            for date,available,source,value in zip(df.index,joined.available_date,joined.source_date,new[f]):
                if pd.notna(value):
                    assert source<available<=date
                    lineage.append({'date':str(date.date()),'feature':f,'source_date':str(source.date()),'modeled_available_et':str(available.tz_localize('America/New_York')+pd.Timedelta(hours=8)),'origin_et':str(date.tz_localize('America/New_York')+pd.Timedelta(hours=9)),'value':value,'actual_historical_delivery_verified':False})
    df.to_csv(HERE/'data/OLD_LAG_1D.csv',encoding='utf-8-sig');new.to_csv(HERE/'data/LATEST_EOD_1D.csv',encoding='utf-8-sig')
    csv('POINT_IN_TIME_POLICY.csv',audit);csv('data/LATEST_FEATURE_LINEAGE.csv',lineage)
    groups=json.loads((D/'config/INFORMATION_SETS.json').read_text(encoding='utf-8'))
    groups={g:groups[g]['columns'] for g in ['M0','M1','M2']};js('config/INFORMATION_SETS.json',groups)
    scenarios={'A_old_annual_expanding':{'timing':'old','update':'annual','window':'expanding'},'B_latest_annual_expanding':{'timing':'latest','update':'annual','window':'expanding'},'C_latest_monthly_expanding':{'timing':'latest','update':'monthly','window':'expanding'},'D_latest_monthly_3years':{'timing':'latest','update':'monthly','window':'3_calendar_years'}}
    js('config/SCENARIOS.json',scenarios)
    text('EXPERIMENT_PLAN.md','''# 1D 개발 수정 비교 — 결과 평가 전에 고정

사용자 요청: 어제 종가 대비 오늘 종가 방향 예측을 개선하도록 가이드하고 진행. 기존D 산출물을 보존한 새 개발 실험입니다.2021년 이후 성능평가·최종 시험·Phase3 잠금은 실행하지 않습니다.

평가 날짜는 기존D와 같은2017~2020년1,007세션입니다. Y는100*(오늘Close/직전Close-1), 상승은>0, 보합·하락은<=0. origin은각 거래일09:00 America/New_York. 실제 당일Close는특징변수에사용하지않습니다.

A:기존2세션지연·연간갱신·확장학습. B:완료시장가격자료만1세션으로단축·연간갱신. C:B에월간갱신. D:C에최근3달력년학습. A/B는지연,B/C는갱신,C/D는학습창변경을분리합니다. 각 시나리오에M0(5)/M1(53)/M2(86)를동일날짜로비교합니다. M1은기존10변수와동일한집합은아닙니다.

01/02/04/09/10/12/13/14/23/46/47 시장가격은직전완료관측을다음미국세션08시에가용한것으로모델링합니다. 나머지위험·심리지표는실제전송증거가부족하여기존2세션가정을유지합니다. FGI/거시/월간산업은추가하지않습니다. 시장종가공개사건과벤더CSV의실제도착기록은다르며, 실제과거벤더시각·정정본검증한계는남습니다. 시간지연을낮춘것은완전한PIT인증이아닙니다.

LogisticClassifier(C1),RidgeRegressor(alpha100),XGBClassifier/Regressor(100trees,depth2,lr.05,lambda10,min_child10)을고정합니다. 분류threshold는.5,회귀는예측수익률>0으로판정합니다. 회귀예측수익률은확률로표시하지않습니다. 회귀ROC-AUC는예측수익률의순위로계산하고Brier는계산하지않습니다. 회귀MAE/RMSE를별도보고합니다. 분류와회귀XGB는같은트리복잡도예산으로비교합니다.

전처리는각학습부분에서만중앙값대치/스케일fit. fold첫origin전에성숙한과거Y만학습하고그달/그해전체를예측합니다. 설정/threshold를외부Y에맞춰튜닝하지않습니다. 초기2011~2016,개발2017~2020. 최근3년창도origin에서달력3년이내만사용합니다.

기준은학습다수클래스와직전완료SOX일간방향. Accuracy/BA/MCC/상승·비상승recall/F1/AUC/상승예측비율과기간별성과를보고합니다. 후보사후최고값에는선정편향이있으므로최종성능으로부르지않습니다. 20세션movingblock bootstrap2000회seed20261019로동일날짜다수기준대비정오차차이의95%구간을기술통계로보고합니다. A→B→C→D차이는동일알고리즘·그룹·날짜에서paired비교하고분류/회귀차이도보존합니다.

이번연구는조건부개발진단입니다. 개선이없거나하락식별력이낮으면그대로보고하고추가탐색/최종시험으로자동진행하지않습니다.
''')
    js('config/ESTIMATOR_PARAMETERS.json',{a:model(a).get_params(deep=True) for a in ['LogisticClassifier','RidgeRegressor','XGBClassifier','XGBRegressor']})
    env=json.loads((D/'config/ENVIRONMENT.json').read_text(encoding='utf-8'));env['revision_seed']=SEED;env['installations_performed']=False;js('config/ENVIRONMENT.json',env)
    return {'old':df,'latest':new},groups,scenarios

def run(tables,groups,scenarios):
    preds=[];folds=[];failures=[]
    prices=pd.read_csv(ROOT/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv',comment='#',usecols=['Date','Close']);prices=prices[prices.Date<='2020-12-31'];prices.index=pd.to_datetime(prices.Date)
    momentum=(prices.Close/prices.Close.shift(1)-1).shift(1)
    for scenario,setting in scenarios.items():
        data=tables[setting['timing']];dev=data[data.index.year>=2017]
        periods=dev.index.to_period('Y' if setting['update']=='annual' else 'M')
        for period in sorted(set(periods)):
            test=dev[periods==period];origin=pd.to_datetime(test.iloc[0].origin_et,utc=True)
            mature=pd.to_datetime(data.label_available_et,utc=True)<origin
            train=data[(data.index<test.index.min())&mature]
            if setting['window']=='3_calendar_years':train=train[train.index>=test.index.min()-pd.DateOffset(years=3)]
            assert len(train)>=500 and train.label_end.max()<test.index.min()
            prior=momentum.reindex(test.index);assert prior.notna().all()
            for name,score,cls in [('Majority',np.full(len(test),train.Y.mean()),np.full(len(test),int(train.Y.mean()>=.5))),('Momentum',(prior>0).astype(float).to_numpy(),(prior>0).astype(int).to_numpy())]:
                for date,y,ret,s,c in zip(test.index,test.Y,test.return_pct,score,cls):preds.append({'scenario':scenario,'group':'BASELINE','algorithm':name,'date':str(date.date()),'Y':int(y),'actual_return_pct':ret,'score':float(s),'probability':float(s),'predicted_return_pct':np.nan,'prediction':int(c),'fold':str(period),'train_n':len(train),'n_features':0})
            for group,cols in groups.items():
                for name in ['LogisticClassifier','RidgeRegressor','XGBClassifier','XGBRegressor']:
                    try:
                        regression='Regressor' in name;m=model(name);m.fit(train[cols],train.return_pct if regression else train.Y)
                        score=m.predict(test[cols]) if regression else m.predict_proba(test[cols])[:,1]
                        cls=(score>0).astype(int) if regression else (score>=.5).astype(int)
                        assert np.isfinite(score).all()
                        filename=f'models/{scenario}_{group}_{name}_{str(period)}.joblib';joblib.dump(m,HERE/filename)
                        folds.append({'scenario':scenario,'group':group,'algorithm':name,'fold':str(period),'train_start':str(train.index.min().date()),'train_end':str(train.index.max().date()),'max_train_label_end':str(train.label_end.max().date()),'first_origin':str(test.index.min().date()),'test_n':len(test),'train_n':len(train),'columns':cols,'model_path':filename})
                        for date,y,ret,s,c in zip(test.index,test.Y,test.return_pct,score,cls):preds.append({'scenario':scenario,'group':group,'algorithm':name,'date':str(date.date()),'Y':int(y),'actual_return_pct':ret,'score':float(s),'probability':np.nan if regression else float(s),'predicted_return_pct':float(s) if regression else np.nan,'prediction':int(c),'fold':str(period),'train_n':len(train),'n_features':len(cols)})
                    except Exception as e:
                        failures.append({'scenario':scenario,'group':group,'algorithm':name,'fold':str(period),'error':repr(e),'traceback':traceback.format_exc()})
            csv('predictions/PREDICTIONS.csv',preds);js('logs/FOLD_DETAILS.json',folds);js('logs/FAILURES.json',failures)
            print(scenario,period,'completed',len(folds),'models; failures',len(failures),flush=True)
    js('logs/RUN_STATUS.json',{'status':'COMPLETED' if not failures else 'COMPLETED_WITH_FAILURES','outer_fits':len(folds),'failures':len(failures),'post2020_evaluations':0})

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1)
    t,g,s=prepare();run(t,g,s)
