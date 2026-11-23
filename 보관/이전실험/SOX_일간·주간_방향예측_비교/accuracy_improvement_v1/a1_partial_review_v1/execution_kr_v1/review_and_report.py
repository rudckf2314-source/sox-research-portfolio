"""Independent disk, metric and preservation review. Never trains or tunes."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import sys,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd,joblib
from threadpoolctl import threadpool_limits
O=Path(__file__).resolve().parent;P=O.parent;A=P.parent;D=A.parent;ROOT=D.parent;V=D/'development_revision_v1'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def js(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def csv(n,x):pd.DataFrame(x).to_csv(O/n,index=False,encoding='utf-8-sig')
def canonical(x):return json.dumps(x,sort_keys=True,default=str)
def table(z,cols):
    x=z[cols].copy().map(lambda v:f'{v:.4f}' if isinstance(v,(float,np.floating)) else str(v))
    return '| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(r)+' |' for r in x.to_numpy().tolist())+'\n'
def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1);assert not (O/'FINAL_VERIFICATION.json').exists(),'Do not overwrite sealed execution'
    checks=[]
    def ck(n,ok,detail=''):
        checks.append(dict(check=n,PASS=bool(ok),detail=str(detail)))
        if not ok:csv('REVIEW_QC.csv',checks);raise RuntimeError(n)
    pre=json.loads((O/'PREFLIGHT.json').read_text());params=json.loads((O/'ESTIMATOR_PARAMETERS.json').read_text())
    for path,key in [(P/'A1_PARTIAL_ROW_REVIEW.csv','mask_source_sha256'),(O/'inputs/FROZEN_KR_MASK.csv','frozen_KR_mask_sha256'),(P/'REVIEW_SCOPE.md','scope_sha256'),(P/'REVISED_EXPERIMENT_PLAN.md','source_plan_sha256'),(O/'EXECUTION_SPEC.md','execution_spec_sha256')]:ck('frozen_hash_'+path.name,sha(path)==pre[key])
    data=pd.read_csv(O/'data/KR_ONLY_1D.csv',parse_dates=['date','label_end']).set_index('date');old=pd.read_csv(V/'data/LATEST_EOD_1D.csv',parse_dates=['date','label_end']).set_index('date')
    cols=json.loads((V/'config/INFORMATION_SETS.json').read_text())['M1'];kr=[c for c in cols if c.startswith('s01_')];others=[c for c in cols if c not in kr]
    ck('same_Y_origins_dates',data.index.equals(old.index) and data.Y.equals(old.Y) and data.origin_et.equals(old.origin_et) and data.label_available_et.equals(old.label_available_et))
    ck('other48_preserved_disk',np.allclose(data[others],old[others],rtol=1e-12,atol=1e-12,equal_nan=True))
    mask=pd.read_csv(O/'inputs/FROZEN_KR_MASK.csv',parse_dates=['date']);pivot=mask.pivot(index='date',columns='feature',values='proposed_same_day_applied').reindex(data.index)
    ck('disk_fixed_values',all(np.allclose(data.loc[~pivot[f],f],old.loc[~pivot[f],f],rtol=1e-12,atol=1e-12,equal_nan=True) for f in kr))
    ck('disk_applied_values',all(np.allclose(data.loc[pivot[f],f],mask[(mask.feature==f)&mask.proposed_same_day_applied].set_index('date').proposed_native_value,rtol=1e-12,atol=1e-12) for f in kr))
    ck('fixed846_days',int(pivot[pivot.index.year>=2017].any(axis=1).sum())==846)
    fits=pd.read_csv(O/'logs/FIT_ATTEMPTS.csv');pred=pd.read_csv(O/'predictions/EXTERNAL_PREDICTIONS.csv',parse_dates=['date']).set_index('date');met=pd.read_csv(O/'METRICS.csv');ci=pd.read_csv(O/'PAIRED_BLOCK_BOOTSTRAP.csv');aux=pd.read_csv(O/'FIXED_MASK_SUBSET_AUXILIARY.csv')
    ck('fit_count_and_failures',len(fits)==48 and fits.month.nunique()==48 and (fits.status=='PASS').all() and len(list((O/'models').glob('*.joblib')))==48)
    ck('one_candidate_only',set(pred.policy)=={'A1_KR_ONLY'} and len(pred)==1007 and pred.index.equals(data[data.index.year>=2017].index))
    ck('predictions_match_label_and_threshold',np.array_equal(pred.Y,data.loc[pred.index].Y) and np.array_equal(pred.prediction,(pred.probability>=.5).astype(int)) and (pred.threshold==.5).all() and (pred.C==1).all())
    replay=[]
    for f in fits.itertuples():
        month=pd.Period(f.month,'M');test=data[data.index.to_period('M')==month];origin=pd.to_datetime(test.iloc[0].origin_et,utc=True);tr=data[(data.index<test.index[0])&(pd.to_datetime(data.label_available_et,utc=True)<origin)]
        m=joblib.load(O/f.model_path);pp=m.predict_proba(test[cols])[:,1];err=float(abs(pp-pred.loc[test.index].probability.to_numpy()).max())
        med=np.nan_to_num(np.nanmedian(tr[cols],axis=0),nan=0);filled=np.where(np.isnan(tr[cols]),med,tr[cols])
        ck('model_file_hash_'+f.month,sha(O/f.model_path)==f.sha256)
        ck('new_model_settings_'+f.month,canonical({s:m.named_steps[s].get_params(deep=False) for s in ['impute','scale','model']})==canonical(params) and list(m.classes_)==[0,1] and list(m.feature_names_in_)==cols)
        ck('disk_probability_'+f.month,err<=1e-9)
        ck('new_fold_preprocess_'+f.month,np.allclose(m.named_steps['impute'].statistics_,med,rtol=1e-10,atol=1e-10) and np.allclose(m.named_steps['scale'].mean_,filled.mean(axis=0),rtol=1e-10,atol=1e-10) and np.allclose(m.named_steps['scale'].var_,filled.var(axis=0),rtol=1e-10,atol=1e-10))
        ck('q_and_train_rows_'+f.month,len(tr)==f.train_n and str(tr.index[0].date())==f.train_start and str(tr.index[-1].date())==f.train_end and np.allclose(pred.loc[test.index].training_up_probability,tr.Y.mean(),rtol=0,atol=1e-12) and (pd.to_datetime(tr.label_available_et,utc=True)<origin).all())
        replay.append(dict(month=f.month,max_disk_probability_error=err,train_n=len(tr),PASS=True))
    csv('NEW_MODEL_DISK_REPLAY.csv',replay)
    confusion=[];decisions=[];auc=[]
    for period in ['ALL','2017','2018','2019','2020']:
        v=pred if period=='ALL' else pred[pred.index.year==int(period)];y=v.Y.to_numpy();p=v.probability.to_numpy();c=v.prediction.to_numpy();q=v.training_up_probability.to_numpy();n=len(v)
        tn=int(((c==0)&(y==0)).sum());fp=int(((c==1)&(y==0)).sum());fn=int(((c==0)&(y==1)).sum());tp=int(((c==1)&(y==1)).sum());ra=tp/(tp+fn);rn=tn/(tn+fp);den=np.sqrt(float((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn)));mcc=(tp*tn-fp*fn)/den if den else 0.
        r=met[(met.policy=='A1_KR_ONLY')&(met.period==period)].iloc[0]
        aa=float(((p[y==1,None]>p[y==0]).sum()+.5*(p[y==1,None]==p[y==0]).sum())/((y==1).sum()*(y==0).sum()))
        loss=float(-np.mean(y*np.log(np.clip(p,1e-15,1))+(1-y)*np.log(np.clip(1-p,1e-15,1))))
        ck('independent_metrics_'+period,r.correct==tp+tn and np.isclose(r.accuracy,(tp+tn)/n) and np.isclose(r.recall_up,ra) and np.isclose(r.recall_nonup,rn) and np.isclose(r.BA,(ra+rn)/2) and np.isclose(r.MCC,mcc) and np.isclose(r.AUC,aa) and np.isclose(r.Brier,np.mean((p-y)**2)) and np.isclose(r.Log_loss,loss))
        confusion.append(dict(period=period,n=n,TN=tn,FP=fp,FN=fn,TP=tp,correct=tp+tn))
        rng=np.random.default_rng(20261019);correct=(c==y).astype(int);refdict={'always_up':v.always_up_prediction.to_numpy(),'R0':v.R0_prediction.to_numpy(),'old_best':v.old_best_prediction.to_numpy()};samples={name:[] for name in refdict}
        for _ in range(2000):
            starts=rng.integers(0,n-19,size=int(np.ceil(n/20)));idx=np.concatenate([np.arange(s,s+20) for s in starts])[:n]
            for name,b in refdict.items():samples[name].append(float((correct-(b==y).astype(int))[idx].mean()*100))
        for name,b in refdict.items():
            expected=np.quantile(samples[name],[.025,.975]);saved=ci[(ci.policy=='A1_KR_ONLY')&(ci.period==period)&(ci.reference==name)].iloc[0]
            ck('bootstrap_replay_'+period+'_'+name,np.allclose(expected,[saved.CI95_low_pp,saved.CI95_high_pp],rtol=0,atol=1e-10))
        base=v.R0_prediction.to_numpy();decisions.append(dict(period=period,changed_decisions=int((c!=base).sum()),repaired_R0_errors=int(((c==y)&(base!=y)).sum()),new_errors=int(((c!=y)&(base==y)).sum()),net_correct=int((c==y).sum()-(base==y).sum())))
        for name,sel in [('fixed_applied_days',v.same_day_applied.to_numpy()),('fixed_fallback_days',~v.same_day_applied.to_numpy())]:
            ar=aux[(aux.policy=='A1_KR_ONLY')&(aux.period==period)&(aux.subset==name)].iloc[0];ck('auxiliary_only_'+period+name,int(sel.sum())==ar.n and int((c[sel]==y[sel]).sum())==ar.correct)
    csv('CONFUSION_COUNTS.csv',confusion);csv('DECISION_CHANGES.csv',decisions)
    for policy,probcol in [('A1_KR_ONLY','probability'),('R0','R0_probability')]:
        weighted=0.;den=0
        for year,v in pred.groupby(pred.index.year):
            pp=v[probcol].to_numpy();yy=v.Y.to_numpy();pairs=int((yy==1).sum()*(yy==0).sum());a=((pp[yy==1,None]>pp[yy==0]).sum()+.5*(pp[yy==1,None]==pp[yy==0]).sum())/pairs;weighted+=a*pairs;den+=pairs
        auc.append(dict(policy=policy,pooled_AUC=float(met[(met.policy==policy)&(met.period=='ALL')].AUC.iloc[0]),within_year_pair_weighted_AUC=float(weighted/den)))
    csv('POOLED_VS_WITHIN_YEAR_AUC.csv',auc)
    ck('no_TW_or_additional_candidate_models',all(p.name.startswith('A1_KR_ONLY_') for p in (O/'models').glob('*')))
    csv('REVIEW_QC.csv',checks)
    r=met[(met.policy=='A1_KR_ONLY')&(met.period=='ALL')].iloc[0];d=pd.DataFrame(decisions).iloc[0];status='ACCURACY_IMPROVEMENT_FAILED' if r.always_up_delta_correct<=0 else 'DEVELOPMENT_ACCURACY_ABOVE_ALWAYS_UP'
    study=dict(disposition=status,R0_improved=bool(r.R0_delta_correct>0),always_up_exceeded=bool(r.always_up_delta_correct>0),old_best_exceeded=bool(r.old_best_delta_correct>0),correct=int(r.correct),n=1007,accuracy=float(r.accuracy),delta_correct_vs_R0=int(r.R0_delta_correct),delta_correct_vs_always_up=int(r.always_up_delta_correct),delta_correct_vs_old_best=int(r.old_best_delta_correct),independent_test=False,conditional_historical_information=True)
    js('RESEARCH_DISPOSITION.json',study)
    show=met.copy()
    for c in ['accuracy','recall_nonup','recall_up','BA','predicted_up_rate']:show[c]*=100
    report=f'''# A1_KR_ONLY 고정 마스크 실행 결과

전체1,007일 중 **{int(r.correct)}일, Accuracy {100*r.accuracy:.2f}%**. R0 대비 **{int(r.R0_delta_correct):+d}일({r.R0_delta_pp:+.2f}%p)**, 항상 상승 대비 **{int(r.always_up_delta_correct):+d}일({r.always_up_delta_pp:+.2f}%p)**, 기존 최고 대비 **{int(r.old_best_delta_correct):+d}일({r.old_best_delta_pp:+.2f}%p)**이다. 연구 판정은 **{status}**이며 실행·무결성 QC PASS와 구분한다. 기준은각각563/549/567일이며 모두같은평가일·Y의저장예측과대조했다.

변경한 것은 s01의기존5특징에고정마스크로적용한당일정보정렬뿐이다. 나머지48특징과Y·09:00 ET origin·월간expanding·Logistic C1·threshold.5·전처리/전체파라미터는유지했다. R0의오류 {int(d.repaired_R0_errors)}일을고쳤고 새오류 {int(d.new_errors)}일을만들어 순차이는{int(d.net_correct):+d}일이다. 대만·C1/T1·추가튜닝·결합은실행하지않았다.

## 전체 성적 및 기준별 차이

Accuracy와예측비중/Recall/BA는%,delta_pp는%p다.

'''
    report+=table(show[show.period=='ALL'],['policy','n','correct','accuracy','always_up_delta_correct','always_up_delta_pp','R0_delta_correct','R0_delta_pp','old_best_delta_correct','old_best_delta_pp'])
    report+='\n## 연도별 주평가\n\n'+table(show[(show.policy=='A1_KR_ONLY')&(show.period!='ALL')],['period','n','correct','accuracy','always_up_delta_correct','always_up_delta_pp','R0_delta_correct','R0_delta_pp','old_best_delta_correct','old_best_delta_pp'])
    differences=met[(met.policy=='A1_KR_ONLY')&(met.period!='ALL')][['period','R0_delta_correct']];report+='\nR0 대비 연도별 정답 수 차이: '+', '.join(f'{x.period} {int(x.R0_delta_correct):+d}일' for x in differences.itertuples())+'. '
    report+=('모든연도에서양수다. 다만아래불확실성구간과반복개발편향을함께해석해야한다.' if (differences.R0_delta_correct>0).all() else '모든연도에서일관된양의개선은아니다.')+'\n\n'
    report+='## 사전 고정 paired block-bootstrap\n\n20세션 비순환 moving-block,2,000회,seed20261019,percentile95% CI. 아래전체/연도별각기준대비구간은%p다. 기간별세기준에같은재표집인덱스를사용했다.\n\n'+table(ci[ci.policy=='A1_KR_ONLY'],['period','reference','delta_correct','delta_pp','CI95_low_pp','CI95_high_pp'])
    report+='\n## 보조지표\n\n'+table(show,['policy','period','recall_nonup','recall_up','BA','MCC','AUC','Brier','Log_loss','q_Brier','q_Log_loss','predicted_up_rate'])
    report+='\npooled와연도내쌍가중AUC는구분한다.\n\n'+table(pd.DataFrame(auc),['policy','pooled_AUC','within_year_pair_weighted_AUC'])
    report+='\n## 고정 적용일 보조분석\n\n마스크가사전에고정된적용846일/fallback161일분석이며전체1,007일주평가를대체하지않는다. 각월의학습입력도변경돼 fallback일에도예측이변할수있다. 따라서하위집합차이를당일입력의순수한인과기여로해석하지않는다. 적용일을이어붙인20세션CI는주평가구간으로제시하지않았다.\n\n'
    ash=aux.copy();ash['accuracy']*=100;report+=table(ash[(ash.policy=='A1_KR_ONLY')&(ash.period=='ALL')],['subset','n','correct','accuracy','always_up_delta_correct','R0_delta_correct','old_best_delta_correct'])
    report+='\n연도별고정마스크하위집합결과도 FIXED_MASK_SUBSET_AUXILIARY.csv에보존했다. 모든실제클래스별확률분포는 PROBABILITY_DISTRIBUTIONS.csv, 오류수정/신규오류는 DECISION_CHANGES.csv다.\n\n## 적용률·fallback\n\n'
    rates=pd.read_csv(O/'APPLICATION_DAYS_BY_YEAR.csv');report+=table(rates,['scope','year','days','applied_days','fallback_days','application_pct','fallback_pct'])
    report+='\n초기학습기간은1,488일 중1,290일(86.69%) 적용/198일(13.31%) fallback, 평가는1,007일 중846일(84.01%) 적용/161일(15.99%) fallback이다. 대상5특징모두같은날마스크를쓰며 분모는해당대상일/특징이다. 학습기간의연초첫native일·11월·2020년12월제한과2019-11-14예외를성능에따라변경하지않았다. 원천부재를휴장으로단정하지않고계획의원래값으로fallback했다. 사유는 FALLBACK_REASONS.csv, 월별누적학습적용셀은 logs/FOLD_PREFLIGHT.csv다.\n\n'
    report+='## 실행·검증·해석 한계\n\n신규fit시도48회/상한48회, 실패0회, 자동재시도0회. 별도내부grid선택없음. 실행전기존seal·RAW01해시·동결마스크·현지마감+2시간→미동부시각·실제학습/평가행·Y·라벨성숙·R0캐시48개의확률/전처리를확인했다. 실행후새모델48개를디스크에서읽어예측과학습전처리를재생하고, 혼동행렬·AUC·확률손실·bootstrap구간을독립재계산했다. 전체보존결과와검사수는 FINAL_VERIFICATION.json을참조한다.\n\n실제과거벤더전달기록과원래vintage는미입증이며, 조건부시장정보가용성의역사실험이다. 일부한국특별일을확인하지못해범위를보수적으로제한한마스크의효과이며전기간모든당일정보효과로일반화할수없다.2017~2020은반복노출된개발자료이므로기존최고와이후보모두선택편향의영향을받는다. 신뢰구간은이를보정하지않으며독립시험성능이아니다. 보조지표만좋아진결과를Accuracy성공으로부르지않는다.\n\n결과를보존하고여기서종료한다. A1_TW23_ONLY·추가튜닝·후보결합·신규수집·설치·2021년이후평가·1W·Phase3·최종시험은실행하지않았다.\n'
    (O/'RESULTS_REPORT.md').write_text(report,encoding='utf-8')
    before=pd.read_csv(O/'PROTECTED_BEFORE.csv');beforemap={r.path:(r.bytes,r.sha256) for r in before.itertuples()};after={}
    for b,ds,fs in os.walk(ROOT,followlinks=False):
        ds[:]=[n for n in ds if n not in {'.git','.venv','.venv_W1'} and not (Path(b)/n).resolve().is_relative_to(O)]
        for n in fs:
            p=Path(b)/n;after[p.relative_to(ROOT).as_posix()]=(p.stat().st_size,sha(p))
    changed=[p for p,x in beforemap.items() if after.get(p)!=x];added=sorted(set(after)-set(beforemap));ck('existing_files_unchanged',not changed);ck('no_new_files_outside_execution',not added);csv('REVIEW_QC.csv',checks)
    final=dict(status='PASS',research_disposition=study,new_fit_attempts=48,fit_failures=0,budget=48,protected_before=len(before),protected_after=len(after),changed_existing_files=changed,added_outside_execution=added,primary_n=1007,applied_evaluation_days=846,fallback_evaluation_days=161,TW23_executed=False,mask_changed=False,additional_tuning=False,original_QC_pass=len(pd.read_csv(O/'QC.csv')),independent_review_QC_pass=len(checks),max_disk_probability_error=max(r['max_disk_probability_error'] for r in replay))
    js('FINAL_VERIFICATION.json',final)
    run=json.loads((O/'RUN_SUMMARY.json').read_text());run['status']='COMPLETED_VERIFIED';run['research_disposition']=status;run['protected_changed']=len(changed);js('RUN_SUMMARY.json',run)
    files=sorted(p for p in O.rglob('*') if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256'])
    csv('OUTPUT_MANIFEST.csv',[dict(path=p.relative_to(O).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]);(O/'OUTPUT_MANIFEST.sha256').write_text(sha(O/'OUTPUT_MANIFEST.csv')+'  OUTPUT_MANIFEST.csv\n',encoding='ascii')
    print(json.dumps(final,ensure_ascii=False,indent=2),flush=True);print('Sealed',len(files),'files. Stopping; no Taiwan execution.',flush=True)
if __name__=='__main__':main()
