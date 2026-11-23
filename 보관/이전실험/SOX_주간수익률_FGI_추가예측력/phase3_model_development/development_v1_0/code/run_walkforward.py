"""원점별 72개 적합, 해시 검증 가능한 체크포인트. 개발만 실행."""
import time,warnings,traceback
from common import *

def signature():
    files=[DATA,OUT/'config/PHASE3_APPROVED_SEARCH_GRID.json',OUT/'config/PHASE3_EXPERIMENT_CONFIG.json',
        OUT/'config/PHASE3_ENVIRONMENT_LOCK.json',OUT/'code/common.py',OUT/'code/run_walkforward.py']
    return {p.relative_to(ROOT).as_posix():sha(p) for p in files}

def main():
    assert load(OUT/'qc/GATE_A.json')['status']=='PASS'
    df=read_data();grid=load(OUT/'config/PHASE3_APPROVED_SEARCH_GRID.json');config=load(OUT/'config/PHASE3_EXPERIMENT_CONFIG.json')
    X=df[FEATURES].to_numpy(float);Y=df.Y.to_numpy(float)
    indices=np.flatnonzero((df.split=='development').to_numpy());sig=signature()
    if not (OUT/'qc/SMOKE_AND_PERTURBATION_QC.json').exists():
        records=[];first=int(indices[0]);ids,_=training_indices(df,first,'expanding')
        # Current target Y and all future X/Y altered; current X and eligible past stay fixed.
        xp=X.copy();yp=Y.copy();yp[first:]=1e9;xp[first+1:]=1e8
        t0=time.perf_counter()
        for algo,candidates in grid['algorithms'].items():
            p,audit=fit_predict(algo,candidates[0],X[ids,:10],Y[ids],X[first:first+1,:10])
            q,_=fit_predict(algo,candidates[0],xp[ids,:10],yp[ids],xp[first:first+1,:10])
            assert p==q,(algo,p,q)
            records.append({'algorithm':algo,'reproducible_prediction':p,'future_current_Y_perturbation_invariant':p==q})
        save('qc/SMOKE_AND_PERTURBATION_QC.json',{'status':'PASS','fit_count':10,'records':records,
            'elapsed_seconds':time.perf_counter()-t0,'scope':'first origin M0 expanding first candidate of all5; full-run date/fit checks separate',
            'current_Y_hidden_from_fit':True,'future_XY_changed':True})
    executed=0;resumed=0;allrows=[];baselines=[];audits=[];preproc=[];start=time.perf_counter()
    for step,i in enumerate(indices):
        week=df.iloc[i].week_start;path=OUT/'logs/checkpoints'/f'{week}.json';hashfile=path.with_suffix('.sha256')
        if path.exists():
            assert hashfile.exists() and sha(path)==hashfile.read_text().strip()
            checkpoint=load(path);assert checkpoint['signature']==sig and checkpoint['week_start']==week
            assert len(checkpoint['predictions'])==72
            resumed+=72
        else:
            rows=[];base=[];auditrows=[];prep=[]
            for window in config['windows']:
                ids,cutoff=training_indices(df,int(i),window);train=df.iloc[ids];current=df.iloc[i]
                assert len(ids)>=156 and (train.label_utc<current.origin_utc).all()
                mean=float(Y[ids].mean())
                identity={'week_start':week,'prediction_origin':current.prediction_origin,'window_type':window,
                    'train_start':train.week_start.iloc[0],'train_end':train.week_start.iloc[-1],
                    'last_matured_label_date':train.label_end_date.max(),'train_n':len(ids),
                    'max_train_label_available_at':train.label_utc.max().isoformat(),
                    'cutoff_origin':cutoff.isoformat() if cutoff else '',
                    'training_week_list_sha256':hashlib.sha256('\n'.join(train.week_start).encode()).hexdigest(),
                    'training_mean':mean,'eligible_flag':True,'exclusion_or_failure_reason':''}
                auditrows.append(identity)
                for name,p in [('zero_return',0.),('training_mean',mean)]:
                    actual=float(current.Y);error=actual-p
                    base.append({**identity,'baseline':name,'prediction':p,'development_actual_y':actual,
                        'error':error,'absolute_error':abs(error)})
                for info,width in [('C-M0',10),('C-M1',11)]:
                    for algo,candidates in grid['algorithms'].items():
                        for candidate in candidates:
                            key={'algorithm':algo,'information_set':info,'candidate_id':candidate['candidate_id']}
                            t0=time.perf_counter()
                            try:
                                with warnings.catch_warnings(record=True) as seen:
                                    warnings.simplefilter('always')
                                    p,diagnostics=fit_predict(algo,candidate,X[ids,:width],Y[ids],X[i:i+1,:width])
                                warning_messages=[str(w.message) for w in seen]
                                if warning_messages:raise RuntimeError('ESTIMATOR_WARNING_REQUIRES_REVIEW: '+';'.join(warning_messages))
                                # Score only AFTER prediction function returns. No target y was passed to it.
                                actual=float(current.Y);error=actual-p
                                rows.append({**identity,**key,'prediction':p,'development_actual_y':actual,
                                    'error':error,'absolute_error':abs(error),'fit_seconds':time.perf_counter()-t0})
                                prep.append({**key,'window_type':window,'week_start':week,'train_n':len(ids),**diagnostics})
                                executed+=1
                            except Exception as exc:
                                save(f'logs/ERROR_{week}_{window}_{info}_{candidate["candidate_id"]}.json',
                                    {'stage':'STOPPED_NO_CANDIDATE_DROPPED','key':key,'identity':identity,
                                        'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc(),
                                        'completed_in_this_origin':rows,'executed_this_run_before_error':executed})
                                raise
            checkpoint={'signature':sig,'week_start':week,'predictions':rows,'baselines':base,'training_audit':auditrows,'preprocessing':prep}
            save('logs/checkpoints/'+week+'.json',checkpoint)
            save('logs/checkpoints/'+week+'.sha256',sha(path)+'\n')
        allrows.extend(checkpoint['predictions']);baselines.extend(checkpoint['baselines']);audits.extend(checkpoint['training_audit']);preproc.extend(checkpoint['preprocessing'])
        if step%5==0 or step==len(indices)-1:
            print(json.dumps({'origins_completed':step+1,'total_origins':len(indices),'week':week,
                'completed_candidate_fits':len(allrows),'elapsed_seconds':round(time.perf_counter()-start,1)},ensure_ascii=False),flush=True)
    assert len(allrows)==15048
    csvsave('predictions/PHASE3_ALL_CANDIDATE_PREDICTIONS.csv',allrows)
    csvsave('predictions/PHASE3_BASELINE_PREDICTIONS.csv',baselines)
    csvsave('predictions/PHASE3_ORIGIN_TRAINING_AUDIT.csv',audits)
    save('logs/PREPROCESSING_FIT_AUDIT.json',preproc)
    save('logs/WALKFORWARD_COMPLETION.json',{'status':'COMPLETED','signature':sig,'candidate_fits_completed':len(allrows),
        'candidate_fits_executed_this_run':executed,'resumed_hash_verified_fits':resumed,'origins':len(indices),
        'failed_fits':0,'smoke_fits':10,'elapsed_seconds':time.perf_counter()-start,
        'actual_test_Y_read':0,'phase4_executed':False})

if __name__=='__main__':main()
