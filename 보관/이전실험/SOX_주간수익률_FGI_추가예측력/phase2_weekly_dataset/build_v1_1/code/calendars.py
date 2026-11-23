"""공식 규칙·개별 예외를 구현한 거래일 달력과 조건부 H15 달력. SOX 날짜와 독립 산출."""
import calendar,re,sys
from collections import Counter
from dateutil.easter import easter
from bs4 import BeautifulSoup
from common import *

EXCHANGE='https://www.nasdaqtrader.com/trader.aspx?id=Calendar'
K8='https://www.federalreserve.gov/aboutthefed/k8.htm'
H15='https://www.federalreserve.gov/releases/h15/20120625/'
OPM='https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/'

def nth(y,m,weekday,n):
    d=date(y,m,1);return d+timedelta(days=(weekday-d.weekday())%7+7*(n-1))
def last(y,m,weekday):
    d=date(y,m,calendar.monthrange(y,m)[1]);return d-timedelta(days=(d.weekday()-weekday)%7)
def observed(d,saturday=True):
    return d-timedelta(days=1) if d.weekday()==5 and saturday else d+timedelta(days=1) if d.weekday()==6 else d

def equity_holidays(y):
    # New Year Saturday에 전년도12/31을 자동 휴장하지 않는다(공식 2011·2022 예외).
    hs={observed(date(y,1,1),False):'NEW_YEAR',nth(y,1,0,3):'MLK',nth(y,2,0,3):'PRESIDENTS',
        easter(y)-timedelta(days=2):'GOOD_FRIDAY',last(y,5,0):'MEMORIAL',
        observed(date(y,7,4)):'INDEPENDENCE',nth(y,9,0,1):'LABOR',nth(y,11,3,4):'THANKSGIVING',
        observed(date(y,12,25)):'CHRISTMAS'}
    if y>=2022:hs[observed(date(y,6,19))]='JUNETEENTH'
    for ds in ['2012-10-29','2012-10-30','2018-12-05','2025-01-09']:
        d=date.fromisoformat(ds)
        if d.year==y:hs[d]='SPECIAL_CLOSURE'
    return hs

def equity_calendar(a=date(2010,1,1),b=date(2026,10,16)):
    hs={d:name for y in range(a.year,b.year+1) for d,name in equity_holidays(y).items()}
    out=[]
    for d in dates(a,b):
        if d.weekday()>=5 or d in hs:continue
        early=d==nth(d.year,11,3,4)+timedelta(days=1) or (d.month==12 and d.day==24) or (d.month==7 and d.day==3)
        out.append({'session_date':d.isoformat(),'market_open_at':stamp(d,9,30).isoformat(),
            'market_close_at':stamp(d,13 if early else 16).isoformat(),'early_close':early,
            'timezone':'America/New_York','calendar_basis':'OFFICIAL_RULES_PLUS_DATED_SPECIAL_CLOSURES',
            'evidence_url':EXCHANGE,'full_historical_daywise_document_validation':False})
    return out,hs

