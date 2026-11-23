"""Explain fixed existing classifiers; reconstruction must reproduce sealed forecasts."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import sys
import numpy as np,pandas as pd,joblib
from threadpoolctl import threadpool_limits
import crossed_feature_algorithm_search_20261023 as s
from verify_crossed_feature_search_20261023 import transform
O=s.W/'outputs/importance_classification_20261024'
CASES=[('BINARY_BEST_OBSERVED','G001100_MONTH2_FIRST','BINARY','LGBM'),('BINARY_REFERENCE','G110000_NONE','BINARY','LR'),('FOUR_BEST_OBSERVED','G001100_MONTH2_FIRST','FOUR','LR')]
def main():
    threadpool_limits(1);s.verify();O.mkdir(exist_ok=False);x,y,fs=s.parent.inputdata();allm={r['mask']:r for r in s.load(s.O/'MASKS.json')}
    dictionary=pd.read_csv(s.W/'outputs/research_D_portable_package_v1_20261022/SOX_D_Portable_20261022/data/FEATURE_DICTIONARY.csv').set_index('feature')
    labels={c:str(r.source)+' '+str(r.description) for c,r in dictionary.iterrows()}
    extra=pd.read_csv(s.W/'outputs/market_fgi_features_v1_20261023/변수설명_RAW_계산식_가용조건.csv')
    labels.update(dict(zip(extra['변수명'],extra['설명'])))
    labels.update(s02_atr14_reseeded_pct_partial='SOX ATR14/종가(부분 OHLC 정책)',s02_bb20_width_pct='SOX 볼린저밴드20 너비')
    state={case:dict(rows={},n=0,loss=0.,correct=0,nonup_correct=0,nonup_n=0) for case,_,_,_ in CASES};rng=np.random.default_rng(20261024);reconstructed=0;restored=0;monthly=[]
    for window in s.load(s.O/'late_COMPLETE.json')['windows']:
        mo=window['window'];root=s.O/'windows'/('late_'+mo);seal=s.load(root/'COMPLETE.json');assert s.sha(root/'TRAIN_TRANSFORM.joblib')==seal['transform_sha256']
        with np.load(root/'PREDICTIONS_NO_Y.npz') as z:dates=z['dates'].astype(str);order=list(zip(z['mask'].astype(str),z['task'].astype(str),z['algo'].astype(str)));saved=z['probabilities']
        stats=joblib.load(root/'TRAIN_TRANSFORM.joblib');a,b,names,td=transform(x,fs,stats,mo+'-01',dates);masks=s.load(root/'FEATURE_MASKS.json');models=joblib.load(s.O/'audit_models'/f'late_{mo}.joblib') if seal['audit_models'] else {}
        for case,mask,task,algo in CASES:
            k=2 if task=='BINARY' else 4;ix=[names.index(c) for c in masks[mask]];at=a[:,ix];bt=b[:,ix];target='Y' if k==2 else 'class4';yy=y.loc[dates,target].to_numpy(int);key=order.index((mask,task,algo))
            if models:model=models[str(key)];restored+=1
            else:model=s.estimator(algo,task);model.fit(at,y.loc[td,target].to_numpy(int));reconstructed+=1
            pp=model.predict_proba(bt);assert np.allclose(pp,saved[key,:,:k],atol=1e-9,rtol=1e-8)
            def losses(p):return -np.log(np.clip(p[np.arange(len(yy)),yy],1e-15,1))
            def predict(p):return (p[:,1]>=.5).astype(int) if k==2 else p.argmax(1)
            base=losses(pp);pr=predict(pp);basecorrect=int((pr==yy).sum());nn=int((yy==0).sum()) if k==2 else 0;tn=int(((pr==0)&(yy==0)).sum()) if k==2 else 0;st=state[case];st['n']+=len(yy);st['loss']+=float(base.sum());st['correct']+=basecorrect;st['nonup_n']+=nn;st['nonup_correct']+=tn
            for j,c in enumerate(masks[mask]):
                if c not in st['rows']:st['rows'][c]=dict(months=0,varying_months=0,within_loss=np.zeros(5),within_correct_drop=np.zeros(5),within_TN_drop=np.zeros(5),past_loss=np.zeros(5))
                r=st['rows'][c];r['months']+=1;varies=np.ptp(bt[:,j])>1e-10;r['varying_months']+=int(varies)
                for repeat in range(5):
                    if varies:
                        perturbed=bt.copy();perturbed[:,j]=perturbed[rng.permutation(len(bt)),j];prob=model.predict_proba(perturbed);pred=predict(prob)
                        r['within_loss'][repeat]+=float((losses(prob)-base).sum());r['within_correct_drop'][repeat]+=basecorrect-int((pred==yy).sum())
                        if k==2:r['within_TN_drop'][repeat]+=tn-int(((pred==0)&(yy==0)).sum())
                    # A separate, clearly labeled sensitivity test can vary monthly-constant French PCs.
                    perturbed=bt.copy();perturbed[:,j]=at[rng.integers(max(0,len(at)-252),len(at),size=len(bt)),j];prob=model.predict_proba(perturbed);r['past_loss'][repeat]+=float((losses(prob)-base).sum())
            monthly.append(dict(case=case,month=mo,n=len(yy),features=len(ix),reproduced_original=True))
        print('EXPLAINED',mo,'3fixed classifiers',flush=True)
    rows=[];baseline=[]
    for case,mask,task,algo in CASES:
        st=state[case];assert st['n']==694
        baseline.append(dict(case=case,mask=mask,task=task,algo=algo,accuracy=st['correct']/694,logloss=st['loss']/694,nonup_recall=st['nonup_correct']/st['nonup_n'] if st['nonup_n'] else None))
        for c,r in st['rows'].items():
            description=labels.get(c,c)
            if '_PC' in c:description='French B 학습내 PCA 요약성분 '+c.rsplit('PC',1)[-1]
            rows.append(dict(case=case,mask=mask,task=task,algo=algo,feature=c,description=description,months_present=r['months'],varying_eval_months=r['varying_months'],within_month_delta_logloss=float(r['within_loss'].mean()/694),within_month_accuracy_drop_pp=float(r['within_correct_drop'].mean()/694*100),within_month_nonup_recall_drop_pp=float(r['within_TN_drop'].mean()/st['nonup_n']*100) if st['nonup_n'] else None,past252_replacement_delta_logloss=float(r['past_loss'].mean()/694),within_month_assessable=r['varying_months']>0))
    df=pd.DataFrame(rows);df.to_csv(O/'ALL_CLASSIFICATION_IMPORTANCE.csv',index=False,encoding='utf-8-sig');s.csv(O/'MODEL_BASELINES.csv',baseline);s.csv(O/'REPLAY_LOG.csv',monthly)
    lines=['# 분류모델의 변수 중요도','','고정 모델3개를34개월694일에서 설명했습니다. 저장된6모델을 복원하고 나머지96개 모델은 기존 설정과 당시 과거입력만으로 재구성한 뒤 원 예측확률과 일치하는지 검사했습니다. 변수선택·파라미터·임곗값을 바꾸지 않았습니다.','', '주분석은 월별 평가X의 한 열을 섞은5회 결과입니다. 확률오차(log loss)의 증가가 클수록 그 모델이 해당 변수를 활용했다는 뜻입니다. 통계적 유의확률·인과효과·변수삭제 재학습효과가 아닙니다.','']
    for case,mask,task,algo in CASES:
        lines +=[f'## {case}: {mask}, {algo}','','|순위|변수|설명|log loss 증가|정확도 감소(%p)|비상승Recall 감소(%p)|','|---:|---|---|---:|---:|---:|']
        part=df[(df['case']==case)&df.within_month_assessable].sort_values('within_month_delta_logloss',ascending=False)
        for rank,r in enumerate(part.head(10).to_dict('records'),1):
            recall='' if pd.isna(r['within_month_nonup_recall_drop_pp']) else f"{r['within_month_nonup_recall_drop_pp']:.3f}"
            lines.append(f"|{rank}|{r['feature']}|{r['description']}|{r['within_month_delta_logloss']:.5f}|{r['within_month_accuracy_drop_pp']:.3f}|{recall}|")
        pc=df[(df['case']==case)&df.feature.str.contains('_PC')].sort_values('past252_replacement_delta_logloss',ascending=False)
        if len(pc):
            lines +=['','### French PC 보조 민감도','','French 월말 요약은 평가월 안에서 일정해 월내섞기로 중요도를 평가할 수 없습니다. 0이라는 이유로 정보가 없다고 해석하면 안 됩니다. 아래는 각 월의 동일 변환으로 계산한 과거252학습행에서 값을 임의 대체했을 때의 별도 민감도입니다. 분포·상관구조를 깨뜨릴 수 있고 실제 삭제효과나 통계검정이 아닙니다.','','|PC|과거값대체 log loss 증가|','|---|---:|']
            for r in pc.head(5).to_dict('records'):lines.append(f"|{r['feature']}|{r['past252_replacement_delta_logloss']:.5f}|")
    lines +=['','## 제한','','이진최고 모델과4등급최고 모델은 평가기간의 사후선정 모델입니다. 4등급은다른조합과정확도동률인설정중하나입니다. 분류기준은동적C기존고정70이아닌현재실험의학습내축소82/C0.1LR입니다.','', '월내섞기는 시계열과 변수간 연관을 깨며 상관변수 간 중요도는 분산될 수 있습니다. 정확도·Recall은 임곗값에 영향을 받고 log loss 순위와 다를 수 있습니다. 음수인 감소량은 섞은 뒤 해당 지표가 오히려 좋아졌다는 뜻입니다. 반복5회는 유의성 검정이 아닙니다.','', 'French의실제공개일/원배포본미확인,현재수정이력 위험과 한국·대만당일시각의원정렬조건을계승합니다. 중요도가 높다고시각가용성이입증된것은아닙니다. SHAP은수행하지않았습니다.']
    (O/'핵심결과.md').write_text('\n'.join(lines),encoding='utf-8');s.js(O/'COMPLETE.json',dict(status='COMPLETE',reconstructed_same_parameter_models=reconstructed,restored_models=restored,reproduced_predictions=102,windows=34,days=694,retuning=False,SHAP=False))
    for case,_,_,_ in CASES:
        print(case,df[(df['case']==case)&df.within_month_assessable].sort_values('within_month_delta_logloss',ascending=False).head(7)[['feature','description','within_month_delta_logloss','within_month_accuracy_drop_pp','within_month_nonup_recall_drop_pp']].to_json(orient='records',force_ascii=False),flush=True)
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
