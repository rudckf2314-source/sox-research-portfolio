"""Audit actual Oct1-7 rules; extend identically. Preprocessing only; no Y or models."""
from pathlib import Path
import json,hashlib,sys,warnings
import numpy as np,pandas as pd,joblib
W=Path(__file__).resolve().parents[1];B=W/'outputs/evaluation_extension_20261023_v1';P=W/'outputs/evaluation_extension_20261023_aaii_v4_20261024';O=W/'outputs/evaluation_extension_20261023_consistent_v5_20261024';O.mkdir(exist_ok=True);HASH={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p,**kw):HASH[str(p)]=sha(p);return pd.read_csv(p,**kw)
def load(p):HASH[str(p)]=sha(p);return json.loads(Path(p).read_text(encoding='utf-8'))
def save(df,name):df.to_csv(O/name,index=False,encoding='utf-8-sig')
def js(name,obj):(O/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def main():
 plan=load(W/'outputs/near_release_reconstruction_v1_20261023/FROZEN_PLAN.json');assert plan['rules']['32']['max_age_days']==120
 old=read(W/'outputs/staged_multi_algorithm_v2_20261023/X216_WITHOUT_FRENCH_COMPONENTS_NO_Y.csv',index_col=0,float_precision='round_trip');old.index=pd.to_datetime(old.index);x=read(P/'추가12일_X216_AAII갱신_NO_Y.csv',index_col=0,float_precision='round_trip');x.index=pd.to_datetime(x.index);before=x.copy()
 native=read(W/'outputs/unused_raw_features_v1_20261023/native_review/32_monthly.csv',index_col=0,float_precision='round_trip');native.index=pd.to_datetime(native.index);cols=list(native);assert len(cols)==4
 original_line=read(W/'outputs/near_release_reconstruction_v1_20261023/LINEAGE_09ET.csv');original_line=original_line[(original_line.source_id==32)&original_line.date.between('2026-10-01','2026-10-07')];assert len(original_line)==5 and original_line.observation_date.eq('2026-07-01').all() and original_line.fresh.all()
 events=read(W/'outputs/near_release_reconstruction_v1_20261023/RELEASE_EVENT_CALENDAR.csv');events=events[events.source_id==32].copy();events['bound']=pd.to_datetime(events.availability_bound_ET,utc=True);audit=[]
 all_dates=old.index[(old.index>='2026-10-01')&(old.index<='2026-10-07')].append(x.index)
 for day in all_dates:
  origin=day.tz_localize('America/New_York')+pd.Timedelta(hours=9);eligible=events[events.bound<origin.tz_convert('UTC')].sort_values('observation_date');assert len(eligible)
  r=eligible.iloc[-1];obs=pd.Timestamp(r.observation_date);age=(day-obs).days;fresh=age<=120;values=native.loc[obs,cols].to_numpy() if fresh else np.full(4,np.nan)
  assert obs==pd.Timestamp('2026-07-01') and r.bound<origin and fresh
  if day in old.index:assert np.allclose(old.loc[day,cols],values,atol=1e-10,rtol=1e-10,equal_nan=True)
  else:x.loc[day,cols]=values
  audit.append(dict(date=str(day.date()),phase='original_Oct1_7' if day in old.index else 'extension_Oct8_23',source_observation_month=str(obs.date()),observation_value=float(native.loc[obs,cols[0]]),availability_bound_et=r.availability_bound_ET,origin_et=origin.isoformat(),age_calendar_days=age,max_age_days=120,eligible=fresh,policy='latest observation in collected native data whose release bound has passed,120day cap',original_rule_reproduced=True,latest_actual_market_release_verified=False))
 assert np.allclose(x.drop(columns=cols),before.drop(columns=cols),atol=0,rtol=0,equal_nan=True)
 assert x[cols].notna().all().all();filled=int((before[cols].isna()&x[cols].notna()).sum().sum());assert filled==48
 full=pd.concat([old,x]);assert full.index.is_unique and list(full.columns)==list(old.columns) and np.allclose(full.loc[old.index],old,atol=0,rtol=0,equal_nan=True)
 save(x.reset_index(names='date'),'추가12일_X216_기존규칙유지_NO_Y.csv');save(full.reset_index(names='date'),'전체기간_X216_기존규칙유지_NO_Y.csv');save(full.loc[all_dates].reset_index(names='date'),'10월01_23일_X216_비교용_NO_Y.csv');save(pd.DataFrame(audit),'대만수출주문_10월전체_동일규칙_대조.csv')
 # Reuse the exact saved October preprocessing object. No fit, model loads, or label reads.
 trroot=W/'outputs/crossed_feature_algorithm_v1_20261023/windows/late_2026-10';complete=load(trroot/'COMPLETE.json');statsfile=trroot/'TRAIN_TRANSFORM.joblib';HASH[str(statsfile)]=sha(statsfile);assert sha(statsfile)==complete['transform_sha256'];stats=joblib.load(statsfile);rawcols=stats['raw_features'];td=old.index[old.index<'2026-10-01'];assert len(td)==stats['n_train'] and str(td[-1].date())==stats['train_end']=='2026-09-30'
 train=old.loc[td,rawcols];med=train.median();assert np.allclose(stats['imputer'].statistics_,med,atol=1e-10,rtol=1e-10,equal_nan=True)
 missing_before=x.isna();missingcols=x.columns[missing_before.any()].tolist();assert missingcols==['s52_unrate_gap12_pp'],missingcols
 imputed=x.copy();imputation=[]
 for c in missingcols:
  assert c in rawcols;v=float(stats['imputer'].statistics_[rawcols.index(c)]);assert np.isfinite(v)
  for day in x.index[missing_before[c]]:imputation.append(dict(date=str(day.date()),feature=c,imputed_value=v,median_training_start=str(td[0].date()),median_training_end='2026-09-30',n_train=len(td),method='original saved October training-only median; no refit',structural_missing=True))
  imputed[c]=imputed[c].fillna(v)
 assert np.isfinite(imputed.to_numpy()).all();save(imputed.reset_index(names='date'),'추가12일_X216_기존학습중앙값대치_NO_Y.csv');save(pd.DataFrame(imputation),'실업률_구조적결측_기존중앙값대치.csv')
 # All monthly group values for original Oct1-7 match the sealed historical X.
 monthly_cols=[c for c in old if c.startswith(tuple(f's{sid:02}_' for sid in [22,24,25,32,36,37]))];source142=read(W/'outputs/near_release_reconstruction_v1_20261023/AVAILABLE142_NEAR_RELEASE_SCENARIO_NO_Y.csv',index_col=0,float_precision='round_trip');source142.index=pd.to_datetime(source142.index);original_dates=all_dates[all_dates<=pd.Timestamp('2026-10-07')];assert np.allclose(old.loc[original_dates,monthly_cols],source142.loc[original_dates,monthly_cols],equal_nan=True,atol=1e-10,rtol=1e-10)
 # Apply archived scale + archived French PCA to prepare all fixed feature masks, without prediction.
 a=stats['scaler'].transform(stats['imputer'].transform(x[rawcols]));pcs=[];rawf=[];names=list(rawcols);french_line=[]
 for lag in ['NEXT20','MONTH2_FIRST']:
  fpath=B/'prepared'/f'{lag}_FRENCH420_추가기간_NO_Y.csv';f=read(fpath,index_col=0,float_precision='round_trip');f.index=pd.to_datetime(f.index);f=f.loc[x.index];fi,sc,pc=stats['PCA'][lag];scores=sc.transform(fi.transform(f));pcs.append(pc.transform(scores));rawf.append(scores);names.extend(lag+'_PC'+str(k+1) for k in range(10));assert len(f.columns)==420 and np.isfinite(scores).all()
  # Compare Oct1-7 source values against last available August snapshot; current official files unchanged.
  original_f=read(W/f'outputs/french_release_scenarios_v1_20261023/{lag}_FRENCH420_ALIGNED_NO_Y.csv',index_col=0,float_precision='round_trip');original_f.index=pd.to_datetime(original_f.index);assert np.allclose(f.iloc[0],original_f.loc['2026-10-07'],atol=1e-10,rtol=1e-10,equal_nan=True)
  save(f.reset_index(names='date'),lag+'_FRENCH420_기존규칙유지_NO_Y.csv');french_line.append(dict(policy=lag,source_month='2026-08',last_observation='2026-08-31',age_on_oct23=53,max_age_days=120,original_lag_and_existing_observation_retained=True,actual_vintage_verified=False))
 a=stats['post_scaler'].transform(np.column_stack([a]+pcs));a=np.column_stack([a]+rawf)
 for lag in ['NEXT20','MONTH2_FIRST']:names.extend(lag+'::'+c for c in f.columns)
 keep=stats['cross_nonconstant_mask'];assert len(names)==len(keep);a=a[:,keep];names=[c for c,k in zip(names,keep) if k];assert names==stats['cross_feature_names'] and np.isfinite(a).all();np.savez_compressed(O/'기존10월전처리_모든조합입력_NO_Y.npz',dates=x.index.strftime('%Y-%m-%d').to_numpy(dtype='U10'),feature_names=np.array(names,dtype='U160'),values=a)
 masks=load(trroot/'FEATURE_MASKS.json');readiness=[]
 for mask,selected in masks.items():
  ix=[names.index(c) for c in selected];assert np.isfinite(a[:,ix]).all();readiness.append(dict(combination=mask,fixed_selected_features=len(selected),complete_days_after_original_preprocessing=len(x),original_october_mask_unchanged=True,algorithm_refitted=False))
 assert len(readiness)==16;save(pd.DataFrame(readiness),'고정16개조합_입력준비검증.csv');save(pd.DataFrame(french_line),'French_동일규칙_대조.csv')
 # Preserve feature audit for every cell before and after structural imputation.
 save(pd.DataFrame([dict(feature=c,raw_complete_days=int(x[c].notna().sum()),raw_missing_days=int(x[c].isna().sum()),complete_days_after_original_imputation=int(imputed[c].notna().sum()),total_days=12) for c in x]),'변수216_원값_대치후_확보현황.csv')
 assert all(sha(p)==h for p,h in HASH.items());js('보호원본_SHA256.json',HASH)
 summary=dict(status='PASS_SAME_RULES_INPUT_PREPARATION_CONDITIONAL_HISTORY',original_october_dates_verified=5,additional_dates=12,end='2026-10-23',original_X_rows_preserved=len(old),feature_columns=216,features_removed=0,source32_added_feature_count=4,source32_filled_cells=48,source32_original_observation='2026-07-01',source32_extension_observation='2026-07-01',source32_age_on_oct23=114,source32_max_age=120,source32_last_valid_date_under_existing_rule='2026-10-29',raw_complete_columns=215,raw_missing_columns=['s52_unrate_gap12_pp'],structural_imputed_cells=len(imputation),median_training_cutoff='2026-09-30',all216_finite_after_saved_train_median=True,fixed_masks_verified=16,all_masks_finite_after_saved_preprocessing=True,original_transform_sha256=sha(statsfile),original_raw_unchanged=True,original_training_X_unchanged=True,feature_selection_changed=False,models_loaded=0,new_fit=0,prediction=0,scoring=0,no_Y_read=True,actual_original_release_verified=False,ready_for_frozen_model_inference_as_conditional_scenario=True,latest_official_Taiwan_August_and_September_raw_still_missing=True)
 js('동일규칙_최종검증.json',summary)
 pointer=load(B/'LATEST_INPUT_PREPARATION.json');pointer.update(active_preparation=str(O),previous_preparation=str(P),additional_X=str(O/'추가12일_X216_기존규칙유지_NO_Y.csv'),full_X=str(O/'전체기간_X216_기존규칙유지_NO_Y.csv'),preprocessed_inputs=str(O/'기존10월전처리_모든조합입력_NO_Y.npz'),ready_for_all_experiments=True,readiness_scope='existing frozen models conditional history; not new independently verified PIT dataset',rules_changed=False,no_model_runs=True);(B/'LATEST_INPUT_PREPARATION.json').write_text(json.dumps(pointer,ensure_ascii=False,indent=2),encoding='utf-8')
 text=f'''# 10월1~7일과 같은 규칙으로 확장 입력 연결

## 확인 결과

원래10월1·2·5·6·7일의입력과공개시점기록을대조했음. 대만전자제품수출주문은5일모두2026년7월자료였고공개경계는8월20일04:30ET였음. 원래규칙은보유자료중공개경계가지난최신관측을선택하고관측월표시일부터120일이내만사용하는방식임. 새관측이없다는이유만으로관련변수를제외하는규칙은없었음.

따라서10월8~23일에도7월의4개변수를같은규칙으로연결했음.23일관측나이는114일로120일이내임. 7월값의유효마지막날은10월29일이며30일부터는새관측없으면원래규칙상결측임. 7월1일은관측월표시이지실제발표일이아님.

기존확장준비에서이4개열을새로일괄차단했던부분을되돌렸음. 이전의'7월값유지는임의연장'이라는설명은기존규칙과맞지않았음. 이번복원은실제공개된가장최신통계가7월이라는뜻이아니라보유파일을사용하는기존조건부역사시나리오를유지한것임.8·9월통계원본미확보한계는남음.

## 결측과 전처리

216개변수는모두유지했음. 원자료로12일모두값이있는변수는215개임. 남은s52_unrate_gap12_pp는월별원자료공백때문이며기존10월학습전처리에저장된중앙값으로만대치했음. 그중앙값의학습자료는2011년부터2026년9월30일까지임.10월평가값이나정답으로중앙값을다시계산하지않았음. 원값과대치후값·각대치근거를별도파일로저장했음.

기존저장표준화·French두지연시나리오PCA·월별중복축소마스크도그대로적용해16개고정조합의모든입력이유한한지확인했음. French는공식최신파일의8월관측만사용하고기존120일제한과공개지연가정을유지했음. 최초배포본이검증된것은아님.

## 검증 범위

- 기존10월1~7일월별자료입력과기존공개경계재현.
- 기존과거X {len(old)}행·216열의값과결측불변.
- 추가12일에서대만4개열외입력불변.
- 각관측의공개경계가09ET이전이며노후제한이내임을확인.
- 저장학습중앙값과실제9월말까지학습X의중앙값일치.
- 기존표준화·PCA만transform하고새fit0회,고정16개마스크변경0개.
- 원RAW·기존실험결과변경없음. 정답읽기·학습·예측·성능평가0회.

입력준비는기존조건부규칙하에서완료했음. 이후예측실험시에도10월모형은9월말까지학습된동일모형을사용해야함. 이준비완료가공개수신시각·수정전배포값이모두입증됐거나독립미열람시험이됐다는뜻은아님.
''';(O/'동일규칙_적용결과.md').write_text(text,encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');warnings.filterwarnings('ignore',category=pd.errors.PerformanceWarning);main()
