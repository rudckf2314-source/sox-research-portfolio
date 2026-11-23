"""Read-only investigation after the failed stage-1 gate. Does not clear the gate."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import math,json,bisect,statistics,datetime,sys
from zoneinfo import ZoneInfo
from pathlib import Path
import numpy as np,pandas as pd,joblib
from threadpoolctl import threadpool_limits
from audit_kr_independent import O,P,A,D,ROOT,V,K,S,sha,native,calc,eq,savecsv,savejson,snapshot
def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1);I=O/'impact_assessment';I.mkdir(exist_ok=True)
    assert json.loads((S/'GATE_RESULT.json').read_text())['status']=='FAIL','Only investigate the preserved failed gate'
    assert not (I/'ASSESSMENT_SUMMARY.json').exists(),'Do not overwrite assessment'
    old=pd.read_csv(V/'data/LATEST_EOD_1D.csv',parse_dates=['date','label_end']).set_index('date').sort_index();kr=pd.read_csv(K/'data/KR_ONLY_1D.csv',parse_dates=['date','label_end']).set_index('date').sort_index();cols=json.loads((V/'config/INFORMATION_SETS.json').read_text())['M1'];targets=[f for f in cols if f.startswith('s01_')];others=[f for f in cols if f not in targets]
    dic=pd.read_csv(D/'FEATURE_DICTIONARY.csv');sessions=pd.read_csv(D/'inputs/US_MARKET_SESSIONS_DEV.csv').session_date.tolist();lin=pd.read_csv(V/'data/LATEST_FEATURE_LINEAGE.csv');lin=lin[lin.feature.isin(cols)].set_index(['date','feature']);frozen=pd.read_csv(P/'A1_PARTIAL_ROW_REVIEW.csv',dtype={'source':str},parse_dates=['date']);frozen=frozen[frozen.source=='01'].set_index(['date','feature']);mismatches=[];mappings=[];direct=[];sourcecache={};independent_checks=[]
    def ck(name,ok,detail=''):
        independent_checks.append(dict(check=name,PASS=bool(ok),detail=str(detail)))
        if not ok:savecsv(I/'ADDITIONAL_CHECKS.csv',independent_checks);raise RuntimeError(name)
    for st,part in dic[dic.feature.isin(cols)].groupby('source_type'):
        source=f'{int(st):02d}';path=ROOT/part.iloc[0].source_path;dd,vv,rr=native(path);av=[sessions[bisect.bisect_right(sessions,d)] if bisect.bisect_right(sessions,d)<len(sessions) else '9999-12-31' for d in dd];sourcecache[source]=(dd,vv,rr,av)
        # Reproduce the observed single-key tie selection solely to diagnose the implementation.
        use=[i for i,a in enumerate(av) if a!='9999-12-31'];events=pd.DataFrame(dict(available_date=pd.to_datetime([av[i] for i in use]),source_date=pd.to_datetime([dd[i] for i in use])));legacy=events.sort_values('available_date').drop_duplicates('available_date',keep='last').set_index('available_date').source_date
        for f in part.feature:
            key=f.split('_',1)[1];computed=[calc(vv,j,key) for j in range(len(dd))];maxerr=0;legacy_bad=[];future=[];older=0;diffvalues=0
            for date in old.index:
                day=str(date.date());j=bisect.bisect_right(av,day)-1;actual=float(old.loc[date,f]);latest_value=computed[j] if j>=0 and (date.date()-datetime.date.fromisoformat(dd[j])).days<=10 else math.nan;record=None
                if math.isfinite(actual):
                    record=lin.loc[(day,f)];selected=record.source_date;idx=bisect.bisect_left(dd,selected);native_value=computed[idx]
                    if not eq(native_value,actual):legacy_bad.append(day)
                    if selected>=day or av[idx]>day:future.append(day)
                    if math.isfinite(native_value):maxerr=max(maxerr,abs(native_value-actual))
                    if selected<dd[j]:
                        older+=1;legacy_selected=str(legacy.loc[pd.Timestamp(av[j])].date());different=not eq(latest_value,actual);diffvalues+=int(different)
                        item=dict(date=day,year=date.year,source=source,feature=f,selected_source_date=selected,latest_eligible_source_date=dd[j],available_date=av[j],saved_value=actual,latest_native_value=latest_value,value_differs=different,single_key_sort_reproduces_saved_source=(legacy_selected==selected),R0_selected_close=vv[idx],latest_eligible_close=vv[j])
                        if source=='01':
                            fr=frozen.loc[(date,f)];item['KR_mask_applied']=bool(fr.proposed_same_day_applied);item['KR_fallback']=bool(fr.fallback);item['KR_actual_X']=float(kr.loc[date,f]);item['KR_inherits_older_fallback']=bool(fr.fallback)
                        mismatches.append(item)
                mappings.append(dict(date=day,feature=f,source=source,actual_selected_source=record.source_date if record is not None else '',latest_eligible_source=dd[j] if j>=0 else '',saved_matches_selected_native=eq(computed[bisect.bisect_left(dd,record.source_date)],actual) if record is not None else True,selected_before_origin=(record.source_date<day) if record is not None else True))
            direct.append(dict(source=source,feature=f,rows=len(old),matches_recorded_native_arithmetic=not legacy_bad,recorded_native_max_error=maxerr,future_source_dates=len(future),older_selected_days=older,older_selected_with_value_difference=diffvalues))
            ck('saved_native_arithmetic_'+f,not legacy_bad);ck('no_future_source_'+f,not future)
        print('Read-only impact native source',source,'checked',flush=True)
    savecsv(I/'STALE_SELECTION_DETAILS.csv',mismatches);savecsv(I/'RECORDED_NATIVE_ARITHMETIC_CHECK.csv',direct);savecsv(I/'SOURCE_DATE_MAPPING_AUDIT.csv',mappings)
    mm=pd.DataFrame(mismatches);counts=mm.groupby(['source','year']).agg(feature_cells=('feature','size'),distinct_dates=('date','nunique'),different_value_cells=('value_differs','sum'),legacy_sort_reproduced=('single_key_sort_reproduces_saved_source','all')).reset_index();savecsv(I/'STALE_SELECTION_COUNTS_BY_YEAR.csv',counts)
    kk=mm[mm.source=='01'].copy();kc=kk.groupby('year').agg(older_source_days=('date','nunique'),feature_cells=('feature','size'),inherited_fallback_cells=('KR_inherits_older_fallback','sum')).reset_index();savecsv(I/'KR_EXPOSURE_COUNTS_BY_YEAR.csv',kc)
    ck('other48_values_and_nan_positions',np.array_equal(np.isnan(kr[others]),np.isnan(old[others])) and np.allclose(kr[others],old[others],rtol=1e-12,atol=1e-12,equal_nan=True))
    dd,vv,rr,av=sourcecache['01'];first={next(d for d in dd if d.startswith(str(y))) for y in sorted({int(d[:4]) for d in dd})};clockrows=[];examples=[];rawexamples=[];exdays={'2011-02-03','2011-07-05','2012-01-17','2012-11-23','2012-07-10','2012-12-04','2016-07-29','2016-08-01','2017-03-10','2017-03-13','2017-07-10','2017-12-04','2018-01-02','2019-11-13','2019-11-14','2019-11-15','2020-12-03'}
    for date,row in kr.iterrows():
        day=str(date.date());j=bisect.bisect_left(dd,day);present=j<len(dd) and dd[j]==day;allowed=present and day not in first and date.weekday()<5 and (date.month!=11 or day=='2019-11-14') and not(date.year==2020 and date.month==12)
        clock='16:30' if day=='2019-11-14' else '15:00' if day<'2016-08-01' else '15:30';local=datetime.datetime.fromisoformat(day+'T'+clock).replace(tzinfo=ZoneInfo('Asia/Seoul'));available=(local+datetime.timedelta(hours=2)).astimezone(ZoneInfo('America/New_York'));origin=datetime.datetime.fromisoformat(row.origin_et)
        for f in targets:
            key=f.split('_',1)[1];nativeval=calc(vv,j,key) if present else math.nan;applied=allowed and math.isfinite(nativeval) and available<=origin;fr=frozen.loc[(date,f)];expected=nativeval if applied else float(old.loc[date,f]);actual=float(row[f]);ok=applied==bool(fr.proposed_same_day_applied) and eq(expected,actual)
            if applied:ok=ok and datetime.datetime.fromisoformat(fr.close_at_local)==local and datetime.datetime.fromisoformat(fr.conditional_available_at_ET)==available and available<=origin
            ck('KR_fixed_mask_value_clock_'+day+f,ok)
            clockrows.append(dict(date=day,feature=f,applied=applied,conditional_available_ET=str(available) if applied else '',origin_ET=str(origin),direct_value_matches=True))
            if day in exdays:
                offsets=[0,1] if key=='ret1' else [0,5] if key=='ret5' else [0,20] if key=='ret20' else list(range(20)) if key=='ma20_gap' else list(range(21));ix=[j-o for o in offsets if present and j-o>=0]
                examples.append(dict(date=day,feature=f,scope='training' if date.year<2017 else 'evaluation',own_native_date_present=present,applied=applied,reason=fr.reason,saved_fallback_source=fr.baseline_source_date,local_close_if_native=str(local) if present else '',conditional_ET_if_native=str(available) if present else '',origin_ET=str(origin),native_today_Close=vv[j] if present else math.nan,saved_X=actual,independent_X=expected,required_dates=','.join(dd[i] for i in ix),required_Close=','.join(str(vv[i]) for i in ix)))
                for i in ix:rawexamples.append(dict(example_date=day,feature=f,**rr[i]))
    savecsv(I/'KR_FIXED_MASK_CLOCK_AUDIT.csv',clockrows);savecsv(I/'BOUNDARY_EXAMPLES.csv',examples);savecsv(I/'BOUNDARY_EXAMPLE_RAW_ROWS.csv',rawexamples)
    sd,sv,_=native(ROOT/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv');truth={sd[j]:int(sv[j]>sv[j-1]) for j in range(1,len(sd))};ck('Y_actual_previous_US_close',all(truth[str(d.date())]==int(y) for d,y in kr.Y.items()))
    fits=pd.read_csv(K/'logs/FIT_ATTEMPTS.csv');pr=pd.read_csv(K/'predictions/EXTERNAL_PREDICTIONS.csv',parse_dates=['date']).set_index('date');folds=[];maximum=0
    for f in fits.itertuples():
        te=kr[kr.index.strftime('%Y-%m')==f.month];origin=datetime.datetime.fromisoformat(te.iloc[0].origin_et);tr=kr[(kr.index<te.index.min())&kr.label_available_et.map(lambda t:datetime.datetime.fromisoformat(t)<origin)];m=joblib.load(K/f.model_path);mat=tr[cols].to_numpy();med=np.array([statistics.median([x for x in mat[:,j] if not math.isnan(x)]) if np.isfinite(mat[:,j]).any() else 0 for j in range(53)]);filled=np.where(np.isnan(mat),med,mat);mean=np.array([statistics.mean(filled[:,j]) for j in range(53)]);var=np.array([statistics.pvariance(filled[:,j]) for j in range(53)]);sc=m.named_steps['scale'];est=m.named_steps['model'];tt=te[cols].to_numpy();tt=np.where(np.isnan(tt),med,tt);logit=((tt-mean)/np.where(var>0,np.sqrt(var),1))@est.coef_[0]+est.intercept_[0];pp=np.array([1/(1+math.exp(-z)) for z in logit]);err=float(abs(pp-pr.loc[te.index].probability).max());maximum=max(maximum,err)
        ck('fold_mature_training_'+f.month,len(tr)==f.train_n and str(tr.index[0].date())==f.train_start and str(tr.index[-1].date())==f.train_end and all(datetime.datetime.fromisoformat(t)<origin for t in tr.label_available_et))
        ck('fold_internal_preprocess_'+f.month,np.allclose(med,m.named_steps['impute'].statistics_,rtol=1e-10,atol=1e-10) and np.allclose(mean,sc.mean_,rtol=1e-10,atol=1e-10) and np.allclose(var,sc.var_,rtol=1e-10,atol=1e-10))
        ck('direct_sigmoid_'+f.month,err<=1e-9 and np.array_equal(pp>=.5,pr.loc[te.index].prediction.to_numpy()))
        ck('model_schema_and_hash_'+f.month,list(m.feature_names_in_)==cols and list(m.classes_)==[0,1] and est.C==1 and est.class_weight is None and sha(K/f.model_path)==f.sha256)
        folds.append(dict(month=f.month,train_n=len(tr),max_mature_label=str(max(tr.label_available_et.map(datetime.datetime.fromisoformat))),origin_ET=str(origin),max_direct_sigmoid_error=err))
    savecsv(I/'MONTHLY_PREPROCESS_AND_DIRECT_SIGMOID.csv',folds)
    metrics=[]
    for period in ['ALL',2017,2018,2019,2020]:
        v=pr if period=='ALL' else pr[pr.index.year==period];y=v.Y.to_numpy();c=v.prediction.to_numpy();p=v.probability.to_numpy();tn=int(((y==0)&(c==0)).sum());tp=int(((y==1)&(c==1)).sum());fp=int(((y==0)&(c==1)).sum());fn=int(((y==1)&(c==0)).sum());rn=tn/(tn+fp);ru=tp/(tp+fn);den=math.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn));auc=float(np.mean((p[y==1,None]>p[y==0])+.5*(p[y==1,None]==p[y==0])))
        metrics.append(dict(period=period,n=len(v),TN=tn,FP=fp,FN=fn,TP=tp,correct=tn+tp,accuracy=(tn+tp)/len(v),recall_nonup=rn,recall_up=ru,BA=(rn+ru)/2,MCC=(tn*tp-fp*fn)/den,AUC=auc,Brier=float(np.mean((p-y)**2)),Log_loss=float(-np.mean(y*np.log(p)+(1-y)*np.log1p(-p))),predicted_up_rate=float(c.mean())))
    savecsv(I/'RECOMPUTED_KR_METRICS.csv',metrics);ck('591_143_448',metrics[0]['correct']==591 and metrics[0]['TN']==143 and metrics[0]['TP']==448)
    originalmetrics=pd.read_csv(K/'METRICS.csv')
    for r in metrics:
        oldmetric=originalmetrics[(originalmetrics.policy=='A1_KR_ONLY')&(originalmetrics.period==str(r['period']))].iloc[0];ck('yearly_metrics_'+str(r['period']),all(np.isclose(r[k],oldmetric[k],rtol=1e-10,atol=1e-10) for k in ['n','correct','accuracy','recall_nonup','recall_up','BA','MCC','AUC','Brier','Log_loss','predicted_up_rate']))
    savecsv(I/'ADDITIONAL_CHECKS.csv',independent_checks)
    summary=dict(overall_gate='FAIL_STOP_STAGE2',additional_readonly_checks='PASS',new_fits=0,new_models=0,TW23_executed=False,KR_reported_count_confirmed=591,TN=143,TP=448,max_direct_sigmoid_error=maximum,stale_selection_cells=len(mm),stale_selection_dates=mm.date.nunique(),by_source=mm.groupby('source').agg(cells=('feature','size'),dates=('date','nunique'),value_difference_cells=('value_differs','sum')).reset_index().to_dict('records'),KR_initial_stale_dates=kk[kk.year<2017].date.nunique(),KR_eval_stale_dates=kk[kk.year>=2017].date.nunique(),KR_initial_inherited_fallback_dates=kk[(kk.year<2017)&kk.KR_inherits_older_fallback.fillna(False)].date.nunique(),KR_eval_inherited_fallback_dates=kk[(kk.year>=2017)&kk.KR_inherits_older_fallback.fillna(False)].date.nunique(),all_mismatch_dates_reproduced_by_legacy_sort=bool(mm.single_key_sort_reproduces_saved_source.all()),actual_future_inputs_found=False,old_results_modified=False,warning='Confirmed saved-score arithmetic is not clearance of the input freshness defect; corrected-model performance cannot be inferred without a separately authorized new version.')
    savejson(I/'ASSESSMENT_SUMMARY.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
