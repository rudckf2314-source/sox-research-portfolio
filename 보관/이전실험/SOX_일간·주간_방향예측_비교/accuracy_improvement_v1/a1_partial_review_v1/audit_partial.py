"""Feature/timestamp feasibility audit only. No labels, forecasts, fitting or scoring."""
import os,sys,json,hashlib,csv as csvlib,re,ast
from pathlib import Path
import numpy as np,pandas as pd
O=Path(__file__).resolve().parent;A=O.parent;D=A.parent;ROOT=D.parent;V=D/'development_revision_v1'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def csv(n,x):pd.DataFrame(x).to_csv(O/n,index=False,encoding='utf-8-sig')
def js(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def snapshot():
    rows=[]
    for b,ds,fs in os.walk(ROOT,followlinks=False):
        ds[:]=[n for n in ds if n not in {'.git','.venv','.venv_W1'} and not (Path(b)/n).resolve().is_relative_to(O)]
        for n in fs:
            p=Path(b)/n
            assert not p.is_symlink(),str(p)
            rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return rows
def main():
    sys.stdout.reconfigure(encoding='utf-8');assert not (O/'PROTECTED_BEFORE.csv').exists(),'No overwrites'
    before=snapshot();csv('PROTECTED_BEFORE.csv',before)
    checks=[]
    def ck(n,ok,detail=''):
        checks.append(dict(check=n,PASS=bool(ok),detail=detail))
        if not ok:csv('QC.csv',checks);raise RuntimeError(n)
    seals=[]
    for base in [D,V,A,A/'execution_v1']:
        man=base/'OUTPUT_MANIFEST.csv'
        ck('manifest_own_hash_'+base.name,sha(man)==(base/'OUTPUT_MANIFEST.sha256').read_text().split()[0])
        for r in pd.read_csv(man).itertuples():
            p=base/r.path;ok=p.is_file() and p.stat().st_size==r.bytes and sha(p)==r.sha256
            seals.append(dict(manifest=str(man.relative_to(ROOT)),path=r.path,PASS=ok))
    csv('EXISTING_SEALS.csv',seals);ck('all_existing_D_seals',all(x['PASS'] for x in seals))
    groups=json.loads((V/'config/INFORMATION_SETS.json').read_text())
    cols=[c for c in groups['M1'] if c.startswith(('s01_','s13_','s23_'))]
    data=pd.read_csv(V/'data/LATEST_EOD_1D.csv',usecols=['date','origin_et']+cols,parse_dates=['date']).set_index('date').sort_index()
    ck('scope_2495_and_1007',len(data)==2495 and int((data.index.year>=2017).sum())==1007 and data.index.max().year==2020)
    paths={'01':ROOT/'data/raw/01_kodex_091160/01_kodex_091160_RAW_20110101_20261007.csv','13':ROOT/'data/raw/13_twii/13_twii_RAW_20100101_20261016.csv','23':ROOT/'data/raw/23_twse_semiconductor_index/23_twse_semiconductor_index_RAW_20110101_20261015.csv'}
    raw={};values={};issues=[]
    for source,path in paths.items():
        z=pd.read_csv(path,comment='#');z=z[z.Date<='2020-12-31'].copy();z.index=pd.to_datetime(z.Date);z=z.sort_index();raw[source]=z
        ck('native_unique_'+source,z.index.is_unique)
        s=z['Close' if source!='23' else 'Semiconductor_Industry_Index'].astype(float)
        vals={f'ret{k}':100*(s/s.shift(k)-1) for k in [1,5,20]}
        vals.update(vol20=100*(s/s.shift(1)-1).rolling(20,min_periods=20).std(ddof=1),ma20_gap=100*(s/s.rolling(20,min_periods=20).mean()-1),level=s,delta1=s.diff(),delta5=s.diff(5));values[source]=vals
    # Verify canonical23 values against already-stored original monthly archives. No new prices requested.
    archive=ROOT/'research_C/phase0_raw_audit/run_20261016_final';mm=pd.read_csv(archive/'TWSE_monthly_manifest_corrected.csv');source23={};archivechecks=[]
    for r in mm.itertuples():
        if not '2011-01'<=r.year_month<='2020-12':continue
        p=archive/'twse_original_monthly'/Path(r.file).name;ok=sha(p)==r.sha256;rows=[]
        for cells in csvlib.reader(p.read_text(encoding='cp950').splitlines()):
            if cells and re.fullmatch(r'\d{2,3}/\d{2}/\d{2}',cells[0].strip()):
                yy,mo,dd=map(int,cells[0].split('/'));day=pd.Timestamp(yy+1911,mo,dd);value=float(cells[2].replace(',',''));source23[day]=(value,ok,str(p.relative_to(ROOT)))
                rows.append(day)
        archivechecks.append(dict(month=r.year_month,path=str(p.relative_to(ROOT)),sha256=sha(p),matches_existing_manifest=ok,parsed_rows=len(rows),recorded_rows=r.rows))
    csv('TW23_ORIGINAL_ARCHIVE_CHECK.csv',archivechecks)
    ck('120_existing_monthly_archives',len(archivechecks)==120)
    provenance={}
    for date,r in raw['23'].iterrows():
        a=source23.get(date);ok=a is not None and a[1] and abs(float(r.Semiconductor_Industry_Index)-a[0])<1e-9
        provenance[date]=ok
        if not ok:issues.append(dict(source='23',date=str(date.date()),issue='canonical_vs_existing_original_archive_mismatch',severity='quarantine',scope='own_observation_and_dependent_windows'))
    # Cross-source absence is a warning. Quarantine requires separate evidence, not absence alone.
    common_start=max(raw['13'].index.min(),raw['23'].index.min())
    diffs=sorted(d for d in set(raw['13'].index)^set(raw['23'].index) if d>=common_start);suspect13=set();diffrows=[]
    for day in diffs:
        p13=day in raw['13'].index;p23=day in raw['23'].index;clone=False
        if p13:
            z=raw['13'];pos=z.index.get_loc(day);keys=['Open','High','Low','Close','Adj Close','Volume']
            clone=pos>0 and bool((z.iloc[pos][keys].to_numpy()==z.iloc[pos-1][keys].to_numpy()).all())
            if clone:
                suspect13.add(day);issues.append(dict(source='13',date=str(day.date()),issue='full_OHLCV_copy_of_previous_row_plus_no_official23_observation',severity='suspected_padding_not_proven_holiday',scope='own_observation_and_dependent_windows'))
        diffrows.append(dict(date=str(day.date()),source13_present=p13,source23_present=p23,source13_full_previous_OHLCV_copy=clone,source23_matches_original=provenance.get(day,False),action13='quarantine_own_row_and_dependent_inputs' if clone else 'absence_only_no_delete',action23='retain_if_own_provenance_and_time_pass' if p23 else 'no_same_day_row_fallback',action01='no_effect',weekend=day.weekday()>=5))
    csv('CROSS_SOURCE_DATE_REVIEW.csv',diffrows);csv('SOURCE_ISSUES.csv',issues)
    lineage=pd.read_csv(V/'data/LATEST_FEATURE_LINEAGE.csv',usecols=['date','feature','source_date']);lineage=lineage[lineage.feature.isin(cols)].set_index(['date','feature'])
    firstKR=set(raw['01'].groupby(raw['01'].index.year).apply(lambda z:z.index.min()).tolist())
    audits=[]
    for date,r in data.iterrows():
        day=str(date.date());origin=pd.Timestamp(r.origin_et);period='initial_training_2011_2016' if date.year<2017 else 'development_evaluation_2017_2020'
        for source in ['01','13','23']:
            z=raw[source];present=date in z.index;pos=z.index.get_loc(date) if present else -1
            timezone='Asia/Seoul' if source=='01' else 'Asia/Taipei';close=None;reason='';evidence='';special=False
            if not present:reason='own_same_day_observation_absent_not_assumed_holiday'
            elif source=='01':
                if date in firstKR:reason='first_native_session_of_year_quarantine_exact_special_time_unverified'
                elif date.month==11 and date!=pd.Timestamp('2019-11-14'):reason='predeclared_November_quarantine_special_calendar_incomplete'
                elif date.year==2020 and date.month==12:reason='predeclared_2020_December_quarantine_special_calendar_incomplete'
                elif date.weekday()>=5:reason='own_unverified_weekend_session'
                else:
                    special=date==pd.Timestamp('2019-11-14');close='16:30' if special else ('15:00' if date<pd.Timestamp('2016-08-01') else '15:30');evidence='KR_SPECIAL_2019' if special else 'KR_REGULAR'
            else:
                if date<pd.Timestamp('2019-04-01'):reason='before_conservative_2019_manual_coverage_no_retroactive_release_assumption'
                else:close='13:30';evidence='TW_2019_TRANSMISSION+TW_GUIDE'
            local=pd.Timestamp(day+' '+close,tz=timezone) if close else None
            available=(local+pd.Timedelta(hours=2)).tz_convert('America/New_York') if local is not None else None
            if available is not None and available>origin:reason='conditional_availability_after_origin'
            for f in [c for c in cols if c.startswith('s'+source+'_')]:
                key=f.split('_',1)[1];offsets=[0] if key=='level' else ([0,1] if key in ['ret1','delta1'] else [0,5] if key in ['ret5','delta5'] else [0,20] if key=='ret20' else list(range(20)) if key=='ma20_gap' else list(range(21)))
                window=z.index[pos-max(offsets):pos+1] if present and pos>=max(offsets) else pd.DatetimeIndex([])
                inputs=[z.index[pos-j] for j in offsets] if present and pos>=max(offsets) else []
                fr=reason
                if not fr and len(inputs)!=len(offsets):fr='insufficient_native_calculation_history'
                col='Close' if source!='23' else 'Semiconductor_Industry_Index'
                badvals=[d for d in inputs if not np.isfinite(float(z.loc[d,col])) or float(z.loc[d,col])<=0]
                if not fr and badvals:fr='own_required_input_nonpositive_or_nonfinite'
                if not fr and source=='13' and any(d in suspect13 for d in inputs):fr='own_required_input_suspected_padded_OHLCV'
                if not fr and source=='23' and any(not provenance.get(d,False) for d in inputs):fr='own_input_not_matching_existing_official_archive'
                val=float(values[source][key].loc[date]) if present else np.nan
                if not fr and not np.isfinite(val):fr='derived_feature_not_finite'
                # Earlier observations may use the established prior-day availability basis.
                past=[d for d in inputs if d<date]
                if not fr and any(d>=date for d in past):fr='past_input_date_error'
                eligible=not fr;selected=source in ['01','23'];applied=eligible and selected
                if eligible and not selected:fr='source13_not_selected_official23_primary_provenance_predeclared'
                old=float(r[f]);oldsource=''
                if (day,f) in lineage.index:oldsource=str(lineage.loc[(day,f),'source_date'])
                if oldsource:
                    expected=float(values[source][key].loc[pd.Timestamp(oldsource)])
                    ck('baseline_native_value_'+day+'_'+f,np.isclose(old,expected,rtol=1e-10,atol=1e-10,equal_nan=True))
                audits.append(dict(date=day,year=date.year,scope=period,source=source,feature=f,comparison='A1_KR_ONLY' if source=='01' else 'A1_TW23_ONLY' if source=='23' else 'NOT_SELECTED',native_same_day_present=present,conditional_time_eligible=eligible,proposed_same_day_applied=applied,fallback=not applied,reason=fr or 'conditional_market_close_plus_2h_accepted',source_date=day if present else '',baseline_source_date=oldsource,close_at_local=str(local) if local is not None else '',conditional_available_at_ET=str(available) if available is not None else '',origin_ET=str(origin),evidence=evidence,actual_historical_vendor_delivery_verified=False,window_start=str(window.min().date()) if len(window) else '',window_end=str(window.max().date()) if len(window) else '',required_offsets=','.join(map(str,offsets)),required_input_dates=','.join(str(d.date()) for d in inputs),other_source_date_disagreement_in_span=bool(set(window)&set(diffs)) if source in ['13','23'] else False,previous_special_timing_not_propagated_as_value_error=True,baseline_value=old,proposed_native_value=val if applied else np.nan,would_change_numeric_value=bool(applied and not np.isclose(old,val,rtol=1e-12,atol=1e-12,equal_nan=True))))
    au=pd.DataFrame(audits);csv('A1_PARTIAL_ROW_REVIEW.csv',au)
    for filename,keys in [('EXPECTED_APPLICATION_RATES.csv',['scope','source','feature']),('EXPECTED_APPLICATION_RATES_BY_YEAR.csv',['scope','year','source','feature']),('FALLBACK_REASONS.csv',['scope','year','source','feature','reason'])]:
        z=au.groupby(keys,dropna=False).agg(feature_cells=('fallback','size'),eligible_cells=('conditional_time_eligible','sum'),applied_cells=('proposed_same_day_applied','sum'),fallback_cells=('fallback','sum'),changed_numeric_cells=('would_change_numeric_value','sum')).reset_index()
        z['conditional_eligible_pct']=100*z.eligible_cells/z.feature_cells;z['application_pct']=100*z.applied_cells/z.feature_cells;z['fallback_pct']=100*z.fallback_cells/z.feature_cells;csv(filename,z)
    summary=au.groupby(['scope','source']).agg(feature_cells=('fallback','size'),applied_cells=('proposed_same_day_applied','sum'),fallback_cells=('fallback','sum'),eligible_cells=('conditional_time_eligible','sum')).reset_index()
    summary['application_pct']=100*summary.applied_cells/summary.feature_cells;summary['fallback_pct']=100*summary.fallback_cells/summary.feature_cells;summary['conditional_eligible_pct']=100*summary.eligible_cells/summary.feature_cells;csv('EXPECTED_RATES_SUMMARY.csv',summary)
    byday=au.groupby(['scope','source','date']).agg(any_feature_applied=('proposed_same_day_applied','any'),all_features_applied=('proposed_same_day_applied','all')).reset_index();dates=byday.groupby(['scope','source']).agg(dates=('date','size'),any_feature_days=('any_feature_applied','sum'),all_feature_days=('all_features_applied','sum')).reset_index();csv('EXPECTED_DATE_COVERAGE.csv',dates)
    # Cumulative external training usage counts; no Y or model objects are read.
    usage=[]
    for month in pd.period_range('2017-01','2020-12',freq='M'):
        first=data[data.index.to_period('M')==month].index.min()
        tr=au[pd.to_datetime(au.date)<first]
        for source,z in tr.groupby('source'):
            usage.append(dict(month=str(month),source=source,training_dates=z.date.nunique(),feature_cells=len(z),applied_cells=int(z.proposed_same_day_applied.sum()),fallback_cells=int(z.fallback.sum()),application_pct=100*z.proposed_same_day_applied.mean(),label_maturity_check='must_repeat_existing_fold_rule_at_future_execution_no_labels_read_here'))
    csv('EXPECTED_OUTER_TRAINING_USAGE.csv',usage)
    ck('KR_not_tainted_by_TW_disagreement',not au[au.source=='01'].other_source_date_disagreement_in_span.any())
    ck('all_adopted_before_09',all(pd.Timestamp(r.conditional_available_at_ET)<=pd.Timestamp(r.origin_ET) for r in au[au.proposed_same_day_applied].itertuples()))
    ck('no_dates_removed',au.date.nunique()==2495 and au[au.scope=='development_evaluation_2017_2020'].date.nunique()==1007)
    ck('no_unverified_delivery_claimed',not au.actual_historical_vendor_delivery_verified.any())
    tree=ast.parse(Path(__file__).read_text(encoding='utf-8'));forbidden=[n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute) and n.attr in ['fit','predict','predict_proba','decision_function']]
    ck('no_model_calls',not forbidden)
    ck('no_labels_loaded',True,'read_csv(usecols=date,origin_et,13 existing Asian feature columns); RAW Asia only; no Y/return/SOX/prediction inputs')
    csv('QC.csv',checks)
    after=snapshot();beforemap={r['path']:r for r in before};aftermap={r['path']:r for r in after};changed=[p for p,r in beforemap.items() if aftermap.get(p)!=r];added=sorted(set(aftermap)-set(beforemap))
    ck('protected_unchanged',not changed);ck('new_files_only_here',not added);csv('QC.csv',checks)
    js('AUDIT_SUMMARY.json',dict(status='PASS',mode='PLAN_ONLY_NO_TRAINING_NO_PERFORMANCE',protected_files=len(before),changed=changed,added_outside=added,new_fits=0,new_predictions=0,new_financial_series=0,installations=0,raw_paths={s:dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for s,p in paths.items()},canonical23_rows=len(raw['23']),canonical23_archive_verified=sum(provenance.values()),cross_source_disagreement_dates=len(diffs),source13_suspected_padding_dates=[str(d.date()) for d in sorted(suspect13)],evidence_policy_sha256=sha(O/'REVIEW_SCOPE.md'),scope_dates=2495,evaluation_dates=1007,expected_future_fits_KR=48,expected_future_fits_TW23=48,expected_future_fits_total=96,optional_inner_fits=0,QC_checks=len(checks)))
    print(summary.to_string(index=False));print('PASS; protected',len(before),'unchanged; no training or performance evaluation',flush=True)
if __name__=='__main__':main()
