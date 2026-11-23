"""Annual expanding outer walk-forward; tuning solely inside prior training years."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import sys,json,traceback,warnings,importlib.util,importlib.metadata as metadata
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.base import BaseEstimator,TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import f_classif
from sklearn.linear_model import LogisticRegression,RidgeClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score,balanced_accuracy_score,matthews_corrcoef,f1_score,roc_auc_score,brier_score_loss,log_loss,recall_score,precision_score
from threadpoolctl import threadpool_limits
import joblib
OUT=Path(__file__).resolve().parents[1];SEED=20261019
warnings.filterwarnings('always')
def save(name,x): (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
class TrainSelector(BaseEstimator,TransformerMixin):
    def __init__(self,cap=25,max_missing=.35,max_corr=.98):self.cap=cap;self.max_missing=max_missing;self.max_corr=max_corr
    def fit(self,X,y):
        X=np.asarray(X,dtype=float);eligible=np.flatnonzero((np.mean(np.isnan(X),axis=0)<=self.max_missing)&(np.nanstd(X,axis=0)>1e-10))
        if not len(eligible):raise ValueError('No eligible train-only selection features')
        z=X[:,eligible];med=np.nanmedian(z,axis=0);z=np.where(np.isnan(z),med,z)
        score=np.nan_to_num(f_classif(z,y)[0],nan=-np.inf,posinf=1e100)
        selected=[]
        for j in sorted(range(len(eligible)),key=lambda j:(-score[j],int(eligible[j]))):
            if all(abs(np.corrcoef(z[:,j],z[:,q])[0,1])<self.max_corr for q in selected):selected.append(j)
            if len(selected)>=self.cap:break
        self.selected_=eligible[selected];return self
    def transform(self,X):return np.asarray(X,dtype=float)[:,self.selected_]

def model(algo,variant,select):
    if algo=='LogisticRegression':est=LogisticRegression(C=1 if variant==0 else .1,max_iter=1500,solver='lbfgs',random_state=SEED)
    elif algo=='RidgeClassifier':est=RidgeClassifier(alpha=10 if variant==0 else 100)
    elif algo=='RandomForest':est=RandomForestClassifier(n_estimators=100,max_depth=4 if variant==0 else 2,min_samples_leaf=20,max_features='sqrt',n_jobs=1,random_state=SEED)
    elif algo=='XGBoost':
        from xgboost import XGBClassifier
        est=XGBClassifier(n_estimators=100,max_depth=2 if variant==0 else 1,learning_rate=.05,min_child_weight=10,reg_lambda=10,subsample=1,colsample_bytree=1,random_state=SEED,n_jobs=1,tree_method='hist',eval_metric='logloss')
    elif algo=='LightGBM':
        from lightgbm import LGBMClassifier
        est=LGBMClassifier(n_estimators=100,num_leaves=7 if variant==0 else 3,max_depth=3 if variant==0 else 2,min_child_samples=30,learning_rate=.05,reg_lambda=10,random_state=SEED,n_jobs=1,verbosity=-1,deterministic=True,force_col_wise=True)
    else:raise ValueError(algo)
    steps=[]
    if select:steps.append(('select',TrainSelector()))
    steps += [('impute',SimpleImputer(strategy='median',keep_empty_features=True)),('scale',StandardScaler()),('model',est)]
    base=Pipeline(steps)
    # Calibration subfolds must also refit imputation/scaling/feature selection.
    if algo=='RidgeClassifier':
        return Pipeline([('model',CalibratedClassifierCV(base,cv=TimeSeriesSplit(n_splits=3),method='sigmoid',ensemble=True,n_jobs=1))])
    return base

def metrics(y,p,cls):
    return {'n':len(y),'accuracy':accuracy_score(y,cls),'balanced_accuracy':balanced_accuracy_score(y,cls),'MCC':matthews_corrcoef(y,cls),'F1':f1_score(y,cls,zero_division=0),'ROC_AUC':roc_auc_score(y,p) if len(set(y))==2 else np.nan,'Brier':brier_score_loss(y,p),'LogLoss':log_loss(y,np.clip(p,1e-10,1-1e-10),labels=[0,1]),'recall_up':recall_score(y,cls,pos_label=1,zero_division=0),'recall_nonup':recall_score(y,cls,pos_label=0,zero_division=0),'precision_up':precision_score(y,cls,zero_division=0),'actual_up_fraction':float(np.mean(y)),'predicted_up_fraction':float(np.mean(cls))}

def run():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1)
    inventory=pd.read_csv(OUT/'FEATURE_DICTIONARY.csv');groups=json.loads((OUT/'config/INFORMATION_SETS.json').read_text(encoding='utf-8'))
    algos=['LogisticRegression','RidgeClassifier','RandomForest']
    for lib,name in [('xgboost','XGBoost'),('lightgbm','LightGBM')]:
        if importlib.util.find_spec(lib):algos.append(name)
    save('config/ENVIRONMENT.json',{'python':sys.version,'executable':sys.executable,'seed':SEED,'threads':1,'packages':{m:metadata.version(m) if importlib.util.find_spec(m.replace('scikit-learn','sklearn')) else None for m in ['numpy','pandas','scipy','scikit-learn','xgboost','lightgbm','catboost','joblib']},'CatBoost':'NOT_INSTALLED_NOT_RUN','installation_performed':False})
    plan='''# Phase2 실행 계획 — 평가 전에 고정

목표는 방향 Accuracy입니다. 초기2011~2016, 외부 검증2017/2018/2019/2020년의4개 expanding fold를 사용합니다. 각 외부 연도 첫 origin 이전에 성숙한 과거 라벨만 학습하고 그 해 전체를 예측합니다. 연도 내 매일 재학습하지 않는 보수적 연간 갱신 walk-forward입니다. 2021년 이후 데이터는 로딩·평가하지 않습니다.

각 외부 학습기간 마지막 달력년도를 내부 검증으로 남깁니다. 나머지 이전 연도로 전처리·모델을 fit합니다. 모든 기본 후보를 내부 threshold=.5로 비교하고, 내부 다수기준 이상이면서 같은 정보집합의 내부 최고 Accuracy와1%p 이내인 알고리즘에만 추가 규제설정1개를 허용합니다. 외부 Y는 이 판단에 쓰지 않습니다. 알고리즘별 허용 설정과 threshold .45/.50/.55를 내부 Accuracy로 결정합니다. 동점은 .5에 가까운 threshold, 작은 variant 순입니다. 그 후 외부 학습전체에 재적합하고 외부연도를 예측합니다. 모든 내부 시도·실패를 기록합니다. 큰 탐색·early stopping·외부 시험튜닝은 없습니다.

M0/M1/M2/M4를 비교합니다. M3은 적격 거시·월간산업 빈티지가 없으므로 M2 예측과 동일한 alias이며 새 fit은 하지 않습니다. M4는 각 학습 fit에서 결측35%초과·상수 제외, F통계 순위, 절대상관 .98이상 제거, 최대25변수입니다. 입력 후보/실제 선택 컬럼을 fold별 보존합니다. SOX와 중복성이 큰 TSM·TWSE·SOXX·SMH를 제외한 M2_no_sector_proxy도 사전 ablation으로 비교합니다.

기준은 학습 다수클래스(동률상승), 직전 완료 SOX 방향입니다. 기준 모멘텀은 origin 전일 실제 종가로 정해지는 직전 일/주 방향을 사용합니다. 복잡모형 M0의2세션 feature 지연보다 최신인 보수적으로 강한 기준입니다. Logistic도 동일 fold로 비교합니다. Ridge 확률은 학습자료 내부 TimeSeriesSplit3개의 sigmoid calibration ensemble로 만듭니다. 나머지는 predict_proba이며 완전한 확률 calibration을 보장하지 않습니다.

Accuracy/BA/MCC/F1/AUC/Brier/LogLoss, 상승·비상승 recall과 상승 precision, 연도별 결과를 저장합니다. Pooled 최고값은 개발후보 탐색 결과이며 최종 시험 성능이 아닙니다. 동일 날짜 다수기준 대비 정오차 차이를 달력 순서 moving block bootstrap(1D20세션/1W8주,2000회,seed20261019,percentile95%)으로 계산합니다. 선택 후 여러 모형을 탐색한 효과를 보정한 최종 추론이 아니며 구간을 개발 기술통계로만 보고합니다.
'''
    (OUT/'PHASE2_EXPERIMENT_PLAN.md').write_text(plan,encoding='utf-8')
    save('config/ESTIMATOR_PARAMS.json',{a:{str(v):model(a,v,False).get_params(deep=True) for v in [0,1]} for a in algos})
    pred=[];attempt=[];foldlog=[];fail=[]
    for h in ['1D','1W']:
        df=pd.read_csv(OUT/f'data/DEV_{h}.csv',parse_dates=['date','label_end']).set_index('date')
        assert df.index.max().year==2020
        maturity=pd.to_datetime(df.label_available_et,utc=True)
        # Build momentum from complete SOX history rather than model warmup-filtered labels.
        raw=pd.read_csv(OUT.parent/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv',comment='#',usecols=['Date','Close'])
        raw=raw[raw.Date<='2020-12-31'];raw.index=pd.to_datetime(raw.Date)
        close=raw.Close
        if h=='1D':past_ret=close.pct_change(fill_method=None).shift(1)
        else:
            g=close.groupby(close.index.to_period('W-FRI'));rets=g.last().pct_change(fill_method=None).shift(1);past_ret=pd.Series(rets.to_numpy(),index=g.apply(lambda s:s.index[0]).to_numpy())
        for year in [2017,2018,2019,2020]:
            test=df[df.index.year==year];origin=pd.to_datetime(test.iloc[0].origin_et,utc=True)
            train=df[(df.index.year<year)&(maturity<origin)]
            assert train.label_end.max()<test.index.min() and train.index.max()<test.index.min()
            inner=train[train.index.year<year-1];val=train[train.index.year==year-1]
            assert len(inner)>100 and len(val)>=40
            ytrain=train.Y.to_numpy();yt=test.Y.to_numpy();yv=val.Y.to_numpy()
            prev=past_ret.reindex(test.index);assert prev.notna().all()
            for name,pp,cls in [('Majority',np.full(len(test),ytrain.mean()),np.full(len(test),int(ytrain.mean()>=.5))),('Momentum',(prev>0).astype(float).to_numpy(),(prev>0).astype(int).to_numpy())]:
                for d,y,p,c in zip(test.index,yt,pp,cls):pred.append({'horizon':h,'group':'BASELINE','algorithm':name,'year':year,'date':str(d.date()),'Y':int(y),'probability':float(p),'prediction':int(c),'threshold':.5,'n_features':0,'variant':-1})
            gmap={g:groups[g]['columns'] for g in ['M0','M1','M2','M4']}
            sector=set(inventory.loc[inventory.high_SOX_overlap,'feature']);gmap['M2_no_sector_proxy']=[c for c in groups['M2']['columns'] if c not in sector]
            for group,cols in gmap.items():
                selected=group=='M4';base={};fits={}
                for algo in algos:
                    try:
                        m=model(algo,0,selected);m.fit(inner[cols],inner.Y);pv=m.predict_proba(val[cols])[:,1]
                        base[algo]=accuracy_score(yv,pv>=.5);fits[algo]=(m,pv)
                        attempt.append({'horizon':h,'group':group,'outer_year':year,'algorithm':algo,'variant':0,'threshold':.5,'inner_accuracy':base[algo],'phase':'default_screen','inner_max_date':str(inner.index.max().date()),'validation_year':year-1})
                    except Exception as e:fail.append({'horizon':h,'group':group,'year':year,'algorithm':algo,'phase':'inner_default','error':repr(e),'traceback':traceback.format_exc()})
                best=max(base.values()) if base else -np.inf;majority=accuracy_score(yv,np.full(len(yv),int(inner.Y.mean()>=.5)))
                for algo in algos:
                    if algo not in fits:continue
                    try:
                        candidates=[(0,fits[algo][1])]
                        if base[algo]>=majority and base[algo]>=best-.01:
                            m=model(algo,1,selected);m.fit(inner[cols],inner.Y);candidates.append((1,m.predict_proba(val[cols])[:,1]))
                        choices=[]
                        for variant,pv in candidates:
                            for threshold in [.45,.5,.55]:
                                score=accuracy_score(yv,pv>=threshold);choices.append((score,-abs(threshold-.5),-variant,-threshold,variant,threshold))
                                attempt.append({'horizon':h,'group':group,'outer_year':year,'algorithm':algo,'variant':variant,'threshold':threshold,'inner_accuracy':score,'phase':'inner_selection','inner_max_date':str(inner.index.max().date()),'validation_year':year-1})
                        choice=max(choices);variant,threshold=choice[-2:]
                        final=model(algo,variant,selected);final.fit(train[cols],train.Y)
                        pp=final.predict_proba(test[cols])[:,1];cls=(pp>=threshold).astype(int)
                        assert np.isfinite(pp).all() and ((pp>=0)&(pp<=1)).all()
                        submodel_columns=[]
                        if selected and algo=='RidgeClassifier':
                            submodel_columns=[[cols[i] for i in cc.estimator.named_steps['select'].selected_] for cc in final.named_steps['model'].calibrated_classifiers_]
                            actual=[c for c in cols if any(c in sub for sub in submodel_columns)]
                        else:actual=[cols[i] for i in final.named_steps['select'].selected_] if selected else cols
                        name=f'{h}_{group}_{algo}_{year}';joblib.dump(final,OUT/f'models/{name}.joblib')
                        foldlog.append({'horizon':h,'group':group,'algorithm':algo,'outer_year':year,'train_n':len(train),'inner_n':len(inner),'inner_validation_n':len(val),'test_n':len(test),'train_end':str(train.index.max().date()),'train_label_end':str(train.label_end.max().date()),'outer_first_origin':str(test.index.min().date()),'variant':variant,'threshold':threshold,'candidate_features':cols,'selected_features':actual,'calibration_submodel_columns':submodel_columns,'selected_count':len(actual),'model_path':f'models/{name}.joblib'})
                        for d,y,p,c in zip(test.index,yt,pp,cls):pred.append({'horizon':h,'group':group,'algorithm':algo,'year':year,'date':str(d.date()),'Y':int(y),'probability':float(p),'prediction':int(c),'threshold':threshold,'n_features':len(actual),'variant':variant})
                    except Exception as e:fail.append({'horizon':h,'group':group,'year':year,'algorithm':algo,'phase':'selection_or_outer','error':repr(e),'traceback':traceback.format_exc()})
                print(h,year,group,'done',flush=True)
                pd.DataFrame(pred).to_csv(OUT/'predictions/DEVELOPMENT_PREDICTIONS.csv',index=False,encoding='utf-8-sig');pd.DataFrame(attempt).to_csv(OUT/'logs/ALL_INNER_ATTEMPTS.csv',index=False,encoding='utf-8-sig');save('logs/FOLD_DETAILS.json',foldlog);save('logs/FAILURES.json',fail)
    p=pd.DataFrame(pred)
    alias=p[p.group=='M2'].copy();alias['group']='M3';p=pd.concat([p,alias],ignore_index=True)
    p.to_csv(OUT/'predictions/DEVELOPMENT_PREDICTIONS.csv',index=False,encoding='utf-8-sig')
    rows=[]
    for (h,g,a),v in p.groupby(['horizon','group','algorithm']):
        for period in ['ALL',2017,2018,2019,2020]:
            w=v if period=='ALL' else v[v.year==period]
            if not len(w):continue
            b=p[(p.horizon==h)&(p.algorithm=='Majority')];b=b if period=='ALL' else b[b.year==period]
            base=accuracy_score(b.Y,b.prediction)
            r={'horizon':h,'group':g,'algorithm':a,'period':period,'feature_min':int(w.n_features.min()),'feature_max':int(w.n_features.max()),'baseline_accuracy':base,'M3_alias':g=='M3'};r.update(metrics(w.Y,w.probability,w.prediction));r['improvement_pp']=100*(r['accuracy']-base);rows.append(r)
    pd.DataFrame(rows).to_csv(OUT/'PHASE2_MODEL_RESULTS.csv',index=False,encoding='utf-8-sig')
    save('logs/EXECUTION_STATUS.json',{'status':'COMPLETED_WITH_FAILURES' if fail else 'COMPLETED','failures':len(fail),'outer_models':len(foldlog),'inner_attempt_records':len(attempt),'post2020_performance_evaluations':0})
    print('MODELS FINISHED',len(foldlog),'failures',len(fail),flush=True)
if __name__=='__main__':run()
