"""Independent source/label/timing/metric/model-reload checks and development reports."""
import sys,json,hashlib,math
from pathlib import Path
import numpy as np,pandas as pd,joblib
from sklearn.metrics import accuracy_score,confusion_matrix
from experiment import TrainSelector,metrics
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parent
# joblib models were created by the experiment.py command-line main module.
sys.modules['__main__'].TrainSelector=TrainSelector
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def js(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def text(n,x):(OUT/n).write_text(x,encoding='utf-8')
def csvout(n,rows):pd.DataFrame(rows).to_csv(OUT/n,index=False,encoding='utf-8-sig')
def tab(df):return df.to_string(index=False,float_format=lambda v:f'{v:.4f}')
def main():
    sys.stdout.reconfigure(encoding='utf-8');checks=[]
    def check(name,condition,detail=''):
        checks.append({'check':name,'PASS':bool(condition),'detail':str(detail)})
        if not condition:print('QC FAIL',name,detail,flush=True)
    p=pd.read_csv(OUT/'predictions/DEVELOPMENT_PREDICTIONS.csv');results=pd.read_csv(OUT/'PHASE2_MODEL_RESULTS.csv');folds=json.loads((OUT/'logs/FOLD_DETAILS.json').read_text(encoding='utf-8'))
    counts=json.loads((OUT/'qc/DATASET_COUNTS.json').read_text(encoding='utf-8'));inv=pd.read_csv(OUT/'RAW_INVENTORY.csv');dic=pd.read_csv(OUT/'FEATURE_DICTIONARY.csv')
    check('raw_inventory_47_types_48_csv',inv.dataset_id.nunique()==47 and len(inv)==48)
    check('FGI_and_post2020_ESOX_excluded',not set(dic.source_type)&{11,42})
    check('no_macro_vintage_claim',set(dic.source_type)<=set(inv.loc[inv.eligibility=='ELIGIBLE_MARKET_EOD','dataset_id'].str[:2].astype(int)))
    check('no_duplicate_predictions',not p.duplicated(['horizon','group','algorithm','date']).any())
    check('no_post2020_prediction',p.date.max()<='2020-12-31')
    check('probabilities_finite_valid',np.isfinite(p.probability).all() and p.probability.between(0,1).all())
    source=pd.read_csv(ROOT/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv',comment='#');source=source[source.Date<='2020-12-31'];source.index=pd.to_datetime(source.Date);close=source.Close
    for h in ['1D','1W']:
        data=pd.read_csv(OUT/f'data/DEV_{h}.csv',parse_dates=['date','label_end']).set_index('date')
        check(h+'_all_input_dates_development',data.index.max().year==2020 and data.label_end.max().year==2020)
        if h=='1D':r=100*(close/close.shift(1)-1);ends=pd.Series(close.index,index=close.index)
        else:
            rows=[]
            for period,part in source.groupby(source.index.to_period('W-FRI')):
                rows.append({'date':part.index[0],'end':part.index[-1],'close':part.Close.iloc[-1]})
            w=pd.DataFrame(rows).set_index('date');r=100*(w.close/w.close.shift(1)-1);ends=w.end
            check('weekly_labels_nonoverlapping',not data.label_end.duplicated().any())
        check(h+'_Y_independent_recomputation',np.allclose(data.return_pct,r.reindex(data.index),atol=1e-10) and np.array_equal(data.Y.to_numpy(),(r.reindex(data.index)>0).astype(int)))
        check(h+'_label_end_exact',np.array_equal(data.label_end.to_numpy(),ends.reindex(data.index).to_numpy()))
        for (g,a),v in p[p.horizon==h].groupby(['group','algorithm']):
            check(f'{h}_{g}_{a}_same_dates',set(v.date)==set(data.loc[data.index.year>=2017].index.strftime('%Y-%m-%d')))
            check(f'{h}_{g}_{a}_truth',np.array_equal(v.sort_values('date').Y.to_numpy(),data.loc[data.index.year>=2017].Y.to_numpy()))
        for f in [f for f in folds if f['horizon']==h]:
            check(f'{h}_{f["group"]}_{f["algorithm"]}_{f["outer_year"]}_mature_past_labels',f['train_label_end']<f['outer_first_origin'] and f['train_end']<f['outer_first_origin'])
            estimator=joblib.load(OUT/f['model_path']);test=data[data.index.year==f['outer_year']]
            got=estimator.predict_proba(test[f['candidate_features']])[:,1]
            expected=p[(p.horizon==h)&(p.group==f['group'])&(p.algorithm==f['algorithm'])&(p.year==f['outer_year'])].sort_values('date').probability.to_numpy()
            check(f'{f["model_path"]}_reload_reproducible',np.allclose(got,expected,rtol=1e-10,atol=1e-12))
    check('M3_exact_alias_M2',p[p.group=='M2'].drop(columns='group').reset_index(drop=True).equals(p[p.group=='M3'].drop(columns='group').reset_index(drop=True)))
    # Independently check every emitted availability event and its raw value.
    line=pd.read_csv(OUT/'data/FEATURE_AVAILABILITY.csv');sessions=pd.DatetimeIndex(pd.read_csv(OUT/'inputs/US_MARKET_SESSIONS_DEV.csv').session_date)
    obs=pd.DatetimeIndex(line.source_observation_date);expected=sessions.searchsorted(obs,side='right')+1
    actual=pd.to_datetime(line.modeled_available_at_et,utc=True).dt.tz_convert('America/New_York')
    origin=pd.to_datetime(line.origin_et,utc=True).dt.tz_convert('America/New_York')
    check('all_emitted_availability_before_origin',(actual<origin).all())
    check('availability_exact_second_US_session',np.array_equal(actual.dt.tz_localize(None).dt.normalize().to_numpy(),sessions[expected].to_numpy()))
    check('observations_before_availability',(obs.to_numpy()<actual.dt.tz_localize(None).dt.normalize().to_numpy()).all())
    check('timing_claims_marked_assumptions',line.timing_status.str.contains('ASSUMPTION').all())
    for feature,events in line.groupby('feature'):
        d=dic[dic.feature==feature].iloc[0];raw=pd.read_csv(ROOT/d.source_path,comment='#');raw=raw[raw.Date<='2020-12-31'];raw.index=pd.to_datetime(raw.Date);raw=raw.sort_index();k=int(d.source_type);key=feature.split('_',1)[1]
        if k==5:s=(raw.New_Highs_52W-raw.New_Lows_52W)/(raw.New_Highs_52W+raw.New_Lows_52W).replace(0,np.nan)
        elif k==6:s=(raw.Advancing_Volume-raw.Declining_Volume)/(raw.Advancing_Volume+raw.Declining_Volume).replace(0,np.nan)
        else:s=raw.Close if 'Close' in raw else raw.iloc[:,1]
        if key.startswith('ret'):lag=int(key[3:]);v=100*(s/s.shift(lag)-1)
        elif key=='vol20':v=(s/s.shift(1)-1).rolling(20).std(ddof=1)*100
        elif key=='ma20_gap':v=(s/s.rolling(20).mean()-1)*100
        elif key=='level':v=s
        else:v=s-s.shift(int(key[5:]))
        check(feature+'_all_values_source_recomputed',np.allclose(v.reindex(pd.DatetimeIndex(events.source_observation_date)).to_numpy(),events.value.to_numpy(),rtol=1e-8,atol=1e-9,equal_nan=False))
    js('qc/INDEPENDENT_IMPLEMENTATION_QC.json',checks)
    # Moving block bootstrap of accuracy difference against same-date majority baseline.
    ci=[];rng=np.random.default_rng(20261019)
    for h,L in [('1D',20),('1W',8)]:
        base=p[(p.horizon==h)&(p.algorithm=='Majority')].sort_values('date');n=len(base);nb=math.ceil(n/L)
        starts=rng.integers(0,n-L+1,size=(2000,nb));indices=(starts[:,:,None]+np.arange(L)[None,None,:]).reshape(2000,-1)[:,:n]
        for (g,a),v in p[p.horizon==h].groupby(['group','algorithm']):
            v=v.sort_values('date');delta=(v.prediction.to_numpy()==v.Y.to_numpy()).astype(float)-(base.prediction.to_numpy()==base.Y.to_numpy()).astype(float)
            boot=delta[indices].mean(axis=1)*100;lo,hi=np.quantile(boot,[.025,.975])
            ci.append({'horizon':h,'group':g,'algorithm':a,'accuracy_gain_pp':delta.mean()*100,'CI95_lower_pp':lo,'CI95_upper_pp':hi,'block_length':L,'replicates':2000,'selection_adjusted':False})
    csvout('PHASE2_BOOTSTRAP_UNCERTAINTY.csv',ci)
    # Record confusion matrices separately for class-level inspection.
    cm=[]
    for (h,g,a),v in p.groupby(['horizon','group','algorithm']):
        tn,fp,fn,tp=confusion_matrix(v.Y,v.prediction,labels=[0,1]).ravel();cm.append({'horizon':h,'group':g,'algorithm':a,'TN':tn,'FP':fp,'FN':fn,'TP':tp})
    csvout('PHASE2_CONFUSION_MATRICES.csv',cm)
    baseline=pd.read_csv(OUT/'inputs/PROTECTED_BEFORE.csv');changed=[]
    for i,row in baseline.iterrows():
        q=ROOT/row.path
        if not q.is_file() or sha(q)!=row.sha256:changed.append(row.path)
    js('qc/PROTECTED_AFTER.json',{'checked':len(baseline),'changed':changed,'scope':'All pre-existing project files except installed .venv/.venv_W1 directories and .git; including research_C source/outputs, RAW, archives and root documents','no_writes_outside_research_D':True})
    check('existing_protected_files_unchanged',not changed)
    # Compare all Research C files, including its bundled environment, with pre-existing backup inventory.
    old=pd.read_csv(ROOT/'archives/research_C_PREBACKUP_INVENTORY_20261019.csv');cchanges=[]
    for row in old.itertuples():
        q=ROOT/row.path
        if not q.is_file() or sha(q)!=row.sha256:cchanges.append(row.path)
    js('qc/RESEARCH_C_FULL_PRESERVATION.json',{'historical_inventory_files':len(old),'changed_or_missing':cchanges,'baseline':'archives/research_C_PREBACKUP_INVENTORY_20261019.csv'})
    check('research_C_all_10515_including_environment_unchanged',len(old)==10515 and not cchanges)
    js('qc/INDEPENDENT_IMPLEMENTATION_QC.json',checks)
    pooled=results[results.period.astype(str)=='ALL'];summary=[];ci_df=pd.DataFrame(ci)
    for h in ['1D','1W']:
        rr=pooled[(pooled.horizon==h)&(pooled.group!='BASELINE')&(pooled.group!='M3')].sort_values(['accuracy','balanced_accuracy','MCC','group','algorithm'],ascending=[False,False,False,True,True]);best=rr.iloc[0];cc=ci_df[(ci_df.horizon==h)&(ci_df.group==best.group)&(ci_df.algorithm==best.algorithm)].iloc[0]
        annual=results[(results.horizon==h)&(results.group==best.group)&(results.algorithm==best.algorithm)&(results.period.astype(str)!='ALL')]
        summary.append({'horizon':h,'best_group':best.group,'best_algorithm':best.algorithm,'n':int(best.n),'baseline_accuracy':best.baseline_accuracy,'accuracy':best.accuracy,'gain_pp':best.improvement_pp,'balanced_accuracy':best.balanced_accuracy,'MCC':best.MCC,'features_min':int(best.feature_min),'features_max':int(best.feature_max),'CI95_lower_pp':cc.CI95_lower_pp,'CI95_upper_pp':cc.CI95_upper_pp,'annual_positive_gain_years':int((annual.improvement_pp>0).sum()),'annual_accuracy_min':annual.accuracy.min(),'annual_accuracy_max':annual.accuracy.max()})
    js('PHASE2_SUMMARY.json',summary)
    limitation='이 결과는 2017~2020 개발기간 탐색 결과입니다. 최고 모델을 여러 후보 중 사후 선정했으므로 그 최고 적중률과 선택 미보정 CI를 독립 시험 성능/유의성으로 해석할 수 없습니다. 시장 EOD 공개시점은2세션 보수적 가정이며 실제 역사적 벤더 전송·모든 정정본 검증은 아닙니다. 연간 재학습 방식이라 매일 갱신하는 운영모형과 다릅니다. 2021년 이후 성능평가·최종 시험·Phase3는 하지 않았습니다.'
    table=tab(pd.DataFrame(summary))
    text('PHASE2_1D_VS_1W_REPORT.md','# 1D·1W 개발 비교\n\n```text\n'+table+'\n```\n\n'+limitation+'\n\n1W는 검증표본209개로1D1007개보다 불확실성이 큽니다. 절대 Accuracy뿐 아니라 다수기준 대비 개선·BA/MCC·연도 일관성을 함께 보십시오. 연도별 수치와 각 클래스 recall/precision은 PHASE2_MODEL_RESULTS.csv, 혼동행렬은 PHASE2_CONFUSION_MATRICES.csv에 있습니다.\n')
    groupbest=pooled[(pooled.group!='BASELINE')&(pooled.group!='M3')].sort_values('accuracy',ascending=False).groupby(['horizon','group'],sort=True).head(1)[['horizon','group','algorithm','feature_min','feature_max','accuracy','baseline_accuracy','improvement_pp','balanced_accuracy','MCC']].sort_values(['horizon','group'])
    csvout('PHASE2_GROUP_BEST_DEVELOPMENT.csv',groupbest)
    text('PHASE2_FEATURE_GROUP_COMPARISON.md','# 정보집합 비교\n\n```text\n'+tab(groupbest)+'\n```\n\n각 그룹별 최고 모델을 고른 탐색표이므로 순수한 변수군 효과가 아닙니다. 같은 알고리즘의 M0/M1/M2/M4 및 sector proxy 제거 결과 전체를 PHASE2_MODEL_RESULTS.csv에서 확인해야 합니다. M0=5, M1=53, M2/M3=86개 후보입니다. M4는 fold 학습 안에서 선택하며 Ridge calibration ensemble은 각 submodel 최대25개, 보고 개수는 union입니다. M3=M2이며 보류된 거시·월간 산업 정보의 효과를 검증했다고 주장하지 않습니다.\n\n'+limitation+'\n')
    bestbaselines=pooled[pooled.group=='BASELINE'][['horizon','algorithm','accuracy','balanced_accuracy','MCC']]
    annualbest=[]
    for s in summary:annualbest.append(results[(results.horizon==s['horizon'])&(results.group==s['best_group'])&(results.algorithm==s['best_algorithm'])&(results.period.astype(str)!='ALL')][['horizon','period','group','algorithm','accuracy','baseline_accuracy','improvement_pp','balanced_accuracy','MCC']])
    text('PHASE2_IMPROVEMENT_REPORT.md','# 예측력 개선 예비실험\n\n## 기준모형\n\n```text\n'+tab(bestbaselines)+'\n```\n\n## 개발 최고 후보\n\n```text\n'+table+'\n```\n\n## 후보의 연도별 안정성\n\n```text\n'+tab(pd.concat(annualbest))+'\n```\n\n'+limitation+'\n\n알고리즘 차이와 정보집합 차이는 같은 날짜·같은 알고리즘 비교로 분리해야 합니다. 설정과 threshold도 학습 내부에서 달라졌으므로 차이를 특정 원천의 인과적 효과로 해석하지 않습니다. M4의 선택빈도는 관련성 진단일 뿐 SHAP/인과 해석은 하지 않았습니다. 추가 데이터가 필요하다면 실제 발표시각과 당시 최초 빈티지를 갖춘 거시·산업 시계열, 조정 이력과 시장자료 정정 로그가 우선입니다. 이번 단계에서 수집하지 않았습니다.\n')
    selection=[]
    for f in folds:
        if f['group']=='M4':
            for feature in f['selected_features']:selection.append({'horizon':f['horizon'],'algorithm':f['algorithm'],'year':f['outer_year'],'feature':feature})
    csvout('logs/M4_SELECTED_FEATURES.csv',selection)
    status='PASS_WITH_POINT_IN_TIME_LIMITATIONS' if all(c['PASS'] for c in checks) else 'FAIL'
    text('PHASE2_QC_REPORT.md',f'# Phase2 QC: {status}\n\n구현 검사 {len(checks)}건 중 {sum(c["PASS"] for c in checks)}건 PASS. 기존 보호파일 {len(baseline)}개 및 기존 연구C 전체10,515개를 재해시 대조했습니다. 변경 {len(changed)}개/C전체변경 {len(cchanges)}개. 모든 학습모델을 다시 읽어 저장 예측확률과 전수 대조했습니다. 원천에서 Y와86개 feature 값을 재계산했고 전체 availability 행을 확인했습니다. 모델 재학습은 QC에서 하지 않았습니다.\n\n'+limitation+'\n\n검사 상세 qc/INDEPENDENT_IMPLEMENTATION_QC.json, 보호대조 qc/PROTECTED_AFTER.json 및 qc/RESEARCH_C_FULL_PRESERVATION.json. 실행 실패는 logs/FAILURES.json에 전부 보존합니다. CatBoost 미설치로 제외했고 패키지 설치·기존 환경 변경은 없습니다.\n')
    text('PHASE3_OPEN_DECISIONS.md','''# Phase3 이전 승인 필요 사항

- 새 독립 최종검증 자료와 미래 paper prediction 정책. 2021~2026 구간은 연구C에 이미 노출돼 새 독립시험으로 부르지 않습니다.
- 1D/1W 대표 지평, 대표 모델·정보집합·학습창·갱신빈도·임곗값 정책의 잠금. 개발 최고값만으로 최종 확정하지 않습니다.
- 시장 EOD2세션 가정 및 과거 벤더정정 한계의 수용 여부. 실제 point-in-time 보장에 필요한 신규 자료 수집은 별도 승인합니다.
- 발표시각·최초빈티지가 있는 거시/산업 자료 확보 여부. FGI 해시 변경의 구체적 원인·승인 기록과 역사적 공개시각 검증 여부.
- 시계열 bootstrap의 블록·검정 family·모델선정 편향 보정 및 대표 검정 사전 고정.
- 기존10여변수와 동일 산식의 별도 bridge 비교 필요 여부. 현재M1은53개 시장 파생변수이므로 기존10개 회귀모형과 정확히 같은 대조가 아닙니다.
- 추가2세션 지연이 지나치게 보수적인지, 증거를 확보해1세션으로 완화할지에 대한 사전 정책. 현재 결과를 보고 지연을 임의 최적화하지 않습니다.
- 논문화 후보: 정보군 확대의 기준모형 대비 개발 예측력, 변수선택과 전체정보의 비교, 지평별 안정성. 주제·제목은 확정하지 않습니다.

Phase2 종료. Phase3/최종시험/연구C Phase5 미실행. 원본 연구와 RAW 및 archives 보존.
''')
    text('README.md','# 연구 D Phase0~2\n\nSOX 방향 예측 개발실험. 입력 감사→1D/1W 구축→시간순 개발 검증을 완료했습니다. PHASE2_IMPROVEMENT_REPORT.md와 PHASE2_QC_REPORT.md를 먼저 확인하십시오. 완전한 실시간 PIT 검증이 아닌 조건부 역사 실험입니다.\n\n실행환경은 config/ENVIRONMENT.json. 코드순서는 prepare.py → experiment.py → finalize.py이며 기존 산출물이 있는 상태에서 prepare.py를 재실행하면 baseline 보호를 위해 중단합니다. 모든 출력은 research_D 내부입니다. 저장모델에는 전체 전처리가 들어 있으며 M4 모델은 code/experiment.py의 TrainSelector를 __main__에 등록한 후 joblib.load해야 합니다(finalize.py가 재현 예시). 기존 자료를 수정하지 않습니다.\n')
    js('qc/FINAL_STATUS.json',{'status':status,'checks':len(checks),'passed':sum(c['PASS'] for c in checks),'phase3_executed':False,'final_test_executed':False,'post2020_performance_evaluations':0})
    manifest=[]
    for f in sorted(OUT.rglob('*')):
        if f.is_file() and f.name not in ['OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256']:manifest.append({'path':f.relative_to(OUT).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f)})
    csvout('OUTPUT_MANIFEST.csv',manifest);text('OUTPUT_MANIFEST.sha256',sha(OUT/'OUTPUT_MANIFEST.csv')+'  OUTPUT_MANIFEST.csv\n')
    print(json.dumps({'status':status,'summary':summary,'checks':len(checks),'failures':[c for c in checks if not c['PASS']]},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
