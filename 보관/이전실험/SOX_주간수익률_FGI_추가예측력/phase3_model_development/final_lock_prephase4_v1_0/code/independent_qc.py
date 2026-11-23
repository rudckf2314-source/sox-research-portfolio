"""별도 NumPy 집계와 표준 datetime 달력 구현으로 감사. 모델 적합 없음."""
import csv,json,math,hashlib,sys,calendar
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import numpy as np
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2];DEV=OUT.parent/'development_v1_0'
BUILD=ROOT/'research_C/phase2_weekly_dataset/build_v1_1';NY=ZoneInfo('America/New_York');UTC=timezone.utc
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):
    assert 'sealed_test' not in p.parts
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def stamp(x):
    v=datetime.fromisoformat(x);assert v.tzinfo is not None;return v.astimezone(UTC)
def cutoff(o):
    x=o.astimezone(NY);yr=x.year-5;day=min(x.day,calendar.monthrange(yr,x.month)[1])
    return x.replace(year=yr,day=day).astimezone(UTC)
def write(rel,obj):
    with (OUT/rel).open('x',encoding='utf-8') as f:f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
    if '--sealed-check' in sys.argv:
        m=load(OUT/'qc/OUTPUT_MANIFEST.json')
        assert sha(OUT/'qc/OUTPUT_MANIFEST.json')==(OUT/'qc/OUTPUT_MANIFEST.sha256').read_text().split()[0]
        assert all(sha(OUT/x['path'])==x['sha256'] for x in m['files'])
        assert {x['path'] for x in m['files']}|set(m['excludes'])=={x.relative_to(OUT).as_posix() for x in OUT.rglob('*') if x.is_file()}
        p=load(OUT/'lock/PHASE3_FINAL_LOCK_v1_0.json');g=load(OUT/'audit/PHASE4_READY_GATE.json')
        assert p['status']=='LOCKED_v1_0' and g['PHASE4_PRETEST_AUDIT']=='PASS' and g['PHASE4_EXECUTION']=='NOT_AUTHORIZED'
        assert g['PHASE4_TEST_PERFORMANCE']=='SEALED'
        assert p['selected_algorithms']==load(DEV/'selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.json')['selected_algorithms']
        before=load(OUT/'qc/INPUT_MANIFEST.json')['protected_files']
        assert all(sha(ROOT/r)==v['sha256'] for r,v in before.items())
        print({'final_seal':'PASS','hashed_outputs':len(m['files']),'protected':len(before),'test_Y_parsed':0});return
    checks={};main=load(OUT/'lock/PHASE3_SELECTION_VERIFICATION.json')
    source=ROOT/'research_C/phase1_research_design/approval_lock_v1_1'
    grid=load(source/'PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json')
    predictions=read(DEV/'predictions/PHASE3_ALL_CANDIDATE_PREDICTIONS.csv')
    groups={}
    for r in predictions:
        k=tuple(r[f] for f in ['algorithm','information_set','window_type','candidate_id']);groups.setdefault(k,[]).append(r)
    scores={k:float(np.mean(np.abs(np.array([float(r['development_actual_y']) for r in rows])-np.array([float(r['prediction']) for r in rows])))) for k,rows in groups.items()}
    reported={(r['algorithm'],r['information_set'],r['window'],r['candidate_id']):r['MAE'] for r in main['all72_MAE']}
    checks['전체72MAE독립집계']=set(scores)==set(reported) and all(math.isclose(scores[k],reported[k],abs_tol=1e-12) for k in scores)
    weeks={r['week_start'] for r in predictions};checks['209원점_15048본실험']=len(weeks)==209 and len(predictions)==15048 and len(groups)==72 and all(len(v)==209 for v in groups.values())
    recalc={}
    for algo in grid['algorithms']:
        best={}
        for info in ['C-M0','C-M1']:
            for win in ['expanding','rolling_5_calendar_years']:
                options=[k for k in scores if k[:3]==(algo,info,win)]
                best[info,win]=sorted(options,key=lambda k:(scores[k],k[3]))[0]
        win=sorted(['expanding','rolling_5_calendar_years'],key=lambda w:(scores[best['C-M0',w]],w!='expanding'))[0]
        recalc[algo]={'window':win,'M0':best['C-M0',win][3],'M1':best['C-M1',win][3]}
    checks['10설정_M0창_정보집합별후보선택일치']=all(v['window']==main['selected'][a]['selected_window'] and v['M0']==main['selected'][a]['models']['C-M0']['candidate_id'] and v['M1']==main['selected'][a]['models']['C-M1']['candidate_id'] for a,v in recalc.items())
    cand=load(DEV/'selection/PHASE3_EXPERIMENT_LOCK_CANDIDATE.json')
    checks['주력Ridge유지']=cand['primary_algorithm']=='Ridge'
    checks['18후보_동등탐색']=sum(map(len,grid['algorithms'].values()))==18 and all(len([k for k in groups if k[:3]==(a,info,w)])==len(cs) for a,cs in grid['algorithms'].items() for info in ['C-M0','C-M1'] for w in ['expanding','rolling_5_calendar_years'])
    checks['고정하이퍼파라미터원본동일']=all(m['hyperparameters']==next(c for c in grid['algorithms'][a] if c['candidate_id']==m['candidate_id']) for a,v in cand['selected_algorithms'].items() for m in v['models'].values())
    data=[r for r in read(BUILD/'data/train_dev/WEEKLY_CORE_COMBINED.csv') if r['paired_common_valid']=='True']
    checks['초기308_개발209_합517']=len(data)==517 and sum(r['split']=='initial_train' for r in data)==308 and sum(r['split']=='development' for r in data)==209
    audits=read(DEV/'predictions/PHASE3_ORIGIN_TRAINING_AUDIT.csv');training={};boundary=True
    for a in audits:
        o=stamp(a['prediction_origin']);rows=[r for r in data if r['week_start']<a['week_start'] and stamp(r['label_assumed_available_at'])<o and stamp(r['prediction_origin'])<o and (a['window_type']=='expanding' or stamp(r['prediction_origin'])>=cutoff(o))]
        training[a['week_start'],a['window_type']]=rows
        boundary &= len(rows)==int(a['train_n']) and len(rows)>=156 and rows[0]['week_start']==a['train_start'] and rows[-1]['week_start']==a['train_end']
        boundary &= hashlib.sha256('\n'.join(r['week_start'] for r in rows).encode()).hexdigest()==a['training_week_list_sha256']
    checks['418개성숙_5달력년_최소156독립확인']=len(training)==418 and boundary
    lineage=read(DEV/'inputs/TRAIN_DEV_FEATURE_AVAILABILITY.csv')
    checks['과거X자체원점이전적격']=len(lineage)==5687 and all(stamp(r['actual_available_at'] if r['actual_available_at'] not in ('null','','None') else r['latest_assumed_available_at'])<stamp(r['prediction_origin']) for r in lineage)
    pre=load(DEV/'logs/PREPROCESSING_FIT_AUDIT.json');stats={};scale=True
    cols=[f'B{i}' for i in range(1,11)]+['F1']
    for key,rows in training.items():
        for p in (10,11):
            X=np.array([[float(r[c]) for c in cols[:p]] for r in rows]);stats[*key,p]=(X.mean(0),X.var(0),len(X))
    for p in pre:
        if p['algorithm'] in ['OLS','Ridge','ElasticNet']:
            mu,var,n=stats[p['week_start'],p['window_type'],p['p_with_intercept']-1]
            scale &= p['scaler_n_samples']==n and np.allclose(mu,p['scaler_mean'],atol=1e-12,rtol=1e-12) and np.allclose(var,p['scaler_var'],atol=1e-12,rtol=1e-12)
        else:scale &= p['scaler_n_samples']==0
    checks['학습구간전용전처리전수확인']=bool(scale)
    syn=load(OUT/'qc/SYNTHETIC_PRETEST_PLANNER_QC.json');synthetic=True
    for c in syn['cases']:
        O=stamp(c['origin']);ids=[]
        if stamp(c['current_x_at'])<O:
            for i,r in enumerate(c['rows']):
                if r['week_start']>=c['week_start'] or stamp(r['origin'])>=O or stamp(r['label_at'])>=O or stamp(r['x_at'])>=stamp(r['origin']):continue
                if c['window']!='expanding' and stamp(r['origin'])<cutoff(O):continue
                ids.append(i)
            expected='ELIGIBLE' if len(ids)>=156 else 'NOT_PREDICTED_INSUFFICIENT_TRAINING'
        else:expected='NOT_ELIGIBLE_CURRENT_X'
        synthetic &= ids==c['result']['indices'] and c['result']['status']==expected
    checks['합성13사례_22경계검사독립재현']=synthetic and syn['status']=='PASS' and syn['count']==22
    protected=load(OUT/'qc/INPUT_MANIFEST.json')['protected_files'];changed=[r for r,v in protected.items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    checks['보호2059파일SHA불변']=len(protected)==2059 and not changed
    checks['개발입력SHA동일']=sha(BUILD/'data/train_dev/WEEKLY_CORE_COMBINED.csv')==cand['dataset']['sha256']
    d13=ROOT/'research_C/phase2_weekly_dataset/d13_bootstrap_policy_v1_0/approval_lock_v1_0'
    checks['D13_LOCK불변_통계설정일치']=sha(d13/'D13_LOCKED_POLICY_v1_0.json')==cand['future_phase4']['D13_lock_sha256'] and load(d13/'D13_GATE_STATUS.json')['D13_LOCK_STATUS']=='LOCKED_v1_0'
    checks['D10구현PASS불변']=load(BUILD/'qc/PHASE2B_D10_GATE_RESULT.json')['D10_GATE']=='IMPLEMENTATION_PASS'
    seal=load(OUT/'audit/PHASE4_DATA_SEAL_AUDIT.json')
    checks['시험3CSV바이너리해시만확인']=seal['files']==3 and not seal['Y_content_decoded_or_parsed'] and all(sha(ROOT/f['path'])==f['sha256'] for f in seal['sealed_files'])
    checks['개발데이터시험Y불포함']=all(r['week_start']<'2021-01-01' for r in data+predictions)
    checks['후보실패_미예측0']=load(DEV/'metrics/PHASE3_FAILURE_COUNTS.json')['candidate_estimator_fit_failures']==0 and len(predictions)==209*18*2*2
    checks['시험실행_성과_추론미실행']=syn['model_fits']==0 and syn['predictions']==0 and not load(DEV/'logs/WALKFORWARD_COMPLETION.json')['phase4_executed']
    checks['Phase5미실행']=not (OUT/'predictions').exists()
    result={'status':'PASS' if all(checks.values()) else 'BLOCKED_REVIEW_REQUIRED','checks':{k:bool(v) for k,v in checks.items()},'count':len(checks),
        'selection_recalculated':recalc,'protected_changed':changed,'new_estimator_fits':0,'actual_test_inference':0,
        'scope':'동일 Codex 작업 내 별도 구현 감사. 외부 독립심사 아님. 개발 지표·경계·스케일러 전수 재계산, 실제 모델 재적합 없음.'}
    write('qc/PHASE3_FINAL_LOCK_INDEPENDENT_QC.json',result)
    write('qc/PHASE3_FINAL_LOCK_INDEPENDENT_QC.md','# 최종 LOCK·시험 직전 독립 QC\n\n'+result['scope']+'\n\n**'+result['status']+f"**, {len(checks)}개 검사.\n\n"+
        '\n'.join('- '+k+': '+('PASS' if v else 'FAIL') for k,v in checks.items())+
        '\n\n주 감사의 fsum 집계와 별도로 NumPy 벡터 절대오차 평균을 계산하고 선택을 다시 수행했다. 주 계획함수는 호출하지 않고 표준 datetime/calendar로 5달력년 경계(윤년포함)를 계산했다. 시험 파일은 바이너리 해시만 검사했다. 저장 코드/로그를 통한 접근감사 한계를 보고서에 남긴다.\n')
    print({'independent_QC':result['status'],'checks':len(checks),'failed':[k for k,v in checks.items() if not v]})
    if result['status']!='PASS':sys.exit(1)

if __name__=='__main__':main()
