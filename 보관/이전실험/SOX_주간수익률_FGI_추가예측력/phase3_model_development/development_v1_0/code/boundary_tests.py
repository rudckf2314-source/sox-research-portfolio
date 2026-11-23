"""실제 X/Y 없이 합성 날짜만으로 운영 훈련선택 경계 검사."""
from common import *
def main():
    origin=pd.Timestamp('2020-01-06T14:00:00Z');cutoff=pd.Timestamp('2015-01-06T14:00:00Z')
    rows=[
        {'case':'label_equal_origin','week_start':'2019-12-23','origin_utc':pd.Timestamp('2019-12-23T14:00Z'),'label_utc':origin},
        {'case':'label_just_before','week_start':'2019-12-23','origin_utc':pd.Timestamp('2019-12-23T14:00Z'),'label_utc':origin-pd.Timedelta(microseconds=1)},
        {'case':'rolling_at_cutoff','week_start':'2015-01-05','origin_utc':cutoff,'label_utc':pd.Timestamp('2015-01-12T13:00Z')},
        {'case':'rolling_before_cutoff','week_start':'2015-01-05','origin_utc':cutoff-pd.Timedelta(microseconds=1),'label_utc':pd.Timestamp('2015-01-12T13:00Z')},
        {'case':'target_week_fake_mature','week_start':'2020-01-06','origin_utc':origin-pd.Timedelta(days=1),'label_utc':origin-pd.Timedelta(days=1)},
        {'case':'future_week_fake_mature','week_start':'2020-01-13','origin_utc':origin-pd.Timedelta(days=1),'label_utc':origin-pd.Timedelta(days=1)},
        {'case':'current_target','week_start':'2020-01-06','origin_utc':origin,'label_utc':origin+pd.Timedelta(days=7)}]
    df=pd.DataFrame(rows)
    exp,_=training_indices(df,6,'expanding');roll,_=training_indices(df,6,'rolling_5_calendar_years')
    tests={'exact_label_origin_excluded':0 not in exp,'label_before_included':1 in exp,
        'cutoff_included':2 in roll,'cutoff_previous_microsecond_excluded':3 not in roll,
        'target_Y_excluded_even_fake_mature':4 not in exp,'future_week_excluded_even_fake_mature':5 not in exp,
        'target_row_excluded':6 not in exp,'expanding_uses_older_past':3 in exp}
    save('qc/PHASE3_BOUNDARY_SYNTHETIC_QC.json',{'status':'PASS' if all(tests.values()) else 'FAIL',
        'checks':tests,'rows':[{**r,'origin_utc':r['origin_utc'].isoformat(),'label_utc':r['label_utc'].isoformat()} for r in rows],
        'target_index':6,'expanding_indices':exp.tolist(),'rolling_indices':roll.tolist(),
        'cutoff_utc':cutoff.isoformat(),'actual_XY_used':False,'estimator_fits':0})
    print({'boundary_QC':'PASS' if all(tests.values()) else 'FAIL','checks':len(tests)})

if __name__=='__main__':main()
