"""Research D Phase0/1. Reads existing inputs; writes only research_D."""
import os,sys,json,hashlib,csv,re,shutil,stat
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'research_D'
for d in ['inputs','data','models','predictions','logs','qc','config']: (OUT/d).mkdir(parents=True,exist_ok=True)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def js(name,x): (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def text(name,x): (OUT/name).write_text(x,encoding='utf-8')
def csvout(name,x): pd.DataFrame(x).to_csv(OUT/name,index=False,encoding='utf-8-sig')
def read(p):
    for enc in ['utf-8-sig','cp949']:
        try:return pd.read_csv(p,comment='#',encoding=enc),enc
        except UnicodeDecodeError:pass
    raise ValueError('Unknown encoding '+str(p))
def protect():
    target=OUT/'inputs/PROTECTED_BEFORE.csv'
    if target.exists(): raise RuntimeError('Do not overwrite an existing baseline')
    rows=[]
    for base,ds,fs in os.walk(ROOT,followlinks=False):
        ds[:]=[d for d in ds if d not in ['research_D','.venv','.venv_W1','.git']]
        for n in fs:
            p=Path(base)/n
            if p.is_symlink():raise RuntimeError('Unexpected link '+str(p))
            rows.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
            if len(rows)%2000==0:print('Protection snapshot',len(rows),flush=True)
    csvout('inputs/PROTECTED_BEFORE.csv',rows)
    print('Protected',len(rows),flush=True)

def audit():
    raw=ROOT/'data/raw'; inv=[]; prov=[]; pit=[]; catalog=[]; tables={}; rawfiles=[]
    # Only market observations publicly determined at their EOD are eligible.
    # Unverified publication/revision archives are held out rather than silently lagged.
    eligible={1,2,4,5,6,7,8,9,10,12,13,14,23,27,28,29,30,31,40,41,46,47}
    risk={5,6,7,8,27,28,29,30,31,40,41}
    overlap={14,23,46,47}
    def group(k):
        if k==2:return 'SOX'
        if k in {4,12}:return 'major_indices'
        if k in {46,47}:return 'semiconductor_ETF'
        if k in {8,27}:return 'risk'
        if k in {3,9,10,15,16,17,18}:return 'rates_FX_bonds'
        if k in {7,11,28,29,36}:return 'sentiment'
        if k in {5,6,30,31,40,41}:return 'breadth'
        if k in {19,20,21,48,49,50,51,52}:return 'macro'
        if k in {14,22,23,24,25,32,37}:return 'industry'
        return 'other'
    for p in sorted(raw.rglob('*')):
        if p.is_file():rawfiles.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    csvout('inputs/RAW_ALL_FILES.csv',rawfiles)
    for folder in sorted(raw.iterdir()):
        if not folder.is_dir():continue
        paths=sorted(folder.glob('*RAW*.csv'))
        if not paths:raise RuntimeError('No canonical RAW '+str(folder))
        k=int(folder.name[:2])
        for p in paths:
            df,enc=read(p); dc='Date' if 'Date' in df else 'statement_date'
            dates=pd.to_datetime(df[dc],errors='coerce'); num=df.select_dtypes(include='number')
            header=p.open(encoding=enc).readline().strip()
            status='ELIGIBLE_MARKET_EOD' if k in eligible else 'HOLD'
            why='Public market EOD observation; 2-US-session conservative embargo; historical delivery timestamps not archived'
            if k==11:why='Current hash differs from recorded refresh output; historical delivery/vintage unverified'
            elif k==42:why='Begins 2021; no 2011-2020 development observations; equal-weight ESOX is not SOX'
            elif k not in eligible:why='Historical release/vintage not verified; lag alone cannot remove revision/lookahead risk'
            dup=int(dates.duplicated().sum())
            multi=''
            if k==24:
                keydup=int(df.duplicated(['Date','HS_Code']).sum());multi=f'Date duplicates={dup}; Date+HS_Code duplicates={keydup}; distinct HS codes={df.HS_Code.nunique()}; do not sum totals/subcategories without classification review'
                if keydup:why+='; duplicate item keys'
            outliers={}
            for c in num:
                s=num[c].dropna(); med=s.median(); mad=(s-med).abs().median()
                outliers[c]=int(((s-med).abs()>10*1.4826*mad).sum()) if mad>0 else None
            rec={'dataset_id':folder.name,'path':p.relative_to(ROOT).as_posix(),'encoding':enc,'rows':len(df),'columns':'|'.join(df.columns),'min_date':str(dates.min().date()),'max_date':str(dates.max().date()),'median_gap_days':dates.drop_duplicates().sort_values().diff().dt.days.median(),'missing_fraction':df.isna().to_numpy().mean(),'missing_by_column':json.dumps(df.isna().mean().to_dict()),'duplicate_dates':dup,'duplicate_full_rows':int(df.duplicated().sum()),'invalid_dates':int(dates.isna().sum()),'robust_outlier_counts':json.dumps(outliers),'multi_observation_review':multi,'sha256':sha(p),'source_header':header,'group':group(k),'eligibility':status,'reason':why}
            inv.append(rec)
            prov.append({'path':rec['path'],'sha256':rec['sha256'],'bytes':p.stat().st_size,'source_header':header,'historical_vintage':'UNVERIFIED_CURRENT_ARCHIVE','status':status,'reason':why})
            pit.append({'dataset_id':folder.name,'path':rec['path'],'group':group(k),'status':status,'availability_rule':'second_US_session_strictly_after_observation_at_08:00_ET' if k in eligible else 'NOT_USED','actual_historical_delivery_time':'UNVERIFIED','revision_policy':'non-dividend-adjusted Close ratios only; current vendor corrections remain a limitation' if k in eligible else 'excluded without release/vintage proof','reason':why})
            catalog.append({'dataset_id':folder.name,'path':rec['path'],'group':group(k),'stage':('M0' if k==2 else 'M2' if k in risk else 'M1') if k in eligible else 'HOLD_M3_OR_SENSITIVITY','high_SOX_overlap':k in overlap,'candidate':'return_1_5_20, vol20, gap_to_MA20' if 'Close' in df else 'level, delta1, delta5','eligible':k in eligible,'reason':why})
            if k in eligible:
                assert dc=='Date' and dup==0 and dates.notna().all(),rec
                df.index=dates;df=df.drop(columns=[dc]).sort_index();df=df.loc[df.index<='2020-12-31']
                tables[k]=(df,rec)
    csvout('RAW_INVENTORY.csv',inv);csvout('RAW_PROVENANCE_AND_HASH_AUDIT.csv',prov);csvout('POINT_IN_TIME_AUDIT.csv',pit);csvout('FEATURE_CANDIDATE_CATALOG.csv',catalog)
    prior=pd.read_csv(ROOT/'archives/research_C_PROTECTED_HASH_AUDIT_20261019.csv')
    anomalies=prior[prior.result!='PASS'];csvout('qc/PRIOR_BACKUP_ANOMALIES.csv',anomalies)
    # Independent local verification: source-to-canonical exact values and recorded source hash.
    p=ROOT/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv'
    q=ROOT/'data/metadata/RAW_REFRESH_20261009/source_downloads/02_sox_SOX_20110101_20261009_yfinance.csv'
    a,_=read(p);b,_=read(q)
    assert a.equals(b) and sha(p)=='00aecd96d4501eee1ad9e36f24a282239e03982612df931287505aa37c37faa5'
    assert sha(q)=='7376af3d67b493488f266e426be0b2eef0bca0742ed9b45638636b7e09f2c39b'
    calpath=ROOT/'research_C/phase2_weekly_dataset/build_v1_1/calendar/US_MARKET_SESSIONS.csv'
    cal=pd.read_csv(calpath);cal=cal[(cal.session_date>='2010-01-01')&(cal.session_date<='2020-12-31')].copy()
    ds=pd.to_datetime(cal.session_date); truth=set(ds[ds>='2011-01-01']);actual=set(pd.to_datetime(a.Date)[pd.to_datetime(a.Date)<='2020-12-31'])
    assert truth==actual
    assert (a.Close>0).all() and (a.High>=a.Low).all() and not a.Date.duplicated().any()
    csvout('inputs/US_MARKET_SESSIONS_DEV.csv',cal)
    js('qc/SOX_SOURCE_VERIFICATION.json',{'canonical_sha256':sha(p),'download_sha256':sha(q),'exact_all_columns_equal':True,'development_sessions':len(truth),'calendar_sha256':sha(calpath),'missing_sessions':0,'independent_provider_verification':False,'note':'Independent computation against preserved vendor source and recorded hashes; not an independent provider or historical tick archive'})
    # Examine available chronology without rewriting any historic records.
    recent=json.loads((ROOT/'research_C/phase4_final_test/execution_v1_0/inputs/PHASE4_INPUT_MANIFEST.json').read_text(encoding='utf-8-sig'))['protected_files']
    fgi=json.loads((ROOT/'data/metadata/FGI_REFRESH_20261016/FGI_REFRESH_QC.json').read_text(encoding='utf-8-sig'))
    chronology={'prior_backup_status':'FAIL','prior_failures':len(anomalies),'unique_paths':anomalies.path.nunique(),'project_index_latest_phase4_hash':recent['RESEARCH_PROJECT_INDEX.md']['sha256'],'project_index_current_hash':sha(ROOT/'RESEARCH_PROJECT_INDEX.md'),'FGI_refresh_recorded_hash':fgi['output_sha256'],'FGI_current_hash':sha(ROOT/fgi['output'].replace('\\','/')),'FGI_phase4_recorded_hash':recent.get('data/raw/11_cnn_fgi/11_cnn_fgi_RAW_20110101_20261015.csv'),'FGI_resolution':'Excluded. Refresh record does not explain current change; no fabricated authorization.','missing_FRED26_resolution':'Absent; never used. Yahoo SOX verified separately.','index_resolution':'Current index agrees with Phase4 baseline but differs from Phase1 historic snapshots; later approved append noted in Phase2 history. No historic manifest edited.'}
    js('qc/BACKUP_ANOMALY_INVESTIGATION.json',chronology)
    text('PHASE0_RAW_AUDIT.md',f'''# Phase 0 RAW 전수 감사

원천 유형 {len(set(x['dataset_id'] for x in inv))}개, canonical CSV {len(inv)}개, RAW 하위 전체 일반 파일 {len(rawfiles)}개를 조사했습니다. 현재 시장 EOD 후보 {len(tables)}유형, 보류 {len(set(x['dataset_id'] for x in inv))-len(tables)}유형입니다. 43번 VW/EW는 별도 CSV이며 같은 원천 유형입니다.

RAW_INVENTORY에 기간·행·컬럼·결측·날짜중복·MAD 이상치 표시·출처·SHA를 기록했습니다. 이상치 표시는 삭제 기준이 아닙니다. 24번은 날짜가 아니라 Date+HS_Code 키를 검사했으며 품목 중복/상하위 합산 위험 때문에 기본 실험에서 제외했습니다. 원천 간 중복 정보는 catalog의 정보군과 high_SOX_overlap으로 구분하고 학습 내부 상관 필터에서 처리합니다.

SOX는 보존 다운로드 원본과 모든 값이 같고 기존 기록 SHA도 일치합니다. 개발 거래일 2,517개를 달력과 대조해 누락·추가 0개입니다. 다른 공급원 검증은 아니며 신규 수집하지 않았습니다.

기존 백업 이상 18건/4경로는 qc/PRIOR_BACKUP_ANOMALIES.csv에 보존했습니다. 최신 Phase4 인덱스와 과거 Phase1 인덱스의 버전 차이를 구분했습니다. FGI는 refresh 보고의 해시와 현재 해시가 달라 미해결로 제외합니다. FRED26 파일은 없고 동일가중 ESOX42로 대체하지 않습니다.

거시·월간 산업·AAII·French·FOMC·FRED 환율/금리는 release/vintage/사전 일정 증거가 불충분해 보류했습니다. 단순 지연으로 수정본 누출이 해결됐다고 주장하지 않습니다. M3은 신규 적격 자료가 없어 M2와 같고 별도 효과 추정은 불가능합니다.

시장 EOD 자료도 실제 과거 벤더 전송시각은 보관돼 있지 않습니다. 따라서 이 연구는 공개된 시장 관측에 2 미국 세션 지연을 적용한 보수적 **조건부 역사 실험**이며 완전한 point-in-time 실시간 재현을 주장하지 않습니다. 배당 조정종가·가격 절대수준을 사용하지 않고 Close 비율을 사용하지만 벤더 정정/분할 처리의 빈티지 한계는 남습니다.
''')
    return tables,cal,catalog

def build(tables,cal,catalog):
    sessions=pd.DatetimeIndex(pd.to_datetime(cal.session_date)); core=tables[2][0]['Close'].astype(float)
    # Truncate first, derive second. No feature calculation ever touches post-2020 values.
    feats={}; feature_rows=[]; availability={}; observation={}
    for k,(df,rec) in tables.items():
        nums=df.apply(pd.to_numeric,errors='coerce')
        prefix=f's{k:02d}'; derived={}
        if 'Close' in nums and k not in {28,29,30,31,40,41}:
            s=nums.Close
            for lag in [1,5,20]:derived[f'ret{lag}']=100*s.pct_change(lag,fill_method=None)
            derived['vol20']=100*s.pct_change(fill_method=None).rolling(20,min_periods=20).std(ddof=1)
            derived['ma20_gap']=100*(s/s.rolling(20,min_periods=20).mean()-1)
        else:
            if k==5:s=(nums.New_Highs_52W-nums.New_Lows_52W)/(nums.New_Highs_52W+nums.New_Lows_52W).replace(0,np.nan)
            elif k==6:s=(nums.Advancing_Volume-nums.Declining_Volume)/(nums.Advancing_Volume+nums.Declining_Volume).replace(0,np.nan)
            elif 'Close' in nums:s=nums.Close
            else:s=nums.iloc[:,0]
            derived={'level':s,'delta1':s.diff(),'delta5':s.diff(5)}
        # Public EOD event embargo: second actual US session strictly after observation.
        idx=sessions.searchsorted(df.index,side='right')+1
        valid=idx<len(sessions); avail=sessions[idx[valid]]
        for key,values in derived.items():
            name=f'{prefix}_{key}'; vv=values[valid].to_numpy(dtype=float)
            events=pd.DataFrame({'available':avail,'source':df.index[valid],'value':vv}).sort_values('available').drop_duplicates('available',keep='last')
            left=pd.DataFrame({'date':sessions})
            joined=pd.merge_asof(left,events,left_on='date',right_on='available',direction='backward')
            age=(joined.date-joined.source).dt.days
            good=age.le(10)
            feats[name]=pd.Series(joined.value.where(good).to_numpy(),index=sessions)
            availability[name]=pd.Series(joined.available.where(good).to_numpy(),index=sessions)
            observation[name]=pd.Series(joined.source.where(good).to_numpy(),index=sessions)
            row=next(x for x in catalog if int(x['dataset_id'][:2])==k)
            formula={'ret1':'100*(Close[t]/Close[t-1]-1)','ret5':'100*(Close[t]/Close[t-5]-1)','ret20':'100*(Close[t]/Close[t-20]-1)','vol20':'100*std20(Close.pct_change,ddof=1)','ma20_gap':'100*(Close/mean20(Close)-1)','level':('NYSE normalized breadth (high-low)/(high+low)' if k==5 else '(adv-dec)/(adv+dec)' if k==6 else 'raw indicator level'),'delta1':'indicator[t]-indicator[t-1]','delta5':'indicator[t]-indicator[t-5]'}[key]
            feature_rows.append({'feature':name,'source_path':rec['path'],'source_sha256':rec['sha256'],'source_type':k,'information_set_first':row['stage'],'formula':formula,'frequency':'native_daily_then_asof','availability_rule':'2nd actual US session after source date,08:00 America/New_York','actual_delivery_time_verified':False,'staleness_max_calendar_days':10,'uses_adjusted_close':False,'high_SOX_overlap':row['high_SOX_overlap']})
    X=pd.DataFrame(feats,index=sessions).replace([np.inf,-np.inf],np.nan)
    groups={}
    groups['M0']=[r['feature'] for r in feature_rows if r['information_set_first']=='M0']
    groups['M1']=[r['feature'] for r in feature_rows if r['information_set_first'] in {'M0','M1'}]
    groups['M2']=list(X.columns);groups['M3']=groups['M2'];groups['M4']=groups['M2']
    js('config/INFORMATION_SETS.json',{g:{'candidate_count':len(v),'columns':v,'note':'M4 is a train-only selection recipe; actual columns vary by fold' if g=='M4' else 'M3 identical to M2; no proven macro vintages' if g=='M3' else ''} for g,v in groups.items()})
    csvout('FEATURE_DICTIONARY.csv',feature_rows)
    data={};lineage=[]
    daily=core.to_frame('end_close');daily['start_close']=core.shift(1);daily['label_end']=daily.index
    # Calendar-week ending Friday includes holidays naturally; no overlapping labels.
    wg=core.groupby(core.index.to_period('W-FRI'))
    weekly=pd.DataFrame({'end_close':wg.last(),'start_close':wg.last().shift(1),'label_end':wg.apply(lambda s:s.index[-1]),'date':wg.apply(lambda s:s.index[0])}).set_index('date')
    for horizon,y in [('1D',daily),('1W',weekly)]:
        y=y.copy(); y['return_pct']=100*(y.end_close/y.start_close-1)
        y=y.loc[(y.index>='2011-01-01')&(y.index<='2020-12-31')&y.return_pct.notna()]
        y=y.join(X);y=y.loc[y[groups['M0']].notna().all(axis=1)]
        y['Y']=(y.return_pct>0).astype(int);y['origin_et']=[d.tz_localize('America/New_York')+pd.Timedelta(hours=9) for d in y.index]
        y['label_available_et']=[pd.Timestamp(d).tz_localize('America/New_York')+pd.Timedelta(hours=20) for d in y.label_end]
        y.index.name='date';y.to_csv(OUT/f'data/DEV_{horizon}.csv',encoding='utf-8-sig')
        data[horizon]=y
        for name in X:
            av=availability[name].reindex(y.index);obs=observation[name].reindex(y.index)
            for d,a,o,v in zip(y.index,av,obs,y[name]):
                if pd.notna(v):
                    assert pd.notna(a) and o<a<=d
                    lineage.append({'horizon':horizon,'date':str(d.date()),'feature':name,'source_observation_date':str(pd.Timestamp(o).date()),'modeled_available_at_et':str(pd.Timestamp(a).tz_localize('America/New_York')+pd.Timedelta(hours=8)),'origin_et':str(y.loc[d,'origin_et']),'value':v,'timing_status':'CONSERVATIVE_MARKET_EOD_ASSUMPTION_NOT_ARCHIVED_DELIVERY'})
    csvout('data/FEATURE_AVAILABILITY.csv',lineage)
    counts={h:{'total':len(y),'initial':int((y.index.year<=2016).sum()),'dev':int((y.index.year>=2017).sum()),'class1_dev':float(y.loc[y.index.year>=2017,'Y'].mean()),'zero_returns':int((y.return_pct==0).sum()),'max_date':str(y.index.max()),'feature_count':len(X.columns)} for h,y in data.items()}
    js('qc/DATASET_COUNTS.json',counts)
    text('TARGET_SPEC_1D_1W.md','''# 1D·1W Y와 예측시점

1D는 실제 거래일 09:00 America/New_York에 직전 실제 거래일 Close 대비 당일 Close 수익률을 예측합니다. 1W는 미국 달력주 첫 실제 거래일 09:00에 직전 주 마지막 실제 거래일 Close 대비 해당 주 마지막 실제 거래일 Close 수익률을 예측합니다. 둘 다 R=100*(end/start-1), Y=int(R>0), 보합은0입니다.

미국 세션 달력은 기존 보존 달력의 개발기간 부분을 복사했고 SOX 거래일과 전수 일치합니다. 주 경계는 W-FRI(토요일~금요일)로 평일 시장주와 같으며 월요일 휴일에는 화요일 등이 origin입니다. 2012 Sandy와 2018 Bush 휴장 등 달력 예외가 포함됩니다. 조기폐장도 하나의 거래세션으로 유지하고 수익률은 실제 종가를 씁니다. 달력에는 early_close와 실제 개폐장 시각이 있습니다. 매일 timestamp를 자정에 지역화한 뒤09시를 더해 DST를 반영합니다. 라벨은 목표 마지막 세션20시에 성숙한 것으로 보수적으로 처리해 origin 이후 Y를 학습하지 않습니다.

원천이 끝난 불완전 주는 생성하지 않습니다. 개발자료는 2020-12-31에서 끝나며 그 날은 실제 해당 주 마지막 세션입니다. 초기 예열 결측 행은 제외합니다. 주간 라벨은 각각 다른 달력주로 비중첩입니다. 2021년 이후 Y는 생성·평가하지 않았습니다.
''')
    text('DATASET_BUILD_SPEC.md','''# 데이터셋 구축

데이터는 날짜 기준으로 먼저 2020-12-31까지 잘라 파생변수를 만듭니다. 22 시장 원천의 비조정 Close 비율/지표 차분/과거 이동통계를 사용합니다. 각 값은 원천일 이후 두 번째 실제 미국 세션08시에 이용 가능한 것으로 모델링하고10달력일 초과된 자료는 결측 처리합니다. as-of join은 과거 방향만 사용합니다. 실제 과거 전송시각 검증이 아니라 조건부 가정임을 모든 lineage에 명시했습니다. ETF Adj Close는 사용하지 않습니다.

모든 비교는 동일한 horizon별 날짜를 사용하고 결측은 fold 학습 중앙값으로만 처리합니다. 전체자료 정규화·PCA·변수선택·미래 보간은 없습니다. SOX M0 예열 결측만 공통 제거합니다. source별 모든 관측을 강제 교집합으로 줄이지 않습니다. 늦게 시작한 42번은 별도 보류하며 이 개발 실험에서 평가하지 않습니다.

M0~M4 후보 실제 컬럼은 config/INFORMATION_SETS.json에 있습니다. M4 실제 선택 컬럼은 fold별 학습 로그에 남깁니다. M3에 적격 신규 거시·산업 공개빈티지가 없어 M2와 동일하며 추가 실험을 중복 실행하지 않습니다. 타이완 지수·TSM·ETF 등 일별 산업 대리변수는 M1에 포함하고 별도 제거 실험으로 구분합니다.
''')
    qc='# Phase 1 데이터셋 QC\n\n'+json.dumps(counts,ensure_ascii=False,indent=2)+'\n\nSOX source/hash/달력 대조 PASS. 모든 비결측 feature는 source_date < modeled_available_date <= origin_date이며 modeled_available_at=08:00 < origin=09:00입니다. source-date 기반 shift와 as-of join을 검증했습니다. 실제 벤더 공개시각·모든 역사적 수정본 검증을 통과했다는 뜻은 아닙니다. FGI, 거시/월간 수정자료는 제외했습니다.\n'
    text('PHASE1_DATASET_QC.md',qc);text('DATASET_QC_REPORT.md',qc)
    print('Datasets',counts,flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    protect()
    shutil.copyfile(Path(r'C:\Users\rudck\.codex\attachments\c662ffd1-29d2-4c14-82a2-d3de4bf13908\Pasted text.txt'),OUT/'inputs/USER_INSTRUCTION.txt')
    t,c,cat=audit();build(t,c,cat)
