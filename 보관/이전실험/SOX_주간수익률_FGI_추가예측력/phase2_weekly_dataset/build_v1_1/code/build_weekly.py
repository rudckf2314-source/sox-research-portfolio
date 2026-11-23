"""D10 사전 게이트 PASS 후에만 비중첩 주간 X/Y 구축. 시험 Y 값 출력 금지."""
import bisect,statistics
from collections import Counter,defaultdict
from common import *
from d10_prebuild import select_week,available_at
X=[f'B{n}' for n in range(1,11)]+['F1']

def main():
    assert load(OUT/'qc/D10_PREBUILD_GATE.json')['status']=='D10_PREBUILD_QC_PASS'
    raw=core();daily={key:{r['Date']:r for r in obj['df']} for key,obj in raw.items()}
    fgicol=load(OUT/'qc/RAW_PREFLIGHT_QC.json')['FGI_column']
    schedule=readcsv(OUT/'calendar/US_MARKET_SESSIONS.csv');session_dates=[r['session_date'] for r in schedule]
    smap={r['session_date']:r for r in schedule}
    byweek=defaultdict(list)
    for ds in session_dates:byweek[monday(date.fromisoformat(ds))].append(ds)
    def eod_available(ds):
        n=bisect.bisect_right(session_dates,ds)
        return stamp(session_dates[n],8) if n<len(session_dates) else None
    def get(key,ds,column):return number(daily[key].get(ds,{}).get(column))
    # 일별 RSI를 실제 세션 순서에서 계산한다. 누락 세션을 건너뛰지 않는다.
    rsi={};rsi_state=[];prev=None;gains=[];losses=[];avg_gain=avg_loss=None;state_start=None;prices_in_state=0
    for ds in session_dates:
        p=get('02',ds,'Close')
        if p is None:
            prev=None;gains=[];losses=[];avg_gain=avg_loss=None;state_start=None;prices_in_state=0;rsi[ds]=None;continue
        if prev is None:prev=p;state_start=ds;prices_in_state=1;rsi[ds]=None;continue
        delta=p-prev;prev=p;prices_in_state+=1;gain=max(delta,0);loss=max(-delta,0)
        if avg_gain is None:
            gains.append(gain);losses.append(loss)
            if len(gains)==14:avg_gain=sum(gains)/14;avg_loss=sum(losses)/14
        else:avg_gain=(13*avg_gain+gain)/14;avg_loss=(13*avg_loss+loss)/14
        value=None if avg_gain is None else 50.0 if avg_gain==avg_loss==0 else 100.0 if avg_loss==0 else 0.0 if avg_gain==0 else 100-100/(1+avg_gain/avg_loss)
        rsi[ds]=value
        rsi_state.append({'source_session_date':ds,'RSI14':value if value is not None else '',
            'state_start_date':state_start,'state_price_count':prices_in_state,'method':'WILDER_SMA14_SEED_RESET_ON_MISSING'})
    csvout('availability/SOX_RSI14_STATE_AUDIT.csv',rsi_state)
    dgs=readcsv(OUT/'availability/D10_OBSERVATION_AVAILABILITY.csv')
    weeks=list(dates(date(2011,1,3),date(2026,10,5)))[::7]
    # 2011은 월요일 week_start 기준. 연말주를 쪼개지 않는다.
    assert all(w.weekday()==0 for w in weeks)
    logs=[];targets=[];features=[];combined=[];missing=[];dgs_selected=[];e4_impact=[]
    def log(w,origin,feature,key,column,deps,value,reason,policy=DAILY,extra=None):
        deps=sorted(set(deps));times=[eod_available(ds) for ds in deps]
        times=[a for a in times if a is not None]
        latest=max(times) if times else None
        logs.append({'week_start':w.isoformat(),'prediction_origin':origin.isoformat(),'feature_id':feature,
            'source_file':str(raw[key]['path'].relative_to(ROOT)),'source_sha256':raw[key]['sha256'],
            'source_column':column,'source_dates':json.dumps(deps),'source_period_complete':not reason,
            'latest_assumed_available_at':latest.isoformat() if latest else '',
            'actual_available_at':'null','actual_release_at':'null','assumption_policy_id':policy,
            'calendar_policy_id':CALPOL if feature=='B10' else '',
            'publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED','valid':value is not None,
            'missing_reason':reason,'detail':json.dumps(extra or {},ensure_ascii=False)})
    def week_price(key,w,column,origin=None):
        ss=byweek.get(w,[])
        if not ss:return None,[],'NO_SESSIONS_IN_SOURCE_WEEK'
        vals=[get(key,ds,column) for ds in ss]
        if any(v is None for v in vals):return None,ss,'MISSING_SESSION_PRICE_OR_NO_WARMUP'
        end=ss[-1]
        if origin is not None and (eod_available(end) is None or eod_available(end)>=origin):return None,ss,'PRICE_NOT_AVAILABLE_AT_ORIGIN'
        return vals[-1],[end],''
    def ratio_feature(key,column,wa,wb,origin,require_intermediate=False):
        pa,da,ra=week_price(key,wa,column,origin);pb,db,rb=week_price(key,wb,column,origin)
        deps=da+db;reason=ra or rb
        if require_intermediate:
            for k in range(1,4):
                _,dd,rr=week_price(key,wa-timedelta(weeks=k),column,origin);deps+=dd;reason=reason or rr
        return (100*(pa/pb-1) if not reason and pb is not None and pb!=0 else None),deps,reason or ('ZERO_PRICE_DENOMINATOR' if pb==0 else '')
    for w in weeks:
        ss=byweek.get(w,[]);origin=stamp(ss[0]) if ss else stamp(w)
        part='initial_train' if w.year<=2016 else 'development' if w.year<=2020 else 'sealed_test'
        row={'week_start':w.isoformat(),'prediction_origin':origin.isoformat(),'split':part,
            'source_version':'RAW_HASH_LOCKED_20261017','transform_version':'research_C_phase2B_build_v1_1',
            'daily_policy_id':DAILY,'D10_timing_policy_id':TIMING,'D10_calendar_policy_id':CALPOL,
            'publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED'}
        # Y 연결은 인접 달력 주만 허용. 내부 세션 누락도 허용하지 않는다.
        py,dy,ry=week_price('02',w,'Close');p0,d0,r0=week_price('02',w-timedelta(weeks=1),'Close')
        y=100*(py/p0-1) if not ry and not r0 and p0 not in {None,0} else None
        label_av=eod_available(dy[-1]) if dy else None
        target={**row,'Y':y if y is not None else '',
            'target_first_session':ss[0] if ss else '', 'target_last_session':ss[-1] if ss else '',
            'base_price_date':d0[-1] if d0 else '', 'target_price_date':dy[-1] if dy else '',
            'base_Close':p0 if p0 is not None else '', 'target_Close':py if py is not None else '',
            'label_end_date':ss[-1] if ss else '', 'label_actual_available_at':'null',
            'label_assumed_available_at':label_av.isoformat() if label_av else '',
            'label_policy_id':'C_LABEL_EOD_NEXT_US_SESSION_0800_ET_v1_1','Y_valid':y is not None,
            'Y_missing_reason':ry or r0,'SOX_source_sha256':raw['02']['sha256']}
        values={};reasons={};sources={}
        configs={'B1':('02','Close',1,2,False),'B2':('02','Close',1,5,True),
            'B5':('04','Close',1,2,False),'B6':('12','Close',1,2,False),'B9':('10','Adj Close',1,2,False)}
        for feature,(key,col,a,b,inter) in configs.items():
            value,deps,reason=ratio_feature(key,col,w-timedelta(weeks=a),w-timedelta(weeks=b),origin,inter)
            values[feature]=value;reasons[feature]=reason;sources[feature]=json.dumps(deps)
            log(w,origin,feature,key,col,deps,value,reason)
        prior=byweek.get(w-timedelta(weeks=1),[]);ret=[];deps=[];reason=''
        for ds in prior:
            pos=bisect.bisect_left(session_dates,ds);prevds=session_dates[pos-1] if pos>0 else None
            p=get('02',ds,'Close');pold=get('02',prevds,'Close') if prevds else None
            deps.extend([ds]+([prevds] if prevds else []))
            if p is None or pold in {None,0}:reason='MISSING_DAILY_RETURN_INPUT'
            elif eod_available(ds)>=origin:reason='RETURN_NOT_AVAILABLE'
            else:ret.append(100*(p/pold-1))
        if len(prior)<2:reason='LESS_THAN_TWO_DAILY_RETURNS'
        values['B3']=statistics.stdev(ret) if not reason and len(ret)==len(prior) else None
        reasons['B3']=reason;sources['B3']=json.dumps(deps)
        log(w,origin,'B3','02','Close',deps,values['B3'],reason,extra={'ddof':1,'annualized':False})
        lastds=prior[-1] if prior else None
        values['B4']=rsi.get(lastds) if lastds and eod_available(lastds)<origin else None
        reason='' if values['B4'] is not None else 'RSI_WARMUP_OR_MISSING_STATE'
        reasons['B4']=reason;sources['B4']=json.dumps([lastds] if lastds else [])
        log(w,origin,'B4','02','Close',[lastds] if lastds else [],values['B4'],reason,extra={'method':'Wilder_SMA14_seed','full_state_file':'availability/SOX_RSI14_STATE_AUDIT.csv','state_uses_prior_sessions_only':True})
        vix=[]
        for lag in [1,2]:
            candidate=[]
            for ds in byweek.get(w-timedelta(weeks=lag),[]):
                v=get('08',ds,'VIXCLS');a=eod_available(ds)
                if v is not None and a is not None and a<origin:candidate.append((ds,v))
            vix.append(candidate[-1] if candidate else None)
        values['B7']=vix[0][1] if vix[0] else None
        values['B8']=vix[0][1]-vix[1][1] if all(vix) else None
        for feature,selected in [('B7',vix[:1]),('B8',vix)]:
            deps=[r[0] for r in selected if r];reason='' if values[feature] is not None else 'NO_ELIGIBLE_VIX_WITHIN_REQUIRED_SOURCE_WEEK'
            reasons[feature]=reason;sources[feature]=json.dumps(deps);log(w,origin,feature,'08','VIXCLS',deps,values[feature],reason)
        rates=[select_week(dgs,w-timedelta(weeks=lag),origin) for lag in [1,2]]
        no_e3=[select_week(dgs,w-timedelta(weeks=lag),origin,False) for lag in [1,2]]
        values['B10']=100*(float(rates[0]['DGS10'])-float(rates[1]['DGS10'])) if all(rates) else None
        reason='' if values['B10'] is not None else 'NO_ELIGIBLE_DGS10_WITHIN_REQUIRED_SOURCE_WEEK'
        deps=[r['observation_date'] for r in rates if r]
        sources['B10']=json.dumps(deps);reasons['B10']=reason
        log(w,origin,'B10','15','DGS10',[],values['B10'],reason,TIMING,extra={'observation_dates':deps,'release_dates':[r['release_calendar_date'] for r in rates if r],
            'assumed_available_at':[r['assumed_available_at'] for r in rates if r],'source_week_offsets':[1,2],'unit':'bp'})
        # D10의 가용시각은 D04가 아닌 D10 시각으로 덮어쓴다.
        logs[-1]['source_dates']=json.dumps(deps)
        logs[-1]['latest_assumed_available_at']=max((r['assumed_available_at'] for r in rates if r),default='')
        dgs_selected.append({'week_start':w.isoformat(),'prediction_origin':origin.isoformat(),
            'prior_observation_date':rates[0]['observation_date'] if rates[0] else '',
            'previous_observation_date':rates[1]['observation_date'] if rates[1] else '',
            'B10_valid':all(rates),'B10_without_E3_valid':all(no_e3),
            'missing_reason':reason,'source_week_starts':json.dumps([(w-timedelta(weeks=k)).isoformat() for k in [1,2]])})
        fgivals=[];fgideps=[]
        for ds in prior:
            v=get('11',ds,fgicol);a=eod_available(ds)
            if v is not None and 0<=v<=100 and a is not None and a<origin:fgivals.append(v);fgideps.append(ds)
        threshold=math.ceil(.8*len(prior));valid=bool(prior) and len(fgivals)>=threshold
        values['F1']=sum(fgivals)/len(fgivals) if valid else None
        reason='' if valid else 'FGI_BELOW_CEIL_80_PERCENT_OF_EXPECTED_SESSIONS'
        sources['F1']=json.dumps(fgideps);reasons['F1']=reason
        log(w,origin,'F1','11',fgicol,fgideps,values['F1'],reason,extra={'N_expected':len(prior),'n_valid':len(fgivals),'minimum':threshold,'LOCF':False})
        feat={**row,**{k:values[k] if values[k] is not None else '' for k in X},
            **{k+'_source_dates':sources[k] for k in X},**{k+'_missing_reason':reasons[k] for k in X},
            'FGI_N_expected':len(prior),'FGI_n_valid':len(fgivals),'FGI_minimum_valid':threshold,
            'M0_X_valid':all(values[k] is not None for k in X[:-1]),'M1_X_valid':all(values[k] is not None for k in X)}
        pair=feat['M1_X_valid'] and y is not None
        combined_row={**feat,'Y':y if y is not None else '', 'Y_valid':y is not None,
            'label_end_date':target['label_end_date'],'label_assumed_available_at':target['label_assumed_available_at'],
            'paired_common_valid':pair,'Y_missing_reason':target['Y_missing_reason']}
        miss={'week_start':w.isoformat(),'prediction_origin':origin.isoformat(),'split':part,'SOX_session_count':len(ss),
            'Y_valid':y is not None,**{k+'_valid':values[k] is not None for k in X},
            'M0_X_valid':feat['M0_X_valid'],'M1_X_valid':feat['M1_X_valid'],
            'M0_Y_valid':feat['M0_X_valid'] and y is not None,'M1_Y_valid':pair,'paired_common_valid':pair,
            'B10_without_E3_valid':all(no_e3),'paired_without_E3_valid':pair and all(no_e3),
            'missing_reasons':';'.join(k+':'+v for k,v in reasons.items() if v)+('Y:'+target['Y_missing_reason'] if y is None else '')}
        targets.append(target);features.append(feat);combined.append(combined_row);missing.append(miss)
    # 공개 로그/집계에는 시험 Y·분포·상관 또는 종가비율을 포함하지 않는다.
    for is_test,folder,names in [(False,'train_dev',['SOX_WEEKLY_Y.csv','WEEKLY_FEATURES_B10_F1.csv','WEEKLY_CORE_COMBINED.csv']),
        (True,'sealed_test',['SOX_WEEKLY_Y_TEST.csv','WEEKLY_FEATURES_TEST.csv','WEEKLY_CORE_TEST.csv'])]:
        for rs,name in zip([targets,features,combined],names):csvout('data/'+folder+'/'+name,[r for r in rs if (r['split']=='sealed_test')==is_test])
    csvout('availability/FEATURE_AVAILABILITY_LOG.csv',logs)
    csvout('availability/D10_WEEKLY_SELECTION_AUDIT.csv',dgs_selected)
    csvout('data/WEEKLY_MISSINGNESS_AUDIT.csv',missing)
    csvout('data/PAIRED_COMMON_WEEK_MEMBERSHIP.csv',[{'week_start':r['week_start'],'split':r['split'],'paired_common_valid':r['paired_common_valid']} for r in missing])
    counts={'calendar_weeks':len(weeks),'SOX_trading_weeks':sum(r['SOX_session_count']>0 for r in missing),
        'Y_valid':sum(r['Y_valid'] for r in missing),
        'feature_valid':{k:sum(r[k+'_valid'] for r in missing) for k in X},
        **{k:sum(r[k] for r in missing) for k in ['M0_X_valid','M1_X_valid','M0_Y_valid','M1_Y_valid','paired_common_valid','paired_without_E3_valid']},
        'B10_valid_without_E3':sum(r['B10_without_E3_valid'] for r in missing),
        'splits':{},'Y_statistics_or_performance_computed':False}
    for part in ['initial_train','development','sealed_test']:
        group=[r for r in missing if r['split']==part]
        counts['splits'][part]={'weeks':len(group),'Y_valid':sum(r['Y_valid'] for r in group),
            'paired_common_valid':sum(r['paired_common_valid'] for r in group),'feature_valid':{k:sum(r[k+'_valid'] for r in group) for k in X},
            'first_week':group[0]['week_start'],'last_week':group[-1]['week_start']}
    valid_weeks=[r['week_start'] for r in missing if r['paired_common_valid']]
    counts['paired_first_week']=min(valid_weeks) if valid_weeks else None;counts['paired_last_week']=max(valid_weeks) if valid_weeks else None
    # 원래 격자의 유효/결손 연속구간. Bootstrap 규칙·n 하한은 미확정이다.
    runs=[]
    for r in missing:
        valid=r['paired_common_valid']
        if not runs or runs[-1]['valid']!=valid:runs.append({'start_week':r['week_start'],'end_week':r['week_start'],'valid':valid,'weeks':1})
        else:runs[-1]['end_week']=r['week_start'];runs[-1]['weeks']+=1
    csvout('data/COMMON_WEEK_CONTIGUOUS_RUNS.csv',runs)
    counts['maximum_common_missing_run_weeks']=max((r['weeks'] for r in runs if not r['valid']),default=0)
    save('data/WEEKLY_SAMPLE_COUNTS.json',counts)
    for r in readcsv(OUT/'calendar/D10_E4_CONFLICT_HANDLING.csv'):
        affected=[o for o in dgs if o['release_evidence_grade']=='E4' and o['release_calendar_date']==r['conflict_date']]
        obsweeks={monday(date.fromisoformat(o['observation_date'])) for o in affected}
        affectedweeks=[w.isoformat() for w in weeks if w-timedelta(weeks=1) in obsweeks or w-timedelta(weeks=2) in obsweeks]
        e4_impact.append({'conflict_date':r['conflict_date'],'blocked_observation_dates':json.dumps([o['observation_date'] for o in affected]),
            'potential_feature_weeks':json.dumps(affectedweeks),'whole_week_deleted':False,
            'B10_missing_feature_weeks':json.dumps([s['week_start'] for s in dgs_selected if s['week_start'] in affectedweeks and not s['B10_valid']]),
            'independent_same_week_rates_preserved':True})
    csvout('availability/D10_E4_OBSERVATION_WEEK_IMPACT.csv',e4_impact)
    dictionary=load(LOCK/'PHASE1_LOCKED_SPEC_v1_1.json')['core_variables']
    table='\n'.join('| '+k+' | '+dictionary[k]['formula'].replace('|','/')+' | '+dictionary[k]['unit']+' |' for k in X[:-1])
    save('data/WEEKLY_DATA_DICTIONARY.md',f'''# 연구 C 주간 데이터 사전

미국 월요일~일요일 week_start 격자. 원점은 첫 미국 실제 세션09:00 ET. Y=100*(이번 주 마지막 SOX Close/직전 주 마지막 Close-1). 인접 주·내부 거래세션 완전성을 검사하고 절댓값·rolling5일로 바꾸지 않는다. 첫 주 선행 SOX 결손은 결측이다. label_assumed_available_at은 다음 미국 세션08:00 ET, actual은 null이다.

| 변수 | 승인 산식 | 단위 |
|---|---|---|
{table}
| F1 | 직전 주 적격 일별 FGI 산술평균; n>=ceil(.8*N_expected) | 0~100 |

B3는 일별 부호수익률·표본표준편차 ddof1·비연율화. B4는 Wilder SMA14 seed/결측시 재시작, 양쪽0=50·손실0=100·상승0=0. B8은 VIX 포인트 차이. B9는 HYG Adj Close이며 당시 조정가격 빈티지 미검증이다. B10은 bp이며 각 원천 주 내부의 적격 관측만 사용한다. F1은 LOCF·보간·미래채움 없이 원래 거래세션 분모를 유지한다.

C-M0=B1~B10; C-M1=C-M0+F1. 공통 유효표본 플래그와 별도 날짜 목록을 보존하며 무조건 다른 용도까지 교집합을 강제하지 않는다. source_dates와 availability 로그를 연결한다. RSI의 과거 state는 별도 일별 감사파일로 연결된다. 실제 시각은 null이고 publication/vintage는 UNVERIFIED다.

train_dev에는 2011~2020만, sealed_test에는 2021~2026-10-05주만 저장한다. 시험 Y는 이 격리 경로 외 보고서·로그·사전검증 파일에 출력하지 않는다. Phase3 개발 코드는 train_dev만 읽어야 한다. D13 세부 규칙 확정 전 시험 오차/성과 접근 금지.

M0_X_valid/M1_X_valid는 X만, M0_Y_valid/M1_Y_valid는 Y까지, paired_common_valid는 M0/M1/Y 공통 조건이다. 결측 원인과 원천 실제 데이터 결손·정책상 이용불가를 구분한다. 기존 RAW의 현재 수정본과 최초 빈티지가 같다고 주장하지 않는다. 학습·표준화·PCA·튜닝은 없다.
''')
    print(json.dumps({'weekly_dataset_created':True,'counts_only':counts},ensure_ascii=False))

if __name__=='__main__':main()
