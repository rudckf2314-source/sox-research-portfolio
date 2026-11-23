"""봉인 해제 후 고정10모형 예측을 전부 저장. 현재 Y는 모델 입력과 분리."""
import time,warnings,traceback
from dateutil.relativedelta import relativedelta
from common import *
from phase3_model_core import fit_predict

def model_inputs():
    ensure_gate();manifest=load(OUT/'inputs/PHASE4_INPUT_MANIFEST.json');files=manifest['sealed_files']
    for f in files:assert sha(ROOT/f['path'])==f['sha256']
    if not (OUT/'inputs/PHASE4_UNSEAL_AUDIT.json').exists():
        save('inputs/PHASE4_UNSEAL_AUDIT.json',{'status':'UNSEALED','unsealed_at_utc':datetime.now(UTC).isoformat(),
            'authorization':'USER_APPROVED','code_hashes':code_hashes(),'files':files,
            'boundary':'승인/사전QC 후에만 시험 CSV 내용 파싱 허용. 현재Y는 vault에서 분리하며 평가조회는 모든 예측 저장 후.'})
        event('UNSEALED_BEFORE_FIRST_CONTENT_PARSE',files=3)
    byname={Path(f['path']).name:ROOT/f['path'] for f in files}
    # Paths resolved from prior manifest, not invented or substituted.
    core=pd.read_csv(byname['WEEKLY_CORE_TEST.csv']);features=pd.read_csv(byname['WEEKLY_FEATURES_TEST.csv']);targets=pd.read_csv(byname['SOX_WEEKLY_Y_TEST.csv'])
    past=pd.read_csv(BUILD/'data/train_dev/WEEKLY_CORE_COMBINED.csv')
    assert len(core)==len(features)==len(targets)==301
    assert core.week_start.tolist()==targets.week_start.tolist()==features.week_start.tolist()
    assert core.week_start.iloc[0]=='2021-01-04' and core.week_start.iloc[-1]=='2026-10-05'
    assert np.allclose(core.Y,targets.Y,equal_nan=True)
    assert np.allclose(core[FEATURES],features[FEATURES],equal_nan=True)
    combined=pd.concat([past,core],ignore_index=True).sort_values('week_start').reset_index(drop=True)
    assert len(combined)==823 and not combined.week_start.duplicated().any()
    Y=combined.pop('Y').to_numpy(float) # Only OutcomeVault receives Y; input dataframe no Y column.
    combined['origin_utc']=pd.to_datetime(combined.prediction_origin,utc=True)
    combined['label_utc']=pd.to_datetime(combined.label_assumed_available_at,utc=True)
    # Actual timestamps override assumed when frozen target file contains one.
    if 'label_actual_available_at' in targets:
        actual=pd.to_datetime(targets.label_actual_available_at.replace('null',None),utc=True,errors='coerce')
        for w,t in zip(targets.week_start,actual):
            if pd.notna(t):combined.loc[combined.week_start==w,'label_utc']=t
    xvalid=combined.M0_X_valid.to_numpy(bool)&combined.M1_X_valid.to_numpy(bool)
    lineage=pd.read_csv(BUILD/'availability/FEATURE_AVAILABILITY_LOG.csv',keep_default_na=False)
    counts=0
    for r in lineage.to_dict('records'):
        index=int(np.flatnonzero((combined.week_start==r['week_start']).to_numpy())[0])
        if not xvalid[index]:continue
        actual=r['actual_available_at'];s=actual if actual not in ('','null','None') else r['latest_assumed_available_at']
        assert r['valid'] in (True,'True') and r['source_period_complete'] in (True,'True')
        assert pd.Timestamp(s).tz_convert('UTC')<combined.iloc[index].origin_utc
        assert r['publication_status']=='UNVERIFIED' and r['vintage_status']=='UNVERIFIED';counts+=1
    assert counts==int(xvalid.sum())*11
    if not (OUT/'inputs/PHASE4_WEEK_GRID_AUDIT.csv').exists():
        csvout('inputs/PHASE4_WEEK_GRID_AUDIT.csv',[{'week_start':r.week_start,'prediction_origin':r.prediction_origin,
            'label_end_date':r.label_end_date,'label_available_at':r.label_utc.isoformat(),'X_pair_valid':bool(xvalid[i]),
            'publication_status':r.publication_status,'vintage_status':r.vintage_status} for i,r in combined.iterrows() if r.split=='sealed_test'])
        save('inputs/PHASE4_CONTENT_VALIDATION.json',{'status':'PASS','calendar_weeks':823,'test_grid':301,
            'core_feature_target_crosscheck':True,'lineage_rows_checked':counts,'historical_publication_vintage':'UNVERIFIED',
            'current_target_Y_not_in_model_dataframe':'Y' not in combined.columns})
    return combined,OutcomeVault(Y,combined,xvalid),xvalid

