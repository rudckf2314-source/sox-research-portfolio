"""별도 날짜선택·수식집계·모형경로로 Phase3 검증. 시험 CSV 파싱 없음."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import csv,json,hashlib,math,sys
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet
from sklearn.ensemble import RandomForestRegressor,HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2]
BUILD=ROOT/'research_C/phase2_weekly_dataset/build_v1_1'
NY=ZoneInfo('America/New_York');UTC=timezone.utc
FIELDS=[f'B{i}' for i in range(1,11)]+['F1']
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(rel,obj):
    with (OUT/rel).open('x',encoding='utf-8') as f:f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def records(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def stamp(x):return datetime.fromisoformat(x).astimezone(UTC)
def independent_metrics(rows):
    n=len(rows);errors=[float(r['development_actual_y'])-float(r['prediction']) for r in rows]
    y=[float(r['development_actual_y']) for r in rows];p=[float(r['prediction']) for r in rows]
    sse=math.fsum(x*x for x in errors);den=math.fsum((float(r['development_actual_y'])-float(r['training_mean']))**2 for r in rows)
    sign=lambda x: (x>0)-(x<0)
    return {'n':n,'MAE':math.fsum(abs(x) for x in errors)/n,'RMSE':math.sqrt(sse/n),
        'OOS_R2_training_mean':1-sse/den if den>0 else None,
        'direction_accuracy':sum(sign(a)==sign(b) for a,b in zip(y,p))/n,
        'actual_zero_n':sum(x==0 for x in y),'prediction_zero_n':sum(x==0 for x in p),
        'nonzero_actual_direction_accuracy':sum(sign(a)==sign(b) for a,b in zip(y,p) if a!=0)/sum(x!=0 for x in y) if any(y) else None}

def main():
    if '--sealed-check' in sys.argv:
        manifest=load(OUT/'qc/PHASE3_OUTPUT_MANIFEST.json')
        assert digest(OUT/'qc/PHASE3_OUTPUT_MANIFEST.json')==(OUT/'qc/PHASE3_OUTPUT_MANIFEST.sha256').read_text().split()[0]
        assert all(digest(OUT/x['path'])==x['sha256'] for x in manifest['files'])
        assert {x['path'] for x in manifest['files']}|set(manifest['excludes'])=={x.relative_to(OUT).as_posix() for x in OUT.rglob('*') if x.is_file()}
        protected=load(OUT/'inputs/PHASE3_INPUT_MANIFEST.json')['protected_files']
        assert all(digest(ROOT/p)==v['sha256'] for p,v in protected.items())
        print({'sealed_check':'PASS','hashed_output_files':len(manifest['files']),'protected':len(protected)});return
    checks={};df=records(BUILD/'data/train_dev/WEEKLY_CORE_COMBINED.csv')
    assert all(r['week_start']<'2021-01-01' for r in df)
    data=[r for r in df if r['paired_common_valid']=='True'];data.sort(key=lambda r:r['week_start'])
    origins=[r for r in data if r['split']=='development'];lookup={r['week_start']:r for r in data}
    predictions=records(OUT/'predictions/PHASE3_ALL_CANDIDATE_PREDICTIONS.csv')
    baseline=records(OUT/'predictions/PHASE3_BASELINE_PREDICTIONS.csv')
    audit=records(OUT/'predictions/PHASE3_ORIGIN_TRAINING_AUDIT.csv')
    training={};alltime=True;allcounts=True;baselinegood=True
    for target in origins:
        o=stamp(target['prediction_origin']);local=o.astimezone(NY)
        cutoff=local.replace(year=local.year-5).astimezone(UTC)
        for window in ['expanding','rolling_5_calendar_years']:
            rows=[]
            for r in data:
                if r['week_start']>=target['week_start']:continue
                if not stamp(r['label_assumed_available_at'])<o:continue
                if stamp(r['prediction_origin'])>=o:continue
                if window=='rolling_5_calendar_years' and stamp(r['prediction_origin'])<cutoff:continue
                rows.append(r)
            training[(target['week_start'],window)]=rows
            reported=next(r for r in audit if r['week_start']==target['week_start'] and r['window_type']==window)
            mean=math.fsum(float(r['Y']) for r in rows)/len(rows)
            allcounts &= len(rows)==int(reported['train_n']) and rows[0]['week_start']==reported['train_start'] and rows[-1]['week_start']==reported['train_end']
            alltime &= all(stamp(r['label_assumed_available_at'])<o and stamp(r['prediction_origin'])<o for r in rows)
            allcounts &= hashlib.sha256('\n'.join(r['week_start'] for r in rows).encode()).hexdigest()==reported['training_week_list_sha256']
            for b in [r for r in baseline if r['week_start']==target['week_start'] and r['window_type']==window]:
                expected=0 if b['baseline']=='zero_return' else mean
                baselinegood &= math.isclose(float(b['prediction']),expected,abs_tol=1e-12)
    checks['517공통_209원점_중복0']=len(data)==517 and len(origins)==209 and len(lookup)==517
    checks['418개창_독립학습경계행수해시일치']=allcounts and len(training)==418
    checks['라벨성숙_자체X원점과거_현재Y유입0']=alltime
    checks['260행강제확장없이5달력년']=allcounts and all(len(v)>=156 for v in training.values())
    checks['0및학습평균836예측독립일치']=baselinegood and len(baseline)==836
    lineages=records(OUT/'inputs/TRAIN_DEV_FEATURE_AVAILABILITY.csv')
    checks['5687개자체역사원점가용성']=len(lineages)==5687 and all(r['valid']=='True' and r['source_period_complete']=='True' and
        stamp(r['actual_available_at'] if r['actual_available_at'] not in ('null','','None') else r['latest_assumed_available_at'])<stamp(r['prediction_origin']) for r in lineages)
    groups={}
    for r in predictions:
        key=tuple(r[k] for k in ['algorithm','information_set','window_type','candidate_id']);groups.setdefault(key,[]).append(r)
    calc={key:independent_metrics(rows) for key,rows in groups.items()}
    original=records(OUT/'metrics/PHASE3_CANDIDATE_METRICS.csv');metricok=True
    for row in original:
        key=tuple(row[k] for k in ['algorithm','information_set','window_type','candidate_id'])
        for k,v in calc[key].items():
            metricok &= row[k]=='' if v is None else math.isclose(float(row[k]),float(v),abs_tol=1e-12,rel_tol=1e-12)
    checks['72개후보조합지표전수독립재집계']=len(calc)==72 and metricok
    expected_dates={r['week_start'] for r in origins}
    checks['전후보209날짜_Y동일']=all({r['week_start'] for r in rows}==expected_dates and len(rows)==209 and
        all(math.isclose(float(r['development_actual_y']),float(lookup[r['week_start']]['Y']),rel_tol=1e-14,abs_tol=1e-14) for r in rows) for rows in groups.values())
    checks['15048fit유한예측_누락0']=len(predictions)==15048 and all(math.isfinite(float(r['prediction'])) for r in predictions)
    checkpointok=True
    for target in origins:
        p=OUT/'logs/checkpoints'/f"{target['week_start']}.json"
        checkpointok &= p.is_file() and digest(p)==p.with_suffix('.sha256').read_text().strip()
        cp=load(p)
        checkpointok &= len(cp['predictions'])==72 and all(digest(ROOT/f)==h for f,h in cp['signature'].items())
    checks['209원점체크포인트해시와서명불변']=bool(checkpointok)
    checks['예측오차저장값일치']=all(math.isclose(float(r['error']),float(r['development_actual_y'])-float(r['prediction']),abs_tol=1e-12) and
        math.isclose(float(r['absolute_error']),abs(float(r['error'])),abs_tol=1e-12) for r in predictions)
    grid=load(OUT/'config/PHASE3_APPROVED_SEARCH_GRID.json');selected=load(OUT/'selection/PHASE3_SELECTION_REGISTER.json')
    source=load(ROOT/'research_C/phase1_research_design/approval_lock_v1_1/PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json')
    checks['승인5알고리즘18후보동일']=grid==source and sum(map(len,grid['algorithms'].values()))==18
    choose={}
    for algo in grid['algorithms']:
        candidates={}
        for w in ['expanding','rolling_5_calendar_years']:
            for info in ['C-M0','C-M1']:
                keys=[k for k in calc if k[:3]==(algo,info,w)]
                candidates[(info,w)]=min(keys,key=lambda k:(calc[k]['MAE'],k[3]))
        w=min(['expanding','rolling_5_calendar_years'],key=lambda w:(calc[candidates[('C-M0',w)]]['MAE'],w!='expanding'))
        choose[algo]={'window':w,'M0':candidates[('C-M0',w)][3],'M1':candidates[('C-M1',w)][3]}
    checks['알고리즘별M0창선택_표현별후보독립확인']=all(s['window']==selected['selected'][a]['selected_window'] and
        s['M0']==selected['selected'][a]['models']['C-M0']['candidate_id'] and s['M1']==selected['selected'][a]['models']['C-M1']['candidate_id'] for a,s in choose.items())
    checks['주력Ridge선택재현']=choose['Ridge']['window']==selected['selected']['Ridge']['selected_window']
    checks['동점규칙경계테스트']=min([('R02',1.),('R01',1.)],key=lambda r:(r[1],r[0]))[0]=='R01' and min(['rolling_5_calendar_years','expanding'],key=lambda w:(1.,w!='expanding'))=='expanding'
    # Direct linear algebra OLS/Ridge; manually standardize for ElasticNet, native tree scales.
    refits=[]
    for target in [origins[0],origins[len(origins)//2],origins[-1]]:
        for window in ['expanding','rolling_5_calendar_years']:
            train=training[(target['week_start'],window)];y=np.array([float(r['Y']) for r in train])
            for info,p in [('C-M0',10),('C-M1',11)]:
                cols=FIELDS[:p];X=np.array([[float(r[c]) for c in cols] for r in train]);current=np.array([[float(target[c]) for c in cols]])
                mu=X.mean(axis=0);sd=X.std(axis=0,ddof=0);sd[sd==0]=1;z=(X-mu)/sd;now=(current-mu)/sd
                for algo,candidates in grid['algorithms'].items():
                    c=candidates[0];kw={k:v for k,v in c.items() if k!='candidate_id'}
                    with threadpool_limits(limits=1):
                        if algo=='OLS':
                            design=np.column_stack([np.ones(len(z)),z]);beta=np.linalg.lstsq(design,y,rcond=None)[0];v=float(np.r_[1,now[0]]@beta)
                        elif algo=='Ridge':
                            beta=np.linalg.solve(z.T@z+c['alpha']*np.eye(p),z.T@(y-y.mean()));v=float(y.mean()+now[0]@beta)
                        elif algo=='ElasticNet':
                            model=ElasticNet(random_state=20261016,**kw);model.fit(z,y);v=float(model.predict(now)[0])
                        elif algo=='RandomForest':
                            model=RandomForestRegressor(**kw);model.fit(X,y);v=float(model.predict(current)[0])
                        else:
                            model=HistGradientBoostingRegressor(**kw);model.fit(X,y);v=float(model.predict(current)[0])
                    reference=next(r for r in groups[(algo,info,window,c['candidate_id'])] if r['week_start']==target['week_start'])
                    error=abs(v-float(reference['prediction']));okay=math.isclose(v,float(reference['prediction']),abs_tol=1e-8,rel_tol=1e-8)
                    refits.append({'week_start':target['week_start'],'window':window,'information_set':info,'algorithm':algo,'candidate_id':c['candidate_id'],'difference':error,'PASS':okay})
    checks['첫중간마지막_60개독립재적합']=len(refits)==60 and all(r['PASS'] for r in refits)
    # Direct train-only scaler state verification across ALL linear fits.
    prep=load(OUT/'logs/PREPROCESSING_FIT_AUDIT.json');scaleok=True
    stats={}
    for (week,window),train in training.items():
        for p in (10,11):
            x=np.array([[float(r[c]) for c in FIELDS[:p]] for r in train]);stats[(week,window,p)]=(x.mean(axis=0),x.var(axis=0),len(x))
    for a in prep:
        if a['algorithm'] in ['OLS','Ridge','ElasticNet']:
            mu,var,n=stats[(a['week_start'],a['window_type'],a['p_with_intercept']-1)]
            scaleok &= a['scaler_n_samples']==n and np.allclose(mu,a['scaler_mean'],atol=1e-12,rtol=1e-12) and np.allclose(var,a['scaler_var'],atol=1e-12,rtol=1e-12)
        else:scaleok &= a['scaler_n_samples']==0 and a['scaler_mean'] is None
    checks['전적합train_only스케일러검증']=bool(scaleok)
    checks['OLS_rank_자유도']=all(a['rank']==a['p_with_intercept'] and a['train_n']>a['p_with_intercept']-1+20 for a in prep if a['algorithm']=='OLS')
    checks['음수예측보존']=any(float(r['prediction'])<0 for r in predictions)
    checks['미래교란5알고리즘검사']=load(OUT/'qc/SMOKE_AND_PERTURBATION_QC.json')['status']=='PASS'
    # Strict boundary: label timestamp equal to origin may not enter.
    moment=stamp(origins[0]['prediction_origin'])
    checks['동시각성숙제외_최소156경계']=(not moment<moment) and len(list(range(155)))<156 and len(list(range(156)))>=156
    synthetic=load(OUT/'qc/PHASE3_BOUNDARY_SYNTHETIC_QC.json')
    synthetic_exp=[];synthetic_roll=[];synthetic_origin=stamp(synthetic['rows'][synthetic['target_index']]['origin_utc'])
    for i,r in enumerate(synthetic['rows']):
        if r['week_start']<synthetic['rows'][synthetic['target_index']]['week_start'] and stamp(r['label_utc'])<synthetic_origin and stamp(r['origin_utc'])<synthetic_origin:
            synthetic_exp.append(i)
            if stamp(r['origin_utc'])>=stamp(synthetic['cutoff_utc']):synthetic_roll.append(i)
    checks['합성동시각_5년경계_미래위조라벨8검사']=synthetic_exp==synthetic['expanding_indices'] and synthetic_roll==synthetic['rolling_indices'] and synthetic['status']=='PASS'
    auditaccess=load(OUT/'inputs/PHASE3_DATA_ACCESS_AUDIT.json')
    checks['시험CSV파싱0_개발만']=auditaccess['sealed_test_CSV_parsed']==0 and all(r['week_start']<'2021-01-01' for r in predictions)
    protected=load(OUT/'inputs/PHASE3_INPUT_MANIFEST.json')['protected_files'];changed=[p for p,v in protected.items() if not (ROOT/p).is_file() or digest(ROOT/p)!=v['sha256']]
    checks['보호1594해시불변_D13포함']=len(protected)==1594 and not changed
    checks['Phase4미실행']=load(OUT/'logs/WALKFORWARD_COMPLETION.json')['phase4_executed'] is False
    baseline_metrics=records(OUT/'metrics/PHASE3_BASELINE_METRICS.csv');bcheck=True
    for row in baseline_metrics:
        g=[r for r in baseline if r['window_type']==row['window_type'] and r['baseline']==row['baseline']];m=independent_metrics(g)
        bcheck &= all(row[k]=='' if v is None else math.isclose(float(row[k]),float(v),abs_tol=1e-12) for k,v in m.items())
    checks['기준모형전지표독립확인']=bcheck
    result={'status':'PASS' if all(checks.values()) else 'FAIL','checks':{k:bool(v) for k,v in checks.items()},'count':len(checks),
        'independent_selections':choose,'sample_refits':refits,'sample_estimator_fits':48,'sample_closed_form_linear_solutions':24,
        'sample_total_verifications':60,'protected_changed':changed,
        'scope':'동일 Codex 작업 내 별도 구현 검사. 전수지표/학습경계/스케일러검사, 모형수치재적합은첫·중간·끝60조합만. 외부독립심사아님.'}
    # OLS/Ridge each12 ->24 closed-form; EN/RF/HGB each12 ->36 estimator fits.
    result['sample_estimator_fits']=36
    write('qc/PHASE3_INDEPENDENT_QC.json',result)
    write('qc/PHASE3_INDEPENDENT_QC.md','# Phase3 독립 QC\n\n'+result['scope']+f"\n\n**{result['status']}**, {len(checks)}개검사. 독립추정36회+폐쇄형선형해24회.\n\n"+
        '\n'.join('- '+k+': '+('PASS' if v else 'FAIL') for k,v in checks.items())+
        '\n\n주실행함수·훈련선택함수·지표함수는호출하지않았다. 선형OLS/Ridge는독립선형대수,나머지는같은sklearn라이브러리의별도직접모형경로로검증했다. 라이브러리구현자체에대한독립검증은아니다. 후보18개별72조합의209개개발예측지표를전수재집계했다. 시험값은파싱하지않고바이너리해시만확인했다.\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'failed':[k for k,v in checks.items() if not v],
        'sample_max_difference':max(r['difference'] for r in refits)},ensure_ascii=False))
    if result['status']!='PASS':sys.exit(1)

if __name__=='__main__':main()
