"""주 MBB 함수를 import/호출하지 않는 저장 재표본 독립 전수 검사."""
import csv, gzip, hashlib, json, math
from datetime import date
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(rel,obj):
    with (OUT/rel).open('x',encoding='utf-8') as f:
        f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def main():
    original=read(OUT/'qc/D13_SYNTHETIC_TEST_RESULTS.json');checks={};details=[]
    all_checks=[]
    for case in original['cases']:
        name=case['case'];p=OUT/'qc/synthetic'/name
        with np.load(p.with_suffix('.npz'),allow_pickle=False) as f:
            grid=f['grid'].tolist();a=f['loss0'].tolist();b=f['loss1'].tolist()
        with np.load(p.parent/(name+'_means.npz'),allow_pickle=False) as f: saved=f['synthetic_resample_means'].tolist()
        n=len(grid);L=case['L'];limit=max(52,math.ceil(n*4/5))
        valid=[math.isfinite(x) and math.isfinite(y) for x,y in zip(a,b)]
        values=[x-y for x,y,v in zip(a,b,valid) if v]
        m=math.fsum(x/len(values) for x in values) if values else 0
        variance=math.fsum((x-m)*(x-m)/len(values) for x in values) if values else 0
        raw=hashlib.sha256('\n'.join(grid).encode('ascii')).digest()
        words=[int.from_bytes(raw[i:i+4],'little') for i in range(0,32,4)]
        random=np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261016,L]+words)))
        accepted=0;attempts=0;local=True;mean_max_error=0;min_nv=n;max_nv=0
        with gzip.open(p.with_suffix('.jsonl.gz'),'rt',encoding='utf-8') as f:
            for line in f:
                row=json.loads(line);attempts+=1
                start=[int(x) for x in random.integers(n-L+1,size=(n+L-1)//L)] if case['injection'] is None else [case['injection']]*((n+L-1)//L)
                local &= start==row['block_starts']
                indices=[s+j for s in start for j in range(L)][:n]
                selected=[i for i in indices if valid[i]]
                nv=len(selected);min_nv=min(min_nv,nv);max_nv=max(max_nv,nv)
                local &= len(indices)==n and all(0<=s<=n-L for s in start)
                # Missing weeks stay in slots; original dates within each block stay seven days apart.
                for j in range(0,n,L):
                    local &= all(indices[k+1]-indices[k]==1 for k in range(j,min(j+L,n)-1))
                run=longest=0
                for i in indices:
                    run=0 if valid[i] else run+1;longest=max(longest,run)
                vb=sum(any(valid[i] for i in indices[j:j+L]) for j in range(0,n,L))
                ok=nv>=limit
                reason='' if ok else ('EMPTY_PAIRED_RESAMPLE' if nv==0 else 'N_VALID_BELOW_MINIMUM')
                local &= (row['attempt']==attempts and row['N_grid']==n and row['L']==L and row['n_valid']==nv
                    and row['accepted']==ok and row['reason']==reason and row['max_missing_run']==longest and row['valid_blocks']==vb)
                if ok:
                    mean=math.fsum(a[i]-b[i] for i in selected)/nv
                    error=abs(mean-saved[accepted]);mean_max_error=max(mean_max_error,error)
                    local &= math.isclose(mean,saved[accepted],rel_tol=1e-12,abs_tol=1e-12)
                    accepted+=1
                local &= attempts<=10000 and accepted<=5000
        status=('ORIGINAL_SAMPLE_INSUFFICIENT' if sum(valid)<limit else
            'INFERENCE_UNAVAILABLE_DEGENERATE' if not math.isfinite(variance) or variance<=0 else
            'RESAMPLING_QC_SUCCESS' if accepted==5000 else 'BOOTSTRAP_INFERENCE_UNAVAILABLE')
        local &= case['status']==status and case['attempts']==attempts and case['accepted']==accepted
        local &= case['original_valid_n']==sum(valid) and case['min_valid_n']==limit
        if status=='BOOTSTRAP_INFERENCE_UNAVAILABLE': local &= attempts==10000
        if status in ('ORIGINAL_SAMPLE_INSUFFICIENT','INFERENCE_UNAVAILABLE_DEGENERATE'): local &= attempts==0
        all_checks.append(bool(local));details.append({'case':name,'PASS':bool(local),'attempts_verified':attempts,
            'accepted_verified':accepted,'max_synthetic_mean_numeric_difference':mean_max_error,
            'resample_valid_n_range':[min_nv,max_nv] if attempts else None})
    checks['22개합성사례_독립인덱스_수치_중단상태']=len(details)==22 and all(all_checks)
    checks['모든시도_블록시작_짝_결측_공백_유효블록전수검사']=all(all_checks)
    checks['시드독립재생성_원래격자보존']=all(all_checks)
    checks['최소표본_경계_재추출한도']=all(all_checks)
    checks['실제연구손실_CI_p값미사용']=all(c['confidence_interval'] is None and c['p_value'] is None for c in original['cases'])
    membership=ROOT/'research_C/phase2_weekly_dataset/build_v1_1/data/PAIRED_COMMON_WEEK_MEMBERSHIP.csv'
    with membership.open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f);checks['메타데이터열만접근']=r.fieldnames==['week_start','split','paired_common_valid'];rows=list(r)
    dates=[date.fromisoformat(r['week_start']) for r in rows]
    flags=[r['paired_common_valid']=='True' for r in rows]
    checks['823격자_818공통_초기5주외결측없음']=len(rows)==823 and sum(flags)==818 and flags==[False]*5+[True]*818
    checks['주간7일간격_중복0']=len(set(dates))==823 and all((b-a).days==7 for a,b in zip(dates,dates[1:]))
    checks['기간별308_209_301']=all(sum(r['split']==s and v for r,v in zip(rows,flags))==n for s,n in [('initial_train',308),('development',209),('sealed_test',301)])
    policy=read(OUT/'policy/D13_LOCK_CANDIDATE.json')
    locked=read(ROOT/'research_C/phase1_research_design/approval_lock_v1_1/PHASE1_LOCKED_SPEC_v1_1.json')
    checks['기존D08_정의전체불변']=policy['inherited_inference']==locked['inference']
    checks['승인전후보상태']=policy['status']=='LOCK_CANDIDATE_REVIEW_REQUIRED' and policy['approved'] is False
    cand=policy['candidate_rules']
    checks['지시한상수일치']=cand['target_valid_replicates']==5000 and cand['max_total_attempts']==10000 and cand['root_seed']==20261016 and cand['block_lengths']==[8,4,12]
    checks['bootstrap_p미도입_추가결정표시']=policy['bootstrap_p_value_enabled'] is False and len(policy['additional_decisions'])>=2
    checks['Phase3미승인_시험밀봉']=policy['gate_snapshot']['PHASE3_EXECUTION']=='NOT_AUTHORIZED' and policy['gate_snapshot']['PHASE4_TEST_PERFORMANCE']=='SEALED'
    inputs=read(OUT/'inputs/D13_INPUT_MANIFEST.json')
    changed=[r for r,v in inputs['protected_files'].items() if not (ROOT/r).is_file() or digest(ROOT/r)!=v['sha256']]
    checks['보호1474개해시불변']=len(inputs['protected_files'])==1474 and not changed
    tests=original['guards']
    checks['압축및중복격자거부기록']=tests['compressed_grid_rejected'] and tests['duplicate_grid_rejected']
    checks['같은시드재실행일치']=tests['same_seed_reproduces']
    checks['원본부족_0분산_비유한_빈블록중단검사']=all(all_checks)
    result={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'count':len(checks),
        'cases_independently_verified':details,'protected_count':len(inputs['protected_files']),'protected_changed':changed,
        'scope':'동일 Codex 작업 내 별도 코드의 독립 계산. 외부 독립심사나 검정력/coverage 증명 아님.'}
    write('qc/D13_INDEPENDENT_QC.json',result)
    write('qc/D13_INDEPENDENT_QC.md','# D13 독립 QC\n\n'+result['scope']+'\n\n판정: **'+result['status']+'**. '+str(len(checks))+'개 검사.\n\n'+
        '\n'.join('- '+k+': '+('PASS' if v else 'FAIL') for k,v in checks.items())+
        '\n\n주 계산함수를 import하거나 호출하지 않았다. 저장된 합성 손실·원래 격자·모든 블록 시작점으로 직접 인덱스를 확장하여 각 시도 유효 n, 이유, 공백, 합성 평균을 다시 계산했다. NumPy 난수 라이브러리는 공유하되 초기화·추출·집계 코드는 별도다. 시험 파일은 SHA-256 바이너리 계산만 허용했고 Y 파싱은 하지 않았다.\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'failed':[k for k,v in checks.items() if not v]},ensure_ascii=False))

if __name__=='__main__':main()
