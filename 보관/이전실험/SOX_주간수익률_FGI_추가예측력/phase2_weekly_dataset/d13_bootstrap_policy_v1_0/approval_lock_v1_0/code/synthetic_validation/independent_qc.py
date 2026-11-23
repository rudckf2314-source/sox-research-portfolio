"""A01은 Decimal, A02는 31개 부분집합 폐쇄검정으로 별도 검증."""
import itertools,math,json,sys
from decimal import Decimal,ROUND_FLOOR,localcontext
from common import OUT,CAND,ROOT,PHASE1,load,sha,write
FAMILY=['OLS','Ridge','Elastic Net','Random Forest','HistGradientBoosting']

def main():
    if '--sealed-check' in sys.argv:
        m=load(OUT/'qc/D13_LOCK_OUTPUT_MANIFEST.json')
        assert sha(OUT/'qc/D13_LOCK_OUTPUT_MANIFEST.json')==(OUT/'qc/D13_LOCK_OUTPUT_MANIFEST.sha256').read_text().split()[0]
        assert all(sha(OUT/x['path'])==x['sha256'] for x in m['files'])
        expected={x['path'] for x in m['files']}|set(m['excludes'])
        assert expected=={x.relative_to(OUT).as_posix() for x in OUT.rglob('*') if x.is_file()}
        g=load(OUT/'D13_GATE_STATUS.json');assert g['D13_LOCK_STATUS']=='LOCKED_v1_0' and g['D13_LOCK_QC']=='PASS'
        assert g['PHASE3_EXECUTION']=='NOT_AUTHORIZED' and g['PHASE4_TEST_PERFORMANCE']=='SEALED'
        policy=load(OUT/'D13_LOCKED_POLICY_v1_0.json')
        assert policy['status']=='LOCKED_v1_0' and policy['approved']
        assert policy['operational_inference']['MBB']['minimum_valid_resample_n']=='max(52, ceil(0.80*N_grid))'
        assert policy['operational_inference']['MBB']['max_total_attempts']==10000
        assert all(x['status']=='APPROVED' for x in load(OUT/'D13_APPROVED_DECISIONS.json')['decisions'])
        assert 'LOCKED_v1_0' in (OUT/'reports/D13_LOCK_REPORT.md').read_text(encoding='utf-8')
        assert 'NOT_AUTHORIZED' in (OUT/'reports/D13_LOCK_HANDOFF.md').read_text(encoding='utf-8')
        manifest=load(OUT/'qc/D13_LOCK_INPUT_MANIFEST.json')
        assert all(sha(ROOT/p)==v['sha256'] for p,v in manifest['protected_files'].items())
        print({'sealed_check':'PASS','hashed_outputs':len(m['files']),'protected':len(manifest['protected_files']),'actual_test_Y_parsing':0})
        return
    test=load(OUT/'qc/D13_LOCK_SYNTHETIC_RESULTS.json');checks={};qresults=[];hresults=[]
    for c in test['A01_cases']:
        with localcontext() as ctx:
            ctx.prec=60
            values=sorted(Decimal(str(x)) for x in c['values']);expected=[]
            for q in [Decimal('0.025'),Decimal('0.975')]:
                h=Decimal(len(values)-1)*q;j=int(h.to_integral_value(rounding=ROUND_FLOOR));g=h-Decimal(j)
                expected.append(float(values[j]+g*(values[min(j+1,len(values)-1)]-values[j])))
        okay=all(math.isclose(a,b,rel_tol=1e-14,abs_tol=1e-12) for a,b in zip(expected,c['result']))
        qresults.append({'case':c['case'],'expected_independent_type7':expected,'PASS':okay})
    for c in test['A02_cases']:
        records=c['input'];actual=c['result'];error=False
        if set(records)!=set(FAMILY):error=True
        for a in FAMILY:
            r=records.get(a,{})
            if r.get('status')=='COMPUTABLE':
                p=r.get('raw_p');error |= isinstance(p,bool) or not isinstance(p,(int,float)) or (isinstance(p,(int,float)) and (not math.isfinite(p) or not 0<=p<=1))
            elif r.get('status')=='NOT_COMPUTABLE':
                error |= r.get('raw_p') is not None or r.get('reason') not in ('INSUFFICIENT_PAIRED_SAMPLE','ZERO_VARIANCE','APPROVED_INFERENCE_UNAVAILABLE') or not r.get('reason_detail')
                error |= r.get('reason')=='APPROVED_INFERENCE_UNAVAILABLE' and not r.get('approved_rule_id')
            else:error=True
        okay=True;adjusted={}
        if error:
            okay=actual['family_status']=='IMPLEMENTATION_ERROR_REVIEW_REQUIRED' and actual['internal_Holm_vector'] is None
            okay &= all(r['internal_Holm_input'] is None and r['reported_adjusted_p'] is None for r in actual['rows'])
        else:
            vector=[1. if records[a]['status']=='NOT_COMPUTABLE' else records[a]['raw_p'] for a in FAMILY]
            # Closed Bonferroni over ALL 31 nonempty subsets, no step-down routine reused.
            for i,a in enumerate(FAMILY):
                values=[]
                for mask in range(1,32):
                    if mask & (1<<i):
                        subset=[vector[j] for j in range(5) if mask & (1<<j)]
                        values.append(min(1.,len(subset)*min(subset)))
                adjusted[a]=max(values)
            rows={r['algorithm']:r for r in actual['rows']};missing=sum(records[a]['status']=='NOT_COMPUTABLE' for a in FAMILY)
            okay &= actual['family_size']==5 and actual['internal_Holm_vector']==vector
            okay &= actual['family_status']==('FAMILY_INFERENCE_UNAVAILABLE' if missing==5 else 'PARTIALLY_EVALUATED_FAMILY' if missing else 'FULLY_EVALUATED_FAMILY')
            okay &= actual['primary_status']==('PRIMARY_RIDGE_INFERENCE_UNAVAILABLE' if records['Ridge']['status']=='NOT_COMPUTABLE' else 'PRIMARY_RIDGE_EVALUABLE')
            order=sorted(range(5),key=lambda i:vector[i])
            okay &= all(adjusted[FAMILY[a]]<=adjusted[FAMILY[b]] for a,b in zip(order,order[1:]))
            for a in FAMILY:
                row=rows[a]
                if records[a]['status']=='NOT_COMPUTABLE':
                    okay &= row['raw_p'] is None and row['reported_adjusted_p'] is None and row['internal_Holm_input']==1. and row['decision']=='REJECTION_NOT_SUPPORTED'
                else:
                    okay &= row['raw_p']==records[a]['raw_p'] and math.isclose(row['reported_adjusted_p'],adjusted[a],abs_tol=1e-15)
                    okay &= row['decision']==('REJECT_NULL' if adjusted[a]<=.05 else 'REJECTION_NOT_SUPPORTED')
        hresults.append({'case':c['case'],'PASS':bool(okay),'independent_closed_Bonferroni_adjusted':adjusted,'implementation_error':bool(error)})
    candidate=load(CAND/'policy/D13_LOCK_CANDIDATE.json');policy=load(OUT/'logs/D13_APPROVED_CONTENT_PRE_QC.json')
    inherited=load(PHASE1/'PHASE1_LOCKED_SPEC_v1_1.json')['inference']
    checks['기존D13후보실행규칙완전동일']=policy['approved_execution_rules']==candidate['candidate_rules']
    checks['D08_HAC및통계설계원문동일']=policy['inherited_inference_reference']==inherited
    checks['A01_Type7_Decimal9사례독립일치']=len(qresults)==9 and all(x['PASS'] for x in qresults)
    checks['A02_부분집합폐쇄검정22사례일치']=len(hresults)==22 and all(x['PASS'] for x in hresults)
    checks['Holm5개family_정렬및단조성']=all(x['PASS'] for x in hresults)
    checks['p미산출보고null_내부만1']=all(x['PASS'] for x in hresults)
    checks['구현오류대체금지_절차중단']=all(x['PASS'] for x in hresults if x['implementation_error'])
    checks['Ridge주력미산출보호']=all(x['PASS'] for x in hresults if x['case'] in ['Ridge_missing','all_missing'])
    checks['A01_A02승인ID정확']=policy['A01']['decision_id']=='D13_A01_PERCENTILE_LINEAR_TYPE7' and policy['A02']['decision_id']=='D13_A02_HOLM_FAMILY5_CONSERVATIVE_MISSING_P'
    checks['Bootstrap_p미도입']=policy['bootstrap_p_value_enabled'] is False
    checks['MBB_RNG_결측구현바이트동일']=sha(CAND/'code/bootstrap_candidate.py')==sha(OUT/'code/synthetic_validation/bootstrap_locked.py')
    old=load(CAND/'qc/D13_SYNTHETIC_TEST_RESULTS.json')
    checks['기존22사례7경계검사보존']=old['status']=='PASS' and old['case_count']==22 and len(old['guards'])==7 and all(old['guards'].values())
    checks['새합성테스트32개PASS']=test['status']=='PASS' and all(test['checks'].values())
    checks['Type7_CI종류변경없음']=policy['A01']['quantiles']==[.025,.975] and policy['A01']['method']=='linear' and policy['A01']['Hyndman_Fan_type']==7
    protected=load(OUT/'qc/D13_LOCK_INPUT_MANIFEST.json')['protected_files']
    changed=[p for p,v in protected.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=v['sha256']]
    checks['보호1569파일불변']=len(protected)==1569 and not changed
    checks['시험Y파싱없는별도합성입력경로']=test['scope'].startswith('합성') and all('values' in x for x in test['A01_cases'])
    checks['정책동결목표및Phase3미승인']=policy['target_lock_status']=='LOCKED_v1_0' and policy['execution_restrictions']=={'empirical_inference_authorized':False,'phase3_authorized':False,'phase4_performance':'SEALED'}
    checks['방법론추가결정종료']=not policy['methodology_decisions_pending'] and policy['A01']['status']==policy['A02']['status']=='APPROVED'
    result={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'count':len(checks),
        'A01_independent':qresults,'A02_independent':hresults,'protected_changed':changed,
        'scope':'동일 Codex 작업 내 별도 구현 QC. 외부 독립심사 아님. 실제 Y/손실/유의성 계산 없음.'}
    write('qc/D13_LOCK_INDEPENDENT_QC.json',result)
    write('qc/D13_LOCK_INDEPENDENT_QC.md','# D13 LOCK 독립 QC\n\n'+result['scope']+'\n\n'+result['status']+f" — {len(checks)}개 검사\n\n"+
        '\n'.join('- '+k+': '+('PASS' if v else 'FAIL') for k,v in checks.items())+
        '\n\nA01은 Decimal 60자리로 h=(n−1)q를 계산했다. A02는 주 계산의 정렬/step-down 코드를 호출하지 않고 31개 비공집합의 Bonferroni 폐쇄검정과 대조했다. 입력·출력 읽기 도우미만 공유한다. 정책 승인과 실제 통계적 유의성을 구별한다. 최종파일 생성 후 --sealed-check로 게이트/보고서/manifest와 보호해시를 추가 확인한다.\n')
    print(json.dumps({'independent_QC':result['status'],'checks':len(checks),'failed':[k for k,v in checks.items() if not v]},ensure_ascii=False))

if __name__=='__main__':main()
