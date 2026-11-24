"""SOXQ simulation extracted from analyze_v4_evidence_20261026.py."""
import numpy as np
import pandas as pd

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
