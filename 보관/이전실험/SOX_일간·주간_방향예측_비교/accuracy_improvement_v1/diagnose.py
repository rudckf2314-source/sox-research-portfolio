"""Read-only prediction diagnostics. No fitting, prediction generation, or threshold search."""
import os,sys,json,hashlib,ast
from pathlib import Path
import numpy as np,pandas as pd,joblib
from sklearn.metrics import accuracy_score,balanced_accuracy_score,matthews_corrcoef,recall_score,roc_auc_score,brier_score_loss,log_loss,confusion_matrix
from threadpoolctl import threadpool_limits

O=Path(__file__).resolve().parent;D=O.parent;ROOT=D.parent
class TrainSelector:
    """Unpickling state only: never used to transform or fit a model."""
    pass
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def csv(n,x):pd.DataFrame(x).to_csv(O/n,index=False,encoding='utf-8-sig')
def js(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def snapshot():
    rows=[]
    for base,ds,fs in os.walk(ROOT,followlinks=False):
        ds[:]=[n for n in ds if n not in {'.git','.venv','.venv_W1'} and not (Path(base)/n).resolve().is_relative_to(O)]
        for n in fs:
            p=Path(base)/n
            if p.is_symlink():raise RuntimeError('Unexpected link: '+str(p))
            rows.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    csv('PROTECTED_BEFORE.csv',rows);return rows
def qmetrics(y,p):
    return {'auc':roc_auc_score(y,p) if len(set(y))==2 else np.nan,'brier':brier_score_loss(y,p),'log_loss':log_loss(y,np.clip(p,1e-15,1-1e-15),labels=[0,1])}
def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1)
    assert not (O/'PROTECTED_BEFORE.csv').exists(),'Existing diagnostic run: do not overwrite'
    protected=snapshot();print('Protected',len(protected),'files',flush=True)
    checks=[]
    def check(n,ok,detail=''):checks.append({'check':n,'PASS':bool(ok),'detail':str(detail)})
    tables={h:pd.read_csv(D/f'data/DEV_{h}.csv',parse_dates=['date','label_end']).set_index('date') for h in ['1D','1W']}
    rev=D/'development_revision_v1'
    revtables={k:pd.read_csv(rev/f'data/{n}.csv',parse_dates=['date','label_end']).set_index('date') for k,n in [('old','OLD_LAG_1D'),('latest','LATEST_EOD_1D')]}
    scenarios=json.loads((rev/'config/SCENARIOS.json').read_text(encoding='utf-8'))
    initial=pd.read_csv(D/'predictions/DEVELOPMENT_PREDICTIONS.csv');initial['study']='initial';initial['scenario']='annual_expanding_inner_selected';initial['is_regression']=False;initial['score']=initial.probability
    revised=pd.read_csv(rev/'predictions/ALL_PREDICTIONS_WITH_BENCHMARKS.csv');revised['study']='revision';revised['horizon']='1D';revised['is_regression']=revised.algorithm.str.contains('Regressor')|revised.algorithm.isin(['TrainingMeanReturn','ZeroReturn']);revised['threshold']=np.where(revised.is_regression,0,.5)
    records=pd.concat([initial,revised],ignore_index=True);records['date']=records.date.astype(str);records['year']=records.date.str[:4].astype(int)
    keycols=['study','horizon','scenario','group','algorithm']
    check('prediction_keys_unique',not records.duplicated(keycols+['date']).any())
    check('no_post2020_evaluation',records.date.min()>='2017-01-01' and records.date.max()<='2020-12-31')
    # Rebuild mature training labels and the training-frequency probability benchmark from metadata.
    trainrows=[];maturity=[];classmeta=[]
    folds0=json.loads((D/'logs/FOLD_DETAILS.json').read_text(encoding='utf-8'));folds1=json.loads((rev/'logs/FOLD_DETAILS.json').read_text(encoding='utf-8'))
    qcache={}
    for study,folds in [('initial',folds0),('revision',folds1)]:
        for f in folds:
            h=f.get('horizon','1D');sc=f.get('scenario','annual_expanding_inner_selected');fold=str(f.get('fold',f.get('outer_year')));cachekey=(study,h,sc,fold)
            data=tables[h] if study=='initial' else revtables[scenarios[sc]['timing']]
            if cachekey not in qcache:
                test=data[(data.index.year==int(fold))] if study=='initial' or scenarios.get(sc,{}).get('update')=='annual' else data[data.index.to_period('M').astype(str)==fold]
                origin=pd.to_datetime(test.iloc[0].origin_et,utc=True)
                tr=data[(data.index<test.index.min())&(pd.to_datetime(data.label_available_et,utc=True)<origin)]
                if study=='revision' and scenarios[sc]['window']=='3_calendar_years':tr=tr[tr.index>=test.index.min()-pd.DateOffset(years=3)]
                qcache[cachekey]=(tr,test,float(tr.Y.mean()))
                for date in test.index:trainrows.append({'study':study,'horizon':h,'scenario':sc,'date':str(date.date()),'train_up_probability':float(tr.Y.mean()),'train_n':len(tr),'fold':fold})
            tr,test,q=qcache[cachekey]
            ok=len(tr)==f['train_n'] and str(tr.index.max().date())==f['train_end'] and tr.label_end.max()<test.index.min() and (pd.to_datetime(tr.label_available_et,utc=True)<pd.to_datetime(test.iloc[0].origin_et,utc=True)).all()
            check(f'{study}_{h}_{sc}_{fold}_{f["group"]}_{f["algorithm"]}_maturity',ok)
            maturity.append({'study':study,'horizon':h,'scenario':sc,'fold':fold,'group':f['group'],'algorithm':f['algorithm'],'recomputed_train_n':len(tr),'recorded_train_n':f['train_n'],'max_train_label_end':str(tr.label_end.max().date()),'first_origin_et':str(test.iloc[0].origin_et),'PASS':bool(ok)})
            # Read existing model metadata only. No .fit/.predict/.predict_proba call.
            if study=='initial' or 'Classifier' in f['algorithm']:
                path=(D if study=='initial' else rev)/f['model_path'];m=joblib.load(path);classes=list(np.asarray(m.classes_).astype(int));okclasses=classes==[0,1]
                classmeta.append({'study':study,'path':str(path.relative_to(ROOT)),'classes':str(classes),'positive_probability_column':1,'PASS':okclasses});check(str(path.relative_to(ROOT))+'_positive_column',okclasses)
    qdf=pd.DataFrame(trainrows);check('training_benchmark_keys_unique',not qdf.duplicated(['study','horizon','scenario','date']).any())
    records=records.merge(qdf,on=['study','horizon','scenario','date'],how='left',validate='many_to_one',suffixes=('','_recomputed'))
    check('training_benchmark_complete',records.train_up_probability.notna().all())
    # Independent Y construction from source Close, with current date range capped before derived targets.
    raw=pd.read_csv(ROOT/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv',comment='#');raw=raw[raw.Date<='2020-12-31'];raw.index=pd.to_datetime(raw.Date);close=raw.Close
    ret1=100*(close/close.shift(1)-1);gg=close.groupby(close.index.to_period('W-FRI'));wc=gg.last();retw=pd.Series((100*(wc/wc.shift(1)-1)).to_numpy(),index=pd.DatetimeIndex(gg.apply(lambda x:x.index[0]).to_numpy()))
    for h,ret in [('1D',ret1),('1W',retw)]:
        v=records[records.horizon==h];truth=(ret.reindex(pd.DatetimeIndex(v.date))>0).astype(int).to_numpy();check(h+'_all_saved_labels_match_close_direction',np.array_equal(truth,v.Y))
    distributions=[];result=[]
    for keys,v in records.groupby(keycols,sort=True):
        study,h,sc,g,a=keys;v=v.sort_values('date');base=records[(records.study==study)&(records.horizon==h)&(records.scenario==sc)&(records.algorithm=='Majority')].sort_values('date')
        check('_'.join(keys)+'_same_dates_as_baseline',np.array_equal(v.date.to_numpy(),base.date.to_numpy()))
        check('_'.join(keys)+'_same_labels_as_baseline',np.array_equal(v.Y.to_numpy(),base.Y.to_numpy()))
        reg=bool(v.is_regression.iloc[0]);prob_ok=(not reg) and v.probability.notna().all() and v.probability.between(0,1).all()
        if not reg:check('_'.join(keys)+'_probability_valid',prob_ok)
        expected=(v.score>0).astype(int) if reg else (v.probability>=v.threshold).astype(int)
        check('_'.join(keys)+'_saved_decisions_match_threshold',np.array_equal(expected,v.prediction))
        if a=='Majority':check('_'.join(keys)+'_probability_matches_recomputed_training_frequency',np.allclose(v.probability,v.train_up_probability,rtol=1e-12,atol=1e-12))
        annual_auc=[]
        if prob_ok:
            for year,yv in v.groupby('year'):
                annual_auc.append((roc_auc_score(yv.Y,yv.probability),int((yv.Y==0).sum())*int((yv.Y==1).sum())))
        strat_auc=sum(x*w for x,w in annual_auc)/sum(w for x,w in annual_auc) if annual_auc else np.nan
        for period in ['ALL',2017,2018,2019,2020]:
            w=v if period=='ALL' else v[v.year==period];b=base if period=='ALL' else base[base.year==period]
            y=w.Y.to_numpy();pred=w.prediction.to_numpy();q=w.train_up_probability.to_numpy();qm=qmetrics(y,q);tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel();acc=accuracy_score(y,pred);bacc=accuracy_score(b.Y,b.prediction)
            r=dict(zip(keycols,keys));r.update({'period':period,'n':len(w),'n_nonup':int((y==0).sum()),'n_up':int((y==1).sum()),'is_regression':reg,'is_M3_alias':g=='M3','accuracy':acc,'same_date_majority_accuracy':bacc,'accuracy_gain_pp':100*(acc-bacc),'predicted_up_fraction':pred.mean(),'recall_up':recall_score(y,pred,pos_label=1,zero_division=0),'recall_nonup':recall_score(y,pred,pos_label=0,zero_division=0),'balanced_accuracy':balanced_accuracy_score(y,pred),'MCC':matthews_corrcoef(y,pred),'TN':int(tn),'FP':int(fp),'FN':int(fn),'TP':int(tp),'threshold_min':w.threshold.min(),'threshold_max':w.threshold.max(),'training_frequency_brier':qm['brier'],'training_frequency_log_loss':qm['log_loss'],'training_frequency_auc':qm['auc'],'probability_auc':np.nan,'regression_score_auc':roc_auc_score(y,w.score) if reg else np.nan,'year_stratified_auc_pair_weighted':strat_auc if period=='ALL' else np.nan})
            if prob_ok:
                prob=w.probability.to_numpy();pm=qmetrics(y,prob);r.update({'probability_auc':pm['auc'],'brier':pm['brier'],'log_loss':pm['log_loss'],'brier_gain_vs_training_frequency':qm['brier']-pm['brier'],'log_loss_gain_vs_training_frequency':qm['log_loss']-pm['log_loss'],'probability_mean':prob.mean(),'probability_std':prob.std(ddof=0),'probability_near_05_fraction':np.mean(np.abs(prob-.5)<=.05),'probability_04_to_06_fraction':np.mean((prob>=.4)&(prob<=.6)),'probability_extreme_fraction':np.mean((prob<=.1)|(prob>=.9))})
                for label in [0,1]:
                    pp=prob[y==label];pfx=f'actual_{label}_p_';r[pfx+'mean']=pp.mean();r[pfx+'std']=pp.std(ddof=0)
                    for quant in [.05,.25,.5,.75,.95]:r[pfx+f'q{int(quant*100):02d}']=np.quantile(pp,quant)
                    edges=np.array([0,.1,.2,.3,.4,.45,.5,.55,.6,.7,.8,.9,1]);hist,_=np.histogram(pp,bins=edges)
                    for lo,hi,count in zip(edges[:-1],edges[1:],hist):distributions.append({**dict(zip(keycols,keys)),'period':period,'actual_Y':label,'bin_lower':lo,'bin_upper':hi,'last_bin_right_closed':hi==1,'count':int(count),'class_n':len(pp),'class_fraction':count/len(pp)})
                r['class_probability_mean_gap_up_minus_nonup']=r['actual_1_p_mean']-r['actual_0_p_mean']
            result.append(r)
    csv('PREDICTION_DIAGNOSTICS.csv',result);csv('PROBABILITY_DISTRIBUTIONS.csv',distributions);csv('RECOMPUTED_TRAINING_BASELINES.csv',qdf);csv('TRAIN_LABEL_MATURITY_AUDIT.csv',maturity);csv('POSITIVE_CLASS_METADATA.csv',classmeta)
    # Source-level feature duplicate audit; algebraic combinations are distinguished from new information.
    dictionary=pd.read_csv(D/'FEATURE_DICTIONARY.csv');csv('EXISTING_FEATURE_AUDIT.csv',dictionary)
    examples=[];coverage=[]
    for code in ['01','13','23']:
        path=next((ROOT/'data/raw').glob(f'{code}_*/*RAW*.csv'));x=pd.read_csv(path,comment='#');dates=pd.DatetimeIndex(pd.to_datetime(x.Date));dates=dates[dates<='2020-12-31'];dev=pd.DatetimeIndex(tables['1D'].loc[tables['1D'].index.year>=2017].index)
        coverage.append({'source':code,'path':str(path.relative_to(ROOT)),'dev_dates':len(dev),'same_local_date_observation_count':int(dev.isin(dates).sum()),'same_local_date_absent_count':int((~dev.isin(dates)).sum()),'absence_proves_exchange_holiday':False})
        zname='Asia/Seoul' if code=='01' else 'Asia/Taipei';hour,minute=(15,30) if code=='01' else (13,30)
        for date in ['2017-07-10','2017-12-04','2018-10-10','2017-10-04','2020-12-03']:
            t=pd.Timestamp(date);prev=dates[dates<t].max();same=t in dates;closed=t.tz_localize(zname)+pd.Timedelta(hours=hour,minutes=minute)
            if code=='01' and date=='2020-12-03':closed=t.tz_localize(zname)+pd.Timedelta(hours=16,minutes=30)
            examples.append({'source':code,'US_prediction_date':date,'origin_ET':str(t.tz_localize('America/New_York')+pd.Timedelta(hours=9)),'old_latest_policy_source_date':str(prev.date()),'proposed_same_date_source_date':date if same else 'NO_SAME_DATE_ROW','regular_or_example_close_local':str(closed),'market_close_ET':str(closed.tz_convert('America/New_York')),'proposed_modeled_available_ET':str(closed.tz_convert('America/New_York')+pd.Timedelta(hours=2)),'same_date_raw_exists':same,'note':'2020-12-03 KRX special time requires source evidence; otherwise regular session example; no historical vendor delivery proof'})
    csv('ASIA_ALIGNMENT_EXAMPLES.csv',examples);csv('ASIA_RAW_COVERAGE.csv',coverage)
    # Verify old sealed study files; the new diagnostics directory is intentionally outside old snapshots.
    for folder in [D,rev]:
        m=folder/'OUTPUT_MANIFEST.csv';check(str(m)+'_seal',sha(m)==m.with_suffix('.sha256').read_text(encoding='utf-8-sig').split()[0])
        bad=[]
        for row in pd.read_csv(m).itertuples():
            if not (folder/row.path).is_file() or sha(folder/row.path)!=row.sha256:bad.append(row.path)
        check(str(m)+'_all_entries_current',not bad,bad)
    js('DIRECT_AUDIT_CHECKS.json',checks)
    out=pd.DataFrame(result);p=out[(out.period=='ALL')&(out.group!='BASELINE')&(~out.is_M3_alias)]
    summary={'candidate_series_including_baselines_aliases':len(records.groupby(keycols)),'diagnostic_rows':len(out),'classification_1D_candidates':len(p[(p.horizon=='1D')&(~p.is_regression)]),'classifiers_1D_brier_better_than_train_frequency':int(((p.horizon=='1D')&(~p.is_regression)&(p.brier_gain_vs_training_frequency>0)).sum()),'classifiers_1D_logloss_better_than_train_frequency':int(((p.horizon=='1D')&(~p.is_regression)&(p.log_loss_gain_vs_training_frequency>0)).sum()),'classifiers_1D_auc_above_05':int(((p.horizon=='1D')&(~p.is_regression)&(p.probability_auc>.5)).sum()),'best_1D_accuracy':p[p.horizon=='1D'].sort_values('accuracy',ascending=False).iloc[0].to_dict(),'model_class_metadata_checked':len(classmeta),'direct_checks':len(checks),'failed':[c for c in checks if not c['PASS']],'new_model_fits':0,'threshold_searches':0,'post2020_performance_evaluations':0}
    js('DIAGNOSTIC_SUMMARY.json',summary);print(json.dumps(summary,ensure_ascii=False,default=str),flush=True)
if __name__=='__main__':main()
