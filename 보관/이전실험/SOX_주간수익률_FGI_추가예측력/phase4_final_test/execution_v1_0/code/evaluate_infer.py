"""전체 예측 저장 후 고정 시험 지표/HAC/MBB/Holm 산출."""
import gzip
from common import *
from statistics_core import hac,mbb,holm_family5
from phase3_model_core import metrics

def main():
    ensure_gate();commit=load(OUT/'logs/ALL_PREDICTIONS_COMMITTED.json')
    assert sha(OUT/'predictions/PHASE4_RAW_PREDICTIONS_BEFORE_OUTCOMES.csv')==commit['raw_prediction_sha256']
    df=pd.read_csv(OUT/'predictions/PHASE4_ALL_TEST_PREDICTIONS.csv');base=pd.read_csv(OUT/'predictions/PHASE4_BASELINE_PREDICTIONS.csv')
    grid=pd.read_csv(OUT/'inputs/PHASE4_WEEK_GRID_AUDIT.csv').week_start.tolist();assert len(grid)==301
    model_metrics=[];directions=[];baseline_metrics=[];comparisons=[];paired=[];delta=[]
    for (window,name),g in base.groupby(['window_type','baseline']):
        ok=np.isfinite(g.actual_y)&np.isfinite(g.prediction)
        baseline_metrics.append({'window_type':window,'baseline':name,**metrics(g.loc[ok,'actual_y'],g.loc[ok,'prediction'],g.loc[ok,'training_mean'])})
    for algo in FAMILY:
        left=df[(df.algorithm==algo)&(df.information_set=='C-M0')].set_index('week_start').reindex(grid)
        right=df[(df.algorithm==algo)&(df.information_set=='C-M1')].set_index('week_start').reindex(grid)
        assert np.allclose(left.actual_y,right.actual_y,equal_nan=True)
        valid=np.isfinite(left.actual_y)&np.isfinite(left.prediction)&np.isfinite(right.prediction)
        for info,g in [('C-M0',left),('C-M1',right)]:
            result=metrics(g.loc[valid,'actual_y'],g.loc[valid,'prediction'],g.loc[valid,'training_mean'])
            model_metrics.append({'algorithm':algo,'information_set':info,'window_type':g.window_type.iloc[0],
                'candidate_id':g.candidate_id.iloc[0],'grid_n':301,'not_paired_valid_n':int((~valid).sum()),**result})
            directions.append({'algorithm':algo,'information_set':info,**{k:result[k] for k in ['n','direction_accuracy','actual_zero_n','prediction_zero_n','nonzero_actual_direction_accuracy']}})
        loss0=np.abs(left.actual_y-left.prediction);loss1=np.abs(right.actual_y-right.prediction)
        loss0=loss0.where(valid,np.nan);loss1=loss1.where(valid,np.nan)
        diff=loss0-loss1
        for i,w in enumerate(grid):
            paired.append({'week_start':w,'prediction_origin':left.prediction_origin.iloc[i],'algorithm':algo,
                'window_type':left.window_type.iloc[i],'actual_y':float(left.actual_y.iloc[i]),
                'M0_prediction':float(left.prediction.iloc[i]) if np.isfinite(left.prediction.iloc[i]) else None,
                'M1_prediction':float(right.prediction.iloc[i]) if np.isfinite(right.prediction.iloc[i]) else None,
                'M0_loss':float(loss0.iloc[i]) if valid.iloc[i] else None,'M1_loss':float(loss1.iloc[i]) if valid.iloc[i] else None,
                'paired_loss_difference':float(diff.iloc[i]) if valid.iloc[i] else None,'paired_valid':bool(valid.iloc[i])})
        m0=float(loss0[valid].mean());m1=float(loss1[valid].mean());d=float(diff[valid].mean())
        delta.append({'algorithm':algo,'N_grid':301,'n_valid':int(valid.sum()),'M0_MAE':m0,'M1_MAE':m1,'Delta_MAE':d,
            'relative_MAE_improvement_percent':100*d/m0 if m0 else None})
        window=left.window_type.iloc[0];b=base[base.window_type==window].pivot(index='week_start',columns='baseline',values='prediction').reindex(grid)
        comparisons.append({'algorithm':algo,'window_type':window,'n_valid':int(valid.sum()),'M0_MAE':m0,'M1_MAE':m1,
            'Training_Mean_MAE':float(np.mean(np.abs(left.actual_y[valid]-b.training_mean[valid]))),
            'Zero_Return_MAE':float(np.mean(np.abs(left.actual_y[valid]-b.zero_return[valid]))),
            **{f'{info}_{k}':next(x for x in model_metrics if x['algorithm']==algo and x['information_set']==info)[k]
                for info in ['C-M0','C-M1'] for k in ['RMSE','OOS_R2_training_mean','direction_accuracy']}})
    csvout('predictions/PHASE4_PAIRED_TEST_PREDICTIONS.csv',paired)
    csvout('metrics/PHASE4_MODEL_METRICS.csv',model_metrics);csvout('metrics/PHASE4_DIRECTION_METRICS.csv',directions)
    csvout('metrics/PHASE4_PAIRED_DELTA_MAE.csv',delta);csvout('metrics/PHASE4_BASELINE_COMPARISON.csv',comparisons)
    csvout('metrics/PHASE4_BASELINE_METRICS.csv',baseline_metrics)
    hacs=[];boots=[];attempt_audit=[];seed_manifest=[];holm_records={}
    (OUT/'inference/bootstrap_logs').mkdir(exist_ok=True)
    for algo in FAMILY:
        rows=[r for r in paired if r['algorithm']==algo]
        difference=[r['paired_loss_difference'] if r['paired_valid'] else np.nan for r in rows]
        for lag in [4,2,8]:hacs.append({'algorithm':algo,**hac(grid,difference,lag)})
        main=next(r for r in hacs if r['algorithm']==algo and r['lag']==4)
        holm_records[NAME[algo]]={'status':main['status'],'raw_p':main['raw_p'],'reason':main['reason'] or None,
            'reason_detail':main['reason'] if main['status']=='NOT_COMPUTABLE' else None,'approved_rule_id':'C_D13_CALENDAR_GRID_MBB_v1_0'}
        for L in [8,4,12]:
            result,means,records,starts=mbb(grid,[r['M0_loss'] if r['paired_valid'] else np.nan for r in rows],
                [r['M1_loss'] if r['paired_valid'] else np.nan for r in rows],L)
            logpath=OUT/'inference/bootstrap_logs'/f'{algo}_L{L}.jsonl.gz'
            with logpath.open('xb') as raw:
                with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as f:
                    for r,s in zip(records,starts):f.write((json.dumps({**r,'block_starts':s},separators=(',',':'))+'\n').encode())
            meanpath=logpath.with_suffix('').with_suffix('.npz')
            with meanpath.open('xb') as f:np.savez_compressed(f,bootstrap_means=np.array(means))
            boots.append({'algorithm':algo,**{k:v for k,v in result.items() if k!='seed_words'}})
            attempt_audit.append({'algorithm':algo,'L':L,'attempts':result['attempts'],'accepted':result['accepted'],'rejected':result['rejected'],
                'rejection_reasons':{reason:sum(r['reason']==reason for r in records) for reason in set(r['reason'] for r in records) if reason},
                'n_valid_range':[min(r['n_valid'] for r in records),max(r['n_valid'] for r in records)] if records else [],
                'log':logpath.relative_to(OUT).as_posix(),'log_sha256':sha(logpath),'means':meanpath.relative_to(OUT).as_posix(),'means_sha256':sha(meanpath)})
            seed_manifest.append({'algorithm':algo,'L':L,'root_seed':20261016,'grid_sha256':result['grid_sha256'],'seed_words':result['seed_words'],
                'starts_sha256':hashlib.sha256(json.dumps(starts,separators=(',',':')).encode()).hexdigest(),'forced_start_used':False})
            print({'bootstrap_algorithm':algo,'L':L,'status':result['status'],'accepted':result['accepted'],'attempts':result['attempts']},flush=True)
    holm=holm_family5(holm_records)
    if holm['family_status']=='IMPLEMENTATION_ERROR_REVIEW_REQUIRED':
        save('logs/HOLM_IMPLEMENTATION_ERROR.json',holm);raise RuntimeError('HOLM_IMPLEMENTATION_ERROR_REVIEW_REQUIRED')
    reverse={v:k for k,v in NAME.items()}
    holmrows=[{**r,'algorithm':reverse[r['algorithm']],'family_status':holm['family_status']} for r in holm['rows']]
    csvout('inference/PHASE4_HAC_RESULTS.csv',[r for r in hacs if r['lag']==4]);csvout('inference/PHASE4_HAC_SENSITIVITY.csv',hacs)
    csvout('inference/PHASE4_BOOTSTRAP_RESULTS.csv',boots)
    save('inference/PHASE4_BOOTSTRAP_ATTEMPT_AUDIT.json',attempt_audit);save('inference/PHASE4_BOOTSTRAP_SEED_MANIFEST.json',seed_manifest)
    csvout('inference/PHASE4_HOLM_FAMILY5_RESULTS.csv',holmrows)
    ridge={'primary_algorithm':'Ridge','Delta_MAE':next(r for r in delta if r['algorithm']=='Ridge'),
        'HAC':next(r for r in hacs if r['algorithm']=='Ridge' and r['lag']==4),
        'Holm':next(r for r in holmrows if r['algorithm']=='Ridge'),'bootstrap':next(r for r in boots if r['algorithm']=='Ridge' and r['L']==8),
        'primary_status':holm['primary_status'],'no_primary_replacement':True}
    save('inference/PHASE4_PRIMARY_RIDGE_INFERENCE.json',ridge)
    complete=all(r['status']=='COMPUTABLE' for r in hacs) and all(r['status']=='COMPLETED' for r in boots)
    save('inference/PHASE4_INFERENCE_STATUS.json',{'status':'COMPLETED' if complete else 'COMPLETED_WITH_INFERENCE_UNAVAILABLE',
        'UNSEALED':True,'predictions':'COMPLETED','metrics':'COMPLETED','Holm_family':holm['family_status'],
        'primary_Ridge':holm['primary_status'],'bootstrap_p_added':False,'phase5':'NOT_AUTHORIZED'})
    event('METRICS_AND_INFERENCE_COMPLETED',all_inferences_available=complete)

if __name__=='__main__':main()