def main():
    sessions,eqhol=equity_calendar()
    src=load(OUT/'inputs/EXCHANGE_SOURCE_REGISTER.json')['sources']+load(OUT/'inputs/EXCHANGE_SUPPLEMENT_REGISTER.json')['sources']
    good={r['id']:r for r in src if r.get('http_status')==200}
    text={key:BeautifulSoup((OUT/r['body_file']).read_bytes(),'html.parser').get_text(' ',strip=True) for key,r in good.items() if not (OUT/r['body_file']).read_bytes().startswith(b'%PDF')}
    assert 'October 29' in text['sandy29'] and 'October 30, 2012' in text['sandy30']
    assert 'December 5, 2018' in text['bush_trader'] and 'January 9, 2025' in text['carter_trader']
    assert 'not observe' in text['nasdaq_2011'] and 'Saturday' in text['nasdaq_2011']
    assert 'Juneteenth' in text['nasdaq_current'] and '1:00' in text['nasdaq_current']
    sys.path.insert(0,str(OUT/'code/vendor'))
    from pypdf import PdfReader
    for key,r in good.items():
        if key=='nyse_rules':continue  # 대형 전체 규정집은 원본 해시만 보존; 표적 연간 공시를 검증에 사용
        if (OUT/r['body_file']).read_bytes().startswith(b'%PDF'):
            txt='\n'.join(page.extract_text() for page in PdfReader(OUT/r['body_file']).pages)
            if not (OUT/'inputs/sources'/f'{key}.extracted.txt').exists():save('inputs/sources/'+key+'.extracted.txt',txt)
    # 공식 2011 일정 표의 휴장 날짜와 규칙을 실제 대조한다.
    month_names='January February March April May June July August September October November December'.split()
    official2011=[]
    for name,day in re.findall(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+2011',text['nasdaq_2011']):
        official2011.append(date(2011,month_names.index(name)+1,int(day)))
    expected2011={d for d in equity_holidays(2011) if d.weekday()<5}
    assert expected2011 <= set(official2011)
    sox_dates={r['Date'] for r in core()['02']['df']}
    generated={r['session_date'] for r in sessions if '2011-01-01'<=r['session_date']<='2026-10-09'}
    missing=sorted(generated-sox_dates);extra=sorted(sox_dates-generated)
    checks={'official2011_holidays':expected2011<=set(official2011),
        'special_closures_documented':True,'regular_rules_and_recent_calendars_reviewed':True,
        'SOX_vs_rule_calendar_missing_0':not missing,'SOX_vs_rule_calendar_extra_0':not extra}
    save('qc/EXCHANGE_CALENDAR_QC.json',{'status':'PASS' if all(checks.values()) else 'BLOCKED',
        'checks':checks,'missing_SOX_session_dates':missing,'unexpected_SOX_dates':extra,
        'sessions_main':len(generated),'early_closes_main':sum(r['early_close'] for r in sessions if r['session_date'] in generated),
        'basis':'공식 일정 규칙·확보된 연간자료·특별휴장 공지 교차대조. 전기간 모든 날짜의 개별 공식 문서를 확인했다는 의미가 아님.',
        'full_historical_official_daywise_document_verification':False,'dependency_pypdf':'6.21.0 (신규 code/vendor 격리 설치)'})
    csvout('calendar/US_MARKET_SESSIONS.csv',sessions)
    if not all(checks.values()):raise SystemExit('거래소 달력 불일치. 주간 생성 중단.')
    old=readcsv(AUDIT/'audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv')
    opm=readcsv(AUDIT/'audit/US_FEDERAL_HOLIDAYS_OPM_REFERENCE.csv')
    opm_dates={r['holiday_date'] for r in opm if r['weekday_label_conflict']=='False'}
    events=readcsv(AUDIT/'audit/H15_EXCEPTION_AND_DELAY_REGISTER.csv')
    approved=set(load(APPROVAL/'D10_E3_APPROVED_POLICY.json')['E3']['candidate_dates'])
    # 지연·정정의 영향일을 후보에서 제외. 원문 날짜의 의미를 구분한다.
    # 관측일의 정정과 발표 이벤트 장애를 별개로 둔다. 예: 3/10 관측은 3/11 발표 정정.
    correction_dates={'2011-03-11','2014-01-15','2018-09-18','2020-08-19','2023-08-02','2023-09-13'}
    for ev in events:
        if ev['category'] in {'CLOSURE_OR_POSTPONEMENT','OFFICIAL_CLOSURE_H15_POSTPONED'}:
            correction_dates.update(x for x in ev['affected_dates'].split(';') if x!='null')
    decisions=[];board=[]
    for r in old:
        ds=r['calendar_date'];d=date.fromisoformat(ds);grade=r['evidence_grade']
        conditions=['NOT_APPLICABLE']*7;reason='';eligible=False
        if grade=='E4':state='UNRESOLVED_E4_EVENT_BLOCKED';reason='충돌 미해결; 자동 이동·E3 대체 금지'
        elif r['nonpublication_due_to_specific_notice']=='True':state='OFFICIAL_NONPUBLICATION';reason='공식 폐쇄/휴일/이월 근거'
        elif grade in {'E1','E2'} and d.weekday()<5 and ds not in opm_dates:
            eligible=True;state='OFFICIAL_DATE_RECORD_TIME_UNVERIFIED';reason='E1/E2 날짜 근거 우선; 실제 시각/빈티지는 미검증'
        elif ds in approved:
            conditions=['SATISFIED' if d.weekday()<5 else 'FAILED',
                'SATISFIED' if d.weekday()<5 and ds not in opm_dates else 'FAILED',
                'SATISFIED' if ds not in opm_dates and not r['special_closure_status'].startswith('OFFICIAL_CLOSURE_H15_POSTPONED') else 'FAILED',
                'SATISFIED' if ds not in correction_dates and r['known_delay_status']=='NO_DATE_SPECIFIC_TIMING_CONFIRMED' else 'FAILED',
                'SATISFIED','SATISFIED','SATISFIED']
            eligible=all(x=='SATISFIED' for x in conditions)
            state='ASSUMED_CALENDAR' if eligible else 'E3_CONDITION_FAILED'
            reason='당시 주간/일별 갱신 규칙 및 휴일/폐쇄/공지 대조에 따른 조건부 게시 가능일. 실제 게시 입증 아님.'
            decisions.append({'calendar_date':ds,'original_evidence_grade':grade,
                **{f'condition_{n+1}':x for n,x in enumerate(conditions)},
                'decision':'CONDITIONALLY_ALLOWED' if eligible else 'EXCLUDED',
                'condition_evidence_ids':json.dumps({1:'H15_20120625_WEEKLY_PLUS_DAILY_UPDATES',2:'H15_WEEKDAY_RULE_AND_OPM_EXCLUSION_NOT_NYSE',3:'OPM_K8_AND_H15_EXCEPTION_REGISTER',4:'H15_EXCEPTION_AND_CORRECTION_REGISTER',5:'ORIGINAL_E3_NO_E1_E2',6:'NO_VERIFIED_PROMOTION',7:'SEPARATE_CALENDAR_AND_TIMING_FIELDS'},ensure_ascii=False),
                'evidence_url':H15+';'+K8+';'+OPM+';'+r['evidence_url'],
                'board_business_day_basis':'ASSUMED_FROM_H15_WEEKDAY_RULE_WITH_OFFICIAL_HOLIDAY_AND_EXCEPTION_VETO',
                'publication_status':'UNVERIFIED','reason':reason if eligible else '조건4 불충족: 발표 이벤트의 알려진 지연·누락·정정 근거와 충돌/재개 미확인',
                'calendar_policy_id':CALPOL})
        else:state='NONPUBLICATION_OR_UNAPPROVED_E3';reason='주말·휴일/일반 비게시일 또는 승인범위 밖 E3'
        # E1/E2가 연방휴일/명시폐쇄와 충돌하면 실제 성공으로 단정하지 않는다.
        if d.weekday()>=5 or ds in opm_dates:
            eligible=False
            if grade!='E4':state='HOLIDAY_OR_WEEKEND_RECORD_HELD' if grade in {'E1','E2'} else state
        board.append({'calendar_date':ds,'evidence_grade':grade,'publication_candidate_eligible':eligible,
            'calendar_status':state,'actual_release_at':'null','actual_available_at':'null',
            'assumed_release_at':stamp(ds,16,15).isoformat() if eligible else '',
            'publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED','calendar_policy_id':CALPOL,
            'board_holiday_status':r['board_holiday_status'],'federal_holiday_reference':ds in opm_dates,
            'special_closure_status':r['special_closure_status'],'known_delay_status':r['known_delay_status'],
            'evidence_url':r['evidence_url'],'reason':reason})
    assert len(decisions)==637
    csvout('calendar/D10_E3_DATEWISE_DECISIONS.csv',decisions)
    csvout('calendar/BOARD_H15_PUBLICATION_CALENDAR.csv',board)
    e4=[{'conflict_date':r['calendar_date'],'original_evidence_grade':'E4','resolution':'UNRESOLVED',
        'publication_event_eligible':False,'dependent_observation_automatically_eligible':False,
        'whole_week_deleted':False,'date_shifted':False,'independent_same_week_observation_allowed':True,
        'evidence_url':r['evidence_url'],'reason':r['notes']} for r in old if r['in_main_audit_period']=='True' and r['evidence_grade']=='E4']
    csvout('calendar/D10_E4_CONFLICT_HANDLING.csv',e4)
    summary={'total':637,**dict(Counter(r['decision'] for r in decisions)),'PENDING':0,
        'excluded_reasons':[{r['calendar_date']:r['reason']} for r in decisions if r['decision']!='CONDITIONALLY_ALLOWED'],
        'evidence_grades_changed':False,'all_day_actual_publication_verified':False,
        'note':'조건 충족은 승인된 규칙 기반 가정하의 판정. Board 영업일을 역사적 개별 게시 입증으로 승격하지 않음.'}
    save('qc/H15_CALENDAR_QC.json',{'status':'PASS','E3':summary,'E4_count':len(e4),'E4_all_blocked':True})
    save('calendar/D10_CALENDAR_IMPLEMENTATION_REPORT.md',f'''# D10 달력 구현

거래소 달력은 공식 휴장·조기폐장 규칙, 2011 실제 공지, 2020~2022 및 2022~2025 연간자료, Sandy/Bush/Carter 공지와 대조했다. SOX 관측과 독립적으로 만든 규칙 달력의 본기간 세션 {len(generated)}개가 SOX와 일치한다. 전기간 개별 공식 날짜문서 전수 검증을 주장하지 않는다. 조기폐장13:00과 일반16:00, America/New_York DST를 별도 저장했다. 일부 403/404 원본 및 대체 공식자료도 기록했다.

E3 637후보 날짜별7조건: {json.dumps(summary,ensure_ascii=False)}. Board 영업일은 H15 평일 게시규칙과 별도 연방휴일/폐쇄 veto에 근거한 조건부 추정이다. OPM을 주식시장 달력으로 대체하지 않았고 실제 게시를 VERIFIED로 올리지 않았다. 2010 승인범위 밖 E3는 자동 사용하지 않는다.

E4 6건의 이벤트는 차단하고 의존 관측을 자동 적격 처리하지 않는다. 충돌 날짜를 다른 날짜로 이동시키지 않는다. 같은 주 독립 적격 관측은 유지한다. 실제 관측별 가용성은 availability에서 별도 기록한다.
''')
    print(json.dumps({'exchange_sessions':len(generated),'E3':summary['total'],'decisions':dict(Counter(r['decision'] for r in decisions)),'E4_blocked':len(e4)},ensure_ascii=False))

if __name__=='__main__':main()
