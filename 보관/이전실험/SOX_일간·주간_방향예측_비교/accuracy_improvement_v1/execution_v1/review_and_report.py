"""Post-execution verification/report only. No fitting or candidate selection changes."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import json,hashlib,sys
from pathlib import Path
import numpy as np,pandas as pd,joblib
from sklearn.metrics import roc_auc_score
from threadpoolctl import threadpool_limits
O=Path(__file__).resolve().parent;A=O.parent;D=A.parent;ROOT=D.parent;V=D/'development_revision_v1'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def csv(n,x):pd.DataFrame(x).to_csv(O/n,index=False,encoding='utf-8-sig')
def js(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def sameparams(a,b):return json.dumps(a,sort_keys=True,default=str)==json.dumps(b,sort_keys=True,default=str)
def mdtable(df,cols):
    z=df[cols].copy();z=z.map(lambda v:f'{v:.4f}' if isinstance(v,(float,np.floating)) else str(v))
    return '| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(r)+' |' for r in z.to_numpy().tolist())+'\n'
def main():
    sys.stdout.reconfigure(encoding='utf-8');threadpool_limits(1)
    assert not (O/'FINAL_VERIFICATION.json').exists(),'Do not overwrite sealed execution'
    checks=[]
    def ck(n,ok):
        checks.append(dict(check=n,PASS=bool(ok)))
        if not ok:csv('REVIEW_QC.csv',checks);raise RuntimeError(n)
    data=pd.read_csv(V/'data/LATEST_EOD_1D.csv',parse_dates=['date','label_end']).set_index('date').sort_index()
    cols=json.loads((V/'config/INFORMATION_SETS.json').read_text())['M1']
    hist=pd.read_csv(O/'logs/MONTHLY_SELECTION_HISTORY.csv');fits=pd.read_csv(O/'logs/FIT_ATTEMPTS.csv')
    ip=pd.read_csv(O/'predictions/INTERNAL_FIXED_BLOCK_PREDICTIONS.csv',parse_dates=['date']);ep=pd.read_csv(O/'predictions/EXTERNAL_PREDICTIONS.csv',parse_dates=['date'])
    ck('48_months',len(hist)==48 and hist.month.nunique()==48)
    ck('54_unique_inner_origins_each_C',all(ip[ip.C==c].block_start.nunique()==54 for c in [.01,.1,1]))
    ck('no_duplicate_internal_predictions',not ip.duplicated(['C','block_start','date']).any())
    ck('no_duplicate_fit_keys',not fits.duplicated(['C','month']).any())
    ck('fit_attempts_124_le_126',len(fits)==124 and (fits.status=='PASS').all())
    ck('R0_only_2016_12',len(fits[fits.C==1])==12 and fits[fits.C==1].month.str.startswith('2016').all())
    ck('selection_fallback_none',not hist.fallback.any())
    baseline_params=None;max_internal_error=0.;trace=[];params=[]
    for month in pd.period_range('2017-01','2020-12',freq='M'):
        m=joblib.load(V/f'models/C_latest_monthly_expanding_M1_LogisticClassifier_{month}.joblib')
        p={step:m.named_steps[step].get_params(deep=False) for step in ['impute','scale','model']}
        if baseline_params is None:baseline_params=p
        ck('all_cached_params_identical_'+str(month),sameparams(p,baseline_params))
        params.append(dict(month=str(month),parameters=p))
    for (c,start),z in ip.groupby(['C','block_start']):
        period=pd.Period(start,'M');trday=data[data.index.to_period('M')==period].index.min();origin=pd.to_datetime(data.loc[trday,'origin_et'],utc=True)
        tr=data[(data.index<trday)&(pd.to_datetime(data.label_available_et,utc=True)<origin)]
        path=O/f'models/C{c:g}_{start}.joblib' if c!=1 or period.year==2016 else V/f'models/C_latest_monthly_expanding_M1_LogisticClassifier_{start}.joblib'
        m=joblib.load(path);zz=z.sort_values('date');p=m.predict_proba(data.loc[zz.date,cols])[:,1]
        error=float(abs(p-zz.probability).max());max_internal_error=max(max_internal_error,error)
        ck('inner_disk_replay_'+str(c)+'_'+start,error<=1e-9)
        ck('inner_bounds_'+str(c)+'_'+start,len(tr)>=500 and tr.Y.nunique()==2 and len(z)>=80 and zz.date.min()>=period.start_time and zz.date.max()<(period+6).start_time)
    for r in hist.to_dict('records'):
        month=pd.Period(r['month'],'M');origin=pd.Timestamp(r['origin']);scores={};tscores={};nn=None
        for c in [.01,.1,1.]:
            z=ip[(ip.C==c)&ip.block_start.isin([str(month-12),str(month-6)])]
            z=z[pd.to_datetime(z.label_available,utc=True)<origin]
            scores[c]=int(((z.probability>=.5).astype(int)==z.Y).sum())
            if c==1:
                nn=len(z);tscores={t:int(((z.probability>=t).astype(int)==z.Y).sum()) for t in [.45,.5,.55]}
            ck('selection_past_only_'+str(month)+'_'+str(c),z.date.max()<month.start_time and (pd.to_datetime(z.label_available,utc=True)<origin).all())
        cs=min(scores,key=lambda c:(-scores[c],c!=1,c));ts=min(tscores,key=lambda t:(-tscores[t],t!=.5,abs(t-.5),t))
        ck('selection_recomputed_'+str(month),cs==r['selected_C'] and ts==r['selected_threshold'] and nn==r['inner_n'] and {float(k):v for k,v in json.loads(r['C_scores']).items()}==scores and {float(k):v for k,v in json.loads(r['threshold_scores']).items()}==tscores)
        trace.append(dict(month=str(month),C=cs,threshold=ts,inner_n=nn,PASS=True))
    ck('T1_probabilities_identical_R0',np.array_equal(ep[ep.policy=='T1'].probability.to_numpy(),ep[ep.policy=='R0'].probability.to_numpy()))
    ck('C1_threshold_fixed',np.all(ep[ep.policy=='C1'].threshold==.5));ck('T1_C_fixed',np.all(ep[ep.policy=='T1'].C==1))
    csv('REVIEW_QC.csv',checks);csv('SELECTION_RECOMPUTED.csv',trace);js('FULL_CACHED_PARAMETER_COMPARISON.json',params)
    ck('new_fit_params_only_C_changed',all((lambda p: all(sameparams(p.named_steps[s].get_params(),baseline_params[s]) for s in ['impute','scale']) and sameparams({**p.named_steps['model'].get_params(),'C':1},baseline_params['model']))(joblib.load(O/r.model_path)) for r in fits.itertuples()))
    csv('REVIEW_QC.csv',checks)
    metrics=pd.read_csv(O/'METRICS.csv');boot=pd.read_csv(O/'PAIRED_BLOCK_BOOTSTRAP.csv');summary=json.loads((O/'RUN_SUMMARY.json').read_text())
    pooled=metrics[metrics.period=='ALL'].copy();annual=metrics[metrics.period!='ALL'].copy()
    for z in [pooled,annual]:
        for c in ['accuracy','predicted_up_rate','recall_nonup','recall_up','BA']:z[c]*=100
    auc=[]
    for policy,w in ep.groupby('policy'):
        nums=[]
        for y,z in w.groupby(w.date.dt.year):nums.append((roc_auc_score(z.Y,z.probability),int((z.Y==0).sum())*int((z.Y==1).sum())))
        auc.append(dict(policy=policy,pooled_AUC=roc_auc_score(w.Y,w.probability),within_year_pair_weighted_AUC=sum(a*n for a,n in nums)/sum(n for a,n in nums)))
    csv('POOLED_VS_WITHIN_YEAR_AUC.csv',auc)
    changes=[]
    r0=ep[ep.policy=='R0'].set_index('date')
    for policy in ['C1','T1']:
        z=ep[ep.policy==policy].set_index('date')
        for year in ['ALL',2017,2018,2019,2020]:
            mask=np.ones(len(z),bool) if year=='ALL' else z.index.year==year
            x=z.loc[mask];b=r0.loc[x.index]
            changes.append(dict(policy=policy,period=year,changed_decisions=int((x.prediction!=b.prediction).sum()),repaired_R0_errors=int(((x.prediction==x.Y)&(b.prediction!=x.Y)).sum()),new_errors=int(((x.prediction!=x.Y)&(b.prediction==x.Y)).sum())))
    csv('DECISION_CHANGES.csv',changes)
    report='''# R0/A1/C1/T1 우선 실행 결과

C1(규제 선택)과 T1(임곗값 선택)은 각각 **553/1007일, 54.92%**로 R0의549일(54.52%)보다 **4일(+0.40%p)** 더 맞혔다. 그러나 항상 상승563일(55.91%)보다10일, 기존 개발 최고567일(56.31%)보다14일 적다. **주목표의 기준모형 초과 개선은 달성하지 못했다.** 보조지표로 성공을 선언하지 않는다.

C1의 R0 대비 연도별 정답 차이는2017 +5,2018 -5,2019 +1,2020 +3일이다. T1은 +5,-6,-3,+8일이다. T1의 이득은2020년에 집중되며2018~2019 손실과 상쇄된다. C1도 연도 전반의 일관된 개선은 아니다. C1과T1의 전체 정답 수는 같지만 예측은 다르다. C1은 입력을 유지한 규제 변화, T1은 동일 확률의 분류 임곗값 변화에 따른 결과다. 입력 변경 A1은 gate 미통과로 미실행이므로 아시아 입력의 효능을 판단할 수 없다.

## 동일 1,007일의 전체 비교

아래 accuracy·상승예측 비율은 %, delta_pp는 %p다. 차이는 후보−기준이다. 기존 최고 비교도 정확히 같은 날짜·Y의 저장 예측을 사용했다.

'''
    report+=mdtable(pooled,['policy','correct','accuracy','always_up_delta_correct','always_up_delta_pp','R0_delta_correct','R0_delta_pp','old_best_delta_correct','old_best_delta_pp','predicted_up_rate'])
    report+='\nR0 개선 여부: C1/T1만 YES. 항상 상승 초과: 모두 NO. 기존 최고 초과: 모두 NO. A1은 NOT_EXECUTED_GATE이며 성능 N/A, 학습0회다.\n\n## 연도별 전체 성적\n\n'
    report+=mdtable(annual,['policy','period','n','correct','accuracy','always_up_delta_correct','R0_delta_correct','old_best_delta_correct','predicted_up_rate'])
    report+='\n## 사전 고정 paired block-bootstrap\n\n20세션 비순환 moving-block,2,000회,seed20261019,95% percentile CI. 같은 기간의 모든 기준 비교에 동일 재표집 인덱스를 썼다. 표는 pooled %p이며 전체 연도별 구간은 PAIRED_BLOCK_BOOTSTRAP.csv에 보존했다.\n\n'
    report+=mdtable(boot[(boot.period=='ALL')&boot.reference.isin(['always_up','R0','old_best'])],['policy','reference','delta_correct','delta_pp','CI95_low_pp','CI95_high_pp'])
    report+='\nC1/T1의 R0 대비 구간도0을 포함한다. R0의 작은 개선을 확정된 우위로 해석하지 않는다. 이 구간은 후보 선택·반복 탐색 편향을 보정하지 않는다.\n\n## 보조지표 — 전체\n\nRecall·BA는 %다. 확률 성능은 각 외부 월 학습구간 상승비율 q와 대조했다. AUC는 pooled와 연도별을 혼합하지 않는다.\n\n'
    report+=mdtable(pooled,['policy','recall_nonup','recall_up','BA','MCC','AUC','Brier','Log_loss','q_Brier','q_Log_loss'])
    report+='\n## 보조지표 — 연도별\n\n'+mdtable(annual,['policy','period','recall_nonup','recall_up','BA','MCC','AUC','Brier','Log_loss','q_Brier','q_Log_loss'])
    report+='\n## AUC의 기간 구분\n\n'+mdtable(pd.DataFrame(auc),['policy','pooled_AUC','within_year_pair_weighted_AUC'])
    report+='\nT1은R0 확률을 그대로 사용하므로AUC/Brier/Log loss가 동일하다. 임곗값 변경 자체가 확률 예측력을 높였다고 해석할 수 없다. C1/T1 전체 상승예측 비중은84.51%로 R0의81.13%보다 높다. 특히2017 C1은98.80%, T1은99.60%로 거의 항상 상승이지만 전체 Accuracy는 항상 상승보다 낮다. 실제 클래스별 확률 분위수·집중도는 PROBABILITY_DISTRIBUTIONS.csv, 결정 수정과 신규 오류는 DECISION_CHANGES.csv에 모두 보존했다.\n\n## 월별 선택과 학습\n\n'
    report+='C 선택 횟수: '+str(hist.selected_C.value_counts().sort_index().to_dict())+'; 임곗값 선택 횟수: '+str(hist.selected_threshold.value_counts().sort_index().to_dict())+'.\n\n'
    report+=f'신규 fit **{summary["new_fit_attempts"]}/126회**: R0 2016년12회, C 대안112회(고유 내부108회+2020-07~12 선택 외부4회), T1 0회, A1 0회. 기존R0 48개 재사용. fit 실패0, 선택 fallback0개월, 평가일 누락0. 월별 후보별 내부 정답 수·선택 C/임곗값·origin·최후 성숙 라벨은 logs/MONTHLY_SELECTION_HISTORY.csv, 각 fit 시도/경고/학습 구간/캐시키는 logs/FIT_ATTEMPTS.csv에 남겼다.\n\n'
    report+='## A1의 미실행과 보존\n\n한국 역사적 특별 세션 및 대만 원천 날짜 불일치·지수 확정시각 gate를 해소하지 못했다. 일반 마감+2시간의 조건부 가용성 가정은 과거 벤더 전달 검증과 구분한다. 전달기록 부재만을 이유로 중단한 것이 아니다. 원천·연도·특징별 적용률0%/fallback100%, 날짜 부재와 계산창 불일치 사유를 A1_APPLICATION_RATES.csv 및 A1_GATE_ROW_AUDIT.csv에 보존했다. 미실행 A1을 R0 복제 후보로 평가하지 않았다. 기존 RAW·코드·계획·예측·모델·archives를 변경하지 않았다.\n\n## 직접 검증과 해석 한계\n\n기존 매니페스트와 이번 전후 해시 검사를 구분했다. 기존 D/수정연구/진단 매니페스트를 다시 확인하고, 캐시48개에 대해 학습행·라벨 성숙·53특징·클래스[0,1]·전처리와1,007개 외부확률을 직접 대조했다. 전체 캐시 파라미터 동일성, 새 모델 C 이외 설정 불변, 내부 고정6개월 예측의 디스크 모델 재생,48개월 선택 이력의 독립 재계산도 통과했다. 상세 QC 및 최종 보호파일 검사는 FINAL_VERIFICATION.json과 REVIEW_QC.csv 참조.\n\n내부는6개월 고정 모델, 외부는 월간 재학습으로 운용 방식이 다르다. 이 차이를 외부 결과에 맞춰 사후 변경하지 않았다. 2017~2020은 이미 반복 노출된 개발자료다. 이번3개 실행 정책, 기존 다수 후보 및 기존 최고 모두 선택 편향의 영향을 받으므로 독립 시험 성능이 아니다. A1 미실행으로 입력 개선 가설은 검증되지 않았다. 새 자료 수집·설치·2021년 이후 평가·1W·후순위132회·추가 알고리즘·클래스 가중·후보 결합·Phase3·최종 시험은 수행하지 않았다. **모든 후보를 보존하고 여기서 종료한다.**\n'
    (O/'RESULTS_REPORT.md').write_text(report,encoding='utf-8')
    # Final preservation reads every pre-existing protected file; no study files are written.
    before=pd.read_csv(O/'PROTECTED_BEFORE.csv');bad=[]
    for r in before.itertuples():
        p=ROOT/r.path
        if not p.is_file() or p.stat().st_size!=r.bytes or sha(p)!=r.sha256:bad.append(r.path)
    ck('final_preservation',not bad);csv('REVIEW_QC.csv',checks)
    js('FINAL_VERIFICATION.json',dict(status='PASS',protected_files=len(before),changed_files=bad,execution_QC_pass=len(pd.read_csv(O/'QC.csv')),review_QC_pass=len(checks),internal_probability_max_error=max_internal_error,new_fit_attempts=len(fits),fit_failures=0,A1='NOT_EXECUTED_GATE',R0_C1_T1='COMPLETED',independent_test=False,scope='R0/A1/C1/T1 only; no further search',environment_original=json.loads((V/'config/ENVIRONMENT.json').read_text())))
    # Seal after every report/QC writer has closed; excludes only the seal itself.
    files=[p for p in O.rglob('*') if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256']]
    csv('OUTPUT_MANIFEST.csv',[dict(path=p.relative_to(O).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(files)])
    (O/'OUTPUT_MANIFEST.sha256').write_text(sha(O/'OUTPUT_MANIFEST.csv')+'  OUTPUT_MANIFEST.csv\n',encoding='ascii')
    print('Review PASS',len(checks),'checks; sealed',len(files),'execution files. No further training.',flush=True)
if __name__=='__main__':main()
