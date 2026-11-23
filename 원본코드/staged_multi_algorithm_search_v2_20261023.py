"""Bounded staged temporal exploration; public-time assumptions retained."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,hashlib,itertools,warnings,time
import numpy as np,pandas as pd,joblib
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.feature_selection import f_classif
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier,ExtraTreesClassifier,HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score,balanced_accuracy_score,f1_score,confusion_matrix,log_loss,roc_auc_score
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
W=Path(__file__).resolve().parents[1];O=W/'outputs/staged_multi_algorithm_v2_20261023';P=W/'outputs/four_groups_2024_2026_v1_20261022/COMBINED82';R=W/'outputs/reduced_four_groups_v1_20261022/COMBINED82';F=W/'outputs/french_release_scenarios_v1_20261023';A=W/'outputs/four_class70_previous_year_v1_20261022';N=W/'outputs/near_release_reconstruction_v1_20261023';SEED=20261023;ALGOS=['LR','RF','ET','HGB','XGB','LGBM'];TASKS=['BINARY','FOUR'];OPTIONAL=['BREADTH','OPTIONS','TECH','FGI','DAILY_MACRO','MONTHLY_REAL']
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def csv(p,x):pd.DataFrame(x).to_csv(p,index=False,encoding='utf-8-sig')
def verify():assert all(sha(p)==h for p,h in load(O/'INPUT_SEAL.json').items())
def model(algo,task):
    if algo=='LR':return LogisticRegression(C=.1,max_iter=2500,solver='lbfgs',random_state=SEED)
    if algo=='RF':return RandomForestClassifier(n_estimators=80,max_depth=6,min_samples_leaf=20,max_features='sqrt',n_jobs=1,random_state=SEED)
    if algo=='ET':return ExtraTreesClassifier(n_estimators=80,max_depth=6,min_samples_leaf=20,max_features='sqrt',n_jobs=1,random_state=SEED)
    if algo=='HGB':return HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,max_depth=5,min_samples_leaf=30,l2_regularization=1,learning_rate=.05,early_stopping=False,random_state=SEED)
    if algo=='XGB':
        from xgboost import XGBClassifier
        return XGBClassifier(n_estimators=100,max_depth=3,min_child_weight=10,reg_lambda=5,learning_rate=.05,subsample=.8,colsample_bytree=.8,tree_method='hist',n_jobs=1,random_state=SEED,eval_metric='logloss' if task=='BINARY' else 'mlogloss')
    if algo=='LGBM':
        from lightgbm import LGBMClassifier
        return LGBMClassifier(n_estimators=100,num_leaves=15,max_depth=5,min_child_samples=30,reg_lambda=5,learning_rate=.05,n_jobs=1,random_state=SEED,verbosity=-1,deterministic=True,force_col_wise=True)
    raise ValueError(algo)
def prepare():
    if O.exists():
        assert not (O/'INPUT_SEAL.json').exists() and not list((O/'models').glob('*'))
        (O/'PREPARATION_REPAIR.md').write_text('학습 전 준비 단계에서 NumPy row_stack 제거로 중단. vstack으로 수정. 당시 fit0,성능평가0.',encoding='utf-8')
    else:O.mkdir()
    (O/'models').mkdir(exist_ok=True)
    inputs=[Path(__file__),P/'PACKET_MANIFEST.json',R/'FROZEN_CONFIG.json',A/'SCORING_TRUTH.csv',A/'ANNUAL_THRESHOLDS.csv',N/'AVAILABLE142_NEAR_RELEASE_SCENARIO_NO_Y.csv',N/'변수목록_RAW_계산식_공개규칙.csv',W/'outputs/atr_bandwidth_70_53_v1_20261022/ADDED_FEATURES.csv',F/'NEXT20_FRENCH420_ALIGNED_NO_Y.csv',F/'MONTH2_FIRST_FRENCH420_ALIGNED_NO_Y.csv']
    packet=load(P/'PACKET_MANIFEST.json')['packets'][-1];assert packet['month']=='2026-10' and sha(packet['path'])==packet['sha256'];inputs.append(Path(packet['path']));sourcecols=load(P/'FROZEN_CONFIG.json')['features'];basecols=sourcecols;ix=[sourcecols.index(c) for c in basecols]
    with np.load(packet['path']) as z:dates=np.concatenate([z['train_dates'],z['eval_dates']]).astype(str);x=np.vstack([z['train_x'][:,ix],z['eval_x'][:,ix]])
    data=pd.DataFrame(x,index=dates,columns=basecols);data.index.name='date';assert data.index.is_unique
    extra=pd.read_csv(N/'AVAILABLE142_NEAR_RELEASE_SCENARIO_NO_Y.csv',index_col=0,float_precision='round_trip').reindex(dates);tech=pd.read_csv(W/'outputs/atr_bandwidth_70_53_v1_20261022/ADDED_FEATURES.csv',index_col=0,float_precision='round_trip').reindex(dates);assert len(tech.columns)==2
    dictionary=pd.read_csv(N/'변수목록_RAW_계산식_공개규칙.csv');monthly=dictionary.loc[dictionary.source_id.isin([22,24,25,32,36,37]),'변수명'].tolist();fgi=[c for c in extra if c.startswith('fgi_')];assert len(fgi)==9 and len(monthly)==56
    groups={'PRICE':[c for c in basecols if not c.startswith(('s05_','s06_','s40_','s41_','s30_','s31_','s07_','s28_','s29_'))], 'BREADTH':[c for c in basecols if c.startswith(('s05_','s06_','s40_','s41_','s30_','s31_'))],'OPTIONS':[c for c in basecols if c.startswith(('s07_','s28_','s29_'))],'TECH':list(tech),'FGI':fgi,'MONTHLY_REAL':monthly,'DAILY_MACRO':[c for c in extra if c not in fgi+monthly]}
    assert len(groups['PRICE'])==55 and len(groups['BREADTH'])==18 and len(groups['OPTIONS'])==9
    overlap=data.columns.intersection(extra.columns).tolist()
    assert np.array_equal(data[overlap].to_numpy(),extra[overlap].to_numpy(),equal_nan=True),'Overlapping SOXX/SMH values disagree'
    csv(O/'ALIASED_FEATURES.csv',[dict(feature=c,kept='original82 price group',removed_duplicate='extra142 source',identical=True) for c in overlap])
    extra=extra.drop(columns=overlap);groups['DAILY_MACRO']=[c for c in groups['DAILY_MACRO'] if c not in overlap]
    data=pd.concat([data,tech,extra],axis=1);assert data.columns.is_unique;data.to_csv(O/'X216_WITHOUT_FRENCH_COMPONENTS_NO_Y.csv',encoding='utf-8-sig')
    truth=pd.read_csv(A/'SCORING_TRUTH.csv').set_index('date').loc[dates];assert (truth.reference_year==pd.to_datetime(truth.index).year-1).all();r=truth.return_pct.to_numpy();t=truth.threshold_pct.to_numpy();assert np.array_equal(np.select([r<=-t,(r>-t)&(r<=0),(r>0)&(r<t),r>=t],[0,1,2,3],default=-1),truth.class4) and np.array_equal((r>0).astype(int),truth.Y)
    for name,mask in [('EARLY',truth.index<'2021-01-01'),('MIDDLE',(truth.index>='2021-01-01')&(truth.index<'2023-01-01')),('CONFIRM',(truth.index>='2023-01-01')&(truth.index<'2024-01-01')),('LATE',truth.index>='2024-01-01')]:truth.loc[mask].to_csv(O/f'TRUTH_{name}.csv',encoding='utf-8-sig')
    truth.to_csv(O/'LABELS_FOR_TRAINING_ONLY.csv',encoding='utf-8-sig');js(O/'GROUPS.json',groups)
    combos=[]
    for flags in itertools.product([0,1],repeat=6):
        for french in ['NONE','NEXT20','MONTH2_FIRST']:
            names=['PRICE']+[g for g,f in zip(OPTIONAL,flags) if f];cid='G'+''.join(map(str,flags))+'_'+french;combos.append(dict(combo=cid,groups=names,french=french))
    baseline=next(r['combo'] for r in combos if r['groups']==['PRICE','BREADTH','OPTIONS'] and r['french']=='NONE');js(O/'COMBINATIONS.json',combos)
    plan=dict(scope='1d binary and previous-year median fourclass; conditional historical development',combination_count=192,core='PRICE55 mandatory; six optional groups; French none/next20/month2 mutually exclusive',algorithms={a:model(a,'BINARY').get_params() for a in ALGOS},baseline_combo=baseline,baseline_classifier='LR_C0.1_FIXED; existing dynamicC results supplementary only',stage1='192 combos x2tasks x3annual origin folds(2016,2018,2020),LR fixedC0.1:1152 fits',stage2='top3 nonbaseline combos plus baseline per task x3 feature selectors(ALL,TOP25,TOP50) x6algorithms x2annual folds(2021,2022); <=288fits',stage3='best middle candidate per algorithm plus baseline per task; monthly2023 confirmation <=168fits',stage4='all sealed algorithm finalists +baseline,monthly2024-01..2026-10, <=476fits; no retuning on results',fit_cap=2084,feature_filter='training coverage>=80%,nonconstant; direct Pearson |r|>=.95 original-order greedy within current candidate; TOP25/50 by training-only ANOVA f_classif; no external Y',French_PCA='420 ->10 inside each training fold, fixed seed, prior assumed release alignment',screening='coarse annual fit is a cheap ranking stage, NOT monthly performance; final stages monthly expanding2011..previousmonth',selection='binary accuracy&BA nonworse than baseline preferred, rank BA then accuracy; four macroF1 then accuracy; final2023 eligibility accuracy strict gain plus TN nondecrease(binary) or macroF1 gain(four)',four_rule='c_y=previous calendar year median absSOXdaily return;0:r<=-c;1:-c<r<=0;2:0<r<c;3:r>=c;each training row retains own pastyear cutoff',excluded=['News:insufficientpre2024traininganddifferentauxiliaryscope','Premarket:insufficienthistoricalcoverage','Constituentfeatures:incompletepointintimemembershipgates','Rawunverifiednativevariables:notalignedfor09ET'],no_automatic_model_replacement=True,independent_test=False,revision_risk_remains=True,API_calls=0)
    js(O/'FROZEN_PLAN.json',plan);csv(O/'GROUP_INVENTORY.csv',[dict(group=g,n=len(cols),features='|'.join(cols)) for g,cols in groups.items()]);js(O/'INPUT_SEAL.json',{str(p):sha(p) for p in inputs+[O/'GROUPS.json',O/'COMBINATIONS.json',O/'FROZEN_PLAN.json',O/'X216_WITHOUT_FRENCH_COMPONENTS_NO_Y.csv',O/'LABELS_FOR_TRAINING_ONLY.csv']})
    print('PREPARED 192 combinations;6algorithms;2tasks;fit cap2084;X columns',len(data.columns),flush=True)
def inputdata():
    x=pd.read_csv(O/'X216_WITHOUT_FRENCH_COMPONENTS_NO_Y.csv',index_col=0,float_precision='round_trip');y=pd.read_csv(O/'LABELS_FOR_TRAINING_ONLY.csv',index_col=0);fs={p:pd.read_csv(F/f'{p}_FRENCH420_ALIGNED_NO_Y.csv',index_col=0,float_precision='round_trip').reindex(x.index) for p in ['NEXT20','MONTH2_FIRST']};return x,y,fs
def bundle(x,y,fs,cutoff,eval_end):
    tr=x.index<cutoff;ev=(x.index>=cutoff)&(x.index<eval_end);tx=x.loc[tr];ex=x.loc[ev];assert len(tx)>500 and len(ex)>0 and tx.index.max()<cutoff;assert (y.loc[tx.index,'reference_year']<pd.to_datetime(tx.index).year).all()
    cols=tx.columns[tx.notna().mean()>=.8].tolist();cols=[c for c in cols if tx[c].nunique(dropna=True)>1];imp=SimpleImputer(strategy='median');sc=StandardScaler();a=sc.fit_transform(imp.fit_transform(tx[cols]));b=sc.transform(imp.transform(ex[cols]));names=list(cols);pcs={}
    for p in fs:
        ft=fs[p].loc[tx.index];fe=fs[p].loc[ex.index];assert ft.notna().any().all();fi=SimpleImputer(strategy='median');ss=StandardScaler();aa=ss.fit_transform(fi.fit_transform(ft));bb=ss.transform(fi.transform(fe));pc=PCA(n_components=10,svd_solver='randomized',random_state=SEED);aa=pc.fit_transform(aa);bb=pc.transform(bb);pcs[p]=(fi,ss,pc);a=np.column_stack([a,aa]);b=np.column_stack([b,bb]);names.extend([p+'_PC'+str(k+1) for k in range(10)])
    # Center/scale PCs as well for comparable rank tests and linear regularization.
    ps=StandardScaler();a=ps.fit_transform(a);b=ps.transform(b);corr=np.abs(np.corrcoef(a,rowvar=False));assert np.isfinite(a).all() and np.isfinite(b).all()
    stats=dict(imputer=imp,scaler=sc,raw_features=cols,PCA=pcs,post_scaler=ps,all_feature_names=names,train_start=tx.index.min(),train_end=tx.index.max(),eval_start=ex.index.min(),eval_end=ex.index.max(),n_train=len(tx))
    return dict(a=a,b=b,names=names,corr=corr,td=tx.index.to_numpy(),ed=ex.index.to_numpy(),stats=stats,y={t:y.loc[tx.index,'Y' if t=='BINARY' else 'class4'].to_numpy(int) for t in TASKS})
def features(b,combo,task,selector):
    groups=load(O/'GROUPS.json');wanted=sum([groups[g] for g in combo['groups']],[])
    if combo['french']!='NONE':wanted +=[combo['french']+'_PC'+str(k+1) for k in range(10)]
    wantedset=set(wanted);ix=[i for i,n in enumerate(b['names']) if n in wantedset];keep=[]
    for i in ix:
        if not any(b['corr'][i,k]>=.95 for k in keep):keep.append(i)
    if selector!='ALL':
        with warnings.catch_warnings():warnings.simplefilter('ignore');scores=f_classif(b['a'][:,keep],b['y'][task])[0]
        limit=int(selector[3:]);rank=sorted(range(len(keep)),key=lambda j:(-np.nan_to_num(scores[j],nan=-np.inf),keep[j]));chosen=set(rank[:limit]);keep=[i for j,i in enumerate(keep) if j in chosen]
    assert len(keep)>0;return keep
def fit(b,combo,task,selector,algo):
    ix=features(b,combo,task,selector);m=model(algo,task)
    with warnings.catch_warnings():warnings.simplefilter('error',ConvergenceWarning);warnings.filterwarnings('ignore',message='X does not have valid feature names');m.fit(b['a'][:,ix],b['y'][task]);prob=m.predict_proba(b['b'][:,ix])
    assert np.array_equal(m.classes_,np.arange(2 if task=='BINARY' else 4)) and np.isfinite(prob).all() and np.allclose(prob.sum(1),1)
    return prob,m,ix
def metric(y,p,task):
    pr=(p[:,1]>=.5).astype(int) if task=='BINARY' else p.argmax(1);cm=confusion_matrix(y,pr,labels=range(p.shape[1]));r=dict(n=len(y),correct=int((pr==y).sum()),accuracy=accuracy_score(y,pr),BA=balanced_accuracy_score(y,pr),macro_F1=f1_score(y,pr,average='macro',zero_division=0),logloss=log_loss(y,p,labels=np.arange(p.shape[1])),majority_correct=int((y==np.bincount(y,minlength=p.shape[1]).argmax()).sum()))
    if task=='BINARY':r.update(TN=int(cm[0,0]),FP=int(cm[0,1]),FN=int(cm[1,0]),TP=int(cm[1,1]),nonup_recall=float(cm[0,0]/cm[0].sum()),up_prediction=float(pr.mean()),AUC=roc_auc_score(y,p[:,1]))
    else:r.update(direction_accuracy=float(((p[:,2]+p[:,3]>=.5)==(y>=2)).mean()),predicted_classes=np.bincount(pr,minlength=4).tolist())
    return r
def rank(rows,task,baseline):
    if task=='BINARY':return sorted(rows,key=lambda r:(not(r['accuracy']>=baseline['accuracy'] and r['BA']>=baseline['BA']),-r['BA'],-r['accuracy'],r['candidate']))
    return sorted(rows,key=lambda r:(-r['macro_F1'],-r['accuracy'],r['candidate']))
def stage1():
    verify();assert not (O/'STAGE1_COMPLETE.json').exists();x,y,fs=inputdata();combos=load(O/'COMBINATIONS.json');cache={};folds=[];fitcount=0
    for yr in [2016,2018,2020]:
        b=bundle(x,y,fs,f'{yr}-01-01',f'{yr+1}-01-01')
        for task in TASKS:
            for j,c in enumerate(combos):
                prob,m,ix=fit(b,c,task,'ALL','LR');cache.setdefault((task,c['combo']),[]).append((b['ed'],prob));folds.append(dict(task=task,candidate=c['combo'],fold=yr,n_features=len(ix),train_end=b['stats']['train_end'],**metric(y.loc[b['ed'],'Y' if task=='BINARY' else 'class4'].to_numpy(),prob,task)));fitcount+=1
                if j%64==63:print('S1',yr,task,j+1,'/192',flush=True)
    rows=[];selected={};baseid=load(O/'FROZEN_PLAN.json')['baseline_combo']
    for (task,cid),entries in cache.items():
        dates=np.concatenate([r[0] for r in entries]);p=np.concatenate([r[1] for r in entries]);rows.append(dict(task=task,candidate=cid,**metric(y.loc[dates,'Y' if task=='BINARY' else 'class4'].to_numpy(),p,task)))
    for task in TASKS:
        tr=[r for r in rows if r['task']==task];base=next(r for r in tr if r['candidate']==baseid);selected[task]=[r['candidate'] for r in rank([r for r in tr if r['candidate']!=baseid],task,base)[:3]]+[baseid]
    csv(O/'STAGE1_ALL_RESULTS.csv',rows);csv(O/'STAGE1_FOLD_RESULTS.csv',folds);js(O/'STAGE1_SELECTED.json',selected);js(O/'STAGE1_COMPLETE.json',dict(fits=fitcount,selected_sha256=sha(O/'STAGE1_SELECTED.json'),results_sha256=sha(O/'STAGE1_ALL_RESULTS.csv')));print('S1 COMPLETE',fitcount,'fits',selected,flush=True)
def stage2():
    verify();assert not (O/'STAGE2_COMPLETE.json').exists();assert sha(O/'STAGE1_SELECTED.json')==load(O/'STAGE1_COMPLETE.json')['selected_sha256'];x,y,fs=inputdata();combos={r['combo']:r for r in load(O/'COMBINATIONS.json')};sel=load(O/'STAGE1_SELECTED.json');cache={};folds=[];fitcount=0
    for yr in [2021,2022]:
        b=bundle(x,y,fs,f'{yr}-01-01',f'{yr+1}-01-01')
        for task in TASKS:
            for cid in sel[task]:
                for selector in ['ALL','TOP25','TOP50']:
                    for algo in ALGOS:
                        candidate=cid+'__'+selector+'__'+algo;prob,m,ix=fit(b,combos[cid],task,selector,algo);cache.setdefault((task,candidate),[]).append((b['ed'],prob));folds.append(dict(task=task,candidate=candidate,fold=yr,features=len(ix),**metric(y.loc[b['ed'],'Y' if task=='BINARY' else 'class4'].to_numpy(),prob,task)));fitcount+=1
                print('S2',yr,task,cid,'done',flush=True)
    rows=[];finalists=[];baseid=load(O/'FROZEN_PLAN.json')['baseline_combo']
    for (task,candidate),entries in cache.items():
        dates=np.concatenate([r[0] for r in entries]);p=np.concatenate([r[1] for r in entries]);rows.append(dict(task=task,candidate=candidate,**metric(y.loc[dates,'Y' if task=='BINARY' else 'class4'].to_numpy(),p,task)))
    for task in TASKS:
        tr=[r for r in rows if r['task']==task];base=next(r for r in tr if r['candidate']==baseid+'__ALL__LR')
        for algo in ALGOS:
            best=rank([r for r in tr if r['candidate'].endswith('__'+algo)],task,base)[0];cid,selector,_=best['candidate'].split('__');finalists.append(dict(task=task,name=algo,algo=algo,combo=cid,selector=selector,selected_using='2021_2022_only'))
        finalists.append(dict(task=task,name='BASELINE',algo='LR',combo=baseid,selector='ALL',selected_using='PREDECLARED'))
    csv(O/'STAGE2_ALL_RESULTS.csv',rows);csv(O/'STAGE2_FOLD_RESULTS.csv',folds);js(O/'FINALISTS.json',finalists);js(O/'STAGE2_COMPLETE.json',dict(fits=fitcount,finalists_sha256=sha(O/'FINALISTS.json')));print('S2 COMPLETE',fitcount,'fits;14finalists frozen',flush=True)
def monthly(stage):
    verify();assert stage in ['confirm','late'];done=O/f'{stage}_FORECAST_SEAL.json';assert not done.exists();assert sha(O/'FINALISTS.json')==load(O/'STAGE2_COMPLETE.json')['finalists_sha256']
    if stage=='late':assert sha(O/'FINAL_DECISION.json')==load(O/'FINAL_DECISION_SEAL.json')['sha256']
    x,y,fs=inputdata();combos={r['combo']:r for r in load(O/'COMBINATIONS.json')};finalists=load(O/'FINALISTS.json');forecasts=[];logs=[];fits=0;start,end=('2023-01','2023-12') if stage=='confirm' else ('2024-01','2026-10')
    for mo in pd.period_range(start,end,freq='M'):
        cutoff=str(mo)+'-01';b=bundle(x,y,fs,cutoff,str(mo+1)+'-01')
        for spec in finalists:
            task=spec['task'];prob,m,ix=fit(b,combos[spec['combo']],task,spec['selector'],spec['algo']);modelpath=O/'models'/f'{stage}_{mo}_{task}_{spec["name"]}.joblib';joblib.dump(dict(model=m,indices=ix,preprocess=b['stats'],spec=spec),modelpath,compress=3)
            for day,pp in zip(b['ed'],prob):forecasts.append(dict(task=task,name=spec['name'],date=day,year=int(day[:4]),month=str(mo),features=len(ix),prediction=int(pp[1]>=.5) if task=='BINARY' else int(pp.argmax()),**{f'p{k}':float(v) for k,v in enumerate(pp)}))
            prior=np.bincount(b['y'][task],minlength=2 if task=='BINARY' else 4)/len(b['td']);logs.append(dict(month=str(mo),task=task,name=spec['name'],spec=spec,features=[b['names'][i] for i in ix],train_start=b['td'][0],train_end=b['td'][-1],train_n=len(b['td']),eval_dates=b['ed'].tolist(),train_majority=int(prior.argmax()),prior=prior.tolist(),model_path=str(modelpath),model_sha256=sha(modelpath)));fits+=1
        print(stage,str(mo),fits,'fits',flush=True)
    csv(O/f'{stage}_FORECASTS_NO_Y.csv',forecasts);js(O/f'{stage}_MODEL_LOG.json',logs);js(done,dict(fits=fits,forecast_sha256=sha(O/f'{stage}_FORECASTS_NO_Y.csv'),finalists_sha256=sha(O/'FINALISTS.json'),eval_Y_used_in_training=False));print(stage,'FORECASTS SEALED',flush=True)
def scoreconfirm():
    verify();assert sha(O/'confirm_FORECASTS_NO_Y.csv')==load(O/'confirm_FORECAST_SEAL.json')['forecast_sha256'];f=pd.read_csv(O/'confirm_FORECASTS_NO_Y.csv');truth=pd.read_csv(O/'TRUTH_CONFIRM.csv');f=f.merge(truth,on='date',validate='many_to_one');rows=[];decision={}
    for (task,name),g in f.groupby(['task','name']):
        p=g[['p0','p1'] if task=='BINARY' else ['p0','p1','p2','p3']].to_numpy();rows.append(dict(task=task,candidate=name,**metric(g.Y.to_numpy() if task=='BINARY' else g.class4.to_numpy(),p,task)))
    for task in TASKS:
        tr=[r for r in rows if r['task']==task];base=next(r for r in tr if r['candidate']=='BASELINE');eligible=[r for r in tr if r['candidate']!='BASELINE' and r['accuracy']>base['accuracy'] and (r['TN']>=base['TN'] if task=='BINARY' else r['macro_F1']>base['macro_F1'])];decision[task]=rank(eligible,task,base)[0]['candidate'] if eligible else 'BASELINE'
    csv(O/'CONFIRM2023_METRICS.csv',rows);js(O/'FINAL_DECISION.json',dict(selected=decision,selection_end='2023-12-29',no_post2023_selection=True,automatic_adoption=False));js(O/'FINAL_DECISION_SEAL.json',dict(sha256=sha(O/'FINAL_DECISION.json')));print('DECISION FROZEN',decision,flush=True)
def scorelate():
    verify();assert sha(O/'FINAL_DECISION.json')==load(O/'FINAL_DECISION_SEAL.json')['sha256'];assert sha(O/'late_FORECASTS_NO_Y.csv')==load(O/'late_FORECAST_SEAL.json')['forecast_sha256'];f=pd.read_csv(O/'late_FORECASTS_NO_Y.csv').merge(pd.read_csv(O/'TRUTH_LATE.csv'),on='date',validate='many_to_one');rows=[];cms=[];pairs=[];logs={(r['month'],r['task'],r['name']):r for r in load(O/'late_MODEL_LOG.json')}
    for (task,name),g in f.groupby(['task','name']):
        y=g.Y.to_numpy() if task=='BINARY' else g.class4.to_numpy();p=g[['p0','p1'] if task=='BINARY' else ['p0','p1','p2','p3']].to_numpy();f.loc[g.index,'correct']=g.prediction.to_numpy()==y
        for period,mask in [('TOTAL',np.ones(len(g),bool))]+[(str(yr),(g.year==yr).to_numpy()) for yr in [2024,2025,2026]]:
            r=dict(task=task,name=name,period=period,**metric(y[mask],p[mask],task));gg=g.loc[mask];majority=np.array([logs[row.month,task,name]['train_majority'] for row in gg.itertuples()]);r['past_training_majority_accuracy']=float((y[mask]==majority).mean());rows.append(r)
        cm=confusion_matrix(y,g.prediction,labels=range(p.shape[1]));cms.extend(dict(task=task,name=name,actual=i,predicted=j,n=int(cm[i,j])) for i in range(len(cm)) for j in range(len(cm)))
    for task in TASKS:
        base=f[(f.task==task)&(f.name=='BASELINE')].set_index('date')
        for name in ALGOS:
            g=f[(f.task==task)&(f.name==name)];d=g.correct.to_numpy(float)-base.loc[g.date,'correct'].to_numpy(float);rng=np.random.default_rng(SEED);n=len(d);ix=(rng.integers(0,n-19,size=(2000,int(np.ceil(n/20))))[:,:,None]+np.arange(20)).reshape(2000,-1)[:,:n];means=d[ix].mean(1)*100;pairs.append(dict(task=task,name=name,delta_correct=int(d.sum()),delta_pp=float(d.mean()*100),lo95=float(np.quantile(means,.025)),hi95=float(np.quantile(means,.975)),lo12comparison=float(np.quantile(means,.05/24)),hi12comparison=float(np.quantile(means,1-.05/24)),conditional_on_search=True))
    csv(O/'LATE_DAILY_RESULTS.csv',f);csv(O/'LATE_METRICS.csv',rows);csv(O/'CONFUSION_MATRICES.csv',cms);csv(O/'PAIRED_BLOCK_BOOTSTRAP.csv',pairs);js(O/'SCORING_COMPLETE.json',dict(status='PASS',selection_sha256=sha(O/'FINAL_DECISION.json'),late_eval_end=f.date.max(),late_eval_days=int(f.date.nunique()),post2023_selection=False,independent_test=False))
    print(pd.DataFrame(rows).query("period=='TOTAL'")[['task','name','accuracy','BA','macro_F1']].to_string(index=False),flush=True)
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1);{'prepare':prepare,'stage1':stage1,'stage2':stage2,'confirm':lambda:monthly('confirm'),'select':scoreconfirm,'late':lambda:monthly('late'),'score':scorelate}[sys.argv[1]]()
