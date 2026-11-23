"""DGS10 정보시점 구현·검사. 게이트 통과 전 주간 B10·SOX Y 산출 없음."""
import bisect
from common import *

CORRECTIONS={'2011-03-10','2014-01-14','2017-04-14','2018-09-17','2020-08-19','2023-08-01','2023-09-12'}

def map_observation(ds,calendar_rows,value):
    # E4 또는 승인 실패한 후보를 건너뛰고 다음 날짜로 조용히 재배정하지 않는다.
    out={'observation_date':ds,'DGS10':value if value is not None else '',
        'release_calendar_date':'','release_evidence_grade':'','assumed_release_at':'','assumed_available_at':'',
        'actual_release_at':'null','actual_available_at':'null','publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED',
        'timing_policy_id':TIMING,'calendar_policy_id':CALPOL,'availability_status':'UNAVAILABLE',
        'known_correction_affected':ds in CORRECTIONS,'reason':''}
    if value is None:out['reason']='SOURCE_MISSING';return out
    if ds in CORRECTIONS:
        out['reason']='KNOWN_10Y_OR_TREASURY_CORRECTION_OR_OMISSION_CURRENT_VINTAGE_HELD';return out
    for r in calendar_rows:
        day=r['calendar_date']
        if day<=ds:continue
        if date.fromisoformat(day).weekday()>=5:continue
        if r['evidence_grade']=='E4':
            out.update({'release_calendar_date':day,'release_evidence_grade':'E4','reason':'NEXT_POTENTIAL_EVENT_E4_UNRESOLVED_NO_SILENT_SHIFT'});return out
        if r['calendar_status']=='E3_CONDITION_FAILED':
            out.update({'release_calendar_date':day,'release_evidence_grade':'E3','reason':'NEXT_CANDIDATE_FAILED_E3_CONDITIONS_NO_SILENT_SHIFT'});return out
        if r['calendar_status']=='NONPUBLICATION_OR_UNAPPROVED_E3' and not r['federal_holiday_reference']=='True':
            # 2010·승인범위 밖 미확인 평일 게시일은 후일로 조용히 대체하지 않는다.
            out.update({'release_calendar_date':day,'release_evidence_grade':r['evidence_grade'],'reason':'UNAPPROVED_OR_UNRESOLVED_WEEKDAY_CALENDAR'});return out
        if r['publication_candidate_eligible']!='True':continue
        release=stamp(day,16,15);avail=stamp(date.fromisoformat(day)+timedelta(days=1),8)
        out.update({'release_calendar_date':day,'release_evidence_grade':r['evidence_grade'],
            'assumed_release_at':release.isoformat(),'assumed_available_at':avail.isoformat(),
            'availability_status':'ASSUMED_CONSERVATIVE','reason':'APPROVED_CALENDAR_AND_TIMING_ASSUMPTIONS'})
        return out
    out['reason']='NO_SUPPORTED_FUTURE_PUBLICATION_DAY_IN_CAPTURED_CALENDAR';return out

def available_at(r):
    actual=r.get('actual_available_at')
    a=datetime.fromisoformat(r['assumed_available_at']) if r.get('assumed_available_at') else None
    if actual and actual!='null':
        actual=datetime.fromisoformat(actual)
        return max(a,actual) if a else actual
    return a

def select_week(records,week,origin,allow_e3=True):
    end=week+timedelta(days=7)
    eligible=[]
    for r in records:
        if not week.isoformat()<=r['observation_date']<end.isoformat():continue
        if not allow_e3 and r['release_evidence_grade']=='E3':continue
        a=available_at(r)
        if r['availability_status']=='ASSUMED_CONSERVATIVE' and a is not None and a<origin:
            eligible.append(r)
    return max(eligible,key=lambda r:r['observation_date']) if eligible else None

