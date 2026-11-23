"""Fixed 16 masks x 6 regressors, monthly expanding historical evaluation.

Reuse sealed, X-only monthly transforms and feature masks from classification.
The target is the actual SOX close-to-close percentage return, not class codes.
"""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:
    os.environ[key]='1'
import sys,json,time,warnings,hashlib,importlib.metadata as metadata
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor,ExtraTreesRegressor,HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error,mean_squared_error,r2_score,confusion_matrix
from threadpoolctl import threadpool_limits
import crossed_feature_algorithm_search_20261023 as source
from verify_crossed_feature_search_20261023 import transform

W=source.W;S=source.O;O=W/'outputs/sox_return_regression16_v1_20261024'
ALGOS=['RIDGE','RF','ET','HGB','XGB','LGBM'];SEED=20261024
js=source.js;load=source.load;sha=source.sha;csv=source.csv

def estimator(algo):
    if algo=='RIDGE':return Ridge(alpha=10.,solver='cholesky')
    if algo in ['RF','ET']:
        cls=RandomForestRegressor if algo=='RF' else ExtraTreesRegressor
        return cls(n_estimators=48,max_depth=6,min_samples_leaf=20,max_features='sqrt',n_jobs=1,random_state=SEED)
    if algo=='HGB':return HistGradientBoostingRegressor(loss='squared_error',max_iter=60,max_leaf_nodes=15,max_depth=5,min_samples_leaf=30,l2_regularization=1,learning_rate=.05,early_stopping=False,random_state=SEED)
    if algo=='XGB':
        from xgboost import XGBRegressor
        return XGBRegressor(objective='reg:squarederror',n_estimators=64,max_depth=3,min_child_weight=10,reg_lambda=5,learning_rate=.05,subsample=.8,colsample_bytree=.8,tree_method='hist',n_jobs=1,random_state=SEED)
    if algo=='LGBM':
        from lightgbm import LGBMRegressor
        return LGBMRegressor(objective='regression',n_estimators=64,num_leaves=15,max_depth=5,min_child_samples=30,reg_lambda=5,learning_rate=.05,n_jobs=1,random_state=SEED,verbosity=-1,deterministic=True,force_col_wise=True)
    raise ValueError(algo)

def verify_inputs():
    source.verify()
    assert all(sha(p)==h for p,h in load(O/'INPUT_SEAL.json').items())

def prepare():
    O.mkdir(exist_ok=False);(O/'windows').mkdir()
    assert load(S/'COMPLETE.json')['status']=='COMPLETE'
    source.verify();windows=load(S/'late_COMPLETE.json')['windows'];assert len(windows)==34
    bank=load(S/'BANK16.json');assert len(bank)==16
    plan=dict(target='SOX return_pct=100*(close_D/close_previous_US_session-1)',target_source=str(source.parent.O/'LABELS_FOR_TRAINING_ONLY.csv'),unit='percentage points; +1 means +1%',origin='09:00 America/New_York; original source-time alignment inherited',evaluation='same694sessions2024-01-02..2026-10-07',training='expanding2011-02-03..previousmonth; actual valid X/Y start retained',masks=bank,algorithms={a:estimator(a).get_params() for a in ALGOS},fits=3264,workers=4,selection='No retuning or early stopping on2024..2026. All96policies evaluated. Rankings are posthoc exploratory.',primary_metric='RMSE; also MAE,R2,forecast-sign accuracy,nonupRecall',baseline=['ZERO','EXPANDING_TRAIN_MEAN','EXPANDING_TRAIN_MEDIAN'],out_of_sample_R2='1-SSE_model/SSE_monthly_past_train_mean_forecast',features='exact same saved actual per-month masks as classification; X-only median,scaling,PCA,coverage,correlation; no Y-based selection',French='same assumed monthly release bounds and current revised RAW; original vintages not verified',independent_test=False,automatic_model_change=False,API_calls=0)
    js(O/'FROZEN_PLAN.json',plan)
    inputs=[Path(__file__),S/'BANK16.json',S/'MASKS.json',S/'late_COMPLETE.json',source.parent.O/'LABELS_FOR_TRAINING_ONLY.csv',source.parent.O/'X216_WITHOUT_FRENCH_COMPONENTS_NO_Y.csv',W/'work/verify_crossed_feature_search_20261023.py',O/'FROZEN_PLAN.json']
    inputs += [source.parent.F/f'{p}_FRENCH420_ALIGNED_NO_Y.csv' for p in ['NEXT20','MONTH2_FIRST']]
    for row in windows:
        root=Path(row['window_root']);inputs += [root/'TRAIN_TRANSFORM.joblib',root/'FEATURE_MASKS.json',root/'COMPLETE.json',root/'PREDICTIONS_NO_Y.npz']
    js(O/'INPUT_SEAL.json',{str(p):sha(p) for p in inputs})
    js(O/'CURRENT_STATE.json',dict(stage='PREPARED',fits_completed=0,total_fits=3264))
    print('PREPARED 16 masks x6regressors x34months;3264fits',flush=True)

