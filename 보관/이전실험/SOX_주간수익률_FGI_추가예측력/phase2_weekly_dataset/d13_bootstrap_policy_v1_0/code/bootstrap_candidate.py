"""합성 QC용 후보 MBB. 실자료 입력/검정 p/CI 계산 기능 없음."""
import hashlib, json, math
from datetime import date
import numpy as np

SEED=20261016
TARGET=5000
MAX_ATTEMPTS=10000

def threshold(n):
    return max(52, (4*n+4)//5)

def rng_for(grid, length):
    # No algorithm, missingness, or observed loss in seed derivation.
    h=hashlib.sha256('\n'.join(grid).encode('ascii')).digest()
    words=np.frombuffer(h,dtype='<u4').tolist()
    seq=np.random.SeedSequence([SEED,int(length),*words])
    return np.random.Generator(np.random.PCG64(seq)), words

def max_gap(valid):
    boundaries=np.flatnonzero(np.r_[True,valid,True])
    return int(np.max(np.diff(boundaries)-1))

def simulate(grid, loss0, loss1, length, *, forced_start=None):
    """Only synthetic loss arrays; fault injection forced_start is never production randomness."""
    a,b=np.asarray(loss0,dtype=float),np.asarray(loss1,dtype=float)
    n=len(grid); minimum=threshold(n)
    dates=[date.fromisoformat(x) for x in grid]
    if a.shape!=(n,) or b.shape!=(n,) or length not in (4,8,12) or n<length:
        raise ValueError('INVALID_SHAPE_OR_BLOCK')
    if any(x.weekday()!=0 for x in dates) or any((y-x).days!=7 for x,y in zip(dates,dates[1:])):
        raise ValueError('NONCONTIGUOUS_MONDAY_GRID')
    if np.any(a[np.isfinite(a)]<0) or np.any(b[np.isfinite(b)]<0):
        raise ValueError('NEGATIVE_ABSOLUTE_LOSS')
    valid=np.isfinite(a)&np.isfinite(b)
    difference=np.full(n,np.nan)
    with np.errstate(over='ignore',invalid='ignore'):
        difference[valid]=a[valid]-b[valid]
    base={'N_grid':n,'L':length,'min_valid_n':minimum,'original_valid_n':int(valid.sum()),
        'target_valid':TARGET,'max_attempts':MAX_ATTEMPTS,'seed':SEED,'injection':forced_start,
        'confidence_interval':None,'p_value':None,'synthetic_only':True}
    rows=[]; starts_log=[]; means=[]
    def finish(status,reason):
        return {**base,'status':status,'reason':reason,'attempts':len(rows),'accepted':len(means),
            'rejected':sum(not x['accepted'] for x in rows)},rows,starts_log,means
    if valid.sum()<minimum: return finish('ORIGINAL_SAMPLE_INSUFFICIENT','N_VALID_BELOW_MINIMUM')
    with np.errstate(over='ignore',invalid='ignore'):
        variance=float(np.var(difference[valid],ddof=0))
    if not math.isfinite(variance) or variance<=0:
        return finish('INFERENCE_UNAVAILABLE_DEGENERATE','ZERO_OR_NONFINITE_ORIGINAL_VARIANCE')
    rng,words=rng_for(grid,length);base['seed_grid_digest_words']=words
    blocks=math.ceil(n/length)
    for attempt in range(1,MAX_ATTEMPTS+1):
        starts=rng.integers(0,n-length+1,size=blocks) if forced_start is None else np.full(blocks,forced_start,dtype=int)
        if np.any(starts<0) or np.any(starts>n-length): raise ValueError('INVALID_INJECTED_START')
        idx=(starts[:,None]+np.arange(length)).ravel()[:n]
        mask=valid[idx]; nv=int(mask.sum()); accepted=nv>=minimum
        reason='' if accepted else ('EMPTY_PAIRED_RESAMPLE' if nv==0 else 'N_VALID_BELOW_MINIMUM')
        stat=None
        if accepted:
            with np.errstate(over='ignore',invalid='ignore'): stat=float(difference[idx][mask].mean())
            if not math.isfinite(stat):
                accepted=False;reason='NONFINITE_STATISTIC_FATAL'
        rows.append({'attempt':attempt,'L':length,'N_grid':n,'n_valid':nv,'accepted':accepted,
            'reason':reason,'max_missing_run':max_gap(mask),
            'valid_blocks':sum(bool(mask[j:j+length].any()) for j in range(0,n,length))})
        starts_log.append(starts.tolist())
        if reason=='NONFINITE_STATISTIC_FATAL': return finish('INFERENCE_UNAVAILABLE_NUMERICAL',reason)
        if accepted: means.append(stat)
        if len(means)==TARGET: break
    if len(means)<TARGET: return finish('BOOTSTRAP_INFERENCE_UNAVAILABLE','MAX_10000_ATTEMPTS_REACHED')
    if not math.isfinite(float(np.var(means))) or float(np.var(means))<=0:
        return finish('INFERENCE_UNAVAILABLE_DEGENERATE','ZERO_OR_NONFINITE_RESAMPLE_VARIANCE')
    return finish('RESAMPLING_QC_SUCCESS','NO_REAL_INFERENCE_COMPUTED')
