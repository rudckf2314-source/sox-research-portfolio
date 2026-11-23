"""예측 경계·지표·통계의 별도 구현. 원 실행/통계함수 호출 없음."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import csv,json,gzip,hashlib,math,calendar,sys
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import numpy as np
from sklearn.linear_model import ElasticNet
from sklearn.ensemble import RandomForestRegressor,HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2]
BUILD=ROOT/'research_C/phase2_weekly_dataset/build_v1_1';NY=ZoneInfo('America/New_York');UTC=timezone.utc
FAMILY=['OLS','Ridge','ElasticNet','RandomForest','HistGradientBoosting'];FIELDS=[f'B{i}' for i in range(1,11)]+['F1']
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(rel,obj):
    with (OUT/rel).open('x',encoding='utf-8') as f:f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def t(s):return datetime.fromisoformat(s).astimezone(UTC)
def metric(rs):
    y=[float(r['actual_y']) for r in rs];p=[float(r['prediction']) for r in rs];n=len(y)
    e=[a-b for a,b in zip(y,p)];S=math.fsum(x*x for x in e);D=math.fsum((float(r['actual_y'])-float(r['training_mean']))**2 for r in rs)
    sign=lambda x:int(x>0)-int(x<0)
    return {'n':n,'MAE':math.fsum(abs(x) for x in e)/n,'RMSE':math.sqrt(S/n),'OOS_R2_training_mean':1-S/D if D else None,
        'direction_accuracy':sum(sign(a)==sign(b) for a,b in zip(y,p))/n,'actual_zero_n':sum(x==0 for x in y),
        'prediction_zero_n':sum(x==0 for x in p),'nonzero_actual_direction_accuracy':sum(sign(a)==sign(b) for a,b in zip(y,p) if a!=0)/sum(x!=0 for x in y) if any(y) else None}
def main():
    if '--sealed-check' in sys.argv:
        m=load(OUT/'qc/PHASE4_OUTPUT_MANIFEST.json');assert sha(OUT/'qc/PHASE4_OUTPUT_MANIFEST.json')==(OUT/'qc/PHASE4_OUTPUT_MANIFEST.sha256').read_text().split()[0]
        assert all(sha(OUT/x['path'])==x['sha256'] for x in m['files'])
        assert {x['path'] for x in m['files']}|set(m['excludes'])=={x.relative_to(OUT).as_posix() for x in OUT.rglob('*') if x.is_file()}
        p=load(OUT/'inputs/PHASE4_INPUT_MANIFEST.json')['protected_files'];assert all(sha(ROOT/r)==v['sha256'] for r,v in p.items())
        print({'final_manifest':'PASS','hashed_outputs':len(m['files']),'protected':len(p)});return
    assert (OUT/'logs/ALL_PREDICTIONS_COMMITTED.json').exists()
    config=load(OUT/'config/PHASE4_LOCKED_EXECUTION_CONFIG.json');selected=config['phase3_lock']['selected_algorithms']
    files=load(OUT/'inputs/PHASE4_INPUT_MANIFEST.json')['sealed_files'];core=next(ROOT/r['path'] for r in files if Path(r['path']).name=='WEEKLY_CORE_TEST.csv')
    raw=read(BUILD/'data/train_dev/WEEKLY_CORE_COMBINED.csv')+read(core);lookup={r['week_start']:r for r in raw}
    target=[r for r in raw if r['split']=='sealed_test'];grid=[r['week_start'] for r in target];N=len(grid)
    checks={};checks['301주고정격자']=N==301 and grid[0]=='2021-01-04' and grid[-1]=='2026-10-05' and all((datetime.fromisoformat(b)-datetime.fromisoformat(a)).days==7 for a,b in zip(grid,grid[1:]))
    ps=read(OUT/'predictions/PHASE4_ALL_TEST_PREDICTIONS.csv');base=read(OUT/'predictions/PHASE4_BASELINE_PREDICTIONS.csv');audit=read(OUT/'predictions/PHASE4_ORIGIN_TRAINING_AUDIT.csv')
    trained={};boundary=True;baselinegood=True
    for a in audit:
        O=t(a['prediction_origin']);loc=O.astimezone(NY);yr=loc.year-5;cut=loc.replace(year=yr,day=min(loc.day,calendar.monthrange(yr,loc.month)[1])).astimezone(UTC)
        rows=[r for r in raw if r['week_start']<a['week_start'] and t(r['prediction_origin'])<O and t(r['label_assumed_available_at'])<O and r['Y_valid']=='True' and r['M0_X_valid']=='True' and r['M1_X_valid']=='True' and (a['window_type']=='expanding' or t(r['prediction_origin'])>=cut)]
        trained[a['week_start'],a['window_type']]=rows
        boundary &= len(rows)==int(a['train_n']) and rows[0]['week_start']==a['train_start'] and rows[-1]['week_start']==a['train_end'] and len(rows)>=156
        boundary &= hashlib.sha256('\n'.join(r['week_start'] for r in rows).encode()).hexdigest()==a['training_week_list_sha256']
        m=math.fsum(float(r['Y']) for r in rows)/len(rows)
        for b in [r for r in base if r['week_start']==a['week_start'] and r['window_type']==a['window_type']]:
            expected=0. if b['baseline']=='zero_return' else m;baselinegood &= math.isclose(float(b['prediction']),expected,abs_tol=1e-12)
    checks['602학습창_5달력년_성숙UTC엄격_최소156']=len(trained)==602 and boundary
    checks['기준0_훈련평균독립확인']=baselinegood and len(base)==1204
    specs=True
    for r in ps:
        a=r['algorithm'];s=selected[a];specs &= r['candidate_id']==s['models'][r['information_set']]['candidate_id'] and r['window_type']==s['selected_window']
    checks['고정10설정_3010예측']=specs and len(ps)==3010 and all(math.isfinite(float(r['prediction'])) for r in ps)
    checks['동일날짜Y_오차검증']=all(math.isclose(float(r['actual_y']),float(lookup[r['week_start']]['Y']),abs_tol=1e-13) and math.isclose(float(r['error']),float(r['actual_y'])-float(r['prediction']),abs_tol=1e-12) for r in ps)
    reported=read(OUT/'metrics/PHASE4_MODEL_METRICS.csv');metricsgood=True
    for r in reported:
        group=[p for p in ps if p['algorithm']==r['algorithm'] and p['information_set']==r['information_set']];m=metric(group)
        metricsgood &= all(r[k]=='' if v is None else math.isclose(float(r[k]),float(v),abs_tol=1e-12,rel_tol=1e-12) for k,v in m.items())
    checks['10모형MAE_RMSE_OOSR2_방향전수재계산']=metricsgood
    checks['음수예측보존']=any(float(r['prediction'])<0 for r in ps)
    paired=read(OUT/'predictions/PHASE4_PAIRED_TEST_PREDICTIONS.csv');d_by={};pairgood=True
    for algo in FAMILY:
        rr=[r for r in paired if r['algorithm']==algo];assert [r['week_start'] for r in rr]==grid
        vals=[]
        for r in rr:
            y=float(r['actual_y']);v=abs(y-float(r['M0_prediction']))-abs(y-float(r['M1_prediction'])) if r['M0_prediction'] and r['M1_prediction'] else float('nan');vals.append(v)
            pairgood &= math.isclose(v,float(r['paired_loss_difference']),abs_tol=1e-12) if math.isfinite(v) else not r['paired_loss_difference']
        d_by[algo]=np.array(vals)
    checks['paired손실차이_부호5알고리즘']=pairgood
    hrows=read(OUT/'inference/PHASE4_HAC_SENSITIVITY.csv');hacgood=True
    for r in hrows:
        full=d_by[r['algorithm']];positions=np.flatnonzero(np.isfinite(full));vals=full[positions];n=len(vals);q=int(r['lag'])
        if n<max(52,math.ceil(.8*N)):
            hacgood &= r['status']=='NOT_COMPUTABLE' and r['reason']=='INSUFFICIENT_PAIRED_SAMPLE';continue
        u=vals-vals.mean();W=np.maximum(0.,1-np.abs(positions[:,None]-positions[None,:])/(q+1));omega=float(u@W@u/n)
        if omega==0:
            hacgood &= r['status']=='NOT_COMPUTABLE' and r['reason']=='ZERO_VARIANCE';continue
        se=math.sqrt(omega/n);z=float(vals.mean())/se;p=.5*math.erfc(z/math.sqrt(2))
        expected={'mean_d':float(vals.mean()),'Omega':omega,'SE':se,'z':z,'raw_p':p,'CI_low':float(vals.mean())-1.95996398454*se,'CI_high':float(vals.mean())+1.95996398454*se}
        hacgood &= all(math.isclose(float(r[k]),v,abs_tol=1e-12,rel_tol=1e-11) for k,v in expected.items())
    checks['HAC15결과_행렬kernel_정규p독립']=hacgood
    refits=[];pre=load(OUT/'logs/PHASE4_PREPROCESSING_FIT_AUDIT.json');scale=True;stats={}
    for (w,win),rs in trained.items():
        for width in (10,11):
            x=np.array([[float(r[c]) for c in FIELDS[:width]] for r in rs]);stats[w,win,width]=(x.mean(0),x.var(0),len(x))
    for p in pre:
        if p['algorithm'] in ['OLS','Ridge','ElasticNet']:
            mu,var,n=stats[p['week_start'],p['window_type'],p['p_with_intercept']-1]
            scale &= p['scaler_n_samples']==n and np.allclose(mu,p['scaler_mean'],atol=1e-12,rtol=1e-12) and np.allclose(var,p['scaler_var'],atol=1e-12,rtol=1e-12)
        else:scale &= p['scaler_n_samples']==0
    checks['전수train_only스케일러']=bool(scale)
    for row in [target[0],target[len(target)//2],target[-1]]:
        for algo,s in selected.items():
            train=trained[row['week_start'],s['selected_window']];y=np.array([float(r['Y']) for r in train])
            for info,width in [('C-M0',10),('C-M1',11)]:
                X=np.array([[float(r[c]) for c in FIELDS[:width]] for r in train]);now=np.array([[float(row[c]) for c in FIELDS[:width]]])
                mu=X.mean(0);sd=X.std(0);sd[sd==0]=1;Z=(X-mu)/sd;z=(now-mu)/sd
                kw={k:v for k,v in s['models'][info]['hyperparameters'].items() if k!='candidate_id'}
                with threadpool_limits(limits=1):
                    if algo=='OLS':beta=np.linalg.lstsq(np.column_stack([np.ones(len(Z)),Z]),y,rcond=None)[0];v=float(np.r_[1,z[0]]@beta)
                    elif algo=='Ridge':beta=np.linalg.solve(Z.T@Z+kw['alpha']*np.eye(width),Z.T@(y-y.mean()));v=float(y.mean()+z[0]@beta)
                    elif algo=='ElasticNet':m=ElasticNet(random_state=20261016,**kw);m.fit(Z,y);v=float(m.predict(z)[0])
                    elif algo=='RandomForest':m=RandomForestRegressor(**kw);m.fit(X,y);v=float(m.predict(now)[0])
                    else:m=HistGradientBoostingRegressor(**kw);m.fit(X,y);v=float(m.predict(now)[0])
                saved=float(next(r for r in ps if r['week_start']==row['week_start'] and r['algorithm']==algo and r['information_set']==info)['prediction'])
                refits.append({'week_start':row['week_start'],'algorithm':algo,'information_set':info,'abs_difference':abs(v-saved),'PASS':math.isclose(v,saved,abs_tol=1e-8,rel_tol=1e-8)})
    checks['첫중간끝30예측_독립재추정']=len(refits)==30 and all(r['PASS'] for r in refits)
    bootmeta=load(OUT/'inference/PHASE4_BOOTSTRAP_ATTEMPT_AUDIT.json');bootresults=read(OUT/'inference/PHASE4_BOOTSTRAP_RESULTS.csv');seeds=load(OUT/'inference/PHASE4_BOOTSTRAP_SEED_MANIFEST.json');bootgood=True;details=[]
    rawhash=hashlib.sha256('\n'.join(grid).encode('ascii')).digest();words=[int.from_bytes(rawhash[i:i+4],'little') for i in range(0,32,4)]
    for meta in bootmeta:
        algo=meta['algorithm'];L=meta['L'];rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261016,L]+words)));d=d_by[algo]
        stats_expected=[];starts_all=[];count=0;accepted=0;local=True
        with gzip.open(OUT/meta['log'],'rt',encoding='utf-8') as f:
            for line in f:
                r=json.loads(line);count+=1;starts=rng.integers(0,N-L+1,size=math.ceil(N/L)).tolist();starts_all.append(starts)
                idx=[s+j for s in starts for j in range(L)][:N];valid=np.isfinite(d[idx]);nv=int(valid.sum());ok=nv>=max(52,math.ceil(.8*N))
                local &= r['block_starts']==starts and r['n_valid']==nv and r['accepted']==ok and r['attempt']==count and count<=10000
                if ok:stats_expected.append(math.fsum(float(d[i]) for i in idx if math.isfinite(d[i]))/nv);accepted+=1
        with np.load(OUT/meta['means'],allow_pickle=False) as f:saved=f['bootstrap_means']
        local &= count==meta['attempts'] and accepted==meta['accepted'] and np.allclose(saved,stats_expected,atol=1e-12,rtol=1e-12)
        result=next(r for r in bootresults if r['algorithm']==algo and int(r['L'])==L);s=sorted(stats_expected);qs=[]
        if result['status']=='COMPLETED':
            for q in (.025,.975):h=(len(s)-1)*q;j=math.floor(h);g=h-j;qs.append((1-g)*s[j]+g*s[min(j+1,len(s)-1)])
            local &= accepted==5000 and math.isclose(float(result['CI_low']),qs[0],abs_tol=1e-12) and math.isclose(float(result['CI_high']),qs[1],abs_tol=1e-12)
        else:local &= not result['CI_low'] and not result['CI_high'] and (accepted==0 or count==10000 or result['reason']=='ZERO_VARIANCE')
        seed=next(r for r in seeds if r['algorithm']==algo and r['L']==L)
        local &= hashlib.sha256(json.dumps(starts_all,separators=(',',':')).encode()).hexdigest()==seed['starts_sha256'] and seed['forced_start_used'] is False
        details.append({'algorithm':algo,'L':L,'attempts_verified':count,'accepted_verified':accepted,'PASS':bool(local)})
        bootgood &= local
        print({'independent_bootstrap':algo,'L':L,'PASS':bool(local)},flush=True)
    checks['15개MBB_75000시도_시드인덱스_Type7']=bool(bootgood)
    checks['5알고리즘공통인덱스']=all(len({json.dumps(r['seed_words']) for r in seeds if r['L']==L})==1 and len({r['grid_sha256'] for r in seeds if r['L']==L})==1 for L in (8,4,12))
    holm=read(OUT/'inference/PHASE4_HOLM_FAMILY5_RESULTS.csv');h4=[r for r in hrows if int(r['lag'])==4]
    pv=[float(next(r for r in h4 if r['algorithm']==a)['raw_p']) if next(r for r in h4 if r['algorithm']==a)['raw_p'] else 1. for a in FAMILY];holmok=True
    for i,a in enumerate(FAMILY):
        adj=max(min(1.,sum(bool(mask&(1<<j)) for j in range(5))*min(pv[j] for j in range(5) if mask&(1<<j))) for mask in range(1,32) if mask&(1<<i))
        row=next(r for r in holm if r['algorithm']==a)
        holmok &= math.isclose(float(row['reported_adjusted_p']),adj,abs_tol=1e-12) if row['raw_p'] else not row['reported_adjusted_p'] and row['decision']=='REJECTION_NOT_SUPPORTED'
    checks['Holm5_31부분집합독립확인']=holmok and len(holm)==5
    checks['Ridge주력보호']=load(OUT/'inference/PHASE4_PRIMARY_RIDGE_INFERENCE.json')['primary_algorithm']=='Ridge'
    events=[json.loads(s) for s in (OUT/'logs/STAGE_ACCESS_LOG.jsonl').read_text(encoding='utf-8').splitlines()]
    stage={r['stage']:r for r in events};checks['사전QC후봉인해제_예측전체저장후평가']=stage['PREEXECUTION_SYNTHETIC_GATE_PASS_BEFORE_UNSEAL']['utc']<stage['UNSEALED_BEFORE_FIRST_CONTENT_PARSE']['utc']<stage['ALL_PREDICTIONS_COMMITTED_BEFORE_SCORING']['utc']<stage['EVALUATION_OUTCOMES_JOINED_AFTER_PREDICTIONS']['utc']
    auth=load(OUT/'config/PHASE4_EXECUTION_AUTHORIZATION.json');checks['시험열람후코드변경0']=all(sha(OUT/p)==h for p,h in auth['code_hashes'].items())
    protected=load(OUT/'inputs/PHASE4_INPUT_MANIFEST.json')['protected_files'];changed=[p for p,v in protected.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=v['sha256']]
    checks['보호2090파일불변']=len(protected)==2090 and not changed
    checks['원본LOCK_D13변경없음']=not changed
    checks['Phase5미실행']=config['phase5_authorized'] is False
    checks['통계미산출오류상태표시']=load(OUT/'inference/PHASE4_INFERENCE_STATUS.json')['status'] in ['COMPLETED','COMPLETED_WITH_INFERENCE_UNAVAILABLE']
    result={'status':'PASS' if all(checks.values()) else 'BLOCKED_REVIEW_REQUIRED','checks':{k:bool(v) for k,v in checks.items()},'count':len(checks),
        'refits':refits,'bootstrap_full_replay':details,'protected_changed':changed,'independent_estimator_refits':18,'independent_closed_form_solves':12,
        'scope':'동일 Codex 작업 내 별도 구현 QC. 경계/지표/스케일러/통계는전수,모형예측은첫·중간·끝30개만. sklearn라이브러리자체독립검증/외부심사아님.'}
    save('qc/PHASE4_INDEPENDENT_QC.json',result)
    save('qc/PHASE4_INDEPENDENT_QC.md','# Phase4 독립 QC\n\n'+result['scope']+f"\n\n**{result['status']}**, {len(checks)}개 검사.\n\n"+'\n'.join('- '+k+': '+('PASS' if v else 'FAIL') for k,v in checks.items())+'\n\n주 예측/통계함수를 호출하지 않았다. OLS/Ridge는 별도 선형대수,나머지는같은라이브러리의별도직접호출이다. HAC는행렬kernel과erfc, MBB는시작점/paired손실전수재추출과직접Type7,Holm은31개부분집합Bonferroni폐쇄검정으로대조했다.\n')
    print({'independent_QC':result['status'],'checks':len(checks),'failed':[k for k,v in checks.items() if not v]})
    if result['status']!='PASS':sys.exit(1)

if __name__=='__main__':main()