def fit_one(algo,a,b,y):
    model=estimator(algo);model.fit(a,y);p=model.predict(b)
    assert p.shape==(len(b),) and np.isfinite(p).all()
    return model,p

def run():
    verify_inputs();x,y,fs=source.parent.inputdata();assert np.isfinite(y.return_pct).all()
    assert np.array_equal((y.return_pct.to_numpy()>0).astype(int),y.Y.to_numpy())
    bank=load(S/'BANK16.json');summaries=[];total=0
    warnings.filterwarnings('ignore',message='X does not have valid feature names')
    for row in load(S/'late_COMPLETE.json')['windows']:
        window=row['window'];root=O/'windows'/window;root.mkdir(exist_ok=True)
        if (root/'COMPLETE.json').exists():
            seal=load(root/'COMPLETE.json')
            for file,h in seal['hashes'].items():assert sha(root/file)==h
            summaries.append(seal);total+=96;print('REUSE',window,flush=True);continue
        old=Path(row['window_root']);oldseal=load(old/'COMPLETE.json')
        assert sha(old/'TRAIN_TRANSFORM.joblib')==oldseal['transform_sha256'] and sha(old/'FEATURE_MASKS.json')==oldseal['features_sha256']
        with np.load(old/'PREDICTIONS_NO_Y.npz') as z:dates=z['dates'].astype(str)
        stats=joblib.load(old/'TRAIN_TRANSFORM.joblib');a,b,names,td=transform(x,fs,stats,window+'-01',dates)
        masks=load(old/'FEATURE_MASKS.json');assert set(masks)==set(bank)
        indices={m:[names.index(c) for c in masks[m]] for m in bank}
        train_y=y.loc[td,'return_pct'].to_numpy(float)
        assert td[-1]<dates[0] and td[-1]==oldseal['train_end']
        # Deliberately no evaluation Y access while fitting/predicting.
        prior=np.array([0.,train_y.mean(),np.median(train_y)])
        order=[(mask,algo) for mask in bank for algo in ALGOS];pos={k:i for i,k in enumerate(order)}
        pred=np.full((96,len(dates)),np.nan);models={};logs=[];start=time.monotonic()
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures={pool.submit(fit_one,algo,a[:,indices[mask]],b[:,indices[mask]],train_y):(mask,algo) for mask,algo in order}
            for future in as_completed(futures):
                mask,algo=futures[future];model,p=future.result();key=pos[(mask,algo)];pred[key]=p;models[str(key)]=model
                logs.append(dict(mask=mask,algo=algo,n_features=len(indices[mask]),n_train=len(td),train_start=str(td[0]),train_end=str(td[-1]),fit_success=True))
                if len(logs)%48==0:
                    js(O/'CURRENT_STATE.json',dict(stage='FIT',window=window,window_fits=len(logs),fits_completed=total+len(logs),total_fits=3264))
                    print('FIT',window,len(logs),'/96',round(time.monotonic()-start,1),'sec',flush=True)
        np.savez_compressed(root/'FORECASTS_NO_Y.npz',dates=dates,predictions=pred,mask=np.array([k[0] for k in order]),algo=np.array([k[1] for k in order]),baseline_values=prior)
        joblib.dump(models,root/'MODELS.joblib',compress=3);js(root/'FIT_LOG.json',logs)
        js(root/'FEATURES.json',masks)
        seal=dict(window=window,fits=96,train_start=str(td[0]),train_end=str(td[-1]),eval_start=str(dates[0]),eval_end=str(dates[-1]),source_transform=str(old/'TRAIN_TRANSFORM.joblib'),source_transform_sha256=sha(old/'TRAIN_TRANSFORM.joblib'),hashes={f:sha(root/f) for f in ['FORECASTS_NO_Y.npz','MODELS.joblib','FIT_LOG.json','FEATURES.json']})
        js(root/'COMPLETE.json',seal);summaries.append(seal);total+=96
    assert total==3264;verify_inputs();js(O/'FIT_COMPLETE.json',dict(fits=total,windows=summaries,eval_Y_used_for_fit=False))
    print('FIT COMPLETE3264;forecasts sealed before scoring',flush=True)

