"""Two explicitly assumed French release lags; no PIT claim; phased evaluation."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,hashlib,warnings
import pandas as pd,numpy as np,joblib
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
W=Path(__file__).resolve().parents[1];O=W/'outputs/french_release_scenarios_v1_20261023';N=W/'outputs/unused_raw_features_v1_20261023';H=W/'outputs/historical_oos_diagnosis_2016_2023_v1_20261022';P=W/'outputs/four_groups_2024_2026_v1_20261022/COMBINED82';R=W/'outputs/reduced_four_groups_v1_20261022/COMBINED82'
POL=['BASE','NEXT20','MONTH2_FIRST'];CS=[.01,.1,1.];SEED=20261019
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def js(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def csv(p,v):pd.DataFrame(v).to_csv(p,index=False,encoding='utf-8-sig')
def prepare():
    O.mkdir(exist_ok=False);(O/'models').mkdir();inv=pd.read_csv(N/'RAW별_생성결과.csv');d=pd.read_csv(N/'변수사전_RAW_계산식_확보조건.csv');rows=inv[inv.source_id.isin([43,44,45])]
    native=pd.concat([pd.read_csv(r.feature_file,index_col=0,float_precision='round_trip') for r in rows.itertuples()],axis=1).sort_index();native.index=pd.to_datetime(native.index);assert native.shape[1]==420 and native.index.is_unique
    # Origins from historical feature table only, no target read.
    origins=pd.read_csv(W/'outputs/unused_raw_aligned09_v1_20261023/ALL562_ALIGNED09_NO_Y.csv',usecols=['date']).date
    out={p:pd.DataFrame(np.nan,index=origins,columns=native.columns) for p in POL[1:]};events=[];line=[]
    for mo,g in native.groupby(native.index.to_period('M')):
        obs=g.index[-1];vals=g.iloc[-1];assert obs.to_period('M')==mo
        for p in POL[1:]:
            start=(mo+(1 if p=='NEXT20' else 2)).to_timestamp()+pd.DateOffset(days=19 if p=='NEXT20' else 0)
            # Boundary must be passed strictly: usable at 09 only after local midnight.
            bound=start.tz_localize('America/New_York');events.append(dict(policy=p,observation_date=str(obs.date()),availability_bound_ET=bound.isoformat(),assumed=True,month=str(mo)))
    e=pd.DataFrame(events)
    for p in POL[1:]:
        ee=e[e.policy==p].copy();ee['utc']=pd.to_datetime(ee.availability_bound_ET,utc=True)
        for day in origins:
            origin=pd.Timestamp(day+' 09:00',tz='America/New_York');valid=ee[ee.utc<origin.tz_convert('UTC')]
            if valid.empty:continue
            r=valid.iloc[-1];age=(pd.Timestamp(day)-pd.Timestamp(r.observation_date)).days;fresh=age<=120
            if fresh:out[p].loc[day]=native.loc[r.observation_date].to_numpy()
            line.append(dict(policy=p,date=day,origin_ET=origin.isoformat(),observation_date=r.observation_date,availability_bound_ET=r.availability_bound_ET,age_days=age,fresh=fresh,release_date_assumed=True,original_vintage_verified=False))
        out[p].index.name='date';out[p].to_csv(O/f'{p}_FRENCH420_ALIGNED_NO_Y.csv',encoding='utf-8-sig')
    csv(O/'RELEASE_ASSUMPTIONS.csv',e);csv(O/'LINEAGE_09ET.csv',line);d[d.source_id.isin([43,44,45])].to_csv(O/'FRENCH_VARIABLE_DICTIONARY.csv',index=False,encoding='utf-8-sig')
    plan=dict(policies=POL,source_ids=[43,44,45],assumed_lags={'NEXT20':'Observation month end -> next month20 00ET -> first session09','MONTH2_FIRST':'Observation month end -> month+2 day1 00ET -> first session09'},max_age_days=120,PCA_components=10,PCA_fit='monthly training only; standardize420; no whitening',C=CS,threshold=.5,selection='2016-2020 accuracy>BASE and TN>=BASE; rank accuracy,TN,policy order; else BASE; 2021-2023 confirmation only',internal_base='82 candidates monthly past-only Pearson .95 pruning; NOT retroactive fixed70',late_base='original frozen combined70; same original C rule',late_selection_no_retuning=True,independent_test=False,current_revised_RAW=True,original_vintage_verified=False,API_calls=0,scope='1d binary direction only; no 4class or other new142 candidates')
    js(O/'FROZEN_PLAN.json',plan)
    protected={str(Path(__file__)):sha(__file__)}
    for r in rows.itertuples():
        for p in [r.raw,r.feature_file]:protected[p]=sha(p)
    for p in [H/'PACKET_MANIFEST.json',H/'CONFIG.json',P/'PACKET_MANIFEST.json',P/'FROZEN_CONFIG.json',R/'FROZEN_CONFIG.json']:protected[str(p)]=sha(p)
    js(O/'PROTECTED_INPUT_HASHES.json',protected);js(O/'PRETRAIN_SEAL.json',{str(p.relative_to(O)):sha(p) for p in O.glob('*') if p.is_file() and p.name!='PRETRAIN_SEAL.json'})
    print('PREPARED: 420->PCA10 monthly; two assumed lag policies; no Y read',flush=True)
def verifyseal():
    assert all(sha(O/p)==h for p,h in load(O/'PRETRAIN_SEAL.json').items());assert all(sha(p)==h for p,h in load(O/'PROTECTED_INPUT_HASHES.json').items())
def prune(tx):
    corr=tx.fillna(tx.median()).corr().abs();keep=[]
    for c in tx.columns:
        if not any(corr.loc[c,k]>=.95 for k in keep):keep.append(c)
    return keep
def run(stage):
    threadpool_limits(1);verifyseal();assert stage in ['internal','late'];done=O/f'{stage}_FORECAST_SEAL.json';assert not done.exists()
    if stage=='late':assert (O/'INTERNAL_DECISION.json').exists() and sha(O/'INTERNAL_DECISION.json')==load(O/'INTERNAL_DECISION_SEAL.json')['sha256']
    config=load(H/'CONFIG.json') if stage=='internal' else load(R/'FROZEN_CONFIG.json');basecols=config['features'];parentcols=load(P/'FROZEN_CONFIG.json')['features']
    manifest=load(H/'PACKET_MANIFEST.json') if stage=='internal' else load(P/'PACKET_MANIFEST.json')['packets'];ix=[parentcols.index(c) for c in basecols] if stage=='late' else None
    french={p:pd.read_csv(O/f'{p}_FRENCH420_ALIGNED_NO_Y.csv',index_col=0,float_precision='round_trip') for p in POL[1:]}
    cache={p:{} for p in POL};forecasts=[];selections=[];logs=[];fitrows=[];truth=[]
    for packet in manifest:
        key=packet['month'];assert sha(packet['path'])==packet['sha256']
        with np.load(packet['path']) as z:v={k:z[k].copy() for k in ['train_x','train_y','train_dates','train_label_ns','eval_x','eval_dates','origin_ns']}
        td=v['train_dates'].astype(str);ed=v['eval_dates'].astype(str);yy=pd.Series(v['train_y'],index=td)
        assert (td<key+'-01').all() and (v['train_label_ns']<int(v['origin_ns'])).all() and all(s.startswith(key) for s in ed)
        if stage=='internal':assert ed[-1]<'2024-01-01'
        tx=pd.DataFrame(v['train_x'] if ix is None else v['train_x'][:,ix],columns=basecols,index=td);ex=pd.DataFrame(v['eval_x'] if ix is None else v['eval_x'][:,ix],columns=basecols,index=ed)
        keep=prune(tx) if stage=='internal' else basecols;bi=SimpleImputer(**config['impute']);bs=StandardScaler(**config['scale']);bx=bs.fit_transform(bi.fit_transform(tx[keep]));be=bs.transform(bi.transform(ex[keep]));assert np.allclose(bi.statistics_,tx[keep].median())
        evaluable=key>=('2016-01' if stage=='internal' else '2024-01');models={}; monthlog={'stage':stage,'month':key,'train_start':td[0],'train_end':td[-1],'train_n':len(td),'eval_n':len(ed),'base_features':keep,'policies':{}}
        for p in POL:
            if p=='BASE':xx,ev=bx,be;transform=None
            else:
                ft=french[p].reindex(td);fe=french[p].reindex(ed);assert ft.notna().any().all();fi=SimpleImputer(strategy='median',keep_empty_features=True);fs=StandardScaler();a=fs.fit_transform(fi.fit_transform(ft));b=fs.transform(fi.transform(fe));pc=PCA(n_components=10,svd_solver='randomized',random_state=SEED);a=pc.fit_transform(a);b=pc.transform(b);xx=np.column_stack([bx,a]);ev=np.column_stack([be,b]);transform=(fi,fs,pc)
                assert int(pc.n_samples_)==len(td) and np.allclose(fi.statistics_,ft.median())
                monthlog['policies'][p]=dict(french_features=420,PCA=10,explained_variance_sum=float(pc.explained_variance_ratio_.sum()),fit_end=td[-1])
            choice=None;scores={}
            if evaluable:
                mo=pd.Period(key,freq='M')
                for c in CS:
                    past=pd.concat([cache[p][str(m),c] for m in pd.period_range(mo-12,mo-1,freq='M')]);assert past.index.isin(yy.index).all() and (past.index<key+'-01').all();scores[c]=int(((past>=.5).astype(int)==yy.loc[past.index]).sum())
                choice=min(CS,key=lambda c:(-scores[c],c!=1,c));selections.append(dict(stage=stage,policy=p,month=key,C=choice,scores=scores,score_end=str(past.index[-1])))
            fitted={}
            for c in CS:
                with warnings.catch_warnings():
                    warnings.simplefilter('error',ConvergenceWarning);m=LogisticRegression(**config['model'],C=c).fit(xx,yy)
                pp=m.predict_proba(ev)[:,1];assert np.isfinite(pp).all();cache[p][key,c]=pd.Series(pp,index=ed);fitted[c]=m
                fitrows.append(dict(stage=stage,policy=p,month=key,C=c,n_train=len(td),max_train_date=td[-1],features=xx.shape[1],iterations=int(m.n_iter_.max())))
                if evaluable and c==choice:
                    for day,prob in zip(ed,pp):forecasts.append(dict(policy=p,date=day,year=int(day[:4]),month=key,probability=float(prob),prediction=int(prob>=.5),C=c,features=xx.shape[1]))
            models[p]=dict(transform=transform,logistic=fitted)
        modelpath=O/'models'/f'{stage}_{key}.joblib';joblib.dump(dict(base_imputer=bi,base_scaler=bs,base_features=keep,models=models),modelpath,compress=3);logs.append(dict(**monthlog,model_path=str(modelpath),model_sha256=sha(modelpath)))
        # Only prior labels from current packet; never use eval Y for any choice.
        truth.extend(dict(date=day,Y=int(y)) for day,y in yy.items())
        if key.endswith('-12') or key==manifest[-1]['month']:print(stage,key,'complete',len(fitrows),'fits',flush=True)
    csv(O/f'{stage}_FORECASTS_NO_Y.csv',forecasts);csv(O/f'{stage}_FIT_LOG.csv',fitrows);js(O/f'{stage}_MONTHLY_LOG.json',logs);js(O/f'{stage}_C_SELECTION.json',selections)
    # Internal scoring labels: final December eval labels exist in strictly pre2024 archive.
    if stage=='internal':
        tr=pd.read_csv(H/'SCORING_TRUTH_THROUGH_2023.csv');assert tr.date.max()<'2024-01-01';csv(O/'INTERNAL_SCORING_TRUTH.csv',tr)
    js(done,dict(forecast_sha256=sha(O/f'{stage}_FORECASTS_NO_Y.csv'),fits=len(fitrows),forecast_rows=len(forecasts),eval_Y_read_during_fitting=False))
    print(stage,'FORECASTS SEALED',flush=True)
def met(f):
    from run_four_groups_2024_2026 import metrics
    return metrics(f)
def scoreinternal():
    verifyseal();assert sha(O/'internal_FORECASTS_NO_Y.csv')==load(O/'internal_FORECAST_SEAL.json')['forecast_sha256']
    f=pd.read_csv(O/'internal_FORECASTS_NO_Y.csv');tr=pd.read_csv(O/'INTERNAL_SCORING_TRUTH.csv');f=f.merge(tr,on='date',validate='many_to_one');f['correct']=f.prediction==f.Y;csv(O/'INTERNAL_DAILY_RESULTS.csv',f)
    rows=[]
    for p,g in f.groupby('policy'):
        for period,sub in [('2016_2020',g[g.year<=2020]),('2021_2023',g[g.year>=2021]),('TOTAL',g)]:rows.append(dict(policy=p,period=period,**met(sub)))
    csv(O/'INTERNAL_METRICS.csv',rows);early={r['policy']:r for r in rows if r['period']=='2016_2020'};b=early['BASE'];eligible=[p for p in POL[1:] if early[p]['correct']>b['correct'] and early[p]['TN']>=b['TN']];selected=min(eligible,key=lambda p:(-early[p]['correct'],-early[p]['TN'],POL.index(p))) if eligible else 'BASE'
    late={r['policy']:r for r in rows if r['period']=='2021_2023'};confirm=late[selected]['correct']>late['BASE']['correct'] and late[selected]['TN']>=late['BASE']['TN'] if selected!='BASE' else False
    decision=dict(selected_on_2016_2020=selected,confirmation_2021_2023=confirm,adoption_eligible=bool(confirm),rule='early accuracy strictly improves and TN does not fall; late same direction confirmation',late_evaluation_policies=POL,late_results_cannot_change_selection=True,independent_test=False)
    js(O/'INTERNAL_DECISION.json',decision);js(O/'INTERNAL_DECISION_SEAL.json',dict(sha256=sha(O/'INTERNAL_DECISION.json')));print(json.dumps(decision),flush=True)
def interval(d):
    d=np.asarray(d,float);n=len(d);rng=np.random.default_rng(SEED);ix=(rng.integers(0,n-19,size=(2000,int(np.ceil(n/20))))[:,:,None]+np.arange(20)).reshape(2000,-1)[:,:n];v=d[ix].mean(1)*100;return dict(delta_correct=int(d.sum()),delta_pp=float(d.mean()*100),lo95=float(np.quantile(v,.025)),hi95=float(np.quantile(v,.975)),lo97_5=float(np.quantile(v,.0125)),hi97_5=float(np.quantile(v,.9875)))
def scorelate():
    verifyseal();assert sha(O/'INTERNAL_DECISION.json')==load(O/'INTERNAL_DECISION_SEAL.json')['sha256'];assert sha(O/'late_FORECASTS_NO_Y.csv')==load(O/'late_FORECAST_SEAL.json')['forecast_sha256']
    truth=pd.read_csv(P.parent/'SCORING_TRUTH.csv');f=pd.read_csv(O/'late_FORECASTS_NO_Y.csv',float_precision='round_trip').merge(truth[['date','Y']],on='date',validate='many_to_one');f['correct']=f.prediction==f.Y;csv(O/'LATE_DAILY_RESULTS.csv',f);base=f[f.policy=='BASE'].set_index('date');old=pd.read_csv(R/'DAILY_RESULTS.csv',float_precision='round_trip').set_index('date');assert base.index.tolist()==old.index.tolist() and np.allclose(base.probability,old.probability,rtol=1e-11,atol=1e-11)
    rows=[];pairs=[]
    for p,g in f.groupby('policy'):
        for period,sub in [('TOTAL',g)]+[(str(y),g[g.year==y]) for y in [2024,2025,2026]]:
            rows.append(dict(policy=p,period=period,**met(sub)))
            if p!='BASE':
                b=base.loc[sub.date];pairs.append(dict(policy=p,period=period,**interval(sub.correct.to_numpy(int)-b.correct.to_numpy(int)),delta_TN=int(((sub.prediction==0)&(sub.Y==0)).sum()-((b.prediction==0)&(b.Y==0)).sum()),delta_FN=int(((sub.prediction==0)&(sub.Y==1)).sum()-((b.prediction==0)&(b.Y==1)).sum())))
    csv(O/'LATE_METRICS.csv',rows);csv(O/'PAIRED_BLOCK_BOOTSTRAP.csv',pairs)
    decision=load(O/'INTERNAL_DECISION.json');lines=['# French 자료 공개 유예 가정 실험','', '420개 후보를 각 월 과거 학습자료만으로 표준화하고 PCA10개로 요약했습니다. 이 요약값 10개를 기존 결합70에 더했으며, 기존 모델은 그대로 재현했습니다. 1일 상승/비상승 실험이고 다른 새142개 후보나 4등급은 포함하지 않았습니다.','', 'NEXT20: 관측월 말까지의 자료를 다음달20일 이후 첫 미국 거래일09시에 사용한다고 가정. MONTH2_FIRST: 다다음달 첫 거래일09시부터 사용. 실제 공개 일정이 확인된 것으로 간주하지 않았습니다. 현재 역사 수정본의 사후 수정 가능성이 남아 있습니다.','',f"내부 전반 선택: {decision['selected_on_2016_2020']}. 2021~2023 확인 통과: {decision['confirmation_2021_2023']}. 내부 비교는 월별82개 중복축소 기준으로 수행하여, 기존 고정70목록을2016년에 소급 적용하지 않았습니다. 2024~2026 비교는 기존 고정70 기준입니다. 후반 결과로 유예·PCA수·임곗값을 바꾸지 않았습니다.",'','|기간|모델|정답/일수|정확도|상승예측|비상승Recall|TN|FN|AUC|','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:lines.append(f"|{r['period']}|{r['policy']}|{r['correct']}/{r['n']}|{r['accuracy']:.2%}|{r['up_prediction']:.2%}|{r['nonup_recall']:.2%}|{r['TN']}|{r['FN']}|{r['AUC']:.4f}|")
    lines+=['','|유예|정확도差(%p)|95%구간|2후보 보정97.5%구간|TN변화|FN변화|','|---|---:|---|---|---:|---:|']
    for r in pairs:
        if r['period']=='TOTAL':lines.append(f"|{r['policy']}|{r['delta_pp']:+.2f}|[{r['lo95']:+.2f},{r['hi95']:+.2f}]|[{r['lo97_5']:+.2f},{r['hi97_5']:+.2f}]|{r['delta_TN']:+}|{r['delta_FN']:+}|")
    lines+=['','差はFrench追加−既存です。'.replace('差はFrench追加−既存です。','차이는 French 추가−기존입니다. 20거래일 이동블록 부트스트랩 2,000회로 계산했습니다.'),'','평가일은2024-01-02~2026-10-07의694일로 기존 실험과 동일합니다. 2026년 전체가 아닙니다. 2024~2026은 이미 여러 번 열람한 역사적 재평가입니다. PCA는 해석이 쉬운 개별 지표가 아니라420개를 섞은 요약이며 추가 예측정보를 보장하지 않습니다. 자료가 공개되기 전 시점으로 코드상 소급하지는 않았지만 공개일 가정과 수정 역사본 사용 때문에 완전한 누수 제거를 입증하지는 않습니다. 실제 자동채택·유료API·뉴스 재분류는 없습니다.']
    (O/'핵심결과.md').write_text('\n'.join(lines),encoding='utf-8');js(O/'SCORING_COMPLETE.json',dict(status='PASS',baseline70_probabilities_reproduced=True,internal_decision_unchanged=True,independent_test=False));print(pd.DataFrame(rows).query("period=='TOTAL'")[['policy','correct','accuracy','TN','FN','up_prediction']].to_string(index=False),flush=True)
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');{'prepare':prepare,'internal':lambda:run('internal'),'select':scoreinternal,'late':lambda:run('late'),'score':scorelate}[sys.argv[1]]()
