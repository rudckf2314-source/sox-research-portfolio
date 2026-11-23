"""모든 후보를 보존한 뒤 개발 MAE로 선택. 시험 데이터 접근 없음."""
from common import *
def main():
    completion=load(OUT/'logs/WALKFORWARD_COMPLETION.json');assert completion['candidate_fits_completed']==15048
    df=pd.read_csv(OUT/'predictions/PHASE3_ALL_CANDIDATE_PREDICTIONS.csv')
    base=pd.read_csv(OUT/'predictions/PHASE3_BASELINE_PREDICTIONS.csv')
    grid=load(OUT/'config/PHASE3_APPROVED_SEARCH_GRID.json')
    keys=['algorithm','information_set','window_type','candidate_id'];rows=[]
    for key,group in df.groupby(keys,sort=True):
        assert len(group)==209 and group.week_start.nunique()==209
        rows.append({**dict(zip(keys,key)),**metrics(group.development_actual_y,group.prediction,group.training_mean)})
    csvsave('metrics/PHASE3_CANDIDATE_METRICS.csv',rows)
    best={}
    for r in rows:
        k=(r['algorithm'],r['information_set'],r['window_type'])
        if k not in best or (r['MAE'],r['candidate_id'])<(best[k]['MAE'],best[k]['candidate_id']):best[k]=r
    windows=[best[k] for k in sorted(best)];csvsave('metrics/PHASE3_WINDOW_COMPARISON.csv',windows)
    selected={};pairs=[];pairedrows=[]
    for algo in grid['algorithms']:
        window=min(['expanding','rolling_5_calendar_years'],key=lambda w:(best[(algo,'C-M0',w)]['MAE'],w!='expanding'))
        selected[algo]={'selected_window':window,'window_basis':'C-M0 minimum-candidate pooled MAE; tie expanding','models':{}}
        for info in ['C-M0','C-M1']:
            m=best[(algo,info,window)];params=next(c for c in grid['algorithms'][algo] if c['candidate_id']==m['candidate_id'])
            selected[algo]['models'][info]={'candidate_id':m['candidate_id'],'hyperparameters':params,'development_metrics':m}
        a=selected[algo]['models']['C-M0'];b=selected[algo]['models']['C-M1']
        pairs.append({'algorithm':algo,'selected_window':window,'M0_candidate_id':a['candidate_id'],'M1_candidate_id':b['candidate_id'],
            'M0_MAE':a['development_metrics']['MAE'],'M1_MAE':b['development_metrics']['MAE'],
            'Delta_MAE_dev':a['development_metrics']['MAE']-b['development_metrics']['MAE'],
            'M0_RMSE':a['development_metrics']['RMSE'],'M1_RMSE':b['development_metrics']['RMSE'],
            'M0_OOS_R2_training_mean':a['development_metrics']['OOS_R2_training_mean'],
            'M1_OOS_R2_training_mean':b['development_metrics']['OOS_R2_training_mean'],
            'M0_direction_accuracy':a['development_metrics']['direction_accuracy'],'M1_direction_accuracy':b['development_metrics']['direction_accuracy']})
        left=df[(df.algorithm==algo)&(df.information_set=='C-M0')&(df.window_type==window)&(df.candidate_id==a['candidate_id'])].set_index('week_start')
        right=df[(df.algorithm==algo)&(df.information_set=='C-M1')&(df.window_type==window)&(df.candidate_id==b['candidate_id'])].set_index('week_start')
        assert left.index.equals(right.index)
        for week in left.index:
            x=left.loc[week];z=right.loc[week];assert x.development_actual_y==z.development_actual_y
            pairedrows.append({'week_start':week,'prediction_origin':x.prediction_origin,'algorithm':algo,'window_type':window,
                'M0_candidate_id':a['candidate_id'],'M1_candidate_id':b['candidate_id'],'development_actual_y':x.development_actual_y,
                'M0_prediction':x.prediction,'M1_prediction':z.prediction,'M0_absolute_error':x.absolute_error,
                'M1_absolute_error':z.absolute_error,'paired_loss_difference':x.absolute_error-z.absolute_error,
                'train_start':x.train_start,'train_end':x.train_end,'train_n':int(x.train_n)})
    csvsave('metrics/PHASE3_MODEL_PAIR_COMPARISON.csv',pairs)
    csvsave('predictions/PHASE3_PAIRED_DEV_PREDICTIONS.csv',pairedrows)
    baserows=[]
    for (window,name),g in base.groupby(['window_type','baseline']):
        baserows.append({'window_type':window,'baseline':name,**metrics(g.development_actual_y,g.prediction,g.training_mean)})
    csvsave('metrics/PHASE3_BASELINE_METRICS.csv',baserows)
    save('metrics/PHASE3_FAILURE_COUNTS.json',{'candidate_estimator_fit_failures':0,'excluded_origins':0,'completed_candidate_fits':15048,
        'planned_candidate_fits':15048,'technical_smoke_fits':10,'initial_aborted_smoke_estimator_fits':3,
        'initial_diagnostic_serialization_failures':1,'record':'logs/INITIAL_SMOKE_DIAGNOSTIC_FAILURE.json',
        'independent_sample_refits_recorded_separately':True})
    save('selection/PHASE3_SELECTION_REGISTER.json',{'status':'COMPLETED','selected':selected,'selection_rule_review_required':False,
        'resolution_source':'PHASE1_LOCKED_SPEC_v1_1.json learning.candidate_selection: per representation',
        'window_exact_tie':'expanding','candidate_exact_tie':'candidate_id ascending','test_data_used':False})
    save('selection/PHASE3_RIDGE_PRIMARY_SELECTION.md','# 주력 Ridge 개발 선택\n\n'+json.dumps(selected['Ridge'],ensure_ascii=False,indent=2)+
        '\n\n주력 Ridge 유지. 이 성능은 후보·창 선택에 사용한 개발결과이며 독립 시험성과가 아니다.\n')
    save('selection/PHASE3_SELECTION_CHANGELOG.md','''# 선택 규칙 검토 이력

기존v1.1 learning.candidate_selection이 per representation을명시하므로 M0/M1 하이퍼파라미터는동일탐색규칙으로별도선택한다.
각창/정보집합에서최적후보선택후각알고리즘M0의창별최소MAE로창선택,쌍에공유. 창동점Expanding,후보동점ID오름차순.
이전초안의PROPOSED와당시Gate상태는후속승인LOCK/D10/D13/현재Phase3실행승인으로적용범위가해결됐다. 실질적미해결충돌없음.
후보조합·기간·변수변경0. Phase4설정은사용자검토용후보이며FINAL_LOCKED아님.
''')
    print(json.dumps({'selected':{a:{'window':s['selected_window'],'M0':s['models']['C-M0']['candidate_id'],'M1':s['models']['C-M1']['candidate_id']} for a,s in selected.items()},'pairs':pairs,'baselines':baserows},ensure_ascii=False))

if __name__=='__main__':main()
