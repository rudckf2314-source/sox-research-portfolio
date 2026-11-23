"""Synthesize existing sealed forecasts into manuscript evidence; no new model fits."""
from pathlib import Path
import sys,json,hashlib,zipfile
import numpy as np,pandas as pd
from sklearn.metrics import accuracy_score,balanced_accuracy_score,f1_score,r2_score
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

W=Path(__file__).resolve().parents[1];C=W/'outputs/crossed_feature_algorithm_v1_20261023';R=W/'outputs/sox_return_regression16_v1_20261024';O=W/'outputs/paper_refresh_20261023_20261024/evidence'
SEED=20261024;B=5000
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def csv(p,rows):pd.DataFrame(rows).to_csv(p,index=False,encoding='utf-8-sig')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def holm(values):
    vals=np.array(values);order=np.argsort(vals);out=np.empty(len(vals));out[order]=np.minimum(1,np.maximum.accumulate((len(vals)-np.arange(len(vals)))*vals[order]));return out
def interval(samples):return float(np.quantile(samples,.025)),float(np.quantile(samples,.975))
def main():
    O.mkdir(parents=True,exist_ok=True)
    protected=[C/'LATE_DAILY_RESULTS.csv',C/'late_METRICS.csv',C/'DECISION_PRE2024.json',C/'FINAL_VERIFICATION.json',R/'DAILY_RESULTS.csv',R/'ALL96_AND_BASELINES_METRICS.csv',R/'VERIFICATION.json',W/'outputs/importance_price_xgb_20261024/FEATURE_IMPORTANCE_ALL55.csv',W/'outputs/importance_classification_20261024/ALL_CLASSIFICATION_IMPORTANCE.csv']
    before={str(p):sha(p) for p in protected};dump(O/'SOURCE_HASHES.json',before)
    cd=pd.read_csv(W/'outputs/frozen_extension_all_tasks_20261023_v1_20261024/FULL706_CLASSIFICATION_DAILY.csv');rd=pd.read_csv(W/'outputs/frozen_extension_all_tasks_20261023_v1_20261024/FULL706_REGRESSION_DAILY.csv');truth=pd.read_csv(W/'outputs/staged_multi_algorithm_v2_20261023/LABELS_FOR_TRAINING_ONLY.csv',index_col='date');dates=sorted(cd.date.unique());assert len(dates)==706
    ca={(m,t,a):g.set_index('date').loc[dates] for (m,t,a),g in cd.groupby(['mask','task','algo'])};ra={(m,a):g.set_index('date').loc[dates] for (m,a),g in rd.groupby(['mask','algo'])}
    y=ca['G110000_NONE','BINARY','LR'].Y.to_numpy(int);q=ca['G110000_NONE','FOUR','LR'].Y.to_numpy(int);yr=ra['G000000_NONE','XGB'].Y.to_numpy();assert np.array_equal(y,(yr>0).astype(int))
    binary={'항상상승':np.ones(706,dtype=int),'분류비교기준':ca['G110000_NONE','BINARY','LR'].prediction.to_numpy(int),'분류사前선정'.replace('前','전'):ca['G001000_MONTH2_FIRST','BINARY','LR'].prediction.to_numpy(int),'분류관측최고':ca['G001100_MONTH2_FIRST','BINARY','LGBM'].prediction.to_numpy(int),'회귀관측최고의방향':(ra['G000000_NONE','XGB'].prediction.to_numpy()>0).astype(int)}
    modes=[]
    for d in dates:
        cutoff=d[:7]+'-01';past=truth.loc[truth.index<cutoff,'class4'];modes.append(int(past.value_counts().sort_index().idxmax()))
    majority_class=int(np.bincount(q,minlength=4).argmax())
    four={'과거학습최빈등급':np.array(modes),'평가기간최다등급상수_사후진단':np.full(706,majority_class),'4등급비교기준':ca['G110000_NONE','FOUR','LR'].prediction.to_numpy(int),'4등급사전선정':ca['G010110_NEXT20','FOUR','HGB'].prediction.to_numpy(int),'4등급관측최고':ca['G001100_MONTH2_FIRST','FOUR','LR'].prediction.to_numpy(int)}
    returns={'항상0%':ra['BASELINE','ZERO'].prediction.to_numpy(),'과거학습평균':ra['BASELINE','TRAIN_MEAN'].prediction.to_numpy(),'과거학습중앙값':ra['BASELINE','TRAIN_MEDIAN'].prediction.to_numpy(),'회귀관측최고':ra['G000000_NONE','XGB'].prediction.to_numpy()}
    rows=[];yearly=[]
    def classification(target,p):
        result=dict(n=len(target),correct=int(np.sum(p==target)),accuracy=accuracy_score(target,p),balanced_accuracy=balanced_accuracy_score(target,p),macro_F1=f1_score(target,p,average='macro',zero_division=0))
        if len(np.unique(target))==2:
            tn=int(((target==0)&(p==0)).sum());fp=int(((target==0)&(p==1)).sum());fn=int(((target==1)&(p==0)).sum());tp=int(((target==1)&(p==1)).sum());result.update(TN=tn,FP=fp,FN=fn,TP=tp,nonup_recall=tn/(tn+fp),up_prediction=float(p.mean()))
        return result
    for task,collection,target in [('BINARY',binary,y),('FOUR',four,q),('REGRESSION',returns,yr)]:
        for name,p in collection.items():
            def measure(t,v):
                if task!='REGRESSION':return classification(t,v)
                e=t-v;return dict(n=len(t),MAE=float(np.abs(e).mean()),RMSE=float(np.sqrt((e**2).mean())),R2=r2_score(t,v),direction_accuracy=float(((t>0)==(v>0)).mean()))
            rows.append(dict(task=task,model=name,**measure(target,p)))
            for year in ['2024','2025','2026']:
                take=np.array([d.startswith(year) for d in dates]);yearly.append(dict(task=task,model=name,year=year,**measure(target[take],p[take])))
    csv(O/'01_핵심성능_기준비교.csv',rows);csv(O/'02_연도별성능.csv',yearly)
    distribution=[dict(task=task,class_id=int(c),n=int((target==c).sum()),share=float((target==c).mean())) for task,target in [('BINARY',y),('FOUR',q)] for c in np.unique(target)]
    csv(O/'03_실제등급분포.csv',distribution)
    # Fixed block lengths chosen here for sensitivity, never choosing a winner by interval.
    bootstrap={}
    for length in [5,20,60]:
        rng=np.random.default_rng(SEED+length);starts=rng.integers(0,len(y),size=(B,int(np.ceil(len(y)/length))));bootstrap[length]=((starts[:,:,None]+np.arange(length))%len(y)).reshape(B,-1)[:,:len(y)]
    comparisons=[]
    cmp=[('BINARY','사전선정vs비교기준','분류사전선정','분류비교기준'),('BINARY','관측최고vs비교기준','분류관측최고','분류비교기준'),('BINARY','관측최고vs항상상승','분류관측최고','항상상승'),('FOUR','사전선정vs비교기준','4등급사전선정','4등급비교기준'),('FOUR','관측최고vs비교기준','4등급관측최고','4등급비교기준'),('FOUR','관측최고vs评价最頻'.replace('评价最頻','评价最頻'),'4등급관측최고','평가기간최다등급상수_사후진단')]
    for task,name,candidate,base in cmp:
        target=y if task=='BINARY' else q;collection=binary if task=='BINARY' else four;delta=(collection[candidate]==target).astype(int)-(collection[base]==target).astype(int)
        for length,ix in bootstrap.items():
            samples=delta[ix].mean(1)*100;lo,hi=interval(samples);comparisons.append(dict(task=task,comparison=name.replace('评价最頻','평가최다등급'),candidate=candidate,baseline=base,metric='accuracy_difference_pp',difference=float(delta.mean()*100),lo95=lo,hi95=hi,block=length,replicates=B,exploratory='사전선정' not in name,selection_bias_removed=False))
    for name,p in returns.items():
        if name=='회귀관측최고':continue
        pbest=returns['회귀관측최고'];besterr=yr-pbest;baseerr=yr-p
        for length,ix in bootstrap.items():
            for metric,samples,point in [('MAE_improvement',np.abs(baseerr)[ix].mean(1)-np.abs(besterr)[ix].mean(1),np.abs(baseerr).mean()-np.abs(besterr).mean()),('RMSE_improvement',np.sqrt((baseerr**2)[ix].mean(1))-np.sqrt((besterr**2)[ix].mean(1)),np.sqrt((baseerr**2).mean())-np.sqrt((besterr**2).mean()))]:
                lo,hi=interval(samples);comparisons.append(dict(task='REGRESSION',comparison='관측최고vs'+name,candidate='회귀관측최고',baseline=name,metric=metric,difference=float(point),lo95=lo,hi95=hi,block=length,replicates=B,exploratory=True,selection_bias_removed=False))
    csv(O/'04_성능차이_블록신뢰구간.csv',comparisons)
    absolute=[]
    for length,ix in bootstrap.items():
        for name in ['분류관측최고','분류비교기준']:
            score=(binary[name]==y).astype(float);lo,hi=interval(score[ix].mean(1)*100);absolute.append(dict(model=name,metric='accuracy_pct',value=float(score.mean()*100),lo95=lo,hi95=hi,block=length,exploratory=True))
        e=yr-returns['회귀관측최고'];samples=1-(e**2)[ix].sum(1)/((yr[ix]-yr[ix].mean(1,keepdims=True))**2).sum(1);lo,hi=interval(samples);absolute.append(dict(model='회귀관측최고',metric='standard_R2',value=r2_score(yr,returns['회귀관측최고']),lo95=lo,hi95=hi,block=length,exploratory=True))
    csv(O/'05_절대성능_참고신뢰구간.csv',absolute)
    print('BASELINES AND INTERVALS COMPLETE',flush=True)
    # Add/remove comparisons: same model family, target, dates and original preprocessing rules.
    pairs=[('가격→FGI추가','G000000_NONE','G000100_NONE'),('가격→FrenchB추가','G000000_NONE','G000000_MONTH2_FIRST'),('가격FGI→기술추가','G000100_NONE','G001100_NONE'),('가격기술FGI→FrenchB추가','G001100_NONE','G001100_MONTH2_FIRST'),('가격시장폭옵션→기술추가','G110000_NONE','G111000_NONE')]
    ix=bootstrap[20];ablation=[]
    for label,base,candidate in pairs:
        for algo in ['LR','RF','ET','HGB','XGB','LGBM']:
            for task,target in [('BINARY',y),('FOUR',q)]:
                a=ca[candidate,task,algo];b=ca[base,task,algo];diff=(a.prediction.to_numpy()==target).astype(float)-(b.prediction.to_numpy()==target).astype(float);samples=diff[ix].mean(1);point=float(diff.mean());lo,hi=interval(samples);pval=float((1+np.sum(np.abs(samples-point)>=abs(point)))/(B+1))
                ablation.append(dict(task=task,comparison=label,algo=algo,base=base,candidate=candidate,metric='accuracy_gain_pp',effect=point*100,lo95=lo*100,hi95=hi*100,p_centered_block_bootstrap_approx=pval,interpretation='positive favors added group; exploratory'))
        for algo in ['RIDGE','RF','ET','HGB','XGB','LGBM']:
            a=ra[candidate,algo].prediction.to_numpy();b=ra[base,algo].prediction.to_numpy();diff=(yr-b)**2-(yr-a)**2;samples=diff[ix].mean(1);point=float(diff.mean());lo,hi=interval(samples);pval=float((1+np.sum(np.abs(samples-point)>=abs(point)))/(B+1))
            ablation.append(dict(task='REGRESSION',comparison=label,algo=algo,base=base,candidate=candidate,metric='MSE_reduction',effect=point,lo95=lo,hi95=hi,p_centered_block_bootstrap_approx=pval,interpretation='positive favors added group; exploratory'))
    assert len(ablation)==90
    adjusted=holm([r['p_centered_block_bootstrap_approx'] for r in ablation])
    for r,p in zip(ablation,adjusted):r.update(p_Holm90=float(p),exploratory=True,full_research_selection_bias_removed=False)
    csv(O/'06_동일알고리즘_변수추가효과90.csv',ablation)
    # Descriptive month-to-month stability, no extra regime search or new model choice.
    monthrows=[]
    for month in sorted({d[:7] for d in dates}):
        take=np.array([d.startswith(month) for d in dates])
        for name,p in binary.items():
            cm=classification(y[take],p[take]);monthrows.append(dict(month=month,model=name,**cm))
    csv(O/'07_월별방향성능.csv',monthrows)
    # Figures are scientific summaries, not trading returns.
    plt.rcParams['font.family']='Malgun Gothic';plt.rcParams['axes.unicode_minus']=False
    yy=pd.DataFrame(yearly);fig,axes=plt.subplots(1,3,figsize=(16,4.5))
    for name in ['항상상승','분류비교기준','분류관측최고','회귀관측최고의방향']:
        g=yy[(yy.task=='BINARY')&(yy.model==name)];axes[0].plot(g.year,g.accuracy*100,marker='o',label=name)
    axes[0].set_title('연도별 방향 정확도');axes[0].set_ylabel('%');axes[0].legend(fontsize=8)
    for name in ['분류비교기준','분류관측최고','회귀관측최고의방향']:
        g=yy[(yy.task=='BINARY')&(yy.model==name)];axes[1].plot(g.year,g.nonup_recall*100,marker='o',label=name)
    axes[1].set_title('연도별 비상승 Recall');axes[1].set_ylabel('%');axes[1].legend(fontsize=8)
    for name in ['과거학습평균','회귀관측최고']:
        g=yy[(yy.task=='REGRESSION')&(yy.model==name)];axes[2].plot(g.year,g.RMSE,marker='o',label=name)
    axes[2].set_title('연도별 수익률 예측오차');axes[2].set_ylabel('RMSE (%p)');axes[2].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.25)
    fig.tight_layout();fig.savefig(O/'08_연도별안정성.png',dpi=180);plt.close(fig)
    for source,name in [(W/'outputs/importance_classification_20261024/ALL_CLASSIFICATION_IMPORTANCE.csv','09_분류_변수중요도.csv'),(W/'outputs/importance_price_xgb_20261024/FEATURE_IMPORTANCE_ALL55.csv','10_회귀_변수중요도.csv')]:
        df=pd.read_csv(source);df['explanation_period']='2024-01-02..2026-10-07';df['explanation_days']=694;df['scope_note']='기존 694일 분석; 10월23일까지 재산출한 중요도가 아님';df.to_csv(O/name,index=False,encoding='utf-8-sig')
    dump(O/'COMPLETE.json',dict(status='COMPLETE',evaluation_days=706,evaluation_end='2026-10-23',new_model_fits=0,importance_days=694,bootstrap_replicates=B,blocks=[5,20,60],independent_unseen_test=False))
    print('UPDATED EVIDENCE COMPLETE',len(cd),len(rd),flush=True)
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
