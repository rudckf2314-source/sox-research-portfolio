"""Reconcile existing group contrasts and an exposure-matched diagnostic benchmark. No fits."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

W=Path(__file__).resolve().parents[1];D=Path('C:/Users/rudck/Desktop/SOX_논문_연구');O=W/'outputs/manuscript_v4_feature_comparison_20261026'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def js(p,o):p.write_text(json.dumps(o,ensure_ascii=False,indent=2),encoding='utf-8')

def groups():
    c=D/'05_전체실험결과/01_분류_이진_4등급'
    contrasts=pd.read_csv(D/'04_핵심근거/06_동일알고리즘_변수추가효과90.csv')
    metrics=pd.read_csv(c/'late_METRICS(2024~2026년 전체 성능).csv')
    assert contrasts.task.value_counts().to_dict()=={'BINARY':30,'FOUR':30,'REGRESSION':30}
    b=metrics[metrics.task=='BINARY'].set_index(['mask','algo'])
    rows=[]
    for _,r in contrasts[contrasts.task=='BINARY'].iterrows():
        a=b.loc[(r.base,r.algo)];z=b.loc[(r.candidate,r.algo)]
        delta=100*(z.accuracy-a.accuracy);assert np.isclose(delta,r.effect,atol=1e-9)
        rows.append(dict(comparison=r.comparison,algo=r.algo,base=r.base,candidate=r.candidate,
            base_accuracy=100*a.accuracy,candidate_accuracy=100*z.accuracy,delta_accuracy_pp=delta,
            delta_macro_F1_pp=100*(z.macro_F1-a.macro_F1),delta_nonup_recall_pp=100*(z.nonup_recall-a.nonup_recall),
            lo95=r.lo95,hi95=r.hi95,p_Holm90=r.p_Holm90))
    out=pd.DataFrame(rows);out.to_csv(O/'ALL_BINARY_GROUP_CONTRASTS.csv',index=False,encoding='utf-8-sig')
    out[out.algo=='LR'].to_csv(O/'PRIMARY_LR_GROUP_CONTRASTS.csv',index=False,encoding='utf-8-sig')
    pos=out[(out.p_Holm90<.05)&(out.delta_accuracy_pp>0)]
    neg=out[(out.p_Holm90<.05)&(out.delta_accuracy_pp<0)]
    assert len(pos)==0 and len(neg)==1
    return dict(primary_LR=out[out.algo=='LR'].to_dict(orient='records'),positive_significant=len(pos),negative_significant=neg.to_dict(orient='records'),family='90 comparisons: binary30, four30, regression30',correction='existing exploratory Holm90, no redefinition of family')

def simulate(q,mode,w=None):
    fee=.0005;cash=10000.;shares=0.;paid=0.;buys=sells=0;close_path=[10000.];exposure=[];daily=[]
    for day,r in q.iterrows():
        action='HOLD'
        if mode=='prediction':
            if shares>0 and r.signal==0:
                amount=shares*r.open;cash+=amount*(1-fee);paid+=amount*fee;shares=0.;sells+=1;action='SELL'
            elif shares==0 and r.signal==1:
                amount=cash/(1+fee);shares=amount/r.open;paid+=amount*fee;cash=0.;buys+=1;action='BUY'
        elif mode=='buyhold':
            if day==q.index[0]:
                amount=cash/(1+fee);shares=amount/r.open;paid+=amount*fee;cash=0.;buys+=1;action='BUY'
        else:
            # Rebalance at the open to target post-fee weight, solving transaction costs exactly.
            stock=shares*r.open;equity=cash+stock;numerator=w*equity-stock
            amount=numerator/(1+w*fee) if numerator>=0 else numerator/(1-w*fee)
            cash-=amount+abs(amount)*fee;shares+=amount/r.open;paid+=abs(amount)*fee
            if amount>1e-9:buys+=1
            elif amount<-1e-9:sells+=1
            assert cash>=-1e-8 and shares>=-1e-8
            assert np.isclose(shares*r.open/(cash+shares*r.open),w,atol=1e-10)
        equity=cash+shares*r.close;share_weight=shares*r.close/equity;exposure.append(share_weight)
        close_path.append(equity);daily.append(dict(date=day,equity=equity,close_weight=share_weight,action=action))
    if shares>0:
        amount=shares*q.close.iloc[-1];cash+=amount*(1-fee);paid+=amount*fee;shares=0.;sells+=1
        close_path[-1]=cash;daily[-1]['equity']=cash;daily[-1]['terminal_liquidation']=True
    v=np.array(close_path);ret=v[1:]/v[:-1]-1;dd=v/np.maximum.accumulate(v)-1
    vol=float(np.std(ret,ddof=1)*np.sqrt(252));sharpe=float(np.mean(ret)/np.std(ret,ddof=1)*np.sqrt(252))
    elapsed=(pd.Timestamp(q.index[-1])-pd.Timestamp(q.index[0])).days/365.25
    metric=dict(strategy=mode,ending=float(v[-1]),total_return_pct=float((v[-1]/10000-1)*100),annualized_vol_pct=vol*100,
        Sharpe_rf0=sharpe,MDD_pct=float(dd.min()*100),mean_close_exposure_pct=float(np.mean(exposure)*100),
        annualized_compound_return_pct=float(((v[-1]/10000)**(1/elapsed)-1)*100),buys=buys,sells=sells,commissions=paid)
    f=pd.DataFrame(daily);f['drawdown_pct']=dd[1:]*100;f['daily_net_return']=ret
    return metric,f

def risk():
    src=W/'outputs/soxq_informal_simulation_20261026';meta=json.loads((src/'SUMMARY.json').read_text(encoding='utf-8'))
    assert sha(src/'SOXQ_YAHOO_RAW.json')==meta['raw_sha256']
    q=pd.read_csv(src/'SOXQ_daily_with_existing_signal.csv').set_index('date').sort_index();assert len(q)==706 and q.index.is_unique
    pred,predpath=simulate(q,'prediction');hold,holdpath=simulate(q,'buyhold')
    assert np.isclose(pred['ending'],21296.67535709392) and np.isclose(hold['ending'],26136.71402520361)
    target=pred['mean_close_exposure_pct']/100;lo=0.;hi=1.
    # Entire-period calibration is explicitly a retrospective diagnostic, never a prospective rule.
    for _ in range(35):
        w=(lo+hi)/2;metric,_=simulate(q,'fixed_weight',w)
        if metric['mean_close_exposure_pct']/100<target:lo=w
        else:hi=w
    w=(lo+hi)/2;matched,matchedpath=simulate(q,'fixed_weight',w)
    assert abs(matched['mean_close_exposure_pct']-pred['mean_close_exposure_pct'])<1e-7
    for metric,path in [(pred,predpath),(hold,holdpath),(matched,matchedpath)]:
        path.to_csv(O/(metric['strategy']+'_DAILY_EQUITY.csv'),index=False,encoding='utf-8-sig')
    pd.DataFrame([hold,matched,pred]).to_csv(O/'RISK_COMPARISON.csv',index=False,encoding='utf-8-sig')
    return dict(period=[q.index[0],q.index[-1]],n=706,capital=10000,additional_contributions=0,fee_per_side=.0005,
        cash_return_and_sharpe_reference_rate=0.,annualization_sessions=252,matched_target_open_weight=w,
        exposure_definition='mean of stock market value / total equity at each daily close, before terminal liquidation',
        matching='bisection matches fixed-weight benchmark mean close exposure to observed strategy; full-period retrospective calibration',
        rebalancing='fixed-weight benchmark rebalanced at each open; fees charged only on actual turnover; terminal close liquidation',
        assumptions=['fractional shares','constant FX','dividends excluded','tax and slippage excluded'],
        selection='observed best classifier and trading rule selected retrospectively; no risk-superiority inference',results=[hold,matched,pred])

def timing():
    root=W/'outputs';p=root/'evaluation_extension_20261023_v1/prepared/예측일별_RAW_공개시점_대조.csv'
    d=pd.read_csv(p);a=d[(d.date=='2026-10-23')&d.source_id.isin([1,2,23])]
    stock=pd.read_csv(root/'evaluation_extension_20261023_stockcharts_v2_20261024/StockCharts_예측시점_정렬근거.csv')
    stock=stock[(stock.date=='2026-10-23')&(stock.source_id==5)]
    fgi=pd.read_csv(root/'evaluation_extension_20261023_fgi_v3_20261024/FGI_예측시점_정렬근거.csv')
    fgi=fgi[fgi.date=='2026-10-23']
    return dict(price_examples=a.to_dict(orient='records'),breadth_example=stock.to_dict(orient='records'),FGI_example=fgi.to_dict(orient='records'),caveat='rule-based availability bounds, not authenticated contemporaneous delivery receipts')

def main():
    O.mkdir(parents=True,exist_ok=True)
    results=dict(group_comparison=groups(),risk=risk(),timing=timing(),new_model_fits=0,new_forecasts=0)
    js(O/'EVIDENCE.json',results)
    print(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