def metric(yy,p,mean_forecast):
    mse=mean_squared_error(yy,p);direc=p>0;truth=yy>0;cm=confusion_matrix(truth,direc,labels=[False,True]);tn,fp,fn,tp=cm.ravel()
    return dict(n=len(yy),MAE=mean_absolute_error(yy,p),RMSE=float(np.sqrt(mse)),MSE=mse,R2=r2_score(yy,p),R2_OOS_vs_train_mean=float(1-np.sum((yy-p)**2)/np.sum((yy-mean_forecast)**2)),direction_accuracy=float(np.mean(direc==truth)),up_prediction=float(direc.mean()),nonup_recall=float(tn/(tn+fp)),TN=int(tn),FP=int(fp),FN=int(fn),TP=int(tp),mean_prediction=float(p.mean()),actual_mean=float(yy.mean()))

def score():
    verify_inputs();_,y,_=source.parent.inputdata();daily=[];check=[];counts={m:[] for m in load(S/'BANK16.json')}
    for seal in load(O/'FIT_COMPLETE.json')['windows']:
        root=O/'windows'/seal['window']
        for file,h in seal['hashes'].items():assert sha(root/file)==h
        with np.load(root/'FORECASTS_NO_Y.npz') as z:
            dates=z['dates'].astype(str);pred=z['predictions'];order=list(zip(z['mask'].astype(str),z['algo'].astype(str)));prior=z['baseline_values']
        assert len(order)==96 and len(set(order))==96
        yy=y.loc[dates,'return_pct'].to_numpy();train_y=y.loc[y.index<seal['window']+'-01','return_pct'].to_numpy()
        assert np.allclose(prior,[0,train_y.mean(),np.median(train_y)])
        masks=load(root/'FEATURES.json')
        for mask,cols in masks.items():counts[mask].append(len(cols))
        for (mask,algo),pp in zip(order,pred):
            daily.extend(dict(mask=mask,algo=algo,date=d,Y=float(yy0),prediction=float(p0),train_mean=float(prior[1]),train_end=seal['train_end']) for d,yy0,p0 in zip(dates,yy,pp))
        for name,value in zip(['ZERO','TRAIN_MEAN','TRAIN_MEDIAN'],prior):daily.extend(dict(mask='BASELINE',algo=name,date=d,Y=float(yy0),prediction=float(value),train_mean=float(prior[1]),train_end=seal['train_end']) for d,yy0 in zip(dates,yy))
    df=pd.DataFrame(daily);df.to_csv(O/'DAILY_RESULTS.csv',index=False,encoding='utf-8-sig');metrics=[];yearly=[]
    for (mask,algo),g in df.groupby(['mask','algo'],sort=False):
        assert len(g)==694 and g.date.nunique()==694
        metrics.append(dict(mask=mask,algo=algo,**metric(g.Y.to_numpy(),g.prediction.to_numpy(),g.train_mean.to_numpy())))
        for yr,sub in g.groupby(g.date.str[:4]):yearly.append(dict(mask=mask,algo=algo,year=yr,**metric(sub.Y.to_numpy(),sub.prediction.to_numpy(),sub.train_mean.to_numpy())))
    csv(O/'ALL96_AND_BASELINES_METRICS.csv',metrics);csv(O/'YEARLY_METRICS.csv',yearly)
    table=pd.DataFrame(metrics);base=table[table['mask']=='BASELINE'];base.to_csv(O/'BASELINE_METRICS.csv',index=False,encoding='utf-8-sig')
    rows=[];bank=load(S/'BANK16.json');specs={m['mask']:m for m in load(S/'MASKS.json')}
    for no,mask in enumerate(bank,1):
        g=table[table['mask']==mask].sort_values(['RMSE','MAE','algo']);best=g.iloc[0].to_dict();best.update(original_number=no,groups='+'.join(specs[mask]['groups']) or 'INDIVIDUAL',French=specs[mask]['french'],actual_features_min=min(counts[mask]),actual_features_max=max(counts[mask]),selection='POSTHOC_BEST_RMSE_IN_EXPOSED_PERIOD');rows.append(best)
    summary=pd.DataFrame(rows).sort_values(['RMSE','MAE']);summary.insert(0,'rank',range(1,17));summary.to_csv(O/'BEST_PER_MASK_RMSE_RANKING.csv',index=False,encoding='utf-8-sig')
    rng=np.random.default_rng(SEED);ix=(rng.integers(0,675,size=(2000,35))[:,:,None]+np.arange(20)).reshape(2000,-1)[:,:694];intervals=[]
    for r in metrics:
        if r['mask']=='BASELINE':continue
        g=df[(df['mask']==r['mask'])&(df.algo==r['algo'])].sort_values('date');yy=g.Y.to_numpy();pp=g.prediction.to_numpy()
        for comparator in ['ZERO','TRAIN_MEAN']:
            b=df[(df['mask']=='BASELINE')&(df.algo==comparator)].sort_values('date');assert g.date.tolist()==b.date.tolist()
            for loss,diff in [('MAE',np.abs(yy-b.prediction.to_numpy())-np.abs(yy-pp)),('MSE',(yy-b.prediction.to_numpy())**2-(yy-pp)**2)]:
                v=diff[ix].mean(1);intervals.append(dict(mask=r['mask'],algo=r['algo'],baseline=comparator,loss=loss,baseline_loss_minus_model_loss=float(diff.mean()),lo95=float(np.quantile(v,.025)),hi95=float(np.quantile(v,.975)),interpretation='positive favors model; exploratory unadjusted for96policy search'))
    csv(O/'PAIRED_LOSS_BLOCK_BOOTSTRAP.csv',intervals)
    js(O/'SCORED.json',dict(policies=96,baseline_policies=3,days=694,posthoc_ranking=True))
    print('SCORED96policies+3baselines;694identicaldays',flush=True)

