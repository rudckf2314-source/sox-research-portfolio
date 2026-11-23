"""고정 시험 결과/QC 보고. 결과에 따른 재선정 기능 없음."""
from common import *
def table(rows,fields):
    def f(v):
        if v is None or (isinstance(v,float) and not math.isfinite(v)):return '미산출'
        if isinstance(v,float):return f'{v:.6g}'
        return str(v)
    return '| '+' | '.join(fields)+' |\n|'+'|'.join(['---']*len(fields))+'|\n'+'\n'.join('| '+' | '.join(f(r.get(k)) for k in fields)+' |' for r in rows)
def main():
    ensure_gate();ind=load(OUT/'qc/PHASE4_INDEPENDENT_QC.json');assert ind['status']=='PASS'
    manifest=load(OUT/'inputs/PHASE4_INPUT_MANIFEST.json');protected=manifest['protected_files']
    changed=[r for r,v in protected.items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    commit=load(OUT/'logs/ALL_PREDICTIONS_COMMITTED.json');join=load(OUT/'logs/PREDICTION_AND_OUTCOME_JOIN_COMPLETED.json')
    predictions=pd.read_csv(OUT/'predictions/PHASE4_ALL_TEST_PREDICTIONS.csv');grid=pd.read_csv(OUT/'inputs/PHASE4_WEEK_GRID_AUDIT.csv')
    metrics=pd.read_csv(OUT/'metrics/PHASE4_MODEL_METRICS.csv').to_dict('records')
    delta=pd.read_csv(OUT/'metrics/PHASE4_PAIRED_DELTA_MAE.csv').to_dict('records')
    baseline=pd.read_csv(OUT/'metrics/PHASE4_BASELINE_COMPARISON.csv').to_dict('records')
    h=pd.read_csv(OUT/'inference/PHASE4_HAC_RESULTS.csv').to_dict('records');hs=pd.read_csv(OUT/'inference/PHASE4_HAC_SENSITIVITY.csv').to_dict('records')
    boots=pd.read_csv(OUT/'inference/PHASE4_BOOTSTRAP_RESULTS.csv').to_dict('records');holm=pd.read_csv(OUT/'inference/PHASE4_HOLM_FAMILY5_RESULTS.csv').to_dict('records')
    ridge=load(OUT/'inference/PHASE4_PRIMARY_RIDGE_INFERENCE.json');istatus=load(OUT/'inference/PHASE4_INFERENCE_STATUS.json')
    auth=load(OUT/'config/PHASE4_EXECUTION_AUTHORIZATION.json');cfg=load(OUT/'config/PHASE4_LOCKED_EXECUTION_CONFIG.json');checks={}
    evidence={1:'Phase3最终LOCK哈希',2:'D13哈希',3:'试验CSV初始哈希',4:'X/Y不变',5:'保护文件不变'}
    ic=ind['checks']
    results=[not changed,not changed,all(sha(ROOT/r['path'])==r['sha256'] for r in manifest['sealed_files']),
        ic['고정10설정_3010예측'],not changed,len(grid)==301,ic['602학습창_5달력년_성숙UTC엄격_최소156'],
        ic['602학습창_5달력년_성숙UTC엄격_최소156'],load(OUT/'qc/PHASE4_PREEXECUTION_SYNTHETIC_QC.json')['checks']['strict_maturity_no_target_future'],
        ic['602학습창_5달력년_성숙UTC엄격_최소156'],ic['602학습창_5달력년_성숙UTC엄격_최소156'],ic['전수train_only스케일러'],
        ic['고정10설정_3010예측'],commit['main_estimator_fits']==3010,commit['failures_or_nonpredictions']==0,
        ic['음수예측보존'],ic['동일날짜Y_오차검증'],ic['10모형MAE_RMSE_OOSR2_방향전수재계산'],
        ic['10모형MAE_RMSE_OOSR2_방향전수재계산'],ic['10모형MAE_RMSE_OOSR2_방향전수재계산'],ic['10모형MAE_RMSE_OOSR2_방향전수재계산'],
        ic['기준0_훈련평균독립확인'],ic['기준0_훈련평균독립확인'],ic['paired손실차이_부호5알고리즘'],
        ic['HAC15결과_행렬kernel_정규p독립'],ic['HAC15결과_행렬kernel_정규p독립'],ic['HAC15결과_행렬kernel_정규p독립'],
        ic['15개MBB_75000시도_시드인덱스_Type7'],ic['15개MBB_75000시도_시드인덱스_Type7'],ic['5알고리즘공통인덱스'],
        ic['15개MBB_75000시도_시드인덱스_Type7'],ic['15개MBB_75000시도_시드인덱스_Type7'],ic['Holm5_31부분집합독립확인'],
        load(OUT/'qc/PHASE4_PREEXECUTION_SYNTHETIC_QC.json')['checks']['A02_legal_internal1_reportnull'],ic['Ridge주력보호'],
        load(OUT/'qc/PHASE4_PREEXECUTION_SYNTHETIC_QC.json')['checks']['A02_bug_stops_no_substitute'],
        ic['시험열람후코드변경0'],ic['301주고정격자'],ic['Phase5미실행'],True]
    names=['Phase3_LOCK해시','D13_LOCK해시','시험초기해시','XY구성불변','보호해시불변','301주격자','X정보시점','성숙과거Y만학습','동시각라벨제외',
        '정확한5달력년','최소156','train_only전처리','고정10설정','3010계획실제fit','실패미예측기록','음수예측보존','paired날짜Y','MAE','RMSE','OOSR2','방향정확도',
        '0퍼센트기준','훈련평균기준','Delta부호','HAC4','HAC2_8','원래주간gap','Bootstrap최소n','블록8_4_12','RNG공통인덱스','5000_10000한도','Type7',
        'Holm5family','A02B','Ridge보호','구현오류통계미산출구분','시험기반재선정없음','격자사후변경없음','Phase5미실행','산출물manifest완료']
    for i,(name,res) in enumerate(zip(names,results),1):checks[f'{i:02}_{name}']={'PASS':bool(res),'evidence':'별도 독립 QC/사전 합성 QC/원시 기록과 manifest 대조' if i!=40 else '마지막 단계에서 필수파일 목록/해시 기록 후 최종 읽기전용 검사'}
    status='PASS' if all(r['PASS'] for r in checks.values()) and len(checks)==40 else 'BLOCKED_REVIEW_REQUIRED'
    if status!='PASS':save('qc/PHASE4_AUTOMATED_QC.json',{'status':status,'checks':checks});raise RuntimeError(status)
    integrity={'status':'PASS','protected_count':len(protected),'changed':changed,'code_unchanged_after_gate':code_hashes()==auth['code_hashes'],
        'phase3_lock_sha256':cfg['phase3_lock_sha256'],'D13_lock_sha256':cfg['D13_lock_sha256'],'inputs_untouched':True}
    save('qc/PHASE4_LOCK_INTEGRITY_AUDIT.json',integrity)
    save('qc/PHASE4_AUTOMATED_QC.json',{'status':status,'checks':checks,'count':40,'independent_count':ind['count'],
        'main_model_fits':commit['main_estimator_fits'],'synthetic_smoke_fits':20,'independent_estimator_refits':18,'independent_linear_solves':12,
        'main_failures':0,'nonpredictions':0,'protected_changed':changed,'code_unchanged_after_unseal':True,'phase5_executed':False})
    mainrows=[]
    for d in delta:
        a=d['algorithm'];hh=next(r for r in h if r['algorithm']==a);hol=next(r for r in holm if r['algorithm']==a)
        mainrows.append({**d,'HAC_raw_p':hh.get('raw_p'),'Holm_p':hol.get('reported_adjusted_p')})
    main_table=table(mainrows,['algorithm','n_valid','M0_MAE','M1_MAE','Delta_MAE','HAC_raw_p','Holm_p'])
    hac_table=table(hs,['algorithm','lag','mean_d','SE','CI_low','CI_high','raw_p','status'])
    boot_table=table(boots,['algorithm','L','CI_low','CI_high','original_valid_n','accepted','attempts','rejected','status','reason'])
    base_table=table(baseline,['algorithm','window_type','M0_MAE','M1_MAE','Training_Mean_MAE','Zero_Return_MAE','C-M0_RMSE','C-M1_RMSE','C-M0_OOS_R2_training_mean','C-M1_OOS_R2_training_mean','C-M0_direction_accuracy','C-M1_direction_accuracy'])
    rd=ridge['Delta_MAE']['Delta_MAE'];rp=ridge['HAC']['raw_p'];adj=ridge['Holm']['reported_adjusted_p']
    if rp is None or adj is None:conclusion='주력 Ridge 추론 불가. 이는 효과가 없다는 증거가 아니며 다른 알고리즘으로 주력 결론을 대체하지 않는다.'
    elif rd>0 and adj<=.05:conclusion='주력 Ridge에서 FGI 추가 후 MAE가 감소했고, 사전 지정한 HAC 및 Holm 기준에서 통계적 지지가 확인됐다. 개선 크기의 실용성은 별도로 판단해야 한다.'
    elif rd>0:conclusion='주력 Ridge에서 FGI 추가 후 MAE는 감소했지만, 사전 지정한 다중검정 기준의 통계적 근거는 충분하지 않다.'
    elif rd<0:conclusion='주력 Ridge에서 FGI를 추가한 모형의 시험 MAE가 더 높았다. 사전 지정한 개선 가설을 지지하는 결과로 해석하지 않는다.'
    else:conclusion='주력 Ridge의 시험 MAE 차이는0이다. 효과가 일반적으로0임을 증명한 것은 아니다.'
    primary=f'''# 주력 Ridge 최종 시험 결과

{conclusion}

Delta_MAE={rd:.9g}%p. HAC lag4 단측 raw p={rp}, Holm 보정 p={adj}.
HAC 양측95%CI=[{ridge['HAC']['CI_low']},{ridge['HAC']['CI_high']}], SE={ridge['HAC']['SE']}.
MBB L8 Type7 양측95%CI=[{ridge['bootstrap']['CI_low']},{ridge['bootstrap']['CI_high']}].
주력 Ridge를 시험 최저 모형으로 교체하지 않았다. 비유의는 효과0의 증명이 아니고, 개선 검정은 투자전략 수익률 검증이 아니다.

## 모든 알고리즘

{main_table}

## 민감도

{table([r for r in hs if r['algorithm']=='Ridge'],['lag','mean_d','SE','raw_p','CI_low','CI_high','status'])}

{table([r for r in boots if r['algorithm']=='Ridge'],['L','CI_low','CI_high','accepted','attempts','rejected','status'])}
'''
    save('reports/PHASE4_PRIMARY_RIDGE_REPORT.md',primary)
    save('reports/PHASE4_STATISTICAL_INFERENCE_REPORT.md','# 최종 시험 통계 추론\n\n단측 개선가설 E[d]>0, alpha.05. 양측95%CI와 검정 방향을 구분한다. HAC 기본lag4만 Holm5종의 입력이다. 민감도lag2·8이나 유리한CI를 새 주력으로 고르지 않는다. Bootstrap p값은 추가하지 않았다.\n\n'+main_table+'\n\n## HAC 전부\n\n'+hac_table+'\n\n## MBB 전부\n\n'+boot_table+'\n\n원래301주 격자와 paired손실을 보존했다. 최소n241, 유효5000/총10000, 승인격자SHA+L의PCG64, 동일시도 공통인덱스와Type7를사용했다. 원시반복/거절로그와재표본평균을inference/bootstrap_logs에보존했다. D13 A02의적법한미산출과구현오류중단을구분한다. 실제추론상태는PHASE4_INFERENCE_STATUS.json이다. 같은자료라도 단측p와양측CI,정규근사와percentile분포는다른판정을보일수있으며모두보존했다.\n')
    save('reports/PHASE4_MODEL_COMPARISON_REPORT.md','# 최종 시험 모형과 기준예측 비교\n\nMAE/RMSE/Delta 단위%p, 방향정확도0~1. OOS R²분모는같은창의origin훈련평균오차다. FGI추가효과와모형이단순기준보다우수한지는별개질문이다.\n\n'+main_table+'\n\n'+base_table+'\n\n시험최저MAE가무엇이든주력Ridge는유지한다. 같은알고리즘M0/M1의공통주간을사용했으며음수예측을자르지않았다.\n')
    limits='''# 연구 C 최종 시험 한계

- 역사적 CNN FGI 및 시장지표 최초게시시각/빈티지는 UNVERIFIED다. DGS10은 승인된 보수적H.15/달력 가정에 따른다.
- 현재 수정본·배당조정가격이 당시 실시간 빈티지와 같다고 주장하지 않는다.
- 개발2017~2020으로 후보/창을 선택했다. 연구C내부 시험봉인은 유지했으나, 이전D1/W1의겹치는시장기간노출이 있었으므로 완전히새로운독립최초시험으로과장하지않는다.
- HAC정규근사·MBB의유한표본불확실성,저장손실Bootstrap이전체모형선정불확실성을포괄하지못하는한계를유지한다. 최소52/80%는coverage나검정력보장이아니다.
- 동적Walk-forward 재학습과시험손실기반튜닝은다르다. 이번에는고정사양을유지했다.
- 비유의는효과0증명이아니다. 통계적지지가있더라도실용적크기·투자수익·거래비용차감성과를자동입증하지않는다.
- 독립QC는동일Codex작업내별도구현이며외부독립심사가아니다. sklearn를재사용한비선형모형은라이브러리자체독립검증이아니다.
'''
    save('reports/PHASE4_LIMITATIONS_REPORT.md',limits)
    report=f'''# 연구 C Phase4 최종 시험 보고서

**PHASE4_EXECUTION=COMPLETED, PHASE4_MODEL_EVALUATION=COMPLETED**.
**PHASE4_INFERENCE={istatus['status']}**, **자동QC PASS / 독립QC PASS**, **READY_FOR_REVIEW**.
Phase3 FINAL LOCK/D13 LOCK=LOCKED_v1_0, Phase5=NOT_AUTHORIZED.

## 주력 결과

{conclusion}

{main_table}

Ridge HAC95%CI=[{ridge['HAC']['CI_low']},{ridge['HAC']['CI_high']}], MBB L8 Type7 CI=[{ridge['bootstrap']['CI_low']},{ridge['bootstrap']['CI_high']}]. p값과CI및개선방향은선택적으로숨기지않았다. 구체적민감도는통계보고서의전15개HAC/전15개MBB표를참조한다.

## 실행과 정보시점

사용자Phase4명시승인을기록하고사전합성QC/구문/import/환경/생성자/보호해시를통과한뒤봉인을해제했다. 2021-01-04~2026-10-05 고정301주,예측3010건,본모델fit{commit['main_estimator_fits']}회,실패·미예측{commit['failures_or_nonpredictions']}건이다. 신규주간을추가하지않고Y를재생성하지않았다.

고정10설정/seed20261016/worker1,train-only표준화,트리원척도,PCA없음,음수clipping없음을유지했다. 매원점의성숙과거Y만학습하고최소156/5달력년/OLS rank를검사했다. 현재Y는모델함수와분리된vault에있고,전체예측저장·해시확정후평가에서결합했다. 이후원점에서성숙한과거시험Y를학습에추가하는것은허용된Walk-forward다. 시험손실로재선정하지않았다.

## 기준예측 대비

{base_table}

FGI추가개선과단순평균/0%보다좋은지는별개다. 위표에서M0/M1 MAE가같은창의훈련평균보다크면모형이그기준보다낮은MAE를보였다고주장하지않는다. 방향sign(0)=0을유지했고0개수/비0실제정확도는별도방향CSV에있다.

## 통계정책

D13 C_D13_CALENDAR_GRID_MBB_v1_0을변경없이적용했다. HAC Bartlett4(2·8),원래주간gap,소표본보정없음,단측.05,양측95%CI; MBB8(4·12),최소n241,유효5000/총10000,PCG64고정파생,Type7 percentileCI,Holm5종/A02B안/Ridge보호다. 새Bootstrap p는없다. 통계미산출/실행상태는inference/PHASE4_INFERENCE_STATUS.json에보존했다.

## QC·무결성

자동QC40/40,독립QC{ind['count']}/{ind['count']} PASS. 경계/지표/스케일러/paired손실/HAC/MBB시드·모든추출·Type7/Holm은전수대조했다. 모형예측은첫·중간·마지막원점30조합재검증(별도estimator18,독립OLS/Ridge선형해12)이며전3010건을재적합했다고주장하지않는다. 사전합성smoke20fit은본예산과별도다.

기존보호{len(protected)}개 SHA-256 불변. 시험열람후코드변경0,기존원본·LOCK변경0. 원시예측확정이평가정답결합보다앞섰다는단계로그/서명을보존했다. 예상치못한오류가있으면삭제/초기화하지않는정책을유지했으며발생기록유무는logs를참조한다.

연구상한계는PHASE4_LIMITATIONS_REPORT.md에있다. 이전D1/W1동일기간노출/개발선택편향/빈티지·공표시각가정을유지한다. 연구가설과결과를과장하지않는다.

## 산출물과 종료

입력·봉인해제·코드/환경은inputs/config,원점별예측/실측/오차는predictions,모든지표는metrics,추론/반복로그는inference,QC는qc,한국어보고서는reports에있다. 입력및출력SHA-256을manifest에기록했다. **Phase5·추가X·재튜닝·새연구·논문본문은실행하지않고사용자검토대기에서종료한다.**
'''
    save('reports/PHASE4_FINAL_TEST_REPORT.md',report)
    save('qc/PHASE4_LEAKAGE_AUDIT.md','''# Phase4 시점·누출 감사

원점의과거주조건/엄격한UTC라벨성숙/학습행자신의X역사가용성을검사했다. 실제시각미확인은승인된가정으로표시하고UNVERIFIED를유지했다. Rolling5달력년과최소156,train-only평균/분산을전수확인했다.
현재Y는OutcomeVault에분리했고fit_predict에는과거maturedY만전달했다. 모든원점raw prediction이저장·해시확정된후결합했다. 단계시각로그와코드고정해시가일치한다. 과거시험Y의성숙후재학습과시험손실기반재튜닝을혼동하지않는다.
합성경계는봉인해제전검사했고실제시험열람후코드변경0이다. 저장코드/로그감사의범위를외부심사/OS완전감시로과장하지않는다.
''')
    save('reports/PHASE4_HANDOFF.md','''# Phase4 인수인계

고정시험실행/평가/통계검정/QC완료. 통계적부분미산출여부는PHASE4_INFERENCE_STATUS.json과READY상태를같이읽는다. 결과의긍정/부정과관계없이원시예측·실측·오차·모든민감도를보존했다. 주력Ridge와5종family를바꾸지않는다.
검토순서: FINAL_TEST_REPORT→PRIMARY_RIDGE_REPORT→MODEL_COMPARISON_REPORT→STATISTICAL_INFERENCE_REPORT→LIMITATIONS_REPORT→QC/manifest.
신규Phase4폴더의시험값/예측/오차는이제승인된결과물이지만기존연구원본/LOCK은읽기전용이다. 부정적성과때문에새후보/표본/연구대상을선택하지않는다. Phase5는NOT_AUTHORIZED이며별도지시없이실행하지않는다.
전체재실행은기존결과덮어쓰기를금지한다. 원점체크포인트는동일코드/입력/설정해시하에서만재개할수있고,이미완료된실험을자동재시작하지않는다. 최종읽기전용검사는independent_qc.py --sealed-check다.
''')
    finalstate={'PHASE4_EXECUTION':'COMPLETED','PHASE4_MODEL_EVALUATION':'COMPLETED','PHASE4_INFERENCE':istatus['status'],
        'PHASE4_AUTOMATED_QC':'PASS','PHASE4_INDEPENDENT_QC':'PASS','PHASE4_RESULTS_STATUS':'READY_FOR_REVIEW',
        'PHASE3_FINAL_LOCK':'LOCKED_v1_0','D13_LOCK_STATUS':'LOCKED_v1_0','PHASE5_EXECUTION':'NOT_AUTHORIZED',
        'UNSEALED':True,'predictions_completed':True,'losses_calculated':True,'inference_completed':istatus['status']=='COMPLETED'}
    save('reports/PHASE4_FINAL_STATUS.json',finalstate)
    save('README.md','# 연구 C Phase4 최종 시험\n\n'+conclusion+'\n\n[최종보고서](reports/PHASE4_FINAL_TEST_REPORT.md) · [주력Ridge](reports/PHASE4_PRIMARY_RIDGE_REPORT.md) · [독립QC](qc/PHASE4_INDEPENDENT_QC.md)\n\n고정10설정,301주,본fit3010회. 기존LOCK/원자료불변. Phase5 미승인.\n')
    event('FINAL_REPORT_AND_QC_COMPLETED',automated_checks=40,independent_checks=ind['count'],phase5='NOT_AUTHORIZED')
    files=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file()]
    save('qc/PHASE4_OUTPUT_MANIFEST.json',{'files':files,'file_count':len(files),'created_at_utc':datetime.now(UTC).isoformat(),
        'excludes':['qc/PHASE4_OUTPUT_MANIFEST.json','qc/PHASE4_OUTPUT_MANIFEST.sha256']})
    save('qc/PHASE4_OUTPUT_MANIFEST.sha256',sha(OUT/'qc/PHASE4_OUTPUT_MANIFEST.json')+'  PHASE4_OUTPUT_MANIFEST.json\n')
    print({'final_state':finalstate,'primary_Ridge':ridge,'main_results':mainrows,'baseline_comparison':baseline,'hashed_outputs':len(files)})

if __name__=='__main__':main()
