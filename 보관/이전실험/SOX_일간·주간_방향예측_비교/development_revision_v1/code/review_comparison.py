"""Recompute metrics, verify all saved models/timing/inputs, and report controlled comparisons."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import sys,json,hashlib,math
from pathlib import Path
import numpy as np,pandas as pd,joblib
from sklearn.metrics import accuracy_score,balanced_accuracy_score,matthews_corrcoef,roc_auc_score,recall_score,f1_score,mean_absolute_error,mean_squared_error,brier_score_loss
from threadpoolctl import threadpool_limits
H=Path(__file__).resolve().parents[1];D=H.parent;ROOT=D.parent
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def js(n,x):(H/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def text(n,s):(H/n).write_text(s,encoding='utf-8')
def csv(n,x):pd.DataFrame(x).to_csv(H/n,index=False,encoding='utf-8-sig')
def metric(v):
    y=v.Y;c=v.prediction;s=v.score
    result={'n':len(v),'Accuracy':accuracy_score(y,c),'BalancedAccuracy':balanced_accuracy_score(y,c),'MCC':matthews_corrcoef(y,c),'ROC_AUC':roc_auc_score(y,s),'F1':f1_score(y,c,zero_division=0),'recall_up':recall_score(y,c,pos_label=1,zero_division=0),'recall_nonup':recall_score(y,c,pos_label=0,zero_division=0),'predicted_up_fraction':float(c.mean())}
    result['Brier']=brier_score_loss(y,v.probability) if v.probability.notna().all() else np.nan
    result['MAE_return_pct']=mean_absolute_error(v.actual_return_pct,v.predicted_return_pct) if v.predicted_return_pct.notna().all() else np.nan
    result['RMSE_return_pct']=np.sqrt(mean_squared_error(v.actual_return_pct,v.predicted_return_pct)) if v.predicted_return_pct.notna().all() else np.nan
    return result
def fmt(v):return f'{100*v:.2f}%'
def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1)
    checkrows=[]
    def check(name,ok,detail=''):checkrows.append({'name':name,'PASS':bool(ok),'detail':str(detail)})
    p=pd.read_csv(H/'predictions/PREDICTIONS.csv');folds=json.loads((H/'logs/FOLD_DETAILS.json').read_text(encoding='utf-8'));scenarios=json.loads((H/'config/SCENARIOS.json').read_text(encoding='utf-8'))
    status=json.loads((H/'logs/RUN_STATUS.json').read_text(encoding='utf-8'));check('all_models_completed',status['outer_fits']==1248 and status['failures']==0)
    policy=pd.read_csv(H/'POINT_IN_TIME_POLICY.csv');policy.loc[policy.source_type==23,'price_column']='Semiconductor_Industry_Index level/deltas';csv('POINT_IN_TIME_POLICY.csv',policy)
    tables={t:pd.read_csv(H/f'data/{name}.csv',parse_dates=['date','label_end']).set_index('date') for t,name in [('old','OLD_LAG_1D'),('latest','LATEST_EOD_1D')]}
    # Non-fitted regression benchmarks constructed from the identical mature training samples.
    extra=[];done=set()
    for f in folds:
        key=(f['scenario'],f['fold'])
        if key in done:continue
        done.add(key);data=tables[scenarios[f['scenario']]['timing']]
        tr=data[(data.index>=f['train_start'])&(data.index<=f['train_end'])]
        mean=float(tr.return_pct.mean());target=p[(p.scenario==f['scenario'])&(p.fold==f['fold'])&(p.algorithm=='Majority')]
        for name,ret in [('TrainingMeanReturn',mean),('ZeroReturn',0.)]:
            for v in target.itertuples():extra.append({'scenario':f['scenario'],'group':'BASELINE','algorithm':name,'date':v.date,'Y':v.Y,'actual_return_pct':v.actual_return_pct,'score':ret,'probability':np.nan,'predicted_return_pct':ret,'prediction':int(ret>0),'fold':f['fold'],'train_n':f['train_n'],'n_features':0})
    p=pd.concat([p,pd.DataFrame(extra)],ignore_index=True);csv('predictions/ALL_PREDICTIONS_WITH_BENCHMARKS.csv',p)
    check('unique_prediction_keys',not p.duplicated(['scenario','group','algorithm','date']).any())
    expected=set(tables['old'].loc[tables['old'].index.year>=2017].index.strftime('%Y-%m-%d'))
    check('development_dates_only',p.date.min()>='2017-01-01' and p.date.max()<='2020-12-31')
    oldref=pd.read_csv(D/'data/DEV_1D.csv',parse_dates=['date','label_end']).set_index('date');numeric=oldref.select_dtypes(include='number').columns;other=oldref.columns.difference(numeric)
    check('old_features_unchanged',tables['old'].index.equals(oldref.index) and np.allclose(tables['old'][numeric],oldref[numeric],rtol=1e-12,atol=1e-12,equal_nan=True) and tables['old'][other].equals(oldref[other]))
    original_dic=pd.read_csv(D/'FEATURE_DICTIONARY.csv');slow=original_dic.loc[~original_dic.source_type.isin({1,2,4,9,10,12,13,14,23,46,47}),'feature'].tolist()
    check('unverified_indicator_lags_unchanged',np.allclose(tables['old'][slow],tables['latest'][slow],rtol=1e-12,atol=1e-12,equal_nan=True))
    for (scenario,g,a),v in p.groupby(['scenario','group','algorithm']):check(f'{scenario}_{g}_{a}_same_1007_dates',len(v)==1007 and set(v.date)==expected)
    for f in folds:
        data=tables[scenarios[f['scenario']]['timing']]
        test=p[(p.scenario==f['scenario'])&(p.group==f['group'])&(p.algorithm==f['algorithm'])&(p.fold==f['fold'])].sort_values('date')
        check(f['model_path']+'_maturity',f['max_train_label_end']<f['first_origin'] and f['train_end']<f['first_origin'])
        estimator=joblib.load(H/f['model_path']);X=data.loc[pd.to_datetime(test.date),f['columns']]
        reg='Regressor' in f['algorithm'];scores=estimator.predict(X) if reg else estimator.predict_proba(X)[:,1]
        check(f['model_path']+'_reload',np.allclose(scores,test.score.to_numpy(),rtol=1e-7,atol=1e-8))
        expected_cls=(test.score.to_numpy()>0).astype(int) if reg else (test.score.to_numpy()>=.5).astype(int)
        check(f['model_path']+'_threshold',np.array_equal(expected_cls,test.prediction.to_numpy()))
    prices=pd.read_csv(ROOT/'data/raw/02_sox/02_sox_RAW_20110101_20261009.csv',comment='#');prices=prices[prices.Date<='2020-12-31'];prices.index=pd.to_datetime(prices.Date);ret=100*(prices.Close/prices.Close.shift(1)-1)
    for name,data in tables.items():check(name+'_Y_matches_today_vs_yesterday',np.allclose(data.return_pct,ret.reindex(data.index)) and np.array_equal(data.Y,(ret.reindex(data.index)>0).astype(int)))
    line=pd.read_csv(H/'data/LATEST_FEATURE_LINEAGE.csv');cal=pd.DatetimeIndex(pd.read_csv(D/'inputs/US_MARKET_SESSIONS_DEV.csv').session_date)
    obs=pd.DatetimeIndex(line.source_date);av=pd.to_datetime(line.modeled_available_et,utc=True).dt.tz_convert('America/New_York');origin=pd.to_datetime(line.origin_et,utc=True)
    check('new_values_available_before_0900',(pd.to_datetime(line.modeled_available_et,utc=True)<origin).all())
    check('new_values_use_next_US_session',np.array_equal(av.dt.tz_localize(None).dt.normalize().to_numpy(),cal[cal.searchsorted(obs,side='right')].to_numpy()))
    check('no_same_day_price_observation',(line.source_date<line.date).all())
    # Independent raw-value recomputation and event-to-dataset mapping.
    for f,events in line.groupby('feature'):
        d=original_dic[original_dic.feature==f].iloc[0];raw=pd.read_csv(ROOT/d.source_path,comment='#');raw=raw[raw.Date<='2020-12-31'];raw.index=pd.to_datetime(raw.Date);raw=raw.sort_index();s=raw.Close if 'Close' in raw else raw.Semiconductor_Industry_Index;key=f.split('_',1)[1]
        if key.startswith('ret'):v=100*(s/s.shift(int(key[3:]))-1)
        elif key=='vol20':v=(s/s.shift(1)-1).rolling(20).std(ddof=1)*100
        elif key=='ma20_gap':v=(s/s.rolling(20).mean()-1)*100
        elif key=='level':v=s
        else:v=s-s.shift(int(key[5:]))
        check(f+'_raw_value_recomputed',np.allclose(v.reindex(pd.DatetimeIndex(events.source_date)),events.value,rtol=1e-8,atol=1e-9))
        check(f+'_dataset_matches_lineage',np.allclose(tables['latest'].loc[pd.to_datetime(events.date),f],events.value,rtol=1e-8,atol=1e-9))
    # Matched metrics and uncertainty on every saved variant.
    results=[];rng=np.random.default_rng(20261019);n=1007;L=20;starts=rng.integers(0,n-L+1,size=(2000,math.ceil(n/L)));indices=(starts[:,:,None]+np.arange(L)).reshape(2000,-1)[:,:n]
    for (scenario,g,a),v in p.groupby(['scenario','group','algorithm']):
        v=v.sort_values('date');base=p[(p.scenario==scenario)&(p.algorithm=='Majority')].sort_values('date');delta=(v.Y.to_numpy()==v.prediction.to_numpy()).astype(float)-(base.Y.to_numpy()==base.prediction.to_numpy()).astype(float)
        lo,hi=np.quantile(delta[indices].mean(axis=1)*100,[.025,.975])
        for period in ['ALL',2017,2018,2019,2020]:
            w=v if period=='ALL' else v[v.date.str.startswith(str(period))];b=base if period=='ALL' else base[base.date.str.startswith(str(period))]
            r={'scenario':scenario,'group':g,'algorithm':a,'period':period};r.update(metric(w));r['baseline_accuracy']=accuracy_score(b.Y,b.prediction);r['gain_pp']=100*(r['Accuracy']-r['baseline_accuracy']);r['CI95_gain_lower_pp']=lo if period=='ALL' else np.nan;r['CI95_gain_upper_pp']=hi if period=='ALL' else np.nan;results.append(r)
    results=pd.DataFrame(results);csv('MODEL_RESULTS.csv',results);allr=results[results.period=='ALL'];models=allr[allr.group!='BASELINE'].sort_values(['Accuracy','BalancedAccuracy','MCC'],ascending=False)
    best=models.iloc[0];js('SUMMARY.json',{'best':best.to_dict(),'dev_samples':1007,'scenario_count':4,'models_fitted':1248,'outer_evaluation_years':[2017,2018,2019,2020],'post2020_evaluations':0})
    paired=[]
    for group in ['M0','M1','M2']:
        for algo in ['LogisticClassifier','RidgeRegressor','XGBClassifier','XGBRegressor']:
            for before,after,change in [('A_old_annual_expanding','B_latest_annual_expanding','information_delay'),('B_latest_annual_expanding','C_latest_monthly_expanding','update_frequency'),('C_latest_monthly_expanding','D_latest_monthly_3years','training_window')]:
                a=p[(p.scenario==before)&(p.group==group)&(p.algorithm==algo)].sort_values('date');b=p[(p.scenario==after)&(p.group==group)&(p.algorithm==algo)].sort_values('date');diff=(b.Y.to_numpy()==b.prediction.to_numpy()).astype(float)-(a.Y.to_numpy()==a.prediction.to_numpy()).astype(float);lo,hi=np.quantile(diff[indices].mean(axis=1)*100,[.025,.975]);paired.append({'group':group,'algorithm':algo,'change':change,'before':before,'after':after,'accuracy_change_pp':diff.mean()*100,'CI95_lower_pp':lo,'CI95_upper_pp':hi})
    csv('CONTROLLED_PAIRED_COMPARISONS.csv',paired)
    protections=pd.read_csv(H/'inputs/PROTECTED_BEFORE.csv');changed=[]
    for row in protections.itertuples():
        if not (ROOT/row.path).is_file() or sha(ROOT/row.path)!=row.sha256:changed.append(row.path)
    check('all_prior_protected_files_unchanged',not changed);js('qc/PROTECTION_RECHECK.json',{'checked':len(protections),'changed':changed})
    oldC=pd.read_csv(ROOT/'archives/research_C_PREBACKUP_INVENTORY_20261019.csv');cchanges=[]
    for i,row in enumerate(oldC.itertuples()):
        if not (ROOT/row.path).is_file() or sha(ROOT/row.path)!=row.sha256:cchanges.append(row.path)
        if i and i%3000==0:print('Research C preservation rechecked',i,flush=True)
    check('C_full_10515_files_preserved',len(oldC)==10515 and not cchanges);js('qc/RESEARCH_C_PRESERVATION.json',{'checked':len(oldC),'changed_or_missing':cchanges})
    js('qc/IMPLEMENTATION_QC.json',checkrows);passed=all(c['PASS'] for c in checkrows)
    js('qc/FINAL_STATUS.json',{'status':'PASS_WITH_TIMING_ARCHIVE_LIMITATIONS' if passed else 'FAIL','checks':len(checkrows),'passed':sum(c['PASS'] for c in checkrows),'model_fit_failures':status['failures'],'prebuild_mapping_error_corrected':1,'post2020_evaluations':0,'original_data_changes':len(changed),'phase3_or_final_test_executed':False})
    report='# 1D 방향 예측 개선 대조실험\n'
    report+='\n이번 Y는 **어제 실제 종가 대비 오늘 실제 종가의 상승/비상승**, origin은미국거래일09:00입니다. 평가날짜는기존과동일한2017~2020년1,007개입니다. 기존결과를덮어쓰지않고4개설정을구분했습니다.\n\n'
    report+='|설정|정보·갱신·학습창|최고모델|변수군|Accuracy|기준 대비|BA|MCC|비상승 Recall|\n|---|---|---|---|---:|---:|---:|---:|---:|\n'
    labels={'A_old_annual_expanding':'기존지연·연간·확장','B_latest_annual_expanding':'직전종가·연간·확장','C_latest_monthly_expanding':'직전종가·월간·확장','D_latest_monthly_3years':'직전종가·월간·최근3년'}
    for scenario in scenarios:
        b=models[models.scenario==scenario].iloc[0];report+=f"|{scenario[0]}|{labels[scenario]}|{b.algorithm}|{b.group}|{fmt(b.Accuracy)}|{b.gain_pp:+.2f}%p|{fmt(b.BalancedAccuracy)}|{b.MCC:.4f}|{fmt(b.recall_nonup)}|\n"
    report+='\n각설정별최고모델을사후고른표이므로설정효과의인과적추정은아닙니다. 같은모델/변수군의A→B→C→D차이는CONTROLLED_PAIRED_COMPARISONS.csv에서별도확인해야합니다. 기존연구D의최고모델은threshold/내부튜닝이달랐으므로이번고정설정A와수치가같을필요는없습니다.\n\n'
    report+='## 회귀와 분류 비교\n\n|모델|개발 최고 Accuracy|설정|변수군|BA|MCC|비상승 Recall|\n|---|---:|---|---|---:|---:|---:|\n'
    for algo in ['LogisticClassifier','RidgeRegressor','XGBClassifier','XGBRegressor']:
        b=models[models.algorithm==algo].iloc[0];report+=f"|{algo}|{fmt(b.Accuracy)}|{b.scenario[0]}|{b.group}|{fmt(b.BalancedAccuracy)}|{b.MCC:.4f}|{fmt(b.recall_nonup)}|\n"
    report+='\n분류는상승확률>=.5,회귀는예측수익률>0으로판정했습니다.회귀값은확률이아니며Brier는해당없음입니다.수익률MAE/RMSE와기준학습평균수익률예측은MODEL_RESULTS.csv에있습니다.각알고리즘최고값도여러후보중개발최고값입니다.\n\n'
    report+=f"## 최고 후보와 안정성\n\n{best.scenario}, {best.group}, {best.algorithm}: Accuracy {fmt(best.Accuracy)}, 다수기준 {fmt(best.baseline_accuracy)}, 개선 {best.gain_pp:+.2f}%p. 개선폭20세션block-bootstrap95%구간 [{best.CI95_gain_lower_pp:.2f}, {best.CI95_gain_upper_pp:.2f}]%p(모델선정편향미보정). 상승예측비중 {fmt(best.predicted_up_fraction)}, ROC-AUC {best.ROC_AUC:.4f}.\n\n"
    annual=results[(results.scenario==best.scenario)&(results.group==best.group)&(results.algorithm==best.algorithm)&(results.period!='ALL')]
    for a in annual.itertuples():report+=f'- {a.period}: Accuracy {fmt(a.Accuracy)}, 기준대비 {a.gain_pp:+.2f}%p, BA {fmt(a.BalancedAccuracy)}, 비상승Recall {fmt(a.recall_nonup)}\n'
    report+='\n## 변경 요인별 진단\n\n'
    paired_df=pd.DataFrame(paired)
    for change,sub in paired_df.groupby('change'):
        report+=f'- {change}: 동일모델·동일변수군12쌍 중 Accuracy 개선 {int((sub.accuracy_change_pp>0).sum())}쌍, 악화 {int((sub.accuracy_change_pp<0).sum())}쌍, 평균차이 {sub.accuracy_change_pp.mean():+.2f}%p. 여러모델을묶은기술적요약이며독립표본검정이아닙니다.\n'
    report+='\n## 판단\n\n'
    if best.gain_pp<=0:
        report+='이번범위의최고모델도다수클래스기준을넘지못했습니다. 최신정보·월간갱신·회귀전환만으로문제가해결됐다고볼수없습니다.\n'
    elif best.CI95_gain_lower_pp<=0:
        report+='개발최고적중률은다수기준보다높지만개선폭구간이0을포함합니다. 후보선택편향도있어안정적인개선확보로판정하지않습니다.\n'
    else:
        report+='개발최고후보의기준대비개선폭구간은0위에있지만여러후보중사후최고를골랐으므로독립검증이필요합니다. 실시간미래성능확보로판정하지않습니다.\n'
    report+='입력지연문제와학습방식의영향을분리한점이이번진단의결과입니다. 그다음은09시이전에알려진당일아시아종가와장전·야간정보의실제시각/품질검토,상승·비상승오류비용을반영한학습목표의사전정의가후보입니다. 이런새설계를현재성적에맞춰자동최적화하지않고후속결정으로남깁니다.\n'
    report+='''
## 구현과 해석 한계

시장가격11종의53개특징은직전완료원천일에서다음미국거래세션08:00가용으로변경했습니다.대만반도체지수는Close가아닌전용지수컬럼이므로level/차분을재구성했습니다.나머지33개위험·심리특징은기존2세션가정입니다.오늘미국종가를X에넣지않습니다.아시아동일날짜종가/미국장전거래등09시전추가정보까지활용한최대정보집합은아닙니다.

실제과거벤더전송시각·정정본의증거는없으므로1세션정렬은시장종가사건에기반한조건부실험이며완전한PIT인증이아닙니다.이한계는기존실험에도있으며일괄지연을늘리는것만으로해결되지않습니다.FGI·거시·월간수정자료는여전히제외했습니다.새데이터수집/패키지설치는없습니다.

모든설정은평가전에고정했고변경효과를분리했지만개발기간을반복검토했으므로최고적중률에는선정편향이있습니다.이번숫자를미래성능이나안정적인초과예측력으로해석하지않습니다.더많은실험을자동추가하지않고이번범위에서종료합니다.시간지연/갱신/학습창수정만으로충분한신호가생기는지는동일모델paired결과와비상승식별력을함께판단해야합니다.

준비단계에서대만반도체지수컬럼매핑오류1건을수정했으며초기오류로그를logs/PREBUILD_FAILURE_001.txt에보존했습니다.학습전에발생한오류로실패모델성적을삭제한것이아닙니다.모든학습시도·모델·예측을보존했습니다.
'''
    report+=f'\n구현 QC: {sum(c["PASS"] for c in checkrows)}/{len(checkrows)} PASS. 기존보호파일 {len(protections)}개 변경 {len(changed)}개, 연구C 전체10,515개 변경 {len(cchanges)}개. 모든저장모델의예측재현과원천feature/Y재계산을완료했습니다.\n\nPhase3·최종시험·2021년이후성과평가는미실행입니다.\n'
    text('COMPARISON_REPORT.md',report)
    text('README.md','# 1D 개발 수정 실험\n\nCOMPARISON_REPORT.md를먼저확인하십시오.설계는EXPERIMENT_PLAN.md,전체성과는MODEL_RESULTS.csv,변경별대조는CONTROLLED_PAIRED_COMPARISONS.csv입니다.실행순서는code/run_comparison.py→code/review_comparison.py.완료폴더에run을재실행하면보호baseline중복으로중단합니다.기존D원본manifest는그대로이며새산출물은이하위폴더별manifest에보존합니다.조건부역사실험이며완전한실시간PIT검증은아닙니다.\n')
    print(json.dumps({'passed':passed,'checks':len(checkrows),'failed':[c for c in checkrows if not c['PASS']],'best':best.to_dict()},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