class OutcomeVault:
    def __init__(self,y,metadata,xvalid):self.__y=y;self.meta=metadata;self.xvalid=xvalid
    def training(self,i,window):
        row=self.meta.iloc[i];O=row.origin_utc
        mask=(self.meta.week_start<row.week_start)&(self.meta.origin_utc<O)&(self.meta.label_utc<O)
        mask &= self.xvalid&self.meta.Y_valid.to_numpy(bool)&np.isfinite(self.__y)
        cutoff=None
        if window=='rolling_5_calendar_years':
            cutoff=O.to_pydatetime().astimezone(NY)-relativedelta(years=5)
            mask &= self.meta.origin_utc>=pd.Timestamp(cutoff.astimezone(UTC))
        ids=np.flatnonzero(mask.to_numpy())
        assert i not in ids
        return ids,self.__y[ids].copy(),cutoff
    def evaluate(self):
        assert (OUT/'logs/ALL_PREDICTIONS_COMMITTED.json').exists(),'CURRENT_OUTCOME_ACCESS_BEFORE_ALL_PREDICTIONS'
        indices=np.flatnonzero((self.meta.split=='sealed_test').to_numpy())
        return self.__y[indices].copy()

def main():
    ensure_gate();config=load(OUT/'config/PHASE4_LOCKED_EXECUTION_CONFIG.json');selection=config['phase3_lock']['selected_algorithms']
    data,vault,xvalid=model_inputs();X=data[FEATURES].to_numpy(float);test=np.flatnonzero((data.split=='sealed_test').to_numpy())
    allrows=[];baselines=[];audits=[];preprocess=[];failures=[];executed=0;start=time.perf_counter()
    signature={'code':code_hashes(),'config':sha(OUT/'config/PHASE4_LOCKED_EXECUTION_CONFIG.json'),'environment':sha(OUT/'config/PHASE4_ENVIRONMENT.json')}
    event('PREDICTION_LOOP_STARTED',test_grid=len(test),no_current_Y_argument=True)
    for step,i in enumerate(test):
        row=data.iloc[i];week=row.week_start;p=OUT/'logs/checkpoints'/f'{week}.json'
        if p.exists():
            assert sha(p)==p.with_suffix('.sha256').read_text().strip();cp=load(p);assert cp['signature']==signature
        else:
            predicted=[];base=[];audit=[];prep=[];failed=[];windows={}
            for window in ['expanding','rolling_5_calendar_years']:
                ids,y,cut=vault.training(int(i),window);windows[window]=(ids,y)
                train=data.iloc[ids];mean=float(y.mean()) if len(y) else None
                info={'week_start':week,'prediction_origin':row.prediction_origin,'window_type':window,'train_n':len(ids),
                    'train_start':train.week_start.iloc[0] if len(ids) else '', 'train_end':train.week_start.iloc[-1] if len(ids) else '',
                    'last_matured_label_date':train.label_end_date.max() if len(ids) else '',
                    'last_label_available_at':train.label_utc.max().isoformat() if len(ids) else '',
                    'cutoff_origin':cut.isoformat() if cut else '', 'training_mean':mean,
                    'training_week_list_sha256':hashlib.sha256('\n'.join(train.week_start).encode()).hexdigest()}
                audit.append(info)
                for name,pred in [('zero_return',0.),('training_mean',mean)]:base.append({**info,'baseline':name,'prediction':pred})
            for algo,chosen in selection.items():
                window=chosen['selected_window'];ids,y=windows[window];identity=next(a for a in audit if a['window_type']==window)
                reason='' if xvalid[i] and len(ids)>=156 else ('CURRENT_X_UNAVAILABLE' if not xvalid[i] else 'NOT_PREDICTED_INSUFFICIENT_TRAINING')
                for info,width in [('C-M0',10),('C-M1',11)]:
                    candidate=chosen['models'][info]['hyperparameters'];key={'algorithm':algo,'information_set':info,'candidate_id':candidate['candidate_id']}
                    if reason:
                        predicted.append({**identity,**key,'prediction':None,'eligible_flag':False,'failure_reason':reason})
                        failed.append({**key,'week_start':week,'reason':reason});continue
                    assert np.isfinite(X[ids,:width]).all() and np.isfinite(y).all() and np.isfinite(X[i,:width]).all()
                    try:
                        with warnings.catch_warnings(record=True) as warns:
                            warnings.simplefilter('always');pred,diag=fit_predict(algo,candidate,X[ids,:width],y,X[i:i+1,:width])
                        if warns:raise RuntimeError('ESTIMATOR_WARNING_REVIEW_REQUIRED: '+';'.join(str(w.message) for w in warns))
                        predicted.append({**identity,**key,'prediction':pred,'eligible_flag':True,'failure_reason':''});executed+=1
                        prep.append({'week_start':week,'window_type':window,**key,'train_n':len(ids),**diag})
                    except Exception as e:
                        save(f'logs/ERROR_AFTER_UNSEAL_{week}_{candidate["candidate_id"]}_{info}.json',{'status':'BLOCKED_REVIEW_REQUIRED','UNSEALED':True,
                            'stage':'PREDICTION','origin':week,'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc(),
                            'code_hashes':code_hashes(),'predictions_in_origin_so_far':predicted,'evaluation_started':False})
                        raise
            cp={'week_start':week,'signature':signature,'predictions':predicted,'baselines':base,'audit':audit,'preprocessing':prep,'failures':failed}
            save('logs/checkpoints/'+week+'.json',cp);save('logs/checkpoints/'+week+'.sha256',sha(p)+'\n')
        allrows.extend(cp['predictions']);baselines.extend(cp['baselines']);audits.extend(cp['audit']);preprocess.extend(cp['preprocessing']);failures.extend(cp['failures'])
        if step%10==0 or step==len(test)-1:print(json.dumps({'test_origins_done':step+1,'total':len(test),'predictions_committed':len(allrows),'fits_this_run':executed,'elapsed_seconds':round(time.perf_counter()-start,1)}),flush=True)
    csvout('predictions/PHASE4_RAW_PREDICTIONS_BEFORE_OUTCOMES.csv',allrows)
    csvout('predictions/PHASE4_ORIGIN_TRAINING_AUDIT.csv',audits)
    csvout('predictions/PHASE4_BASELINES_BEFORE_OUTCOMES.csv',baselines)
    csvout('predictions/PHASE4_MODEL_FAILURES.csv',failures,fields=['algorithm','information_set','candidate_id','week_start','reason'])
    save('logs/PHASE4_PREPROCESSING_FIT_AUDIT.json',preprocess)
    save('logs/ALL_PREDICTIONS_COMMITTED.json',{'status':'PREDICTIONS_COMPLETED','prediction_rows':len(allrows),'test_origins':len(test),
        'main_estimator_fits':len(preprocess),'executed_this_run':executed,'failures_or_nonpredictions':len(failures),
        'raw_prediction_sha256':sha(OUT/'predictions/PHASE4_RAW_PREDICTIONS_BEFORE_OUTCOMES.csv'),
        'created_at_utc':datetime.now(UTC).isoformat(),'signature':signature})
    event('ALL_PREDICTIONS_COMMITTED_BEFORE_SCORING',model_fits=len(preprocess),raw_prediction_sha256=sha(OUT/'predictions/PHASE4_RAW_PREDICTIONS_BEFORE_OUTCOMES.csv'))
    # Only now may evaluation outcomes be exposed.
    outcomes=dict(zip(data.iloc[test].week_start,vault.evaluate()));scored=[];scored_base=[]
    for r in allrows:
        y=float(outcomes[r['week_start']]);p=r['prediction'];error=y-p if p is not None else None
        scored.append({**r,'actual_y':y,'error':error,'absolute_error':abs(error) if error is not None else None})
    for r in baselines:
        y=float(outcomes[r['week_start']]);p=r['prediction'];error=y-p if p is not None else None
        scored_base.append({**r,'actual_y':y,'error':error,'absolute_error':abs(error) if error is not None else None})
    csvout('predictions/PHASE4_ALL_TEST_PREDICTIONS.csv',scored)
    csvout('predictions/PHASE4_BASELINE_PREDICTIONS.csv',scored_base)
    save('logs/PREDICTION_AND_OUTCOME_JOIN_COMPLETED.json',{'status':'COMPLETED','elapsed_seconds':time.perf_counter()-start,
        'main_fits':len(preprocess),'failures':len(failures),'current_Y_used_before_prediction':False,'outcomes_accessed_after_all_predictions':True})
    event('EVALUATION_OUTCOMES_JOINED_AFTER_PREDICTIONS',rows=len(scored))

if __name__=='__main__':main()