def verify():
    verify_inputs();x,y,fs=source.parent.inputdata();replayed=0
    for seal in load(O/'FIT_COMPLETE.json')['windows']:
        root=O/'windows'/seal['window']
        for file,h in seal['hashes'].items():assert sha(root/file)==h
        assert sha(seal['source_transform'])==seal['source_transform_sha256']
        with np.load(root/'FORECASTS_NO_Y.npz') as z:dates=z['dates'].astype(str);pp=z['predictions'];order=list(zip(z['mask'].astype(str),z['algo'].astype(str)))
        stats=joblib.load(seal['source_transform']);a,b,names,td=transform(x,fs,stats,seal['window']+'-01',dates);models=joblib.load(root/'MODELS.joblib');masks=load(root/'FEATURES.json')
        assert td[-1]<dates[0] and set(masks)==set(load(S/'BANK16.json')) and np.isfinite(pp).all()
        for i,(mask,algo) in enumerate(order):
            ix=[names.index(c) for c in masks[mask]];model=models[str(i)];pred=model.predict(b[:,ix]);assert np.allclose(pred,pp[i],atol=1e-9,rtol=1e-8);assert model.n_features_in_==len(ix);replayed+=1
        print('VERIFIED',seal['window'],96,'storedregressors',flush=True)
    assert replayed==3264
    # Confirm score uses continuous returns and completely reconciles with saved forecasts.
    df=pd.read_csv(O/'DAILY_RESULTS.csv');assert np.allclose(df.Y,y.loc[df.date,'return_pct'])
    for row in pd.read_csv(O/'ALL96_AND_BASELINES_METRICS.csv').to_dict('records'):
        g=df[(df['mask']==row['mask'])&(df.algo==row['algo'])];m=metric(g.Y.to_numpy(),g.prediction.to_numpy(),g.train_mean.to_numpy())
        assert all(np.isclose(row[k],v,rtol=1e-9,atol=1e-10) for k,v in m.items())
    js(O/'VERIFICATION.json',dict(status='PASS_CONDITIONAL_HISTORICAL_REGRESSION',models_replayed=replayed,all96_same694days=True,continuous_Y_verified=True,same_X_and_masks_as_classification=True,source_transforms_train_only_verified=True,all_scores_recomputed=True,independent_test=False,French_release_and_revision_assumptions_remain=True))

