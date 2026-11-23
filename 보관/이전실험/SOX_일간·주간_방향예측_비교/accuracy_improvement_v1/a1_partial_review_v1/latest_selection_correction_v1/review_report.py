"""Disk replay, independent metric/bootstrap checks and final preservation. No fitting."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import sys,math
import numpy as np,pandas as pd,joblib
from threadpoolctl import threadpool_limits
from common import *
def table(z,cols):
    x=z[cols].copy().map(lambda v:f'{v:.4f}' if isinstance(v,(float,np.floating)) else str(v))
    return '| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(r)+' |' for r in x.to_numpy().tolist())+'\n'
def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1);assert not (O/'FINAL_VERIFICATION.json').exists(),'Do not overwrite sealed review'
    pre=json.loads((O/'PREFLIGHT_RESULT.json').read_text());run=json.loads((O/'RUN_SUMMARY.json').read_text());assert pre['status']=='PASS' and run['new_fit_attempts']==96
    checks=[]
    def ck(n,ok,detail=''):
        checks.append(dict(check=n,PASS=bool(ok),detail=str(detail)))
        if not ok:csv('REVIEW_CHECKS.csv',checks);raise RuntimeError(n)
    for k,f in [('corrected_R0_file_sha256','data/CORRECTED_R0_1D.csv'),('corrected_KR_file_sha256','data/CORRECTED_A1_KR_ONLY_1D.csv')]:ck('data_hash_'+f,sha(O/f)==pre[k])
    ck('original_mask_hash',sha(P/'A1_PARTIAL_ROW_REVIEW.csv')==pre['input_mask_sha256'])
    data={p:pd.read_csv(O/f'data/{p}_1D.csv',parse_dates=['date','label_end']).set_index('date') for p in ['CORRECTED_R0','CORRECTED_A1_KR_ONLY']};b=data['CORRECTED_R0'];k=data['CORRECTED_A1_KR_ONLY'];cols=json.loads((V/'config/INFORMATION_SETS.json').read_text())['M1'];krcols=[c for c in cols if c.startswith('s01_')];others=[c for c in cols if c not in krcols]
    ck('identical48_values_and_missing',k[others].equals(b[others]) and np.array_equal(k[others].isna(),b[others].isna()))
    ck('same_labels_origins_dates',b.index.equals(k.index) and all(b[c].equals(k[c]) for c in ['Y','origin_et','label_available_et','label_end']))
    frozen=pd.read_csv(O/'inputs/FROZEN_KR_MASK.csv',parse_dates=['date']);mask=frozen.pivot(index='date',columns='feature',values='proposed_same_day_applied').reindex(b.index)
    for c in krcols:
        ck('fallback_corrected_R0_'+c,k.loc[~mask[c],c].equals(b.loc[~mask[c],c]))
        expected=frozen[(frozen.feature==c)&frozen.proposed_same_day_applied].set_index('date').proposed_native_value
        ck('same_day_frozen_value_'+c,np.allclose(k.loc[mask[c],c],expected,rtol=1e-12,atol=1e-12))
    fits=pd.read_csv(O/'logs/FIT_ATTEMPTS.csv');pr=pd.read_csv(O/'predictions/EXTERNAL_PREDICTIONS.csv',parse_dates=['date']);params=json.loads((O/'ESTIMATOR_PARAMETERS.json').read_text());metrics=pd.read_csv(O/'METRICS.csv');intervals=pd.read_csv(O/'PAIRED_BLOCK_BOOTSTRAP.csv');refs=pd.read_csv(O/'inputs/REFERENCE_PREDICTIONS.csv',parse_dates=['date']).set_index('date');refnames=['always_up','corrected_R0','SOX_best_567','legacy_KR_591','legacy_R0_549']
    ck('96fits48each',len(fits)==96 and (fits.status=='PASS').all() and fits.groupby('policy').size().to_dict()=={'CORRECTED_A1_KR_ONLY':48,'CORRECTED_R0':48} and len(list((O/'models').glob('*.joblib')))==96)
    replay=[]
    for f in fits.itertuples():
        z=data[f.policy];te=z[z.index.strftime('%Y-%m')==f.month];origin=pd.to_datetime(te.iloc[0].origin_et,utc=True);tr=z[(z.index<te.index[0])&(pd.to_datetime(z.label_available_et,utc=True)<origin)];m=joblib.load(O/f.model_path);saved=pr[(pr.policy==f.policy)&(pr.month==f.month)].set_index('date').loc[te.index];mat=tr[cols].to_numpy();med=np.nan_to_num(np.nanmedian(mat,axis=0),nan=0);filled=np.where(np.isnan(mat),med,mat);mean=filled.mean(axis=0);var=filled.var(axis=0);tt=te[cols].to_numpy();tt=np.where(np.isnan(tt),med,tt);est=m.named_steps['model'];logit=((tt-mean)/np.where(var>0,np.sqrt(var),1))@est.coef_[0]+est.intercept_[0];manual=np.array([1/(1+math.exp(-v)) for v in logit]);disk=m.predict_proba(te[cols])[:,1];err=float(abs(disk-saved.probability).max());err2=float(abs(manual-saved.probability).max())
        ck('model_hash_'+str(f.attempt),sha(O/f.model_path)==f.sha256)
        ck('model_params_'+str(f.attempt),canonical({s:m.named_steps[s].get_params(deep=False) for s in ['impute','scale','model']})==canonical(params) and list(m.classes_)==[0,1] and list(m.feature_names_in_)==cols)
        ck('new_preprocessing_'+str(f.attempt),np.allclose(med,m.named_steps['impute'].statistics_,rtol=1e-10,atol=1e-10) and np.allclose(mean,m.named_steps['scale'].mean_,rtol=1e-10,atol=1e-10) and np.allclose(var,m.named_steps['scale'].var_,rtol=1e-10,atol=1e-10))
        ck('predictions_'+str(f.attempt),err<=1e-9 and err2<=1e-9 and np.array_equal(manual>=.5,saved.prediction))
        ck('training_hash_maturity_'+str(f.attempt),framehash(tr[cols+['Y']])==f.training_XY_sha256 and len(tr)==f.train_n and (pd.to_datetime(tr.label_available_et,utc=True)<origin).all() and np.allclose(saved.training_up_probability,tr.Y.mean(),rtol=0,atol=1e-12))
        replay.append(dict(policy=f.policy,month=f.month,max_disk_error=err,max_manual_sigmoid_error=err2,train_n=len(tr),PASS=True))
    csv('MODEL_DISK_AND_SIGMOID_REPLAY.csv',replay)
    decisions=[]
    for policy,vv in pr.groupby('policy'):
        vv=vv.set_index('date').sort_index();ck('all1007_dates_'+policy,vv.index.equals(refs.index) and np.array_equal(vv.Y,refs.Y))
        for period in ['ALL',2017,2018,2019,2020]:
            v=vv if period=='ALL' else vv[vv.index.year==period];y=v.Y.to_numpy();p=v.probability.to_numpy();c=v.prediction.to_numpy();n=len(v);tn=int(((c==0)&(y==0)).sum());tp=int(((c==1)&(y==1)).sum());fp=int((y==0).sum())-tn;fn=int((y==1).sum())-tp;ru=tp/(tp+fn);rn=tn/(tn+fp);den=math.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn));auc=float(np.mean((p[y==1,None]>p[y==0])+.5*(p[y==1,None]==p[y==0])));loss=float(-np.mean(y*np.log(p)+(1-y)*np.log1p(-p)));r=metrics[(metrics.policy==policy)&(metrics.period==str(period))].iloc[0]
            ck('independent_metrics_'+policy+str(period),r.correct==tn+tp and r.TN==tn and r.TP==tp and np.isclose(r.accuracy,(tn+tp)/n) and np.isclose(r.recall_nonup,rn) and np.isclose(r.recall_up,ru) and np.isclose(r.BA,(ru+rn)/2) and np.isclose(r.MCC,(tp*tn-fp*fn)/den if den else 0) and np.isclose(r.AUC,auc) and np.isclose(r.Brier,np.mean((p-y)**2)) and np.isclose(r.Log_loss,loss))
            rng=np.random.default_rng(SEED);samples={name:[] for name in refnames};correct=(c==y).astype(int);ref={name:refs.loc[v.index,name].to_numpy() for name in refnames}
            for _ in range(2000):
                starts=rng.integers(0,n-19,size=int(np.ceil(n/20)));idx=np.concatenate([np.arange(s,s+20) for s in starts])[:n]
                for name,bc in ref.items():samples[name].append(float((correct-(bc==y).astype(int))[idx].mean()*100))
            for name,bc in ref.items():
                saved=intervals[(intervals.policy==policy)&(intervals.period==str(period))&(intervals.reference==name)].iloc[0];ci=np.quantile(samples[name],[.025,.975]);ck('CI_replay_'+policy+str(period)+name,np.allclose(ci,[saved.CI95_low_pp,saved.CI95_high_pp],rtol=0,atol=1e-10))
            bc=ref['corrected_R0'];decisions.append(dict(policy=policy,period=period,changed_decisions=int((c!=bc).sum()),repaired_R0_errors=int(((c==y)&(bc!=y)).sum()),new_errors=int(((c!=y)&(bc==y)).sum()),net_correct=int((c==y).sum()-(bc==y).sum())))
    csv('DECISION_CHANGES.csv',decisions);csv('REVIEW_CHECKS.csv',checks)
    r0=metrics[(metrics.policy=='CORRECTED_R0')&(metrics.period=='ALL')].iloc[0];kr=metrics[(metrics.policy=='CORRECTED_A1_KR_ONLY')&(metrics.period=='ALL')].iloc[0];impact=pd.read_csv(O/'CORRECTION_IMPACT.csv');impact['accuracy']*=100;show=metrics.copy()
    for c in ['accuracy','recall_nonup','recall_up','BA','predicted_up_rate']:show[c]*=100
    disposition=dict(primary='CORRECTED_KR_MINUS_CORRECTED_R0',observed_Accuracy_improvement=bool(kr.corrected_R0_delta_correct>0),beats_always_up=bool(kr.always_up_delta_correct>0),beats_SOX_best=bool(kr.SOX_best_567_delta_correct>0),corrected_R0_correct=int(r0.correct),corrected_KR_correct=int(kr.correct),delta_correct=int(kr.corrected_R0_delta_correct),delta_TN=int(kr.corrected_R0_delta_TN),delta_TP=int(kr.corrected_R0_delta_TP),legacy_KR_591_impact=int(kr.legacy_KR_591_delta_correct),independent_test=False,conditional_information_only=True)
    js('RESEARCH_DISPOSITION.json',disposition)
    report=f'''# 최신 적격 관측 선택 보정 비교 결과

보정 한국 후보는 비상승 **{int(kr.TN)}일**, 상승 **{int(kr.TP)}일**을 맞혔다. 보정 R0의 비상승{int(r0.TN)}일·상승{int(r0.TP)}일 대비 각각 **{int(kr.corrected_R0_delta_TN):+d}일 / {int(kr.corrected_R0_delta_TP):+d}일**, 합계 **{int(kr.corrected_R0_delta_correct):+d}일**이다.

주비교의 Accuracy는 보정 한국 **{100*kr.accuracy:.2f}%({int(kr.correct)}/1007)**, 보정 R0 **{100*r0.accuracy:.2f}%({int(r0.correct)}/1007)**로 차이는 **{kr.corrected_R0_delta_pp:+.2f}%p**다. 이 결과는 단일 정렬 오류 수정 후 같은 날짜·Y·모델 설정으로 재학습한 개발 비교이며, 독립 시험 성능은 아니다.

## 수정 범위와 사전 검증

available_date/source_date를 함께 명시적으로 정렬하고 같은 가용일에서는 최신 source_date를 선택했다. 해당 로직의11개 원천 전체를 검사했다. 같은 source_date 중복·충돌을 별도로 검사했으며 실제 충돌은0건이다. 합성 동일 중복/충돌, 원천/이벤트 입력 역순·무작위순, 적격 후보 전체의 독립 max(source_date) scan, 알려진 미국 휴장 경계를 모두 통과했다. 산식·시차·마스크·staleness10일 기준을 바꾸지 않았다.

실제 보정 R0 변경은 **{pre['R0_changed_cells']}셀**, 기존 한국 데이터 대비 보정 한국 변경은 **{pre['KR_changed_cells']}셀**이다. 기존 유한값 차이230셀 외에2020-01-28~30 TWII5특징의15개 결측 변화가 추가 확인됐다. 같은 오류로 과거원천01-17(11~13일경과)을 택해 결측이었으나 최신01-20(8~10일경과)을 택하면 원래10일 규칙에서 유효해진다. 최초 preflight는 이 추가 변경을 잡아 학습 전에 중단했고, 동일 오류의 영향임을 확인한 후 회귀검증을 보강했다. 최초FAIL/코드와 조사표를 보존했으며 이때fit0회였다. 새로운 원천 정책이나 결측 대체 방법을 도입한 것이 아니다.

보정 한국은 보정 R0에서 s01의5개만 동결 마스크로 당일값으로 교체했다. fallback도 보정 R0 값이다. 나머지48개 값·결측 위치, Y·origin·기간은 두 후보에서 동일하다. 대만13/23의 과거 관측 선택 오류도 보정 R0에 수정했지만 대만 당일 정렬 후보를 실행하거나 한국과 결합하지 않았다.

## 전체/연도별 성적과 클래스 적중

Accuracy·Recall·BA·상승예측 비중은%, 차이는 후보−기준이다.

'''
    report+=table(show,['policy','period','n','TN','FP','FN','TP','correct','accuracy'])
    report+='\n## 주비교 및 기준 대비 개선폭\n\n'+table(show[show.policy=='CORRECTED_A1_KR_ONLY'],['period','corrected_R0_delta_correct','corrected_R0_delta_pp','always_up_delta_correct','always_up_delta_pp','SOX_best_567_delta_correct','SOX_best_567_delta_pp'])
    yearly=metrics[(metrics.policy=='CORRECTED_A1_KR_ONLY')&(metrics.period!='ALL')];report+='\n보정 R0 대비 연도별 정답 차이: '+', '.join(f'{r.period} {int(r.corrected_R0_delta_correct):+d}일' for r in yearly.itertuples())+'. '
    report+=('모든연도에서관측개선이양수다.' if (yearly.corrected_R0_delta_correct>0).all() else '모든연도에서일관된양의개선은아니다.')+'\n\n'
    report+='## 오류 수정 영향 — 기존 결과와 별도 비교\n\n기존58.69%(591일)와 기존R0 549일은 덮어쓰지 않는다. 이 표는 각 정책의 오류 수정 전후 차이이며, 한국 당일 정보의 주효과 비교와 구분한다.\n\n'+table(impact,['policy','period','legacy_reference','correct','accuracy','delta_TN','delta_TP','delta_correct','delta_pp'])
    report+='\n## 사전 고정 신뢰구간\n\n20세션 비순환 moving-block bootstrap2,000회,seed20261019,percentile95% CI다. 같은기간각대조에동일재표집인덱스를썼다. 아래는보정한국의주비교/항상상승/기존SOX최고및자신의오류수정영향이다. 보정R0의수정영향을포함한전체구간은 PAIRED_BLOCK_BOOTSTRAP.csv에보존했다.\n\n'
    report+=table(intervals[(intervals.policy=='CORRECTED_A1_KR_ONLY')&intervals.reference.isin(['corrected_R0','always_up','SOX_best_567','legacy_KR_591'])],['period','reference','delta_correct','delta_pp','CI95_low_pp','CI95_high_pp'])
    ciall=intervals[(intervals.policy=='CORRECTED_A1_KR_ONLY')&(intervals.period=='ALL')]
    report+='\n전체기간 구간 해석: '+ '; '.join(f'{name} 대비 [{float(ciall[ciall.reference==ref].CI95_low_pp.iloc[0]):+.2f}, {float(ciall[ciall.reference==ref].CI95_high_pp.iloc[0]):+.2f}]%p' for name,ref in [('보정R0','corrected_R0'),('항상상승','always_up'),('기존SOX최고','SOX_best_567')])+'. 0포함여부와별개로반복개발/선택편향은보정하지않는다.\n\n'
    report+='## 보조지표\n\n'+table(show,['policy','period','recall_nonup','recall_up','BA','MCC','AUC','Brier','Log_loss','q_Brier','q_Log_loss','predicted_up_rate'])
    report+='\npooledAUC와연도내쌍가중AUC는구분한다.\n\n'+table(pd.read_csv(O/'POOLED_VS_WITHIN_YEAR_AUC.csv'),['policy','pooled_AUC','within_year_pair_weighted_AUC'])
    report+='\n## 고정 마스크와 보조 하위집합\n\n마스크는초기1,488일 중1,290일(86.69%), 평가1,007일 중846일(84.01%)에적용된다. fallback은각각198일(13.31%)/161일(15.99%)이며 범위를성능에따라변경하지않았다. 사유별/연도별/특징별적용률은 APPLICATION_RATES.csv, APPLICATION_RATES_BY_YEAR.csv, FALLBACK_REASONS.csv다. 새한국 fallback은오류보정R0를사용했다.\n\n'
    sub=pd.read_csv(O/'FIXED_MASK_SUBSET_AUXILIARY.csv');sub=sub[sub.period=='ALL'].copy();sub['accuracy']*=100
    report+=table(sub,['policy','subset','n','correct','accuracy','corrected_R0_delta_correct','always_up_delta_correct','SOX_best_567_delta_correct'])
    report+='\n위하위집합은보조분석이고전체1,007일주평가를대체하지않는다. 학습입력도바뀌므로fallback일예측도변할수있으며순수한당일입력의인과효과로해석하지않는다. 적용일만이어붙인20세션CI를주평가구간으로쓰지않았다.\n\n'
    report+='## 학습·보존·한계\n\n총신규fit96회(정책별48), 실패0회, 재시도0회다. 두정책모두모든월에서기존학습X가달라기존캐시재사용0회이며그근거를 CACHE_REUSE_ASSESSMENT.csv에보존했다. 설정·전처리·seed·라벨성숙·학습기간을유지했고새모델96개의파일해시·학습전처리·저장예측·직접sigmoid·혼동행렬·AUC/손실·bootstrap을독립재확인했다. 보존검사수와최대오차는 FINAL_VERIFICATION.json을참조한다.\n\n실제과거벤더전달과원래vintage동일성은미입증인조건부역사실험이다. 고정마스크가제외한특별일/기간의효과로확대해석할수없다.2017~2020은이미반복노출된개발자료이며이비교와기존최고모두선택편향의영향을받는다. 실행QC PASS와연구목표개선/확정적일반화우위는구분한다.\n\n기존결과·오류보고서는그대로보존했다. 보정비교후추가튜닝·후보결합·대만비교·신규수집·설치·2021년이후평가·1W·Phase3·최종시험을하지않고종료한다.\n'
    (O/'RESULTS_REPORT.md').write_text(report,encoding='utf-8')
    before=pd.read_csv(O/'PROTECTED_BEFORE.csv');bm={r.path:(r.bytes,r.sha256) for r in before.itertuples()};after=snapshot();am={r['path']:(r['bytes'],r['sha256']) for r in after};changed=[p for p,x in bm.items() if am.get(p)!=x];added=sorted(set(am)-set(bm));ck('all_existing_preserved',not changed);ck('new_files_only_here',not added);csv('REVIEW_CHECKS.csv',checks)
    final=dict(status='PASS',research_disposition=disposition,protected_before=len(before),protected_after=len(after),changed_existing_files=changed,added_outside=added,new_fit_attempts=96,fit_failures=0,budget=96,legacy_cache_reused=0,preflight_checks=pre['checks'],review_checks=len(checks),max_disk_probability_error=max(r['max_disk_error'] for r in replay),max_manual_sigmoid_error=max(r['max_manual_sigmoid_error'] for r in replay),R0_correction_cells=pre['R0_changed_cells'],KR_correction_cells=pre['KR_changed_cells'],additional_missing_cells=15,mask_changed=False,TW_comparison_executed=False)
    js('FINAL_VERIFICATION.json',final);run['status']='COMPLETED_VERIFIED';js('RUN_SUMMARY.json',run)
    files=sorted(p for p in O.rglob('*') if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256']);csv('OUTPUT_MANIFEST.csv',[dict(path=p.relative_to(O).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]);(O/'OUTPUT_MANIFEST.sha256').write_text(sha(O/'OUTPUT_MANIFEST.csv')+'  OUTPUT_MANIFEST.csv\n',encoding='ascii')
    print(json.dumps(final,ensure_ascii=False,indent=2),flush=True);print('Sealed',len(files),'files; stopping.',flush=True)
if __name__=='__main__':main()
