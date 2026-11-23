"""합성 주간 메타데이터 전용 실행계획 검증. 모델/Y 로더 없음."""
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta
from common import write
NY=ZoneInfo('America/New_York');UTC=timezone.utc
def t(x):
    v=datetime.fromisoformat(x)
    if v.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return v.astimezone(UTC)
def plan(rows,origin,week,window,current_x_at,minimum=156):
    o=t(origin)
    if not t(current_x_at)<o:return {'status':'NOT_ELIGIBLE_CURRENT_X','indices':[]}
    cutoff=(o.astimezone(NY)-relativedelta(years=5)).astimezone(UTC)
    ids=[]
    if window not in ('expanding','rolling_5_calendar_years'):raise ValueError('UNAPPROVED_WINDOW')
    for i,r in enumerate(rows):
        if r['week_start']>=week or not t(r['origin'])<o or not t(r['label_at'])<o:continue
        if not t(r['x_at'])<t(r['origin']):continue
        if window=='rolling_5_calendar_years' and t(r['origin'])<cutoff:continue
        ids.append(i)
    return {'status':'ELIGIBLE' if len(ids)>=minimum else 'NOT_PREDICTED_INSUFFICIENT_TRAINING','indices':ids,
        'train_n':len(ids),'cutoff_utc':cutoff.isoformat() if window!='expanding' else None}

def main():
    O=datetime(2025,1,6,9,tzinfo=NY);week='2025-01-06';rows=[]
    for i in range(200):
        d=O-timedelta(weeks=200-i)
        rows.append({'week_start':d.date().isoformat(),'origin':d.isoformat(),
            'label_at':(d+timedelta(days=7,hours=-1)).isoformat(),'x_at':(d-timedelta(hours=1)).isoformat()})
    cases=[]
    def add(name,rs=rows,origin=O,window='expanding',x_at=None,expected=None):
        v=plan(rs,origin.isoformat(),origin.date().isoformat(),window,(x_at or origin-timedelta(hours=1)).isoformat())
        cases.append({'case':name,'rows':rs,'origin':origin.isoformat(),'week_start':origin.date().isoformat(),
            'window':window,'current_x_at':(x_at or origin-timedelta(hours=1)).isoformat(),'result':v,'expected_status':expected})
    add('200_past_mature',expected='ELIGIBLE')
    add('155_insufficient',rs=rows[:155],expected='NOT_PREDICTED_INSUFFICIENT_TRAINING')
    add('156_boundary',rs=rows[:156],expected='ELIGIBLE')
    add('current_X_equal_origin',x_at=O,expected='NOT_ELIGIBLE_CURRENT_X')
    rs=[dict(r) for r in rows];rs[-1]['label_at']=O.isoformat();add('label_equal_origin_excluded',rs=rs,expected='ELIGIBLE')
    rs=[dict(r) for r in rows];rs[-1]['label_at']=(O-timedelta(microseconds=1)).isoformat();add('label_just_before',rs=rs,expected='ELIGIBLE')
    rs=[dict(r) for r in rows];rs[-1]['x_at']=rs[-1]['origin'];add('own_historical_X_equal_excluded',rs=rs,expected='ELIGIBLE')
    rs=rows+[{'week_start':week,'origin':(O-timedelta(days=1)).isoformat(),'label_at':(O-timedelta(days=1)).isoformat(),'x_at':(O-timedelta(days=2)).isoformat()}]
    add('fake_mature_current_week_excluded',rs=rs,expected='ELIGIBLE')
    cutoff=O-relativedelta(years=5)
    old={'week_start':'2019-12-30','origin':cutoff.isoformat(),'label_at':(cutoff+timedelta(days=1)).isoformat(),'x_at':(cutoff-timedelta(hours=1)).isoformat()}
    add('rolling_cutoff_included',rs=rows+[old],window='rolling_5_calendar_years',expected='ELIGIBLE')
    before=dict(old);before['origin']=(cutoff-timedelta(microseconds=1)).isoformat();before['x_at']=(cutoff-timedelta(hours=1)).isoformat()
    add('rolling_cutoff_before_excluded',rs=rows+[before],window='rolling_5_calendar_years',expected='ELIGIBLE')
    add('rolling_never_extend_to260',rs=rows[:155]+[before]*120,window='rolling_5_calendar_years',expected='NOT_PREDICTED_INSUFFICIENT_TRAINING')
    leap=datetime(2024,2,29,9,tzinfo=NY);add('calendar_leap_day',origin=leap,window='rolling_5_calendar_years',expected='NOT_PREDICTED_INSUFFICIENT_TRAINING')
    summer=datetime(2025,3,10,9,tzinfo=NY);add('DST_summer_UTC',origin=summer,window='rolling_5_calendar_years',expected='ELIGIBLE')
    checks={c['case']:c['result']['status']==c['expected_status'] for c in cases}
    by={c['case']:c for c in cases}
    checks['label_equal_reduces_n']=by['label_equal_origin_excluded']['result']['train_n']==199
    checks['label_before_keeps_n']=by['label_just_before']['result']['train_n']==200
    checks['own_X_late_reduces_n']=by['own_historical_X_equal_excluded']['result']['train_n']==199
    checks['same_week_not_train']=by['fake_mature_current_week_excluded']['result']['train_n']==200
    checks['cutoff_include_201']=by['rolling_cutoff_included']['result']['train_n']==201
    checks['cutoff_before_200']=by['rolling_cutoff_before_excluded']['result']['train_n']==200
    checks['DST_09local_13UTC']=t(summer.isoformat()).hour==13
    checks['leap_cutoff_Feb28']=by['calendar_leap_day']['result']['cutoff_utc']=='2019-02-28T14:00:00+00:00'
    try:t('2025-01-06T09:00:00');checks['naive_timezone_rejected']=False
    except ValueError:checks['naive_timezone_rejected']=True
    write('qc/SYNTHETIC_PRETEST_PLANNER_QC.json',{'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,
        'count':len(checks),'cases':cases,'actual_XY_used':False,'model_fits':0,'predictions':0})
    print({'synthetic_planner':'PASS' if all(checks.values()) else 'FAIL','cases':len(cases),'checks':len(checks)})

if __name__=='__main__':main()
