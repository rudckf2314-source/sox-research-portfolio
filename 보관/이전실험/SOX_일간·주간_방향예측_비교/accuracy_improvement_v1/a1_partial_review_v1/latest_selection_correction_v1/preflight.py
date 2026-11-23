"""Correct only the tie-selection defect and prove data invariants before any fit."""
import sys,math,bisect,statistics,datetime,shutil,ast
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
from common import *
CHECKS=[]
def ck(n,ok,detail=''):
    CHECKS.append(dict(check=n,PASS=bool(ok),detail=str(detail)))
    if not ok:csv('PREFLIGHT_CHECKS.csv',CHECKS);raise RuntimeError(n+': '+str(detail))
def scalar(v,i,key):
    if key=='level':return v[i]
    if key.startswith('delta'):
        k=int(key[5:]);return v[i]-v[i-k] if i>=k else math.nan
    if key.startswith('ret'):
        k=int(key[3:]);return 100*(v[i]/v[i-k]-1) if i>=k else math.nan
    if key=='vol20':return 100*statistics.stdev([v[j]/v[j-1]-1 for j in range(i-19,i+1)]) if i>=20 else math.nan
    return 100*(v[i]/statistics.mean(v[i-19:i+1])-1) if i>=19 else math.nan
def main():
    sys.stdout.reconfigure(encoding='utf-8');resume='--resume-verified-preflight' in sys.argv
    if (O/'PROTECTED_BEFORE.csv').exists():
        assert resume and (O/'PREFLIGHT_ADDENDUM.md').exists() and not list((O/'models').glob('*')) and not (O/'logs/FIT_ATTEMPTS.csv').exists(),'Only documented prefit review may resume'
        for r in pd.read_csv(O/'PROTECTED_BEFORE.csv').itertuples():assert sha(ROOT/r.path)==r.sha256,r.path
    for n in ['inputs','data','models','logs','predictions']:(O/n).mkdir(exist_ok=True)
    before=pd.read_csv(O/'PROTECTED_BEFORE.csv').to_dict('records') if resume else snapshot()
    if not resume:csv('PROTECTED_BEFORE.csv',before)
    print('Protected',len(before),'files',flush=True)
    seals=[]
    for base in [D,V,A,A/'execution_v1',P,K,E]:
        man=base/'OUTPUT_MANIFEST.csv';ck('manifest_'+str(base.relative_to(ROOT)),sha(man)==(base/'OUTPUT_MANIFEST.sha256').read_text().split()[0])
        for r in pd.read_csv(man).itertuples():
            p=base/r.path;seals.append(dict(manifest=str(man.relative_to(ROOT)),path=r.path,PASS=p.is_file() and p.stat().st_size==r.bytes and sha(p)==r.sha256))
    csv('EXISTING_SEALS.csv',seals);ck('all_prior_seals',all(r['PASS'] for r in seals))
    (O/'OLD_RESULT_DISPOSITION.md').write_text('# 기존 결과 보존 분류\n\n**저장 예측 집계 확인, 최신 관측 선택 오류 발견, 수정 결과 대기**\n\n이 분류는 보정 비교 착수 시 기존58.69% 결과의 상태다. 기존 코드·RAW·데이터·모델·예측·오류 보고서는 그대로 보존한다. 새 보정 비교 결과는 별도 파일로 보고하며 기존 보고서를 소급 수정하지 않는다.\n',encoding='utf-8')
    for src in [P/'REVIEW_SCOPE.md',P/'REVISED_EXPERIMENT_PLAN.md',P/'PUBLIC_EVIDENCE.json']:shutil.copy2(src,O/'inputs'/src.name)
    old=pd.read_csv(V/'data/LATEST_EOD_1D.csv',parse_dates=['date','label_end']).set_index('date').sort_index();oldkr=pd.read_csv(K/'data/KR_ONLY_1D.csv',parse_dates=['date','label_end']).set_index('date').sort_index();corrected=old.copy()
    cols=json.loads((V/'config/INFORMATION_SETS.json').read_text())['M1'];dic=pd.read_csv(D/'FEATURE_DICTIONARY.csv');policy=pd.read_csv(V/'POINT_IN_TIME_POLICY.csv');fast=set(policy[policy.new_lag_US_sessions==1].source_type.astype(int));sessions=pd.DatetimeIndex(pd.read_csv(D/'inputs/US_MARKET_SESSIONS_DEV.csv').session_date)
    ck('all_logic_sources_in_scope',fast==set(dic[dic.feature.isin(cols)].source_type.astype(int)))
    sources={};dups=[];rawhashes=[];lineage=[];independent=[];permutations=[];selections={};legacy_selections={}
    # Same-date duplicate and conflict behavior is tested explicitly.
    synth=pd.DataFrame({'Date':['2018-07-03','2018-07-04','2018-07-04'],'Close':[100.,102.,102.]});ck('identical_duplicate_handled',len(normalize_raw(synth))==2)
    conflict=synth.copy();conflict.loc[2,'Close']=103.;caught=False
    try:normalize_raw(conflict)
    except ValueError:caught=True
    ck('same_date_conflict_rejected',caught)
    for st in sorted(fast):
        part=dic[dic.source_type==st];features=part.feature.tolist();path=ROOT/part.iloc[0].source_path;raw=pd.read_csv(path,comment='#');raw=raw[raw.Date<='2020-12-31'].copy();duplicates=raw[raw.duplicated('Date',keep=False)];norm=normalize_raw(raw)
        dups.append(dict(source=st,rows=len(raw),duplicate_rows=len(duplicates),duplicate_dates=duplicates.Date.nunique(),value_conflicts=0));rawhashes.append(dict(source=st,path=str(path.relative_to(ROOT)),sha256=sha(path)));sources[st]=norm
        merged,events=reconstruct(raw,features,sessions,old.index);source_dates=merged.source_date.dt.strftime('%Y-%m-%d').fillna('');selections[st]=merged
        legacy=events.sort_values('available_date').drop_duplicates('available_date',keep='last');legacy_selections[st]=pd.merge_asof(pd.DataFrame({'date':old.index}),legacy,left_on='date',right_on='available_date',direction='backward').set_index('date')
        ck('source_hash_'+str(st),sha(path)==policy.loc[policy.source_type==st,'sha256'].iloc[0])
        for name,permuted in [('reverse',raw.iloc[::-1]),('shuffle',raw.sample(frac=1,random_state=SEED))]:
            again,_=reconstruct(permuted,features,sessions,old.index);ok=again.equals(merged);permutations.append(dict(source=st,raw_input_order=name,PASS=ok));ck('raw_order_'+str(st)+name,ok)
        for name,ev in [('reverse',events.iloc[::-1]),('shuffle',events.sample(frac=1,random_state=SEED))]:
            ck('event_order_'+str(st)+name,select_latest(ev).equals(select_latest(events)))
        # Independent scan over EVERY eligible native observation, rather than comparing selected values.
        nd=norm.Date.tolist();vv=norm['Close' if 'Close' in norm else 'Semiconductor_Industry_Index'].astype(float).tolist();sd=sessions.strftime('%Y-%m-%d').tolist();available=[sd[bisect.bisect_right(sd,d)] if bisect.bisect_right(sd,d)<len(sd) else '9999-12-31' for d in nd]
        for row in merged.itertuples(index=False):
            day=str(row.date.date());eligible=[i for i,a in enumerate(available) if a<=day];j=max(eligible,key=lambda i:nd[i]) if eligible else None;expected=nd[j] if j is not None else '';chosen=str(row.source_date.date()) if pd.notna(row.source_date) else '';ck('all_eligible_max_'+str(st)+day,chosen==expected)
            age=(row.date.date()-datetime.date.fromisoformat(expected)).days if expected else 99999
            for f in features:
                val=float(getattr(row,f));manual=scalar(vv,j,f.split('_',1)[1]) if j is not None and age<=10 else math.nan;ok=np.isclose(val,manual,rtol=1e-10,atol=1e-10,equal_nan=True);ck('native_scalar_'+day+f,ok)
                lineage.append(dict(date=day,feature=f,source=st,source_date=chosen,available_date=str(row.available_date.date()) if pd.notna(row.available_date) else '',modeled_available_ET=str(pd.Timestamp(row.available_date).tz_localize('America/New_York')+pd.Timedelta(hours=8)) if pd.notna(row.available_date) else '',origin_ET=old.loc[row.date,'origin_et'],staleness_days=age,value=val,eligible_native_count=len(eligible),actual_delivery_verified=False))
            if expected:ck('no_future_source_'+str(st)+day,expected<day and str(row.available_date.date())<=day)
            independent.append(dict(source=st,date=day,eligible_count=len(eligible),independent_latest_source=expected,selected_source=chosen,PASS=chosen==expected))
        for f in features:corrected[f]=merged[f].to_numpy()
        print('Corrected source',st,'full eligibility/native/permutation checks PASS',flush=True)
    csv('DUPLICATE_AND_CONFLICT_AUDIT.csv',dups);csv('RAW_HASHES.csv',rawhashes);csv('INPUT_ORDER_INVARIANCE.csv',permutations);csv('INDEPENDENT_ELIGIBILITY_SCAN.csv',independent);csv('CORRECTED_R0_LINEAGE.csv',lineage)
    expected=pd.read_csv(E/'impact_assessment/STALE_SELECTION_DETAILS.csv');expected_keys=set(zip(expected.date,expected.feature));changes=[];actual_keys=set();oldline=pd.read_csv(V/'data/LATEST_FEATURE_LINEAGE.csv');oldline=oldline[oldline.feature.isin(cols)].set_index(['date','feature'])
    for f in cols:
        different=~np.isclose(corrected[f],old[f],rtol=1e-12,atol=1e-12,equal_nan=True)
        for date in corrected.index[different]:
            day=str(date.date());st=int(f.split('_')[0][1:]);m=selections[st].set_index('date').loc[date];actual_keys.add((day,f));changes.append(dict(policy='CORRECTED_R0',date=day,year=date.year,feature=f,source=st,old_source_date=oldline.loc[(day,f),'source_date'] if (day,f) in oldline.index else '',new_source_date=str(m.source_date.date()),old_value=old.loc[date,f],new_value=corrected.loc[date,f],missing_changed=bool(pd.isna(old.loc[date,f])!=pd.isna(corrected.loc[date,f]))))
    extra=actual_keys-expected_keys;allowed_extra={(d,f) for d in ['2020-01-28','2020-01-29','2020-01-30'] for f in cols if f.startswith('s13_')}
    ck('known230_plus15_missing_cells_only',expected_keys.issubset(actual_keys) and extra==allowed_extra,str((len(actual_keys),len(expected_keys),len(extra))))
    missing_tests=[]
    for day,f in sorted(extra):
        date=pd.Timestamp(day);legacy=legacy_selections[13].loc[date];new=selections[13].set_index('date').loc[date];oldage=(date-legacy.source_date).days;newage=(date-new.source_date).days
        ok=pd.isna(old.loc[date,f]) and pd.notna(corrected.loc[date,f]) and oldage>10 and newage<=10 and legacy.available_date==new.available_date and legacy.source_date<new.source_date
        ck('same_bug_staleness_boundary_'+day+f,ok);missing_tests.append(dict(date=day,feature=f,old_source_date=str(legacy.source_date.date()),new_source_date=str(new.source_date.date()),available_date=str(new.available_date.date()),old_staleness=oldage,new_staleness=newage,old_value=old.loc[date,f],new_value=corrected.loc[date,f],PASS=bool(ok)))
    csv('MISSING_BOUNDARY_REGRESSION.csv',missing_tests);csv('CORRECTION_CHANGED_CELLS.csv',changes)
    # Replay every known error and explicit US holiday boundary cases as regression checks.
    regression=[]
    for r in expected.itertuples():
        st=int(r.source);m=selections[st].set_index('date').loc[pd.Timestamp(r.date)];ok=str(m.source_date.date())==r.latest_eligible_source_date and np.isclose(corrected.loc[pd.Timestamp(r.date),r.feature],r.latest_native_value,rtol=1e-10,atol=1e-10);regression.append(dict(date=r.date,feature=r.feature,expected_source=r.latest_eligible_source_date,selected_source=str(m.source_date.date()),PASS=ok))
    ck('all_known_cases_regression',all(r['PASS'] for r in regression));csv('HOLIDAY_REGRESSION_CASES.csv',regression)
    for day,source in [('2011-07-05','2011-07-04'),('2012-01-17','2012-01-16'),('2012-11-23','2012-11-22'),('2018-11-23','2018-11-22')]:ck('explicit_KR_holiday_'+day,str(selections[1].set_index('date').loc[pd.Timestamp(day),'source_date'].date())==source)
    untouched=[c for c in old.columns if c not in cols];ck('all_other_original_fields_identical',corrected[untouched].equals(old[untouched]))
    maskfile=P/'A1_PARTIAL_ROW_REVIEW.csv';mask=pd.read_csv(maskfile,dtype={'source':str},parse_dates=['date']);mask=mask[mask.source=='01'].copy();csv('inputs/FROZEN_KR_MASK.csv',mask);mask=mask.set_index(['date','feature']);krcols=[c for c in cols if c.startswith('s01_')];other48=[c for c in cols if c not in krcols];newkr=corrected.copy();native=native_features(sources[1],krcols).set_index('source_date');native_dates=sources[1].Date.tolist();first={next(d for d in native_dates if d.startswith(str(y))) for y in sorted({int(d[:4]) for d in native_dates})};application=[]
    for date in old.index:
        day=str(date.date());present=date in native.index;allowed=present and day not in first and date.weekday()<5 and (date.month!=11 or day=='2019-11-14') and not(date.year==2020 and date.month==12)
        clock='16:30' if day=='2019-11-14' else '15:00' if day<'2016-08-01' else '15:30';local=datetime.datetime.fromisoformat(day+'T'+clock).replace(tzinfo=ZoneInfo('Asia/Seoul'));avail=(local+datetime.timedelta(hours=2)).astimezone(ZoneInfo('America/New_York'));origin=datetime.datetime.fromisoformat(old.loc[date,'origin_et'])
        for f in krcols:
            m=mask.loc[(date,f)];value=float(native.loc[date,f]) if present else math.nan;apply=allowed and math.isfinite(value) and avail<=origin;ck('unchanged_mask_'+day+f,apply==bool(m.proposed_same_day_applied) and bool(m.fallback)==(not apply))
            if apply:ck('frozen_KR_value_time_'+day+f,np.isclose(value,m.proposed_native_value,rtol=1e-10,atol=1e-10) and datetime.datetime.fromisoformat(m.conditional_available_at_ET)==avail and avail<=origin);newkr.loc[date,f]=value
            application.append(dict(date=day,year=date.year,feature=f,applied=apply,fallback=not apply,reason=m.reason,conditional_available_ET=str(avail) if apply else '',origin_ET=str(origin),corrected_fallback_value=corrected.loc[date,f],actual_value=newkr.loc[date,f]))
    csv('KR_FROZEN_MASK_APPLICATION.csv',application);ck('KR_other48_identical_values_nan',newkr[other48].equals(corrected[other48]) and np.array_equal(newkr[other48].isna(),corrected[other48].isna()))
    app=pd.DataFrame(application);pivot=app.pivot(index='date',columns='feature',values='applied');pivot.index=pd.to_datetime(pivot.index);ck('fixed_6450_4230_applied_cells',pivot[pivot.index.year<2017].to_numpy().sum()==6450 and pivot[pivot.index.year>=2017].to_numpy().sum()==4230)
    for f in krcols:ck('corrected_fallback_'+f,newkr.loc[~pivot[f],f].equals(corrected.loc[~pivot[f],f]))
    krchanges=[]
    for f in cols:
        diff=~np.isclose(newkr[f],oldkr[f],rtol=1e-12,atol=1e-12,equal_nan=True)
        for date in newkr.index[diff]:krchanges.append(dict(policy='CORRECTED_A1_KR_ONLY',date=str(date.date()),year=date.year,feature=f,old_value=oldkr.loc[date,f],new_value=newkr.loc[date,f],masked_same_day=bool(pivot.loc[date,f]) if f in krcols else False))
    csv('KR_CORRECTION_CHANGED_CELLS.csv',krchanges)
    sox=sources[2];truth=(sox.Close>sox.Close.shift()).astype(int);truth.index=pd.to_datetime(sox.Date);ck('Y_actual_previous_US_close',np.array_equal(truth.reindex(old.index),old.Y));ck('2495_rows_1007_eval',len(old)==2495 and len(old[old.index.year>=2017])==1007 and old.index.max().year==2020);ck('09_origin',old.origin_et.str.contains('09:00:00').all())
    folds=[];cache=[];labels=pd.to_datetime(old.label_available_et,utc=True);meta={f['fold']:f for f in json.loads((V/'logs/FOLD_DETAILS.json').read_text()) if f['scenario']=='C_latest_monthly_expanding' and f['group']=='M1' and f['algorithm']=='LogisticClassifier'}
    for month in pd.period_range('2017-01','2020-12',freq='M'):
        te=old[old.index.to_period('M')==month];origin=pd.to_datetime(te.iloc[0].origin_et,utc=True);tr=old[(old.index<te.index[0])&(labels<origin)];m=meta[str(month)];ck('mature_fold_'+str(month),len(tr)==m['train_n'] and str(tr.index.min().date())==m['train_start'] and str(tr.index.max().date())==m['train_end'] and tr.Y.nunique()==2 and (pd.to_datetime(tr.label_available_et,utc=True)<origin).all())
        folds.append(dict(month=str(month),origin=str(origin),train_n=len(tr),train_start=str(tr.index[0].date()),train_end=str(tr.index[-1].date()),max_label_available=str(pd.to_datetime(tr.label_available_et,utc=True).max()),test_n=len(te)))
        for policy,new,previous in [('CORRECTED_R0',corrected,old),('CORRECTED_A1_KR_ONLY',newkr,oldkr)]:
            same=new.loc[tr.index,cols].equals(previous.loc[tr.index,cols]);cache.append(dict(policy=policy,month=str(month),training_X_identical_to_legacy=same,training_Y_identical=True,reuse_eligible=False,reason='changed_initial_training_X' if not same else 'requires_full_cache_validation; no reuse requested'))
    ck('all96_training_X_changed',not any(r['training_X_identical_to_legacy'] for r in cache));csv('FOLD_PREFLIGHT.csv',folds);csv('CACHE_REUSE_ASSESSMENT.csv',cache)
    corrected.to_csv(O/'data/CORRECTED_R0_1D.csv',encoding='utf-8-sig');newkr.to_csv(O/'data/CORRECTED_A1_KR_ONLY_1D.csv',encoding='utf-8-sig');csv('PREFLIGHT_CHECKS.csv',CHECKS)
    js('PREFLIGHT_RESULT.json',dict(status='PASS',new_fits=0,checks=len(CHECKS),fast_sources=sorted(fast),source_date_duplicate_rows=sum(r['duplicate_rows'] for r in dups),conflicts=0,R0_changed_cells=len(changes),KR_changed_cells=len(krchanges),input_mask_sha256=sha(maskfile),RAW_hashes=rawhashes,corrected_R0_file_sha256=sha(O/'data/CORRECTED_R0_1D.csv'),corrected_KR_file_sha256=sha(O/'data/CORRECTED_A1_KR_ONLY_1D.csv'),expected_new_fits=96,budget=96,legacy_cache_reusable=0,conditional_information_only=True))
    print('PREFLIGHT PASS; R0 cells',len(changes),'KR correction cells',len(krchanges),'; new fits still0; planned96.',flush=True)
if __name__=='__main__':
    try:main()
    except Exception as e:js('PREFLIGHT_RESULT.json',dict(status='FAIL',error=repr(e),new_fits=0,action='STOP; no training or source correction beyond this run'));raise
