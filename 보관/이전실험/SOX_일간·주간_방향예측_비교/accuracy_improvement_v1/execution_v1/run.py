import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']: os.environ[k]='1'
import sys,json,hashlib,shutil,platform,warnings
from pathlib import Path
import numpy as np
import pandas as pd
import sklearn,joblib
from sklearn.base import clone
from sklearn.metrics import accuracy_score,balanced_accuracy_score,matthews_corrcoef,recall_score,roc_auc_score,brier_score_loss,log_loss
from threadpoolctl import threadpool_limits

O=Path(__file__).resolve().parent; A=O.parent; D=A.parent; ROOT=D.parent; V=D/'development_revision_v1'
SEED=20261019
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def js(n,x): (O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def csv(n,x): pd.DataFrame(x).to_csv(O/n,index=False,encoding='utf-8-sig')
def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True,default=str).encode()).hexdigest()
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
def check(n,ok,detail=''):
    CHECKS.append(dict(check=n,PASS=bool(ok),detail=str(detail)))
    csv('QC.csv',CHECKS)
    if not ok: raise RuntimeError(n+': '+str(detail))

def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1)
    assert not (O/'PROTECTED_BEFORE.csv').exists(),'Do not rerun or overwrite execution'
    for n in ['models','predictions','logs','inputs']: (O/n).mkdir(exist_ok=True)
    shutil.copy2(A/'EXPERIMENT_PLAN.md',O/'inputs/EXPERIMENT_PLAN_ORIGINAL.md')
    shutil.copy2(A/'CHANGE_PLAN.md',O/'inputs/CHANGE_PLAN_ORIGINAL.md')
    before=snapshot();csv('PROTECTED_BEFORE.csv',before)
    print('Preserved',len(before),'files; specification hash',sha(O/'EXECUTION_SPEC.md'),flush=True)
    seals=[]
    for base in [D,V,A]:
        manifest=base/'OUTPUT_MANIFEST.csv'
        for r in pd.read_csv(manifest).to_dict('records'):
            p=base/r['path'];ok=p.is_file() and sha(p)==r['sha256'] and p.stat().st_size==r['bytes']
            seals.append(dict(manifest=str(manifest.relative_to(ROOT)),path=r['path'],PASS=ok))
    csv('EXISTING_SEAL_CHECK.csv',seals);check('existing_D_revision_diagnosis_seals',all(x['PASS'] for x in seals))
    env=dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__,joblib=joblib.__version__,seed=SEED,threads=1)
    js('ENVIRONMENT.json',env)
    data=pd.read_csv(V/'data/LATEST_EOD_1D.csv',parse_dates=['date','label_end']).set_index('date').sort_index()
    cols=json.loads((V/'config/INFORMATION_SETS.json').read_text())['M1']
    X=data[cols];labels=pd.to_datetime(data.label_available_et,utc=True)
    dev=data[(data.index.year>=2017)&(data.index.year<=2020)]
    check('fixed_1007_dates',len(dev)==1007 and dev.index.is_unique and data.index.max().year==2020)
    check('origins_09_ET',data.origin_et.str.contains('09:00:00').all())
    raw=pd.read_csv(ROOT/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv',comment='#')
    raw=raw[raw.Date<='2020-12-31'].set_index('Date').sort_index()
    truth=(raw.Close>raw.Close.shift()).astype(int)
    check('labels_independent_close',np.array_equal(truth.reindex(data.index.strftime('%Y-%m-%d')),data.Y))
    saved=pd.read_csv(V/'predictions/ALL_PREDICTIONS_WITH_BENCHMARKS.csv',parse_dates=['date'])
    def old(sc,g,alg):
        z=saved[(saved.scenario==sc)&(saved.group==g)&(saved.algorithm==alg)].set_index('date').sort_index()
        check(sc+g+alg+'_dates_labels',z.index.equals(dev.index) and np.array_equal(z.Y,dev.Y));return z
    base=old('C_latest_monthly_expanding','M1','LogisticClassifier')
    best=old('D_latest_monthly_3years','M0','LogisticClassifier')
    momentum=old('C_latest_monthly_expanding','BASELINE','Momentum')
    check('fixed_reference_counts',int(dev.Y.sum())==563 and int((best.prediction==dev.Y).sum())==567)
    csv('inputs/COMPARISON_PREDICTIONS.csv',pd.DataFrame(dict(date=dev.index,Y=dev.Y.to_numpy(),always_up=1,R0=base.prediction.to_numpy(),old_best=best.prediction.to_numpy(),momentum=momentum.prediction.to_numpy())))

    # A1 gate is decided before any model fit or policy evaluation.
    coverage=pd.read_csv(A/'ASIA_RAW_COVERAGE.csv',dtype={'source':str})
    native={}
    for r in coverage.to_dict('records'):
        p=ROOT/r['path'];z=pd.read_csv(p,comment='#');z=z[z.Date<='2020-12-31'].sort_values('Date');native[r['source']]=z.Date.tolist()
    disagreements=set(native['13'])^set(native['23']);audit=[]
    for date in data.index:
        day=date.strftime('%Y-%m-%d')
        for source in ['01','13','23']:
            dates=native[source];present=day in dates
            for feature in [c for c in cols if c.startswith('s'+source+'_')]:
                suffix=feature.split('_',1)[1];width={'ret1':2,'ret5':6,'ret20':21,'vol20':21,'ma20_gap':20,'level':1,'delta1':2,'delta5':6}[suffix]
                pos=dates.index(day) if present else -1;window=dates[max(0,pos-width+1):pos+1] if present else []
                conflict=source in ['13','23'] and bool(set(window)&disagreements)
                reason='native_date_absent_not_proven_holiday' if not present else ('unresolved_cross_source_date_in_window' if conflict else ('historical_special_sessions_unverified' if source=='01' else 'historical_session_and_final_index_gate_unverified'))
                audit.append(dict(date=day,year=date.year,scope='evaluation' if date.year>=2017 else 'training',source=source,feature=feature,native_date_present=present,window_required=width,window_start=window[0] if window else '',window_end=window[-1] if window else '',cross_source_conflict=conflict,same_day_applied=False,fallback=True,reason=reason,original_value=data.loc[date,feature],close_time_basis='regular_market_only_not_full_historical_sessions',actual_vendor_delivery_verified=False))
    au=pd.DataFrame(audit);csv('A1_GATE_ROW_AUDIT.csv',au)
    rates=au.groupby(['scope','source','year','feature','reason'],dropna=False).agg(rows=('fallback','size'),applied=('same_day_applied','sum'),fallback=('fallback','sum')).reset_index()
    rates['same_day_rate']=rates.applied/rates.rows;rates['fallback_rate']=rates.fallback/rates.rows;csv('A1_APPLICATION_RATES_BY_REASON.csv',rates)
    totals=au.groupby(['scope','source','year','feature']).agg(rows=('fallback','size'),applied=('same_day_applied','sum'),fallback=('fallback','sum')).reset_index();totals['same_day_rate']=totals.applied/totals.rows;totals['fallback_rate']=totals.fallback/totals.rows;csv('A1_APPLICATION_RATES.csv',totals)
    (O/'A1_GATE.md').write_text('# A1: NOT_EXECUTED\n\n원계획의 미해결 gate를 그대로 적용했다. 당일 정보 적용0%, 기존 과거값 fallback100%. 이는 R0와 동일한 후보를 실행했다는 뜻이 아니며 A1 성능은 N/A다. RAW를 변경하지 않았다. 원천 관측일 부재는 휴장 증거가 아니다. 계산창 내 13/23 원천 날짜 불일치와 한국 특별 세션 미확인을 행별로 보존했다. 일반 시장 마감+2시간의 조건부 가용성과 과거 벤더 전달 검증은 별개이며 후자는 없음.\n\n기존 근거: ../ASIA_CALENDAR_LIMITATIONS.md, ../ASIA_SESSION_DISCREPANCIES.csv, ../SOURCES.md. KRX 일반 거래 안내 https://global.krx.co.kr/contents/GLB/01/0109/0109000000/guide_to_trading_in_the_korean_stock_market.pdf ; TWSE 일반 거래 안내 https://www.twse.com.tw/en/about/company/guide.html . 일반 안내는 전체 역사적 특별일/지수 확정시각 증거가 아니다.\n',encoding='utf-8')
    print('A1 gated out; maximum new fit attempts 126',flush=True)

    foldmeta={f['fold']:f for f in json.loads((V/'logs/FOLD_DETAILS.json').read_text()) if f['scenario']=='C_latest_monthly_expanding' and f['group']=='M1' and f['algorithm']=='LogisticClassifier'}
    models={}; provenance=[];fits=[];blockcache={};selection=[];preds=[];innerpred=[];cacheaudit=[]
    def trainset(month):
        test=data[data.index.to_period('M')==month];assert len(test)
        origin=pd.to_datetime(test.iloc[0].origin_et,utc=True)
        tr=data[(data.index<test.index[0])&(labels<origin)]
        assert len(tr)>=500 and tr.Y.nunique()==2 and (pd.to_datetime(tr.label_available_et,utc=True)<origin).all()
        return tr,test,origin
    template=None
    for month,f in sorted(foldmeta.items()):
        period=pd.Period(month,'M');tr,test,origin=trainset(period);m=joblib.load(V/f['model_path'])
        p=m.named_steps['model'].get_params();imp=m.named_steps['impute'];scale=m.named_steps['scale']
        med=np.nanmedian(tr[cols].to_numpy(),axis=0);med=np.nan_to_num(med,nan=0);filled=np.where(np.isnan(tr[cols]),med,tr[cols])
        pp=m.predict_proba(test[cols])[:,1];sp=base.loc[test.index].probability.to_numpy()
        ok=(list(m.classes_)==[0,1] and list(m.feature_names_in_)==cols and p['C']==1 and p['class_weight'] is None and p['max_iter']==2000 and p['random_state']==SEED and len(tr)==f['train_n'] and str(tr.index[-1].date())==f['train_end'] and str(tr.index[0].date())==f['train_start'] and str(tr.label_end.max().date())==f['max_train_label_end'] and np.allclose(imp.statistics_,med,rtol=1e-10,atol=1e-10) and np.allclose(scale.mean_,filled.mean(axis=0),rtol=1e-10,atol=1e-10) and np.allclose(scale.var_,filled.var(axis=0),rtol=1e-10,atol=1e-10) and np.allclose(pp,sp,rtol=0,atol=1e-9) and np.array_equal((pp>=.5).astype(int),base.loc[test.index].prediction))
        cacheaudit.append(dict(month=month,path=f['model_path'],train_n=len(tr),train_start=str(tr.index[0]),train_end=str(tr.index[-1]),max_probability_error=float(np.max(abs(pp-sp))),PASS=ok,parameters=p))
        check('cache_'+month,ok);models[(1.,period)]=m;template=m
    js('CACHE_REUSE_AUDIT.json',cacheaudit);js('ESTIMATOR_PARAMETERS.json',template.get_params(deep=True))
    print('Validated all 48 parent models and 1007 saved probabilities',flush=True)
    def getmodel(c,month):
        key=(float(c),month)
        if key in models:return models[key]
        tr,test,origin=trainset(month);m=clone(template).set_params(model__C=float(c))
        category='R0_2016' if c==1 else 'C_alternative'
        assert len(fits)<126 and sum(r['category']==category for r in fits)<(12 if c==1 else 114)
        row=dict(attempt=len(fits)+1,C=c,month=str(month),category=category,train_n=len(tr),train_start=str(tr.index[0].date()),train_end=str(tr.index[-1].date()),max_label_available=str(pd.to_datetime(tr.label_available_et,utc=True).max()),origin=str(origin),status='STARTED')
        row['training_XY_sha256']=hashlib.sha256(pd.util.hash_pandas_object(tr[cols+['Y']],index=True).values.tobytes()).hexdigest()
        row['cache_key']=digest(dict(origin=str(origin),training=row['training_XY_sha256'],policy='original_M1_latest',parameters=m.get_params(),environment=env))
        fits.append(row);csv('logs/FIT_ATTEMPTS.csv',fits)
        try:
            with warnings.catch_warnings(record=True) as ws:
                warnings.simplefilter('always');m.fit(tr[cols],tr.Y)
            row['warnings']=' | '.join(str(w.message) for w in ws)
            assert m.named_steps['model'].n_iter_.max()<m.named_steps['model'].max_iter,'Convergence limit reached'
            path=O/f'models/C{c:g}_{month}.joblib';joblib.dump(m,path);row['model_path']=str(path.relative_to(O));row['sha256']=sha(path);row['status']='PASS'
        except Exception as e:
            row['status']='FAIL';row['error']=repr(e);csv('logs/FIT_ATTEMPTS.csv',fits);raise
        csv('logs/FIT_ATTEMPTS.csv',fits);models[key]=m
        print('Fit',len(fits),category,c,str(month),flush=True);return m
    def block(c,start,outerorigin):
        key=(float(c),start)
        if key not in blockcache:
            end=(start+6).start_time;val=data[(data.index>=start.start_time)&(data.index<end)]
            tr,_,origin=trainset(start)
            assert len(val)>=80 and len(tr)>=500 and tr.Y.nunique()==2
            m=getmodel(c,start);p=m.predict_proba(val[cols])[:,1]
            z=pd.DataFrame(dict(date=val.index,Y=val.Y.to_numpy(),probability=p,label_available=val.label_available_et.to_numpy()))
            blockcache[key]=z
            for r in z.to_dict('records'):innerpred.append(dict(C=c,block_start=str(start),block_end=str(start+6),**r))
        z=blockcache[key];z=z[pd.to_datetime(z.label_available,utc=True)<outerorigin]
        assert len(z)>=80
        return z
    for month in pd.period_range('2017-01','2020-12',freq='M'):
        tr,test,origin=trainset(month);starts=[month-12,month-6];scores={};fallback=False
        try:
            inn={c:pd.concat([block(c,s,origin) for s in starts],ignore_index=True) for c in [.01,.1,1.]}
            for c,z in inn.items():scores[c]=int(((z.probability>=.5).astype(int)==z.Y).sum())
            csel=min(scores,key=lambda c:(-scores[c],c!=1.,c))
            z=inn[1.];tscores={t:int(((z.probability>=t).astype(int)==z.Y).sum()) for t in [.45,.5,.55]}
            tsel=min(tscores,key=lambda t:(-tscores[t],t!=.5,abs(t-.5),t))
            in_n=len(z)
        except AssertionError as e:
            # Only sample sufficiency may fall back; model/cache errors are fatal.
            raise RuntimeError('Inner validation condition failed; no silent fallback of implementation error') from e
        selection.append(dict(month=str(month),selected_C=csel,selected_threshold=tsel,inner_n=in_n,C_scores=json.dumps(scores),threshold_scores=json.dumps(tscores),fallback=fallback,origin=str(origin),inner_max_label_available=str(pd.to_datetime(z.label_available,utc=True).max()),inner_blocks=','.join(map(str,starts))))
        for policy,c,t in [('R0',1.,.5),('C1',csel,.5),('T1',1.,tsel)]:
            prob=base.loc[test.index].probability.to_numpy() if c==1 else getmodel(c,month).predict_proba(test[cols])[:,1]
            for date,y,p in zip(test.index,test.Y,prob):preds.append(dict(policy=policy,date=str(date.date()),Y=int(y),probability=float(p),prediction=int(p>=t),threshold=t,C=c,month=str(month),training_up_probability=float(tr.Y.mean())))
        csv('logs/MONTHLY_SELECTION_HISTORY.csv',selection);csv('predictions/EXTERNAL_PREDICTIONS.csv',preds)
    csv('predictions/INTERNAL_FIXED_BLOCK_PREDICTIONS.csv',innerpred)
    check('all_fit_attempts_success',all(r['status']=='PASS' for r in fits));check('fit_budget',len(fits)<=126)
    check('inner_labels_mature',all(pd.Timestamp(r['inner_max_label_available'])<pd.Timestamp(r['origin']) for r in selection))
    result=pd.DataFrame(preds);metrics=[];comparisons=[];distributions=[]
    refs=dict(always_up=np.ones(len(dev),dtype=int),R0=base.prediction.to_numpy(),old_best=best.prediction.to_numpy(),momentum=momentum.prediction.to_numpy())
    for policy,w in result.groupby('policy',sort=False):
        check(policy+'_all_dates_Y',w.date.tolist()==dev.index.strftime('%Y-%m-%d').tolist() and np.array_equal(w.Y,dev.Y))
        check(policy+'_thresholds',np.array_equal(w.prediction,(w.probability>=w.threshold).astype(int)))
        for year in ['ALL',2017,2018,2019,2020]:
            mask=np.ones(len(dev),bool) if year=='ALL' else dev.index.year==year
            v=w.loc[mask];y=v.Y.to_numpy();p=v.probability.to_numpy();pred=v.prediction.to_numpy();q=v.training_up_probability.to_numpy();n=len(v);correct=(pred==y).astype(int)
            rng=np.random.default_rng(SEED);nb=int(np.ceil(n/20));starts=rng.integers(0,n-20+1,size=(2000,nb));idx=(starts[:,:,None]+np.arange(20)).reshape(2000,-1)[:,:n]
            row=dict(policy=policy,period=year,n=n,correct=int(correct.sum()),accuracy=accuracy_score(y,pred),recall_nonup=recall_score(y,pred,pos_label=0),recall_up=recall_score(y,pred,pos_label=1),BA=balanced_accuracy_score(y,pred),MCC=matthews_corrcoef(y,pred),AUC=roc_auc_score(y,p),Brier=brier_score_loss(y,p),Log_loss=log_loss(y,p,labels=[0,1]),q_Brier=brier_score_loss(y,q),q_Log_loss=log_loss(y,q,labels=[0,1]),predicted_up_rate=float(pred.mean()))
            for name,ref in refs.items():
                d=correct-(ref[mask]==y).astype(int);ci=np.quantile(d[idx].mean(axis=1)*100,[.025,.975])
                row[name+'_delta_correct']=int(d.sum());row[name+'_delta_pp']=float(d.mean()*100);row['beats_'+name]=bool(d.sum()>0)
                comparisons.append(dict(policy=policy,period=year,reference=name,n=n,delta_correct=int(d.sum()),delta_pp=float(d.mean()*100),CI95_low_pp=ci[0],CI95_high_pp=ci[1],block=20,replicates=2000,seed=SEED))
            metrics.append(row)
            for cl in [0,1]:
                cp=p[y==cl];distributions.append(dict(policy=policy,period=year,actual_class=cl,n=len(cp),mean=cp.mean(),std=cp.std(),q05=np.quantile(cp,.05),q25=np.quantile(cp,.25),median=np.median(cp),q75=np.quantile(cp,.75),q95=np.quantile(cp,.95),fraction_045_055=((cp>=.45)&(cp<=.55)).mean()))
    csv('METRICS.csv',metrics);csv('PAIRED_BLOCK_BOOTSTRAP.csv',comparisons);csv('PROBABILITY_DISTRIBUTIONS.csv',distributions)
    csv('CANDIDATE_STATUS.csv',[dict(policy=p,status='COMPLETED' if p!='A1' else 'NOT_EXECUTED_GATE',new_fits=(sum(x['category']=='R0_2016' for x in fits) if p=='R0' else sum(x['category']=='C_alternative' for x in fits) if p=='C1' else 0)) for p in ['R0','A1','C1','T1']])
    # Independent disk reload reproduces all newly generated monthly external C1 probabilities.
    newerrors=[]
    for r in fits:
        m=joblib.load(O/r['model_path']);month=pd.Period(r['month'],'M');tr,_,_=trainset(month)
        check('new_model_classes_'+r['cache_key'],list(m.classes_)==[0,1])
        check('new_model_training_preprocessing_'+r['cache_key'],np.allclose(m.named_steps['impute'].statistics_,np.nan_to_num(np.nanmedian(tr[cols],axis=0),nan=0),rtol=1e-10,atol=1e-10))
        used=result[(result.policy=='C1')&(result.month==str(month))&(result.C==r['C'])]
        if len(used):
            error=float(np.max(abs(m.predict_proba(data.loc[pd.to_datetime(used.date),cols])[:,1]-used.probability)))
            newerrors.append(dict(month=str(month),C=r['C'],max_error=error));check('new_disk_predictions_'+str(month),error<=1e-9)
    csv('NEW_DISK_PREDICTION_CHECK.csv',newerrors)
    after=snapshot();beforemap={r['path']:r for r in before};aftermap={r['path']:r for r in after}
    changed=[p for p,r in beforemap.items() if p not in aftermap or r!=aftermap[p]];added=sorted(set(aftermap)-set(beforemap))
    js('PRESERVATION_CHECK.json',dict(protected_before=len(before),protected_after=len(after),changed=changed,added_outside_execution=added,excluded_runtime_directories=['.git','.venv','.venv_W1']))
    check('preexisting_files_unchanged',not changed);check('no_new_files_outside_execution',not added)
    js('RUN_SUMMARY.json',dict(status='PASS',new_fit_attempts=len(fits),fit_failures=sum(r['status']!='PASS' for r in fits),R0_fits=sum(r['category']=='R0_2016' for r in fits),C1_fits=sum(r['category']=='C_alternative' for r in fits),A1_fits=0,T1_fits=0,budget=126,A1_status='NOT_EXECUTED_GATE',fallback_months=sum(r['fallback'] for r in selection),old_files_changed=len(changed),QC_checks=len(CHECKS),plan_sha256=sha(A/'EXPERIMENT_PLAN.md'),spec_sha256=sha(O/'EXECUTION_SPEC.md')))
    print('EXECUTION COMPLETE',len(fits),'new fits; preservation PASS',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:
        js('EXECUTION_FAILURE.json',dict(status='FAIL',error=repr(e)));raise
