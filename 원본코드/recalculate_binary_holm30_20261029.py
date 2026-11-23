"""Re-scope existing unadjusted tests to the 30 binary comparisons; no fitting."""
from pathlib import Path
from fractions import Fraction
from collections import Counter
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('C:/Users/rudck/Desktop/SOX_논문_연구/04_핵심근거/06_동일알고리즘_변수추가효과90.csv')
DAILY = ROOT / 'outputs/frozen_extension_all_tasks_20261023_v1_20261024/FULL706_CLASSIFICATION_DAILY.csv'
PDF = Path('C:/Users/rudck/Desktop/필라델피아 반도체 지수 방향 예측의 변수중요도와 추가 예측력 비교.pdf')
OUT = ROOT / 'outputs/holm30_binary_20261029'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def holm_float(p):
    order = sorted(range(len(p)), key=lambda i: p[i])
    result = [0.0] * len(p)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(p)-rank)*p[i])
        result[i] = min(1.0, running)
    return result

def holm_exact(p):
    order = sorted(range(len(p)), key=lambda i: p[i])
    # Explicit prefix maximum, independent of the iterative float implementation.
    result = [None]*len(p)
    weighted = [(len(p)-rank)*p[i] for rank, i in enumerate(order)]
    for rank, i in enumerate(order):
        result[i] = min(Fraction(1), max(weighted[:rank+1]))
    return result

