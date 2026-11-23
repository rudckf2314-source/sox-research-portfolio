"""승인 A01/A02 구현. 실증 자료 로더/HAC/Bootstrap p 검정 없음."""
import math
import numpy as np
FAMILY=('OLS','Ridge','Elastic Net','Random Forest','HistGradientBoosting')
LEGAL_REASONS={'INSUFFICIENT_PAIRED_SAMPLE','ZERO_VARIANCE','APPROVED_INFERENCE_UNAVAILABLE'}

def percentile_type7(values):
    a=np.asarray(values,dtype=float)
    if a.ndim!=1 or len(a)==0 or not np.isfinite(a).all():raise ValueError('INVALID_QUANTILE_INPUT')
    return np.quantile(a,[0.025,0.975],method='linear').tolist()

def holm_family5(records):
    """Records must classify non-computability; never turn a bug into p=1."""
    errors=[]
    if set(records)!=set(FAMILY):errors.append('FAMILY_MEMBERS_MUST_EQUAL_FIVE')
    rows={};vector={}
    for algo in FAMILY:
        rec=records.get(algo,{})
        status=rec.get('status');p=rec.get('raw_p');reason=rec.get('reason')
        reported_p=None if isinstance(p,float) and not math.isfinite(p) else p
        rows[algo]={'algorithm':algo,'raw_p':reported_p,'status':status,'reason':reason,
            'reported_adjusted_p':None,'internal_Holm_input':None,'decision':'PROCEDURE_NOT_RUN'}
        if status=='COMPUTABLE':
            if isinstance(p,bool) or not isinstance(p,(float,int)) or not math.isfinite(p) or not 0<=p<=1:
                errors.append(algo+':INVALID_RAW_P')
            else:vector[algo]=float(p)
        elif status=='NOT_COMPUTABLE':
            if p is not None or reason not in LEGAL_REASONS or not rec.get('reason_detail'):
                errors.append(algo+':UNJUSTIFIED_NONCOMPUTABILITY')
            elif reason=='APPROVED_INFERENCE_UNAVAILABLE' and not rec.get('approved_rule_id'):
                errors.append(algo+':APPROVED_RULE_ID_REQUIRED')
            else:vector[algo]=1.0
        else:errors.append(algo+':IMPLEMENTATION_OR_UNKNOWN_STATUS')
    if errors:
        return {'family_size':5,'family_status':'IMPLEMENTATION_ERROR_REVIEW_REQUIRED',
            'primary_status':'IMPLEMENTATION_ERROR_REVIEW_REQUIRED','errors':errors,
            'internal_Holm_vector':None,'rows':list(rows.values())}
    order=sorted(FAMILY,key=lambda a:(vector[a],FAMILY.index(a)))
    adjusted={};running=0.0
    for rank,algo in enumerate(order):
        running=max(running,(5-rank)*vector[algo]);adjusted[algo]=min(1.0,running)
    missing=0
    for algo in FAMILY:
        rows[algo]['internal_Holm_input']=vector[algo]
        rows[algo]['reason_detail']=records[algo].get('reason_detail')
        if rows[algo]['status']=='NOT_COMPUTABLE':
            missing+=1;rows[algo]['decision']='REJECTION_NOT_SUPPORTED'
        else:
            rows[algo]['reported_adjusted_p']=adjusted[algo]
            rows[algo]['decision']='REJECT_NULL' if adjusted[algo]<=0.05 else 'REJECTION_NOT_SUPPORTED'
    return {'family_size':5,'family_status':'FAMILY_INFERENCE_UNAVAILABLE' if missing==5 else
        'PARTIALLY_EVALUATED_FAMILY' if missing else 'FULLY_EVALUATED_FAMILY',
        'primary_status':'PRIMARY_RIDGE_INFERENCE_UNAVAILABLE' if rows['Ridge']['status']=='NOT_COMPUTABLE' else 'PRIMARY_RIDGE_EVALUABLE',
        'missing_algorithms':missing,'internal_Holm_vector':[vector[a] for a in FAMILY],
        'sort_order':order,'errors':[],'rows':[rows[a] for a in FAMILY]}