def report():
    assert load(O/'VERIFICATION.json')['models_replayed']==3264
    names={'RIDGE':'Ridge','RF':'RandomForest','ET':'ExtraTrees','HGB':'HistGradientBoost','XGB':'XGBoost','LGBM':'LightGBM'}
    translate={'PRICE':'가격','BREADTH':'시장폭','OPTIONS':'옵션','TECH':'ATR·밴드너비','FGI':'FGI','DAILY_MACRO':'일·주간 거시'}
    summary=pd.read_csv(O/'BEST_PER_MASK_RMSE_RANKING.csv');allm=pd.read_csv(O/'ALL96_AND_BASELINES_METRICS.csv');baseline=pd.read_csv(O/'BASELINE_METRICS.csv');year=pd.read_csv(O/'YEARLY_METRICS.csv')
    lines=['# SOX 당일 수익률 회귀: 동일16개 조합 ×6개 알고리즘','','## 설계','','- Y=100×(SOX 당일 종가/전 미국 거래일 종가−1). 클래스번호를 회귀한 것이 아닙니다.','- 평가2024-01-02~2026-10-07, 동일694일. 매월2011-02-03~직전달까지 누적 학습합니다.','- Ridge·RandomForest·ExtraTrees·HistGradientBoost·XGBoost·LightGBM. 총96개 정책,34개월,3,264회 학습.','- 기존 분류 실험의 동일16조합·월별 실제 변수목록·학습 내 변환을 그대로 사용합니다.','- 모든 모델은 제곱오차 기반 회귀이며 평가기간으로 파라미터·변수·예측값을 조정하지 않았습니다.','- 표의 순위는 평가기간을 본 뒤 RMSE가 낮은 순서입니다. 독립시험 또는 사전 선정 우승 모델을 의미하지 않습니다.','','## 단순 예측 기준','','|방법|MAE(%p)|RMSE(%p)|R²|방향 정확도|','|---|---:|---:|---:|---:|']
    for r in baseline.to_dict('records'):lines.append(f"|{r['algo']}|{r['MAE']:.4f}|{r['RMSE']:.4f}|{r['R2']:.4f}|{r['direction_accuracy']:.2%}|")
    lines +=['','## 16조합별 최저 RMSE 알고리즘 — 탐색적 순위','','|순위|기존번호|조합|French|변수수|알고리즘|MAE(%p)|RMSE(%p)|R²|과거평균대비 OOS R²|방향정확도|비상승Recall|','|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|']
    for r in summary.to_dict('records'):
        groups=' + '.join(translate.get(c,c) for c in r['groups'].split('+'))
        lines.append(f"|{r['rank']}|{r['original_number']}|{groups} ({r['mask']})|{r['French']}|{r['actual_features_min']}~{r['actual_features_max']}|{names[r['algo']]}|{r['MAE']:.4f}|{r['RMSE']:.4f}|{r['R2']:.4f}|{r['R2_OOS_vs_train_mean']:.4f}|{r['direction_accuracy']:.2%}|{r['nonup_recall']:.2%}|")
    top=summary.iloc[0];lines +=['','## 관측 최상위 모델의 연도별 결과','','|연도|일수|MAE(%p)|RMSE(%p)|R²|방향정확도|비상승Recall|','|---|---:|---:|---:|---:|---:|---:|']
    for r in year[(year['mask']==top['mask'])&(year.algo==top['algo'])].to_dict('records'):lines.append(f"|{r['year']}|{r['n']}|{r['MAE']:.4f}|{r['RMSE']:.4f}|{r['R2']:.4f}|{r['direction_accuracy']:.2%}|{r['nonup_recall']:.2%}|")
    lines +=['','## 해석과 한계','','MAE・RMSE는 작을수록 좋습니다. 단위는 수익률 퍼센트포인트이며, MAE1.2는 예측 수익률이 실제와 평균1.2%p 차이났다는 뜻입니다. R²는 클수록 좋고 음수도 가능합니다. 표준 R²의 분모는 평가표본 평균 기준 편차이며, 실행 가능한 과거정보 기준과 비교하려고 월별 과거 학습평균 예측 대비 OOS R²도 별도로 제시합니다.','', '방향정확도는 예측수익률>0이면 상승, 나머지는 비상승으로 분류해 계산한 부가 지표입니다. 회귀 RMSE 최소화와 방향정확도 최대화는 다릅니다. 0%기준은 모두 비상승이 되므로 방향성 기준으로 항상상승 모델을 대체하지 않습니다.','', 'French A(NEXT20)는 관측월 다음달20일 이후, French B(MONTH2_FIRST)는 다다음달 첫 거래일부터 월말 요약값을 사용한다는 가정입니다. 당시 배포본・실제 공개시각・수정이력 미입증 위험이 남아 있으며 유예만으로 제거되지 않습니다. FGI/일부 거시 등 원 실험의 조건부 가용성도 계승합니다.','', '2024~2026은 이미 여러 연구에서 열람한 기간입니다. 동일16조합도 과거 분류 탐색에서 정한 목록으로, 회귀 조합 전수탐색을 뜻하지 않습니다. 전체96정책의 관측상 최고를 선정한 편향이 있으므로 일반화나 통계적 유의성을 확정하지 않습니다. 블록부트스트랩95%구간은20거래일블록2,000회 탐색적 참고값이며96개 다중비교 보정은 하지 않았습니다.','', '모든3,264개 저장회귀모델로 예측을 재현했고 날짜・입력해시・학습내 변환・점수 일치를 검사했습니다. 이는 자료의 과거 실제 배포본까지 검증했다는 뜻이 아닙니다. 기존 분류모델・원본・이전결과는 변경하지 않았고 새 모델 자동배포・API소비는0입니다.','','## 공식 참고문서','','- https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html','- https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html','- https://xgboost.readthedocs.io/en/stable/parameter.html','- https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRegressor.html']
    (O/'핵심결과.md').write_text('\n'.join(lines),encoding='utf-8')
    # Standalone scientific plot: every model RMSE, no decorative presentation.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    matrix=allm[allm['mask']!='BASELINE'].pivot(index='mask',columns='algo',values='RMSE').reindex(index=summary['mask'],columns=ALGOS)
    fig,ax=plt.subplots(figsize=(10,9));im=ax.imshow(matrix.to_numpy(),aspect='auto',cmap='viridis_r');ax.set_xticks(range(6),ALGOS);ax.set_yticks(range(16),[f"#{int(n)} {m}" for n,m in zip(summary.original_number,summary['mask'])]);ax.set_title('SOX 1D return: RMSE (percentage points), lower is better')
    for i in range(16):
        for j in range(6):ax.text(j,i,f'{matrix.iloc[i,j]:.3f}',ha='center',va='center',fontsize=8,color='black',bbox=dict(facecolor='white',alpha=.6,edgecolor='none',pad=1))
    fig.colorbar(im,ax=ax,label='RMSE (percentage points)');fig.tight_layout();fig.savefig(O/'RMSE_ALL96.png',dpi=180);plt.close(fig)
    js(O/'ENVIRONMENT.json',dict(python=sys.version,packages={k:metadata.version(k) for k in ['numpy','pandas','scikit-learn','xgboost','lightgbm','joblib']}))
    js(O/'COMPLETE.json',dict(status='COMPLETE',fits=3264,policies=96,days=694,models_replayed=3264,posthoc_rankings=True,independent_test=False))
    js(O/'CURRENT_STATE.json',dict(stage='COMPLETE',fits_completed=3264,total_fits=3264))
    js(O/'OUTPUT_MANIFEST.json',{str(p.relative_to(O)):sha(p) for p in O.rglob('*') if p.is_file() and p.name!='OUTPUT_MANIFEST.json'})
    assert all(sha(O/p)==h for p,h in load(O/'OUTPUT_MANIFEST.json').items())
    print('REGRESSION EXPERIMENT COMPLETE',flush=True)

def main():
    threadpool_limits(1)
    if not O.exists():prepare()
    if not (O/'FIT_COMPLETE.json').exists():run()
    if not (O/'SCORED.json').exists():score()
    if not (O/'VERIFICATION.json').exists():verify()
    if not (O/'COMPLETE.json').exists():report()

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