def main():
    calendar_rows=readcsv(OUT/'calendar/BOARD_H15_PUBLICATION_CALENDAR.csv')
    rows=core()['15']['df'];mapped=[map_observation(r['Date'],calendar_rows,number(r['DGS10'])) for r in rows]
    csvout('availability/D10_OBSERVATION_AVAILABILITY.csv',mapped)
    by={r['observation_date']:r for r in mapped};cal={r['calendar_date']:r for r in calendar_rows}
    tests=[]
    def check(name,ok,evidence):tests.append({'name':name,'pass':bool(ok),'evidence':evidence})
    origin=stamp('2024-02-05')
    check('정상 금요일 월요일09시 부적격',available_at(by['2024-02-02'])>origin,{'observation':'2024-02-02','origin':origin.isoformat()})
    check('정상 목요일 월요일09시 적격',available_at(by['2024-02-01'])<origin,{'observation':'2024-02-01'})
    check('Board 월요일 휴일',by['2024-10-11']['release_calendar_date']=='2024-10-15','2024-10-14 Board휴일·미국 주식시장 개장')
    check('Board 금요일 폐쇄',by['2026-07-02']['release_calendar_date']=='2026-07-06','2026-07-03 Board 휴일')
    sessions={r['session_date'] for r in readcsv(OUT/'calendar/US_MARKET_SESSIONS.csv')}
    check('주식시장/Board 휴일 분리','2024-10-14' in sessions and cal['2024-10-14']['publication_candidate_eligible']=='False'
          and '2024-03-29' not in sessions and cal['2024-03-29']['publication_candidate_eligible']=='True','Columbus Day 대 Good Friday')
    check('DST 겨울·여름',stamp('2024-01-08').astimezone(timezone.utc).hour==14 and stamp('2024-07-08').astimezone(timezone.utc).hour==13,'America/New_York')
    e3=readcsv(OUT/'calendar/D10_E3_DATEWISE_DECISIONS.csv')
    check('E3 조건별 반영',len(e3)==637 and all((r['decision']=='CONDITIONALLY_ALLOWED')==all(r[f'condition_{n}']=='SATISFIED' for n in range(1,8)) for r in e3),'637 후보 날짜별 검사')
    check('E4 미해결 게시 차단',all(r['availability_status']=='UNAVAILABLE' for r in mapped if r['release_evidence_grade']=='E4')
          and all(cal[d]['publication_candidate_eligible']=='False' for d in ['2011-12-26','2012-10-29','2016-01-22','2018-03-02','2019-01-19','2022-12-31']),'이벤트 차단; 주 전체 삭제 없음')
    synthetic=dict(by['2024-02-01']);synthetic['actual_available_at']=stamp('2024-02-05',10).isoformat()
    check('알려진 실제 지연 우선',available_at(synthetic)>origin,'합성 실제 지연 사례는 테스트에만 사용, 산출 실제 필드에는 저장하지 않음')
    check('실제 시각 미확인 null',all(r['actual_release_at']==r['actual_available_at']=='null' and r['vintage_status']=='UNVERIFIED' for r in mapped),'actual/assumed 분리')
    synthetic2=dict(by['2024-02-01']);synthetic2['assumed_available_at']=origin.isoformat();synthetic2['actual_available_at']='null'
    check('09시 동시각 엄격 부적격',select_week([synthetic2],date(2024,1,29),origin) is None,'available_at == origin 제외')
    check('결측·정정 관측 보류',all(r['availability_status']=='UNAVAILABLE' for r in mapped if r['known_correction_affected']=='True' or r['DGS10']==''),
        '정정/누락 복구의 실제 시점 미해결인 해당 관측만 보수적으로 보류. 다른 주로 채우지 않음')
    original=select_week(mapped,date(2024,1,29),origin)
    perturb=[dict(r) for r in mapped]
    for r in perturb:
        a=available_at(r)
        if r['observation_date']>=origin.date().isoformat() or (a and a>=origin):r['DGS10']=99999
    perturb.append({'observation_date':'2024-01-31','DGS10':99999,'release_evidence_grade':'E2','assumed_available_at':'2030-01-01T08:00:00-05:00','actual_available_at':'null','availability_status':'ASSUMED_CONSERVATIVE'})
    changed=select_week(perturb,date(2024,1,29),origin)
    check('미래자료 교란 불변',original is not None and changed is not None and (original['observation_date'],original['DGS10'])==(changed['observation_date'],changed['DGS10']),
        '미래 관측/원점 이후 이용 가능 값 변경·추가에도 과거 선택과 값 불변. 현재 수정본의 실제 최초 빈티지 불변을 입증하는 검사가 아님')
    check('관측일 다음 게시일·하루 후08시',all(not r['assumed_release_at'] or
        (r['release_calendar_date']>r['observation_date'] and datetime.fromisoformat(r['assumed_available_at']).date()==date.fromisoformat(r['release_calendar_date'])+timedelta(days=1)) for r in mapped),
        '동일 관측일 게시 사용 금지')
    exchange=load(OUT/'qc/EXCHANGE_CALENDAR_QC.json');h15=load(OUT/'qc/H15_CALENDAR_QC.json')
    status='D10_PREBUILD_QC_PASS' if all(t['pass'] for t in tests) and exchange['status']==h15['status']=='PASS' else 'D10_PREBUILD_QC_BLOCKED'
    save('availability/D10_INFORMATION_LEAKAGE_TESTS.json',{'status':status,'tests':tests,'count':len(tests),
        'actual_vintage_verified':False,'weekly_B10_or_Y_created_at_gate':False})
    save('qc/D10_PREBUILD_GATE.json',{'status':status,'test_count':len(tests),'all_tests_pass':all(t['pass'] for t in tests),
        'calendar_QC':exchange['status']+'/'+h15['status'],'weekly_data_created':False})
    save('availability/D10_ASOF_AUDIT.md',f'''# D10 정보시점 사전감사

{status}. {len(tests)}개 정보시점 검사. 가정 시각은 실제 시각이 아니다. 관측일 다음 게시 가능일16:15, 다음 달력일08:00 및 strict-before를 구현했다. 금요일 자동 사용·주 밖 이월·미래채움은 없다. E4/미승인 후보에 의존하는 관측을 다음 발표일로 조용히 옮기지 않는다. 알려진 10년물 또는 Treasury 전체 정정/누락 관측 {len(CORRECTIONS)}일은 최초 복구시점 미확인으로 보류했다. 다른 만기만의 정정은 DGS10으로 오인하지 않는다.

알려진 폐쇄는 게시일 후보에서 제외하고 독립 근거 있는 다음 게시일을 찾는다. 정확한 재개시각은 actual로 만들지 않는다. DDP 채널 중단을 H15 웹 전체 중단으로 처리하지 않는다. 미래자료 교란 테스트는 시점 선택 로직만 검증하며 현재 수정본과 최초 빈티지의 동일성을 입증하지 않는다.

이 게이트 기록은 주간 B10/Y 산출 전에 저장했다. BLOCKED이면 즉시 중단하며 PASS여도 역사적 실제 최초 공개시각·빈티지는 UNVERIFIED다.
''')
    print(json.dumps({'status':status,'tests':len(tests),'failures':[t['name'] for t in tests if not t['pass']]},ensure_ascii=False))
    if status!='D10_PREBUILD_QC_PASS':raise SystemExit(2)

if __name__=='__main__':main()