def main():
    OUT.mkdir(exist_ok=True)
    protected = {str(p): sha(p) for p in [SOURCE, DAILY, PDF]}
    with SOURCE.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        all_rows = list(reader)
    assert len(all_rows) == 90
    assert Counter(r['task'] for r in all_rows) == {'BINARY':30, 'FOUR':30, 'REGRESSION':30}
    raw_all = [float(r['p_centered_block_bootstrap_approx']) for r in all_rows]
    old = holm_float(raw_all)
    assert all(math.isclose(q, float(r['p_Holm90']), abs_tol=1e-12) for q,r in zip(old,all_rows))
    binary = [dict(r) for r in all_rows if r['task']=='BINARY']
    assert len({(r['comparison'],r['algo']) for r in binary}) == 30
    assert len({r['comparison'] for r in binary}) == 5
    assert {r['algo'] for r in binary} == {'LR','RF','ET','HGB','XGB','LGBM'}
    assert all(v==6 for v in Counter(r['comparison'] for r in binary).values())
    p = [float(r['p_centered_block_bootstrap_approx']) for r in binary]
    q = holm_float(p)
    p_exact = [Fraction(round(v*5001),5001) for v in p]
    assert all(abs(float(a)-b)<1e-14 for a,b in zip(p_exact,p))
    exact = holm_exact(p_exact)
    assert all(abs(float(a)-b)<1e-12 for a,b in zip(exact,q))
    for r,value in zip(binary,q):
        assert value <= float(r['p_Holm90'])+1e-12
        r.update(p_Holm30=value,
                 significant_Holm90=float(r['p_Holm90'])<.05,
                 significant_Holm30=value<.05,
                 direction='positive' if float(r['effect'])>0 else 'negative' if float(r['effect'])<0 else 'zero',
                 evaluation_start='2024-01-02',evaluation_end='2026-10-23',evaluation_days=706,
                 hypothesis='mean daily accuracy difference = 0; approximate two-sided centered block bootstrap',
                 family='five feature-group pairs x six binary classifiers',
                 selection_bias_removed=False)

    # Check every effect against the original 706-day predictions, without fitting or changing predictions.
    needed={(r[k],'BINARY',r['algo']) for r in binary for k in ['base','candidate']}
    series={k:{} for k in needed}
    with DAILY.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            key=(r['mask'],r['task'],r['algo'])
            if key not in needed: continue
            assert r['date'] not in series[key]
            series[key][r['date']] = (int(r['Y']),int(r['prediction']))
    target_dates=None
    for values in series.values():
        dates=sorted(values)
        assert len(dates)==706 and dates[0]=='2024-01-02' and dates[-1]=='2026-10-23'
        if target_dates is None: target_dates=dates
        assert dates==target_dates
    for r in binary:
        a=series[(r['candidate'],'BINARY',r['algo'])]
        b=series[(r['base'],'BINARY',r['algo'])]
        assert all(a[d][0]==b[d][0] for d in target_dates)
        effect=100*sum((a[d][0]==a[d][1])-(b[d][0]==b[d][1]) for d in target_dates)/706
        assert math.isclose(effect,float(r['effect']),abs_tol=1e-12)
        r['effect_verified_from_706_predictions']=True

    extra=[k for k in binary[0] if k not in fields]
    target=OUT/'이진분류30개_Holm보정_90개대비.csv'
    with target.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields+extra)
        writer.writeheader(); writer.writerows(binary)
    significant=[r for r in binary if r['significant_Holm30']]
    positive=[r for r in significant if r['direction']=='positive']
    negative=[r for r in significant if r['direction']=='negative']
    et=next(r for r in binary if r['algo']=='ET' and r['comparison']=='가격→FGI추가')
    report=dict(status='PASS_BINARY_HOLM30_RECALCULATED',
                source=protected,original_family=90,new_family=30,
                original_Holm90_reproduced=True,independent_fraction_check=True,
                all_30_effects_verified_from_706_predictions=True,
                models_refitted=0,predictions_changed=False,
                effects_and_confidence_intervals_changed=False,
                positive_significant_count=len(positive),negative_significant_count=len(negative),
                old_negative_significant_count=sum(r['significant_Holm90'] and r['direction']=='negative' for r in binary),
                all_binary_p_values_nonincreasing=True,
                minimum_positive_adjusted_p=min(r['p_Holm30'] for r in binary if r['direction']=='positive'),
                ET_FGI=dict(effect_pp=float(et['effect']),unadjusted_p=float(et['p_centered_block_bootstrap_approx']),old_adjusted_p=float(et['p_Holm90']),new_adjusted_p=et['p_Holm30']),
                graph1_change_required=False,table3_change_required=False,
                text_changes=['Holm family:90 -> 30','ET FGI adjusted p:.036 -> .012'],
                no_positive_improvement_conclusion_changed=False,
                inferential_scope='exploratory; family re-scoped to binary-only manuscript; broader model-selection uncertainty remains',
                output_csv=str(target))
    assert all(sha(Path(p))==digest for p,digest in protected.items())
    report['original_sources_and_manuscript_unchanged']=True
    (OUT/'재계산_검증결과.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=(
        '이진분류 30개 Holm 보정 재계산\n'
        '평가기간:2024.01.02~2026.10.23,706거래일\n'
        '모형 재학습·예측 변경 없음. 기존 30개 비보정 p값을 그대로 사용.\n'
        '5개 변수군 추가 비교×6개 분류기=30개 검정군으로 Holm 보정.\n'
        f'유의한 양의 개선:{len(positive)}개. 유의한 음의 변화:{len(negative)}개.\n'
        f"ET 가격→FGI: 정확도 {float(et['effect']):.5f}%p, 보정 p={float(et['p_Holm90']):.9f} → {et['p_Holm30']:.9f}.\n"
        '그림1·표3 수치·신뢰구간·변수중요도·모의투자 변경 없음.\n'
        '국영문 요약·결론의 보정 후 유의한 양의 개선 없음이라는 판단 유지.\n'
        '4.2절은 검정군90→30,보정 p=.036→.012만 수정 필요.\n'
        '각주 권장:20일 블록 5,000회 재표집으로 성능 차이 구간을 산출하고 차이 0을 근사 양측검정했다. 이진분류 30개(5쌍×6분류기)에 Holm 보정을 적용했다. 사후 모형 선택의 불확실성은 반영하지 않는다.\n'
        '원본90개 결과·706일 예측·논문PDF는 수정하지 않음.\n'
    )
    (OUT/'계산결과와_논문수정안.txt').write_text(summary,encoding='utf-8-sig')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
