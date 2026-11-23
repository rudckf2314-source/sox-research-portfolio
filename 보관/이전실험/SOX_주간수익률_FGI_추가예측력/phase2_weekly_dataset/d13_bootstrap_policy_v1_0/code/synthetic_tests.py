"""실제 X/Y를 읽지 않는 D13 합성 재표본화 시험."""
import gzip, hashlib, json
from datetime import date, timedelta
import numpy as np
from prepare import OUT, save
from bootstrap_candidate import simulate, threshold

def main():
    cases=[]
    def add(name,n=301,L=8,missing=(),forced=None,kind='normal',expect=None):
        grid=[str(date(2000,1,3)+timedelta(weeks=i)) for i in range(n)]
        t=np.arange(n,dtype=float)
        a=2+np.sin(t/9)+t/1000; b=1.5+0.3*np.cos(t/7)
        a[list(missing)]=np.nan
        if kind=='zero_variance': a[:]=2;b[:]=1
        if kind=='nonfinite': a[4]=np.inf;b[20]=-np.inf;a[17]=np.nan
        if kind=='overflow_variance': a[::2]=1e308;b[::2]=0
        if kind=='asymmetric': a[10:20]=np.nan;b[30:40]=np.nan
        cases.append((name,grid,a,b,L,forced,expect))
    for L in (4,8,12): add(f'complete301_L{L}',L=L,expect='RESAMPLING_QC_SUCCESS')
    missing=np.random.Generator(np.random.PCG64(9102026)).choice(301,30,replace=False)
    add('random_missing30',missing=missing,expect='RESAMPLING_QC_SUCCESS')
    add('consecutive_missing40',missing=range(100,140),expect='RESAMPLING_QC_SUCCESS')
    add('threshold_below240',missing=range(61),expect='ORIGINAL_SAMPLE_INSUFFICIENT')
    add('threshold_equal241',missing=range(60))
    add('threshold_above242',missing=range(59))
    for n in (50,51,52):
        add(f'minimum_grid{n}',n=n,expect='ORIGINAL_SAMPLE_INSUFFICIENT' if n<52 else 'RESAMPLING_QC_SUCCESS')
    add('65grid_valid51',n=65,missing=range(14),expect='ORIGINAL_SAMPLE_INSUFFICIENT')
    add('65grid_valid52',n=65,missing=range(13))
    add('all_missing',missing=range(301),expect='ORIGINAL_SAMPLE_INSUFFICIENT')
    add('forced_missing_blocks_10000',missing=range(120,130),forced=120,expect='BOOTSTRAP_INFERENCE_UNAVAILABLE')
    add('repeat_seed_complete301',expect='RESAMPLING_QC_SUCCESS')
    add('asymmetric_pair_missing',kind='asymmetric',expect='RESAMPLING_QC_SUCCESS')
    add('auxiliary104_sparse',n=104,missing=range(0,100,10),expect='RESAMPLING_QC_SUCCESS')
    add('auxiliary104_insufficient',n=104,missing=range(25),expect='ORIGINAL_SAMPLE_INSUFFICIENT')
    add('zero_variance',kind='zero_variance',expect='INFERENCE_UNAVAILABLE_DEGENERATE')
    add('nonfinite_values',kind='nonfinite',expect='RESAMPLING_QC_SUCCESS')
    add('nonfinite_variance',kind='overflow_variance',expect='INFERENCE_UNAVAILABLE_DEGENERATE')
    results=[]
    (OUT/'qc/synthetic').mkdir(exist_ok=True)
    for name,grid,a,b,L,forced,expect in cases:
        prefix=OUT/'qc/synthetic'/name
        with prefix.with_suffix('.npz').open('xb') as f:
            np.savez_compressed(f,grid=np.array(grid),loss0=a,loss1=b)
        summary,records,starts,means=simulate(grid,a,b,L,forced_start=forced)
        with prefix.with_suffix('.jsonl.gz').open('xb') as raw:
            with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as f:
                for record,st in zip(records,starts):
                    f.write((json.dumps({**record,'block_starts':st},separators=(',',':'))+'\n').encode())
        with (prefix.parent/(name+'_means.npz')).open('xb') as f:
            np.savez_compressed(f,synthetic_resample_means=np.array(means))
        checks={'expected_status':expect is None or summary['status']==expect,
            'attempt_limit':summary['attempts']<=10000,
            'accepted_limit':summary['accepted']<=5000,
            'success_requires5000':summary['status']!='RESAMPLING_QC_SUCCESS' or summary['accepted']==5000,
            'all_acceptance_thresholds':all(r['accepted']==(r['n_valid']>=summary['min_valid_n']) for r in records),
            'no_inference':summary['confidence_interval'] is None and summary['p_value'] is None}
        summary.update({'case':name,'expected':expect or '경계값 부근: 성공 또는 최대 시도 도달 모두 규칙대로 기록',
            'checks':checks,'test_status':'PASS' if all(checks.values()) else 'FAIL',
            'starts_sha256':hashlib.sha256(json.dumps(starts,separators=(',',':')).encode()).hexdigest()})
        # Report in Korean; no empirical study values exist in these fixtures.
        if expect is None: summary['expected']='경계값 부근: 성공 또는 최대 시도 도달 모두 규칙대로 기록'
        results.append(summary)
        print(name,summary['status'],summary['attempts'],summary['accepted'],flush=True)
    by={r['case']:r for r in results}
    guards={'threshold301_241':threshold(301)==241,'threshold209_168':threshold(209)==168,
        'threshold50_52':threshold(50)==52,
        'same_seed_reproduces':by['complete301_L8']['starts_sha256']==by['repeat_seed_complete301']['starts_sha256'],
        'forced_failure_exact10000':by['forced_missing_blocks_10000']['attempts']==10000}
    for label,dates in [('compressed_grid',['2000-01-03','2000-01-17']+[str(date(2000,1,24)+timedelta(weeks=i)) for i in range(50)]),
        ('duplicate_grid',['2000-01-03']*52)]:
        try: simulate(dates,np.arange(52)+1,np.ones(52),8);guards[label+'_rejected']=False
        except ValueError: guards[label+'_rejected']=True
    save('qc/D13_SYNTHETIC_TEST_RESULTS.json',{'scope':'합성 손실과 결측표지만 사용. 실증 검정/CI/p-value 없음.',
        'status':'PASS' if all(r['test_status']=='PASS' for r in results) and all(guards.values()) else 'FAIL',
        'case_count':len(results),'cases':results,'guards':guards,
        'synthetic_data_seed':9102026,'bootstrap_root_seed':20261016,
        'no_claim_of_size_power_or_coverage_validation':True})

if __name__=='__main__': main()
