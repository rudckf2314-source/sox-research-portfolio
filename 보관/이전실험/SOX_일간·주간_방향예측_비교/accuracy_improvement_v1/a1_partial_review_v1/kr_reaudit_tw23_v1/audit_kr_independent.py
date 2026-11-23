"""Stage 1: independent native-row arithmetic and disk-model audit. Never fits."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import sys,csv,json,math,statistics,bisect,hashlib,datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import numpy as np,pandas as pd,joblib
from threadpoolctl import threadpool_limits
O=Path(__file__).resolve().parent;P=O.parent;A=P.parent;D=A.parent;ROOT=D.parent;V=D/'development_revision_v1';K=P/'execution_kr_v1';S=O/'stage1_kr_audit'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def savejson(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def savecsv(p,x):pd.DataFrame(x).to_csv(p,index=False,encoding='utf-8-sig')
def snapshot():
    out=[]
    for b,ds,fs in os.walk(ROOT,followlinks=False):
        ds[:]=[n for n in ds if n not in {'.git','.venv','.venv_W1'} and not (Path(b)/n).resolve().is_relative_to(O)]
        for n in fs:
            p=Path(b)/n;assert not p.is_symlink(),str(p);out.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return out
def native(path):
    with path.open(encoding='utf-8-sig',newline='') as f:rr=list(csv.DictReader(line for line in f if not line.startswith('#')))
    rr=sorted([r for r in rr if r['Date']<='2020-12-31'],key=lambda r:r['Date']);dates=[r['Date'] for r in rr];assert len(dates)==len(set(dates))
    col='Close' if 'Close' in rr[0] else 'Semiconductor_Industry_Index'
    def num(s):
        try:return float(s)
        except (TypeError,ValueError):return math.nan
    return dates,[num(r[col]) for r in rr],rr
def calc(values,i,key):
    def valid(ix):return all(j>=0 and math.isfinite(values[j]) and values[j]>0 for j in ix)
    if key.startswith('ret'):
        lag=int(key[3:]);return 100*(values[i]/values[i-lag]-1) if valid([i,i-lag]) else math.nan
    if key=='vol20':
        return 100*statistics.stdev([values[j]/values[j-1]-1 for j in range(i-19,i+1)]) if valid(range(i-20,i+1)) else math.nan
    if key=='ma20_gap':return 100*(values[i]/statistics.mean(values[i-19:i+1])-1) if valid(range(i-19,i+1)) else math.nan
    if key=='level':return values[i]
    lag=int(key[5:]);return values[i]-values[i-lag] if valid([i,i-lag]) else math.nan
def eq(a,b,rtol=1e-10,atol=1e-10):return (math.isnan(a) and math.isnan(b)) or (math.isfinite(a) and math.isfinite(b) and abs(a-b)<=atol+rtol*abs(b))
def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1);S.mkdir(exist_ok=True)
    assert not (O/'PROTECTED_BEFORE.csv').exists(),'Do not overwrite prior run'
    before=snapshot();savecsv(O/'PROTECTED_BEFORE.csv',before);print('Stage1 protected snapshot',len(before),flush=True)
    checks=[]
    def ck(name,ok,detail=''):
        checks.append(dict(check=name,PASS=bool(ok),detail=str(detail)))
        if not ok:savecsv(S/'CHECKS.csv',checks);raise RuntimeError(name+': '+str(detail))
    seals=[]
    for base in [D,V,A,A/'execution_v1',P,K]:
        man=base/'OUTPUT_MANIFEST.csv';ck('seal_manifest_'+str(base.relative_to(ROOT)),sha(man)==(base/'OUTPUT_MANIFEST.sha256').read_text().split()[0])
        for r in pd.read_csv(man).itertuples():
            p=base/r.path;seals.append(dict(manifest=str(man.relative_to(ROOT)),path=r.path,PASS=p.is_file() and p.stat().st_size==r.bytes and sha(p)==r.sha256))
    savecsv(S/'SEAL_CHECK.csv',seals);ck('all_prior_seals_pass',all(x['PASS'] for x in seals))
    old=pd.read_csv(V/'data/LATEST_EOD_1D.csv',parse_dates=['date','label_end']).set_index('date').sort_index();kr=pd.read_csv(K/'data/KR_ONLY_1D.csv',parse_dates=['date','label_end']).set_index('date').sort_index()
    cols=json.loads((V/'config/INFORMATION_SETS.json').read_text())['M1'];targets=[f for f in cols if f.startswith('s01_')];others=[f for f in cols if f not in targets]
    ck('53_schema_5_KR_48_other',len(targets)==5 and len(others)==48)
    ck('row_identity',kr.index.equals(old.index) and len(kr)==2495 and len(kr[kr.index.year>=2017])==1007)
    ck('label_origin_identity',all(kr[c].equals(old[c]) for c in ['Y','origin_et','label_available_et','label_end']))
    changes=[]
    for f in cols:
        a=kr[f].to_numpy();b=old[f].to_numpy();nan_same=np.array_equal(np.isnan(a),np.isnan(b));equal=np.allclose(a,b,rtol=1e-12,atol=1e-12,equal_nan=True);delta=float(np.nanmax(abs(a-b)))
        changes.append(dict(feature=f,targeted=f in targets,missing_positions_identical=nan_same,all_values_equal_within_csv_tolerance=equal,max_absolute_difference=delta,changed_numeric_cells=int((~np.isclose(a,b,rtol=1e-12,atol=1e-12,equal_nan=True)).sum())))
        if f in others:ck('unchanged48_'+f,nan_same and equal,delta)
    savecsv(S/'COLUMN_CHANGE_AUDIT.csv',changes)
    ck('only_s01_changed',{r['feature'] for r in changes if not r['all_values_equal_within_csv_tolerance']}==set(targets))
    dictionary=pd.read_csv(D/'FEATURE_DICTIONARY.csv');sessions=pd.read_csv(D/'inputs/US_MARKET_SESSIONS_DEV.csv').session_date.tolist();ck('session_order',sessions==sorted(set(sessions)))
    sources={};hashes=[];reconstruction=[];lineage=[]
    for st,part in dictionary[dictionary.feature.isin(cols)].groupby('source_type'):
        source=f'{int(st):02d}';path=ROOT/part.iloc[0].source_path;dd,vv,rr=native(path);sources[source]=(dd,vv,rr);hashes.append(dict(source=source,path=str(path.relative_to(ROOT)),sha256=sha(path)))
        av=[sessions[bisect.bisect_right(sessions,d)] if bisect.bisect_right(sessions,d)<len(sessions) else '9999-12-31' for d in dd]
        for f in part.feature:
            key=f.split('_',1)[1];computed=[calc(vv,i,key) for i in range(len(dd))];errs=[];bad=[];nan_bad=[]
            for date in old.index:
                day=str(date.date());j=bisect.bisect_right(av,day)-1;value=computed[j] if j>=0 and (datetime.date.fromisoformat(day)-datetime.date.fromisoformat(dd[j])).days<=10 else math.nan
                actual=float(old.loc[date,f]);ok=eq(value,actual)
                if not ok:bad.append(day)
                if math.isnan(value)!=math.isnan(actual):nan_bad.append(day)
                if math.isfinite(value) and math.isfinite(actual):errs.append(abs(value-actual))
                if math.isfinite(actual):
                    ck('source_date_prior_'+day+'_'+f,j>=0 and dd[j]<day and av[j]<=day)
                    lineage.append(dict(date=day,feature=f,source=source,source_date=dd[j],modeled_available_date=av[j],origin_date=day,source_before_US_origin_day=True,actual_delivery_verified=False))
            reconstruction.append(dict(source=source,feature=f,rows=len(old),arithmetic='csv/bisect/statistics native calculation; no pandas rolling/asof',max_absolute_error=max(errs,default=0),value_mismatch_dates=','.join(bad),missing_mismatch_dates=','.join(nan_bad)))
            ck('manual_R0_native_'+f,not bad and not nan_bad,str(bad[:5]))
    savecsv(S/'RAW_INPUT_HASHES.csv',hashes);savecsv(S/'R0_NATIVE_RECONSTRUCTION.csv',reconstruction);savecsv(S/'R0_NO_FUTURE_LINEAGE.csv',lineage)
    rawhash=json.loads((P/'AUDIT_SUMMARY.json').read_text())['raw_paths']['01']['sha256'];ck('RAW01_frozen_hash',next(r['sha256'] for r in hashes if r['source']=='01')==rawhash)
    frozen=pd.read_csv(P/'A1_PARTIAL_ROW_REVIEW.csv',dtype={'source':str},parse_dates=['date']);frozen=frozen[frozen.source=='01'].set_index(['date','feature']).sort_index();ck('KR_mask_unique',frozen.index.is_unique and len(frozen)==2495*5)
    dd,vv,rr=sources['01'];first=set(next(d for d in dd if d.startswith(str(y))) for y in sorted({int(d[:4]) for d in dd}));maskrows=[];examples=[];rawexamples=[];maximum_error=0
    exampledates={'2011-02-03','2012-07-10','2012-12-04','2016-07-29','2016-08-01','2017-03-10','2017-03-13','2017-07-10','2017-12-04','2018-01-02','2019-11-13','2019-11-14','2019-11-15','2020-12-03'}
    for date,row in kr.iterrows():
        day=str(date.date());i=bisect.bisect_left(dd,day);present=i<len(dd) and dd[i]==day
        allowed=present and day not in first and date.weekday()<5 and (date.month!=11 or day=='2019-11-14') and not (date.year==2020 and date.month==12)
        clock='16:30' if day=='2019-11-14' else '15:00' if day<'2016-08-01' else '15:30'
        local=datetime.datetime.fromisoformat(day+'T'+clock).replace(tzinfo=ZoneInfo('Asia/Seoul'));avail=(local+datetime.timedelta(hours=2)).astimezone(ZoneInfo('America/New_York'));origin=datetime.datetime.fromisoformat(row.origin_et)
        for f in targets:
            key=f.split('_',1)[1];calcval=calc(vv,i,key) if present else math.nan;applied=allowed and math.isfinite(calcval) and avail<=origin;fr=frozen.loc[(date,f)];expected=calcval if applied else float(old.loc[date,f]);actual=float(row[f])
            ck('mask_values_'+day+'_'+f,applied==bool(fr.proposed_same_day_applied) and bool(fr.fallback)==(not applied) and eq(expected,actual))
            if applied:
                ck('KR_clock_'+day+'_'+f,datetime.datetime.fromisoformat(fr.conditional_available_at_ET)==avail and datetime.datetime.fromisoformat(fr.close_at_local)==local and avail<=origin and fr.source_date==day)
                maximum_error=max(maximum_error,abs(expected-actual))
            maskrows.append(dict(date=day,feature=f,applied=applied,fallback=not applied,source_date=day if applied else fr.baseline_source_date,available_ET=str(avail) if applied else '',origin_ET=str(origin),conditional_only=True,actual_value=actual,manual_expected=expected))
            if day in exampledates:
                offsets=[0,1] if key=='ret1' else [0,5] if key=='ret5' else [0,20] if key=='ret20' else list(range(20)) if key=='ma20_gap' else list(range(21));idx=[i-j for j in offsets if present and i-j>=0]
                examples.append(dict(date=day,feature=f,scope='training' if date.year<2017 else 'evaluation',same_day_native_present=present,applied=applied,fallback_reason=fr.reason,original_source_date=fr.baseline_source_date,local_regular_or_special_close=str(local) if present else '',conditional_available_ET=str(avail) if present else '',US_origin=str(origin),actual_X=actual,independent_X=expected,native_current_close=vv[i] if present else math.nan,required_native_dates=','.join(dd[j] for j in idx),required_native_Close=','.join(repr(vv[j]) for j in idx),publication_timing_status='conditional not actual delivery'))
                for j in idx:rawexamples.append(dict(example_date=day,feature=f,raw_Date=dd[j],raw_Close=vv[j],raw_Open=rr[j].get('Open'),raw_High=rr[j].get('High'),raw_Low=rr[j].get('Low'),raw_Volume=rr[j].get('Volume')))
    savecsv(S/'KR_MASK_CLOCK_NATIVE_AUDIT.csv',maskrows);savecsv(S/'BOUNDARY_EXAMPLES.csv',examples);savecsv(S/'BOUNDARY_EXAMPLE_RAW_ROWS.csv',rawexamples)
    audit=pd.DataFrame(maskrows);daily=audit.groupby('date').applied.any();ck('fixed1290_and846_days',int(daily[daily.index<'2017-01-01'].sum())==1290 and int(daily[daily.index>='2017-01-01'].sum())==846)
    # Independent label construction from actual prior rows, no business-day approximation.
    soxdd,soxvv,_=native(ROOT/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv');truth={soxdd[j]:int(soxvv[j]>soxvv[j-1]) for j in range(1,len(soxdd))};ck('all_Y_from_previous_actual_US_close',all(truth[str(d.date())]==int(v) for d,v in kr.Y.items()))
    fits=pd.read_csv(K/'logs/FIT_ATTEMPTS.csv');saved=pd.read_csv(K/'predictions/EXTERNAL_PREDICTIONS.csv',parse_dates=['date']).set_index('date');foldchecks=[];maxprob=0
    for f in fits.itertuples():
        month=f.month;te=kr[kr.index.strftime('%Y-%m')==month];origin=datetime.datetime.fromisoformat(te.iloc[0].origin_et);tr=kr[(kr.index<te.index.min())&kr.label_available_et.map(lambda x:datetime.datetime.fromisoformat(x)<origin)]
        m=joblib.load(K/f.model_path);im=m.named_steps['impute'];sc=m.named_steps['scale'];est=m.named_steps['model'];mat=tr[cols].to_numpy();med=np.array([statistics.median([v for v in mat[:,j] if not math.isnan(v)]) if np.isfinite(mat[:,j]).any() else 0 for j in range(len(cols))]);filled=np.where(np.isnan(mat),med,mat);mean=np.array([statistics.mean(filled[:,j]) for j in range(len(cols))]);var=np.array([statistics.pvariance(filled[:,j]) for j in range(len(cols))])
        ck('fold_maturity_'+month,len(tr)==f.train_n and str(tr.index[0].date())==f.train_start and str(tr.index[-1].date())==f.train_end and all(datetime.datetime.fromisoformat(x)<origin for x in tr.label_available_et))
        ck('fold_inner_preprocess_'+month,np.allclose(med,im.statistics_,rtol=1e-10,atol=1e-10) and np.allclose(mean,sc.mean_,rtol=1e-10,atol=1e-10) and np.allclose(var,sc.var_,rtol=1e-10,atol=1e-10))
        ck('53_named_model_features_'+month,list(m.feature_names_in_)==cols and list(m.classes_)==[0,1] and est.C==1 and est.class_weight is None)
        tt=te[cols].to_numpy();tt=np.where(np.isnan(tt),med,tt);sd=np.where(var>0,np.sqrt(var),1);logits=((tt-mean)/sd)@est.coef_[0]+est.intercept_[0];prob=np.array([1/(1+math.exp(-v)) for v in logits]);error=float(abs(prob-saved.loc[te.index].probability).max());maxprob=max(maxprob,error)
        ck('explicit_sigmoid_saved_probability_'+month,error<=1e-9 and np.array_equal((prob>=.5).astype(int),saved.loc[te.index].prediction))
        ck('saved_model_file_hash_'+month,sha(K/f.model_path)==f.sha256)
        foldchecks.append(dict(month=month,train_n=len(tr),max_label_available=max(tr.label_available_et.map(datetime.datetime.fromisoformat)),origin=origin,max_manual_sigmoid_error=error,preprocess_recomputed_without_fit=True))
    savecsv(S/'MONTHLY_FOLD_PREPROCESS_CHECK.csv',foldchecks)
    metric=[]
    for period in ['ALL',2017,2018,2019,2020]:
        v=saved if period=='ALL' else saved[saved.index.year==period];y=v.Y.to_numpy();p=v.probability.to_numpy();c=v.prediction.to_numpy();tn=int(((c==0)&(y==0)).sum());fp=int(((c==1)&(y==0)).sum());fn=int(((c==0)&(y==1)).sum());tp=int(((c==1)&(y==1)).sum());ru=tp/(tp+fn);rn=tn/(tn+fp);den=math.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn));auc=float(np.mean((p[y==1,None]>p[y==0])+0.5*(p[y==1,None]==p[y==0])))
        metric.append(dict(period=period,n=len(v),TN=tn,FP=fp,FN=fn,TP=tp,correct=tn+tp,accuracy=(tn+tp)/len(v),recall_nonup=rn,recall_up=ru,BA=(rn+ru)/2,MCC=(tp*tn-fp*fn)/den,AUC=auc,Brier=float(np.mean((p-y)**2)),Log_loss=float(-np.mean(y*np.log(p)+(1-y)*np.log1p(-p))),predicted_up_rate=float(c.mean())))
    savecsv(S/'RECOMPUTED_METRICS.csv',metric);ck('591_143_448_independently_confirmed',metric[0]['n']==1007 and metric[0]['TN']==143 and metric[0]['TP']==448 and metric[0]['correct']==591)
    reported=pd.read_csv(K/'METRICS.csv');reported=reported[reported.policy=='A1_KR_ONLY']
    for row in metric:
        orig=reported[reported.period==str(row['period'])].iloc[0];ck('annual_saved_metrics_'+str(row['period']),all(np.isclose(row[k],float(orig[k]),rtol=1e-10,atol=1e-10) for k in ['n','correct','accuracy','recall_nonup','recall_up','BA','MCC','AUC','Brier','Log_loss','predicted_up_rate']))
    savecsv(S/'CHECKS.csv',checks)
    report=f'''# 한국 후보 독립 재검증 — PASS

기존 검증 스크립트를 import/재실행하지 않고 별도의 csv/bisect/statistics 산식으로 원천 관측·53개 R0 특징·한국 당일5개 특징·날짜 정렬·시각을 대조했다. 학습은0회다. 저장 계수와 학습 내부에서 재계산한 대치/스케일로 직접 sigmoid를 계산해1,007일 저장 예측을 확인했다.

**591/1,007일(58.69%), 비상승 적중143일·상승 적중448일**을 확인했다. 혼동행렬 TN143/FP301/FN115/TP448이다. 기존 결과나 마스크를 수정하지 않았다.

나머지48컬럼의 결측 위치가 모두 같고 값은 CSV직렬화허용오차내에서 동일했다. 실제 변경 컬럼은s01 다섯개뿐이다. R0의53컬럼 전체를 실제원천과다음미국거래일08시정렬로재구성했다. 미국원천의source_date는모두미국origin의전날이전이며한국동일현지일값만조건부마감+2시간을거쳐채택됐다. 모델입력컬럼은53개로고정돼미국당일Close/Y/실현수익률은포함되지않았다.

각월라벨성숙·학습행·학습내중앙값/평균/분산을별도계산했다. 새학습없이모델계수의생성과정자체를재현한것은아니며,보존된fit기록/해시및입력·전처리·계수예측의일치범위를검증한것이다. 직접sigmoid최대오차는{maxprob:.3g}이다.

BOUNDARY_EXAMPLES.csv와BOUNDARY_EXAMPLE_RAW_ROWS.csv는초기학습/평가,여름/겨울,DST경계,한국원천부재/fallback,2016거래시간연장,연초첫관측,2019-11-14확인특별일과인접fallback,2020-12제한의실제RAW행을보여준다. 원천행부재만으로휴장을확정하지않았다. fallback예시에서표시한가상당일정규시각은채택근거가아니며실제로기존과거값을썼다.

직접확인한것은RAW해시·native계산/날짜정렬·고정마스크·timezone산술·학습라벨성숙·전처리·저장예측/지표다. 마감+2시간정보가용성·실제과거벤더전달·당시vintage동일성은조건부가정/미입증이다. 기존과같이2017~2020반복개발자료결과이며독립시험성능은아니다.

필수검사모두통과하여승인된대만단독비교의선행조건을충족했다. 아직이1단계에서는모델을학습하지않았다.
''';(S/'AUDIT_REPORT.md').write_text(report,encoding='utf-8')
    savejson(S/'GATE_RESULT.json',dict(status='PASS',new_fits=0,checks=len(checks),correct=591,TN=143,TP=448,model_probability_max_error=maxprob,native_KR_value_max_error=maximum_error,KR_result_preserved=True,stage2_authorized_to_proceed=True,conditional_information_only=True,mask_sha256=sha(P/'A1_PARTIAL_ROW_REVIEW.csv')))
    print('STAGE1 PASS:',len(checks),'checks, 591=143+448, new fits0. Taiwan gate open.',flush=True)
if __name__=='__main__':
    try:main()
    except Exception as e:
        S.mkdir(exist_ok=True);savejson(S/'GATE_RESULT.json',dict(status='FAIL',error=repr(e),new_fits=0,stage2_authorized_to_proceed=False,action='STOP; do not modify old results or train. Assess affected arithmetic/input lineage before any separate correction.'));raise
