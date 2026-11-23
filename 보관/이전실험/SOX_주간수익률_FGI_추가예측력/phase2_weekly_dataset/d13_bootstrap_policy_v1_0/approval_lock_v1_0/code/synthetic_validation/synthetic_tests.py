"""A01/A02의 합성 전용 테스트. 기존 MBB는 바이트 동일 사본으로 smoke만 검사."""
import copy,json
from datetime import date,timedelta
from common import write,OUT
from approved_inference_details import FAMILY,percentile_type7,holm_family5
from bootstrap_locked import simulate

def main():
    quantiles=[]
    for name,x in [('two_points',[-10.,30.]),('exact_rank41',list(range(41))),
        ('exact_rank401',list(range(401))),('duplicates',[-2,-2,-2,0,0,3,3,3]),
        ('negative_positive',[-40,-3,0,1,20]),('single',[7.]),('unsorted',[8,-2,3,1,-5]),
        ('large_finite',[1e12,2e12,3e12]),('symmetric',[-9,-5,-1,0,1,5,9])]:
        out=percentile_type7(x)
        quantiles.append({'case':name,'values':x,'quantiles':[.025,.975],'result':out,
            'exact_rank':[(len(x)-1)*q for q in (.025,.975)]})
    guards={}
    for name,x in [('empty',[]),('nonfinite',[1,float('nan')]),('inf',[1,float('inf')])]:
        try:percentile_type7(x);guards[name+'_rejected']=False
        except ValueError:guards[name+'_rejected']=True
    def normal(p=None):return {a:{'status':'COMPUTABLE','raw_p':v,'reason':None} for a,v in zip(FAMILY,p or [.001,.01,.02,.2,.9])}
    def unavailable(r,algos,reason='ZERO_VARIANCE'):
        for a in algos:r[a]={'status':'NOT_COMPUTABLE','raw_p':None,'reason':reason,'reason_detail':'합성 통계적 미산출 시험',
            'approved_rule_id':'D13_APPROVED_RULE_SYNTHETIC'}
        return r
    cases=[]
    def add(name,r,error=False):cases.append({'case':name,'input':r,'expect_implementation_error':error,'result':holm_family5(r)})
    add('all_normal',normal())
    add('one_missing',unavailable(normal(),['Random Forest']))
    add('multiple_missing',unavailable(normal(),['OLS','Elastic Net','HistGradientBoosting']))
    add('Ridge_missing',unavailable(normal(),['Ridge']))
    add('all_missing',unavailable(normal(),FAMILY))
    add('p_zero_one',normal([0.,1.,.02,.03,1.]))
    add('all_ties',normal([.01]*5))
    add('mixed_ties',normal([.02,.01,.02,.01,.6]))
    add('threshold_equal05',normal([.01,.02,.03,.2,.4]))
    add('missing_insufficient',unavailable(normal(),['OLS'],'INSUFFICIENT_PAIRED_SAMPLE'))
    add('missing_approved_unavailable',unavailable(normal(),['Ridge'],'APPROVED_INFERENCE_UNAVAILABLE'))
    r=normal();r['OLS']={'status':'IMPLEMENTATION_ERROR','raw_p':None,'reason':'CODE_BUG'};add('bug_no_substitute',r,True)
    r=normal();r['Random Forest']={'status':'IMPLEMENTATION_ERROR_REVIEW_REQUIRED','raw_p':None,'reason':'ALIGNMENT_ERROR'};add('alignment_no_substitute',r,True)
    r=normal();r['Ridge']['raw_p']=None;add('null_without_reason',r,True)
    r=normal();r['OLS']['raw_p']=-.1;add('negative_invalid_p',r,True)
    r=normal();r['OLS']['raw_p']=1.1;add('greater_one_invalid',r,True)
    r=unavailable(normal(),['OLS']);r['OLS']['reason']='UNKNOWN_NUMERIC_ERROR';add('unexplained_failure',r,True)
    r=unavailable(normal(),['Ridge']);r['Ridge']['raw_p']=1.;add('raw_missing_cannot_be_one',r,True)
    r=normal();r.pop('OLS');add('family4_forbidden',r,True)
    r=normal();r['extra']={'status':'COMPUTABLE','raw_p':.1};add('family6_forbidden',r,True)
    r=normal();r['OLS']['raw_p']=True;add('boolean_invalid_p',r,True)
    r=unavailable(normal(),['Ridge'],'APPROVED_INFERENCE_UNAVAILABLE');r['Ridge'].pop('approved_rule_id');add('unapproved_rule',r,True)
    checks={}
    for c in cases:
        o=c['result'];err=c['expect_implementation_error']
        checks[c['case']]=o['family_size']==5 and ((o['family_status']=='IMPLEMENTATION_ERROR_REVIEW_REQUIRED' and o['internal_Holm_vector'] is None
            and all(r['internal_Holm_input'] is None and r['reported_adjusted_p'] is None for r in o['rows'])) if err else
            (not o['errors'] and len(o['internal_Holm_vector'])==5 and all(
                r['raw_p'] is None and r['reported_adjusted_p'] is None and r['internal_Holm_input']==1. and r['decision']=='REJECTION_NOT_SUPPORTED'
                for r in o['rows'] if r['status']=='NOT_COMPUTABLE')))
    checks['two_point_interpolation']=quantiles[0]['result']==[-9.,29.]
    checks['rank41_exact']=quantiles[1]['result']==[1.,39.]
    checks['rank401_exact']=quantiles[2]['result']==[10.,390.]
    by={c['case']:c['result'] for c in cases}
    checks['primary_Ridge_unavailable']=by['Ridge_missing']['primary_status']=='PRIMARY_RIDGE_INFERENCE_UNAVAILABLE'
    checks['all_unavailable_not_negative_evidence']=by['all_missing']['family_status']=='FAMILY_INFERENCE_UNAVAILABLE'
    checks['one_missing_partial_disclosed']=by['one_missing']['family_status']=='PARTIALLY_EVALUATED_FAMILY'
    # Byte-identical MBB smoke. Prior 22+7 QC and every original artifact remain protected.
    grid=[str(date(2000,1,3)+timedelta(weeks=i)) for i in range(52)]
    result,_,_,_=simulate(grid,[2+i/100 for i in range(52)],[1.]*52,8)
    checks['unchanged_MBB_smoke5000']=result['status']=='RESAMPLING_QC_SUCCESS' and result['accepted']==5000
    checks.update(guards)
    status='PASS' if all(checks.values()) else 'FAIL'
    write('qc/D13_LOCK_SYNTHETIC_RESULTS.json',{'status':status,'scope':'합성 분위수와 합성p값만; 실제Y/예측손실 미사용',
        'A01_cases':quantiles,'A02_cases':cases,'checks':checks,'check_count':len(checks),
        'MBB_smoke':result,'prior_22_cases_and_7_guards':'원본 및 해시 보존; RNG/추출코드 바이트 동일',
        'real_bootstrap_p_values_added':False})
    print(json.dumps({'status':status,'A01_cases':len(quantiles),'A02_cases':len(cases),'checks':len(checks),
        'failed':[k for k,v in checks.items() if not v]},ensure_ascii=False))

if __name__=='__main__':main()
