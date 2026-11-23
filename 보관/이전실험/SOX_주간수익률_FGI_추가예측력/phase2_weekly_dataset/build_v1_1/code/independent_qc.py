"""생성기/공통/D10 모듈을 가져오지 않는 별도 독립 재계산. 시험 값은 출력하지 않는다."""
import ast,bisect,csv,hashlib,json,math,statistics,sys
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2]
NY=ZoneInfo('America/New_York')
X=[f'B{i}' for i in range(1,11)]+['F1']

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(line for line in f if not line.startswith('#')))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(131072),b''):h.update(b)
    return h.hexdigest()
def num(x):
    try:
        f=float(x);return f if math.isfinite(f) else None
    except (ValueError,TypeError):return None
def mon(d):return d-timedelta(days=d.weekday())
def et(ds,h=9):return datetime.combine(date.fromisoformat(str(ds)),datetime.min.time()).replace(hour=h,tzinfo=NY)
def same(a,b):return a is None and b is None or a is not None and b is not None and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-9)

def main():
    checks=[]
    def check(name,ok,detail):checks.append({'name':name,'pass':bool(ok),'detail':detail})
    manifest=load(OUT/'qc/PHASE2B_INPUT_MANIFEST.json')
    bad=[rel for rel,v in manifest['protected_files'].items() if not (ROOT/rel).is_file() or sha(ROOT/rel)!=v['sha256']]
    check('원천·승인·기존 결과 SHA256',not bad,{'protected':len(manifest['protected_files']),'changed':bad})
    old=load(OUT.parent/'build_v1_0/inputs/RAW_VERSION_AUDIT.json')
    raw={r['dataset_id'].split('_')[0]:{x['Date']:x for x in rows(ROOT/r['path'])} for r in old['core_hashes']}
    check('RAW47종48파일 재대조',all(sha(ROOT/r['path'])==r['sha256'] for r in old['inventory'])
          and len(old['inventory'])==48,'일별 원천 수치·예측성과를 출력하지 않고 해시/구조만 확인')
    schedule=rows(OUT/'calendar/US_MARKET_SESSIONS.csv');ss=[r['session_date'] for r in schedule]
    assert ss==sorted(set(ss))
    weekmap=defaultdict(list)
    for ds in ss:weekmap[mon(date.fromisoformat(ds))].append(ds)
    check('거래일·SOX 날짜 대조',{d for d in ss if '2011-01-01'<=d<='2026-10-09'}==set(raw['02']),
          '공식 규칙으로 만든3966세션과 원천 Date 집합 대조; SOX만으로 거래소 검증했다는 의미 아님')
    check('특별휴장·조기마감',all(d not in ss for d in ['2012-10-29','2012-10-30','2018-12-05','2025-01-09'])
          and any(r['session_date']=='2014-07-03' and datetime.fromisoformat(r['market_close_at']).hour==13 for r in schedule),
          '확보한 거래소 개별 공지와 교차확인')
    board=rows(OUT/'calendar/BOARD_H15_PUBLICATION_CALENDAR.csv')
    decisions=rows(OUT/'calendar/D10_E3_DATEWISE_DECISIONS.csv')
    original_grid=rows(OUT.parent/'calendar_evidence_remediation_v1_0/audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv')
    original_by={r['calendar_date']:r for r in original_grid}
    approved=set(load(OUT.parent/'calendar_evidence_remediation_v1_0/approval_E3_v1_0/D10_E3_APPROVED_POLICY.json')['E3']['candidate_dates'])
    incidents={'2011-03-11','2014-01-15','2018-09-18','2020-08-19','2023-08-02','2023-09-13'}
    for ev in rows(OUT.parent/'calendar_evidence_remediation_v1_0/audit/H15_EXCEPTION_AND_DELAY_REGISTER.csv'):
        if ev['category'] in {'CLOSURE_OR_POSTPONEMENT','OFFICIAL_CLOSURE_H15_POSTPONED'}:incidents.update(d for d in ev['affected_dates'].split(';') if d!='null')
    opm={r['holiday_date'] for r in rows(OUT.parent/'calendar_evidence_remediation_v1_0/audit/US_FEDERAL_HOLIDAYS_OPM_REFERENCE.csv') if r['weekday_label_conflict']=='False'}
    errors=[]
    for d in decisions:
        ds=d['calendar_date'];r=original_by[ds]
        expected=[date.fromisoformat(ds).weekday()<5,date.fromisoformat(ds).weekday()<5 and ds not in opm,
            ds not in opm and not r['special_closure_status'].startswith('OFFICIAL_CLOSURE_H15_POSTPONED'),
            ds not in incidents and r['known_delay_status']=='NO_DATE_SPECIFIC_TIMING_CONFIRMED',True,True,True]
        if any((d[f'condition_{i+1}']=='SATISFIED')!=e for i,e in enumerate(expected)) or (d['decision']=='CONDITIONALLY_ALLOWED')!=all(expected):errors.append(ds)
    check('E3 637일 7조건 별도 재판정',len(decisions)==637 and {r['calendar_date'] for r in decisions}==approved and not errors,
          {'mismatched_dates':errors,'allowed':sum(r['decision']=='CONDITIONALLY_ALLOWED' for r in decisions),'excluded':sum(r['decision']=='EXCLUDED' for r in decisions)})
    check('원본 등급 불변·E4이벤트 차단',all(original_by[r['calendar_date']]['evidence_grade']==r['evidence_grade'] for r in board)
          and all(r['publication_candidate_eligible']=='False' for r in board if r['evidence_grade']=='E4'),
          '사후 등급 승격·충돌 날짜 이동 없음')
    avail=rows(OUT/'availability/D10_OBSERVATION_AVAILABILITY.csv')
    corrections={'2011-03-10','2014-01-14','2017-04-14','2018-09-17','2020-08-19','2023-08-01','2023-09-12'}
    expected_av={};mapping_errors=[]
    for ds,r in raw['15'].items():
        value=num(r['DGS10']);a=None;rd='';reason=''
        if value is not None and ds not in corrections:
            for c in board:
                day=c['calendar_date']
                if day<=ds or date.fromisoformat(day).weekday()>=5:continue
                if c['evidence_grade']=='E4' or c['calendar_status']=='E3_CONDITION_FAILED':rd=day;break
                if c['calendar_status']=='NONPUBLICATION_OR_UNAPPROVED_E3' and c['federal_holiday_reference']!='True':rd=day;break
                if c['publication_candidate_eligible']=='True':rd=day;a=et(date.fromisoformat(day)+timedelta(days=1),8);break
        expected_av[ds]=(a,rd,value)
    for r in avail:
        a,rd,_=expected_av[r['observation_date']]
        actual=datetime.fromisoformat(r['assumed_available_at']) if r['assumed_available_at'] else None
        if a!=actual or (a is not None and rd!=r['release_calendar_date']):mapping_errors.append(r['observation_date'])
    check('D10 각 관측 가정시각 독립 재계산',not mapping_errors,{'mismatched_dates':mapping_errors,'observations':len(avail)})
    check('actual/assumed·UNVERIFIED 보존',all(r['actual_release_at']==r['actual_available_at']=='null'
          and r['publication_status']==r['vintage_status']=='UNVERIFIED' for r in avail),'최초 빈티지·실제 게시시각 입증으로 승격하지 않음')
    byavail={r['observation_date']:r for r in avail}
    check('D10 금요일·목요일·휴일·DST 경계',expected_av['2024-02-02'][0]>et('2024-02-05')
          and expected_av['2024-02-01'][0]<et('2024-02-05') and expected_av['2024-10-11'][1]=='2024-10-15'
          and expected_av['2026-07-02'][1]=='2026-07-06' and et('2024-01-08').astimezone(timezone.utc).hour==14
          and et('2024-07-08').astimezone(timezone.utc).hour==13,'달력 규칙의 개별 경계 및 DST')
    def rate(week,origin,noe3=False):
        found=[]
        for ds,(a,rd,value) in expected_av.items():
            if week.isoformat()<=ds<(week+timedelta(days=7)).isoformat() and a is not None and a<origin:
                if not noe3 or byavail[ds]['release_evidence_grade']!='E3':found.append((ds,value))
        return max(found) if found else None
    def eod(ds):
        pos=bisect.bisect_right(ss,ds)
        return et(ss[pos],8) if pos<len(ss) else None
    def v(key,ds,col):return num(raw[key].get(ds,{}).get(col))
    def price(key,w,col):
        ds=weekmap.get(w,[])
        if not ds or any(v(key,d,col) is None for d in ds):return None
        return v(key,ds[-1],col)
    # 독립 RSI는 이득/손실 배열 구간을 먼저 구성한 후 recurrence를 별도로 수행한다.
    rsivals={};streak=[]
    for ds in ss:
        p=v('02',ds,'Close')
        if p is None:streak=[];continue
        streak.append((ds,p))
        if len(streak)<15:rsivals[ds]=None
        elif len(streak)==15:
            diffs=[streak[j][1]-streak[j-1][1] for j in range(1,15)]
            ag=statistics.mean(max(d,0) for d in diffs);al=statistics.mean(max(-d,0) for d in diffs)
            rsivals[ds]=50.0 if ag==al==0 else 100.0 if al==0 else 100-100/(1+ag/al)
        else:
            delta=streak[-1][1]-streak[-2][1];ag=ag*(13/14)+max(delta,0)/14;al=al*(13/14)+max(-delta,0)/14
            rsivals[ds]=50.0 if ag==al==0 else 100.0 if al==0 else 100-100/(1+ag/al)
    td=rows(OUT/'data/train_dev/WEEKLY_CORE_COMBINED.csv')
    test=rows(OUT/'data/sealed_test/WEEKLY_CORE_TEST.csv')
    allrows=td+test
    all_target=rows(OUT/'data/train_dev/SOX_WEEKLY_Y.csv')+rows(OUT/'data/sealed_test/SOX_WEEKLY_Y_TEST.csv')
    all_features=rows(OUT/'data/train_dev/WEEKLY_FEATURES_B10_F1.csv')+rows(OUT/'data/sealed_test/WEEKLY_FEATURES_TEST.csv')
    check('기간분리·날짜유일·공통 행',len(allrows)==823 and len({r['week_start'] for r in allrows})==823
          and all(r['week_start']<'2021-01-01' for r in td) and all(r['week_start']>='2021-01-01' for r in test)
          and [r['week_start'] for r in allrows]==[r['week_start'] for r in all_target]==[r['week_start'] for r in all_features],
          {'train_dev_weeks':len(td),'sealed_test_weeks':len(test)})
    check('라벨 종료일·원천 인접주·성숙시점',all(r['label_end_date']==weekmap[date.fromisoformat(r['week_start'])][-1]
          and r['target_price_date']==weekmap[date.fromisoformat(r['week_start'])][-1]
          and datetime.fromisoformat(r['label_assumed_available_at'])==eod(r['label_end_date'])
          and (not r['base_price_date'] or mon(date.fromisoformat(r['base_price_date']))==date.fromisoformat(r['week_start'])-timedelta(weeks=1))
          for r in all_target),'실제 미국 세션·인접 달력 주. 다른 주 건너뛰기 없음')
    check('FGI 80퍼센트 임계값 경계',math.ceil(.8*5)==4 and 3<math.ceil(.8*5)
          and math.ceil(.8*3)==3 and math.ceil(.8*1)==1,
          '합성 유효개수 경계 검사. 결손을 제거해 기대 세션 분모를 줄이지 않음')
    formula_errors=[];validcounter=Counter();pair=Counter();ycount=0;noe3b10=0;noe3pair=0
    fgicol='Fear Greed'
    for r in allrows:
        w=date.fromisoformat(r['week_start']);o=datetime.fromisoformat(r['prediction_origin'])
        check_origin=et(weekmap[w][0]);assert o==check_origin
        p=price('02',w,'Close');q=price('02',w-timedelta(weeks=1),'Close')
        y=None if p is None or q in {None,0} else 100*(p/q-1)
        if not same(y,num(r['Y'])):formula_errors.append((r['week_start'],'Y'))
        expected={}
        for k,key,col,lag in [('B1','02','Close',2),('B2','02','Close',5),('B5','04','Close',2),('B6','12','Close',2),('B9','10','Adj Close',2)]:
            a=price(key,w-timedelta(weeks=1),col);b=price(key,w-timedelta(weeks=lag),col)
            expected[k]=None if a is None or b in {None,0} else 100*(a/b-1)
        prior=weekmap[w-timedelta(weeks=1)]
        rr=[]
        for ds in prior:
            idx=bisect.bisect_left(ss,ds);old=ss[idx-1] if idx else ''
            a=v('02',ds,'Close');b=v('02',old,'Close')
            if a is not None and b not in {None,0}:rr.append(100*(a/b-1))
        expected['B3']=statistics.stdev(rr) if len(rr)==len(prior) and len(rr)>=2 else None
        expected['B4']=rsivals.get(prior[-1]) if prior else None
        vx=[]
        for lag in [1,2]:
            xx=[(d,v('08',d,'VIXCLS')) for d in weekmap[w-timedelta(weeks=lag)] if v('08',d,'VIXCLS') is not None and eod(d)<o]
            vx.append(xx[-1][1] if xx else None)
        expected['B7']=vx[0];expected['B8']=vx[0]-vx[1] if all(x is not None for x in vx) else None
        rates=[rate(w-timedelta(weeks=k),o) for k in [1,2]]
        expected['B10']=100*(rates[0][1]-rates[1][1]) if all(rates) else None
        no_rates=[rate(w-timedelta(weeks=k),o,True) for k in [1,2]]
        fv=[v('11',d,fgicol) for d in prior if v('11',d,fgicol) is not None and 0<=v('11',d,fgicol)<=100 and eod(d)<o]
        expected['F1']=statistics.mean(fv) if prior and len(fv)>=math.ceil(.8*len(prior)) else None
        for k in X:
            if expected[k] is not None:validcounter[k]+=1
            if not same(expected[k],num(r[k])):formula_errors.append((r['week_start'],k))
        common=all(expected[k] is not None for k in X) and y is not None
        if common:pair[r['split']]+=1
        if y is not None:ycount+=1
        if all(no_rates):noe3b10+=1
        if common and all(no_rates):noe3pair+=1
        if common!=(r['paired_common_valid']=='True'):formula_errors.append((r['week_start'],'paired_flag'))
    check('주간 Y·B1~B10·F1 전수 독립 재계산',not formula_errors,
          {'checked_weeks':len(allrows),'mismatch_count':len(formula_errors),'mismatch_dates_and_variables':formula_errors[:25],
           'note':'시험 Y 숫자·분포·상관은 기록/출력하지 않음'})
    counts=load(OUT/'data/WEEKLY_SAMPLE_COUNTS.json')
    check('유효주수·공통표본·E3 대안 가용성',dict(validcounter)==counts['feature_valid'] and ycount==counts['Y_valid']
          and sum(pair.values())==counts['paired_common_valid'] and noe3b10==counts['B10_valid_without_E3']
          and noe3pair==counts['paired_without_E3_valid'] and all(pair[k]==counts['splits'][k]['paired_common_valid'] for k in pair),
          {'Y_valid_count_only':ycount,'paired_counts_only':dict(pair),'B10_without_E3':noe3b10,'paired_without_E3':noe3pair})
    logs=rows(OUT/'availability/FEATURE_AVAILABILITY_LOG.csv')
    leak=[]
    for r in logs:
        o=datetime.fromisoformat(r['prediction_origin'])
        if r['valid']=='True' and (not r['latest_assumed_available_at'] or datetime.fromisoformat(r['latest_assumed_available_at'])>=o):leak.append((r['week_start'],r['feature_id']))
        if any(d>=o.date().isoformat() for d in json.loads(r['source_dates'])):leak.append((r['week_start'],r['feature_id'],'future_date'))
    check('전체 X 원점이전·미래 원천일 0',not leak,{'violations':leak[:20],'lineage_rows':len(logs)})
    # 원점 이후 자료 변조를 독립 선택기에서 다시 수행. 시점 선택 검증이며 빈티지 검증 아님.
    o=et('2024-02-05');w=date(2024,1,29)
    base=rate(w,o)
    saved=dict(expected_av)
    expected_av['2024-02-02']=(et('2024-02-06',8),'2024-02-05',999999)
    expected_av['2024-01-31']=(et('2030-01-01',8),'2029-12-31',999999)
    future=rate(w,o);expected_av.clear();expected_av.update(saved)
    check('독립 미래자료 교란 테스트',base==future and base is not None,'원점 이후 이용 가능 데이터 수정에도 과거 적격 선택 불변')
    check('동시각 배제·정정 보류',not et('2024-02-05')<et('2024-02-05')
          and all(expected_av[d][0] is None for d in corrections),'엄격 <; 알려진 해당 관측만 보류')
    check('시험 Y 저장 격리',all(not any(k in rr for k in ['Y','target_Close','base_Close']) for rr in rows(OUT/'data/WEEKLY_MISSINGNESS_AUDIT.csv'))
          and all('Y' not in rr for path in (OUT/'data').glob('*.csv') for rr in rows(path)),
          '시험 Y는 sealed_test에만 존재; 공개 집계는 유효/결측 개수. WEEKLY라는 파일명 자체는 Y 노출로 오인하지 않음')
    # 실행 코드 내 모델·통계·PCA API가 없는지 확인. 라이브러리 vendor는 제외.
    forbidden={'fit','fit_transform','predict','corr','corrcoef','mean_squared_error','r2_score','mean_absolute_error'}
    forbidden_calls=[]
    for p in (OUT/'code').glob('*.py'):
        for node in ast.walk(ast.parse(p.read_text(encoding='utf-8-sig'))):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in forbidden:forbidden_calls.append(p.name+':'+node.func.attr)
    check('모델·시험 성능·D13 결정 미실행',not forbidden_calls,{'forbidden_calls':forbidden_calls,'D13':'PENDING_WEEKLY_MISSINGNESS_REVIEW'})
    result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks,'count':len(checks),
        'independence':'동일 Codex 작업 안의 별도 구현. 생성기·공통·D10 계산 모듈 미사용. 외부 독립심사 아님.',
        'sealed_test_Y_values_printed':False,'performance_computed':False}
    if '--check-only' not in sys.argv:
        with (OUT/'qc/PHASE2B_INDEPENDENT_QC.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
        text=['# 연구 C Phase2-B v1.1 독립 QC','',result['independence'],'',f"판정: **{result['status']}**, {len(checks)}개 검사.",'',
            '|검사|결과|근거|','|---|---|---|']
        for r in checks:text.append('|'+r['name']+'|'+('PASS' if r['pass'] else 'FAIL')+'|'+str(r['detail']).replace('|','/')+'|')
        with (OUT/'qc/PHASE2B_INDEPENDENT_QC.md').open('x',encoding='utf-8') as f:f.write('\n'.join(text)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'failures':[{'name':r['name'],'detail':r['detail']} for r in checks if not r['pass']]},ensure_ascii=False))
    if result['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
