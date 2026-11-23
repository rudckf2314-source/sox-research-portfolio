"""승인 D13 산식 구현. RNG/분위수/Holm은 바이트동일 승계 함수."""
from datetime import date
from scipy.stats import norm
from common import *
from d13_rng_core import rng_for,threshold,max_gap
from d13_approved_details import percentile_type7,holm_family5
def grid_check(grid):
    d=[date.fromisoformat(s) for s in grid]
    if len(set(d))!=len(d) or any(x.weekday()!=0 for x in d) or any((b-a).days!=7 for a,b in zip(d,d[1:])):raise ValueError('IMPLEMENTATION_ERROR_INVALID_CALENDAR_GRID')
def hac(grid,d,lag):
    grid_check(grid);a=np.asarray(d,float)
    if lag not in (2,4,8):raise ValueError('IMPLEMENTATION_ERROR_UNAPPROVED_HAC_LAG')
    if len(a)!=len(grid) or np.isinf(a).any():raise ValueError('IMPLEMENTATION_ERROR_NONFINITE_OR_SHAPE')
    mask=np.isfinite(a);positions=np.flatnonzero(mask);vals=a[mask];n=len(vals)
    base={'lag':lag,'N_grid':len(grid),'n_valid':n,'min_valid_n':threshold(len(grid)),
        'mean_d':float(vals.mean()) if n else None,'SE':None,'z':None,'raw_p':None,'CI_low':None,'CI_high':None}
    if n<threshold(len(grid)):return {**base,'status':'NOT_COMPUTABLE','reason':'INSUFFICIENT_PAIRED_SAMPLE'}
    u=vals-vals.mean();terms=[float(x*x) for x in u]
    for i in range(n):
        for j in range(i+1,n):
            gap=int(positions[j]-positions[i])
            if gap>lag:break
            terms.append(2*(1-gap/(lag+1))*float(u[i]*u[j]))
    omega=math.fsum(terms)/n
    if not math.isfinite(omega) or omega<0:raise ValueError('IMPLEMENTATION_ERROR_INVALID_HAC_VARIANCE')
    if omega==0:return {**base,'status':'NOT_COMPUTABLE','reason':'ZERO_VARIANCE','Omega':0.}
    se=math.sqrt(omega/n);mean=float(vals.mean());z=mean/se
    return {**base,'status':'COMPUTABLE','reason':'','Omega':omega,'SE':se,'z':z,'raw_p':float(norm.sf(z)),
        'CI_low':mean-1.95996398454*se,'CI_high':mean+1.95996398454*se}
def mbb(grid,loss0,loss1,L):
    grid_check(grid);a=np.asarray(loss0,float);b=np.asarray(loss1,float);N=len(grid);m=threshold(N)
    if a.shape!=(N,) or b.shape!=(N,) or np.isinf(a).any() or np.isinf(b).any() or L not in (4,8,12) or N<L:raise ValueError('IMPLEMENTATION_ERROR_MBB_INPUT')
    if (a[np.isfinite(a)]<0).any() or (b[np.isfinite(b)]<0).any():raise ValueError('IMPLEMENTATION_ERROR_NEGATIVE_LOSS')
    mask=np.isfinite(a)&np.isfinite(b);d=a-b;n=int(mask.sum());rng,words=rng_for(grid,L)
    result={'L':L,'N_grid':N,'original_valid_n':n,'min_valid_n':m,'target':5000,'max_attempts':10000,
        'attempts':0,'accepted':0,'rejected':0,'seed':20261016,'grid_sha256':hashlib.sha256('\n'.join(grid).encode('ascii')).hexdigest(),
        'seed_words':words,'CI_low':None,'CI_high':None}
    means=[];records=[];starts_list=[]
    if n<m:return {**result,'status':'BOOTSTRAP_INFERENCE_UNAVAILABLE','reason':'INSUFFICIENT_PAIRED_SAMPLE'},means,records,starts_list
    var=float(np.var(d[mask]))
    if not math.isfinite(var):raise ValueError('IMPLEMENTATION_ERROR_NONFINITE_MBB_VARIANCE')
    if var==0:return {**result,'status':'BOOTSTRAP_INFERENCE_UNAVAILABLE','reason':'ZERO_VARIANCE'},means,records,starts_list
    for attempt in range(1,10001):
        starts=rng.integers(0,N-L+1,size=math.ceil(N/L));idx=(starts[:,None]+np.arange(L)).ravel()[:N]
        valid=mask[idx];nv=int(valid.sum());accept=nv>=m
        record={'attempt':attempt,'L':L,'N_grid':N,'n_valid':nv,'accepted':accept,
            'reason':'' if accept else ('EMPTY_PAIRED_RESAMPLE' if nv==0 else 'N_VALID_BELOW_MINIMUM'),
            'max_missing_run':max_gap(valid),'valid_blocks':sum(bool(valid[j:j+L].any()) for j in range(0,N,L))}
        records.append(record);starts_list.append(starts.tolist())
        if accept:
            value=float(d[idx][valid].mean())
            if not math.isfinite(value):raise ValueError('IMPLEMENTATION_ERROR_MBB_STATISTIC')
            means.append(value)
        if len(means)==5000:break
    result.update({'attempts':len(records),'accepted':len(means),'rejected':sum(not r['accepted'] for r in records)})
    if len(means)<5000:return {**result,'status':'BOOTSTRAP_INFERENCE_UNAVAILABLE','reason':'MAX_10000_ATTEMPTS_REACHED'},means,records,starts_list
    v=float(np.var(means))
    if not math.isfinite(v):raise ValueError('IMPLEMENTATION_ERROR_MBB_RESULT_VARIANCE')
    if v==0:return {**result,'status':'BOOTSTRAP_INFERENCE_UNAVAILABLE','reason':'ZERO_VARIANCE'},means,records,starts_list
    lo,hi=percentile_type7(means)
    return {**result,'status':'COMPLETED','reason':'','CI_low':lo,'CI_high':hi},means,records,starts_list
