import os,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
O=Path(__file__).resolve().parent;P=O.parent;A=P.parent;D=A.parent;ROOT=D.parent;V=D/'development_revision_v1';K=P/'execution_kr_v1';E=P/'kr_reaudit_tw23_v1';SEED=20261019
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def js(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def csv(n,x):pd.DataFrame(x).to_csv(O/n,index=False,encoding='utf-8-sig')
def canonical(x):return json.dumps(x,sort_keys=True,default=str)
def framehash(x):return hashlib.sha256(pd.util.hash_pandas_object(x,index=True).values.tobytes()).hexdigest()
def snapshot():
    out=[]
    for b,ds,fs in os.walk(ROOT,followlinks=False):
        ds[:]=[n for n in ds if n not in {'.git','.venv','.venv_W1'} and not (Path(b)/n).resolve().is_relative_to(O)]
        for n in fs:
            p=Path(b)/n;assert not p.is_symlink(),str(p);out.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return out
def normalize_raw(raw):
    dups=raw[raw.duplicated('Date',keep=False)]
    for date,g in dups.groupby('Date'):
        if len(g.drop_duplicates())!=1:raise ValueError('Conflicting same-source-date rows: '+str(date))
    return raw.drop_duplicates('Date').sort_values('Date',kind='stable').reset_index(drop=True)
def native_features(raw,features):
    z=normalize_raw(raw);s=z['Close' if 'Close' in z else 'Semiconductor_Industry_Index'].astype(float)
    vals={f'ret{k}':100*(s/s.shift(k)-1) for k in [1,5,20]};vals.update(vol20=100*(s/s.shift(1)-1).rolling(20,min_periods=20).std(ddof=1),ma20_gap=100*(s/s.rolling(20,min_periods=20).mean()-1),level=s,delta1=s.diff(),delta5=s.diff(5))
    f=pd.DataFrame({'source_date':pd.to_datetime(z.Date)})
    for col in features:f[col]=vals[col.split('_',1)[1]].to_numpy()
    return f
def select_latest(events):
    # Explicit second key determines the last row, independent of input order.
    return events.sort_values(['available_date','source_date'],kind='stable').drop_duplicates('available_date',keep='last').sort_values('available_date').reset_index(drop=True)
def reconstruct(raw,features,sessions,origins):
    f=native_features(raw,features);idx=sessions.searchsorted(f.source_date,side='right');valid=idx<len(sessions);events=f.loc[valid].copy();events['available_date']=sessions[idx[valid]].to_numpy();selected=select_latest(events)
    merged=pd.merge_asof(pd.DataFrame({'date':origins}),selected,left_on='date',right_on='available_date',direction='backward');ok=(merged.date-merged.source_date).dt.days.le(10)
    for c in features:merged[c]=merged[c].where(ok)
    return merged,events
