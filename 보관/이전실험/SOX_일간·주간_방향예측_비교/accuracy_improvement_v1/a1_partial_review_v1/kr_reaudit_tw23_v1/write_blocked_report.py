"""Document the failed gate and read-only impact assessment; no experiments."""
import json,hashlib
from pathlib import Path
import pandas as pd
from audit_kr_independent import O,P,D,ROOT,K,S,sha,native,calc,savecsv,savejson,snapshot
def table(df,cols):
    x=df[cols].copy().map(lambda v:f'{v:.4f}' if isinstance(v,float) else str(v))
    return '| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(r)+' |' for r in x.to_numpy().tolist())+'\n'
def main():
    I=O/'impact_assessment';a=json.loads((I/'ASSESSMENT_SUMMARY.json').read_text());assert a['overall_gate']=='FAIL_STOP_STAGE2';assert not (O/'FINAL_STATUS.json').exists()
    counts=pd.read_csv(I/'STALE_SELECTION_COUNTS_BY_YEAR.csv',dtype={'source':str});detail=pd.read_csv(I/'STALE_SELECTION_DETAILS.csv',dtype={'source':str});met=pd.read_csv(I/'RECOMPUTED_KR_METRICS.csv');kr=detail[detail.source=='01'];kcounts=pd.read_csv(I/'KR_EXPOSURE_COUNTS_BY_YEAR.csv')
    # Explicit raw rows for the actually used fallback input in each boundary example.
    dd,vv,rr=native(ROOT/'data/raw/01_kodex_091160/01_kodex_091160_RAW_20110101_20261007.csv');position={d:i for i,d in enumerate(dd)};ex=pd.read_csv(I/'BOUNDARY_EXAMPLES.csv');fallback=[]
    for r in ex[~ex.applied].itertuples():
        if not isinstance(r.saved_fallback_source,str) or r.saved_fallback_source not in position:continue
        j=position[r.saved_fallback_source];key=r.feature.split('_',1)[1];off=[0,1] if key=='ret1' else [0,5] if key=='ret5' else [0,20] if key=='ret20' else list(range(20)) if key=='ma20_gap' else list(range(21))
        for lag in off:
            if j-lag>=0:fallback.append(dict(example_date=r.date,feature=r.feature,role='ACTUALLY_USED_PAST_FALLBACK_INPUT',selected_source_date=r.saved_fallback_source,raw_Date=dd[j-lag],raw_Close=vv[j-lag],saved_X=r.saved_X,manual_fallback_X=calc(vv,j,key)))
    savecsv(I/'EXAMPLE_ACTUAL_FALLBACK_INPUT_ROWS.csv',fallback)
    summary=detail.groupby('source').agg(affected_dates=('date','nunique'),feature_cells=('feature','size'),different_value_cells=('value_differs','sum')).reset_index();savecsv(I/'STALE_SELECTION_COUNTS_BY_SOURCE.csv',summary)
    report=f'''# 한국 독립 재검증에서 정렬 문제 발견 — 대만 실행 중단

**1단계 gate는 FAIL이며 2단계 A1_TW23_ONLY는 실행하지 않았다. 신규 학습0회, 새 모델0개다.** 사용자 지시에 따라 기존 결과·RAW·계획·모델을 수정하지 않고, 실패와 영향 조사를 새 경로에 보존했다. 이 FAIL은 저장 Accuracy의 산술 오류를 뜻하지 않는다.

독립 계산에서 한국 후보의 **591/1,007일(58.69%), 비상승143일·상승448일 적중**은 확인했다. 같은 날짜의 R0는 비상승88일·상승461일 적중이다. 따라서 비상승55일을 더 맞히고 상승13일을 덜 맞혀 순증42일이라는 기존 집계도 유지된다. 그러나 비교 기준 R0의 일부 원천 정렬이 문서화된 ‘최신 완료 과거정보’와 달라, 입력·비교 기준의 완전한 재검증을 통과한 결과로 확정할 수 없다. 수정 후 모델의 성능은 이번 조사로 알 수 없다.

## 발견한 문제와 재현 근거

development_revision_v1/code/run_comparison.py:72에서 원천 관측을 다음 실제 미국 거래일로 매핑한 뒤, available_date만 sort_values하고 drop_duplicates(keep='last')한다. 한국이나 대만이 거래한 미국 휴장일 전후에는 서로 다른 원천일이 같은 available_date에 묶인다. 이때 단일 키 정렬은 동률의 원천일 순서를 보장하지 않아, 최신 원천일이 아닌 더 오래된 행이 남을 수 있다. 현재 환경에서 이 단일 키 정렬을 재현했으며 저장된 잘못된 source_date와 대조했다.

예를 들어2011-07-05에는 한국2011-07-01과07-04가 모두미국07-05 08시에가용한것으로매핑된다. 정규정책상더최신인07-04를택해야하지만저장R0는07-01을선택했다.07-01 Close16050,07-04 Close16400으로 s01_ret1도달라진다. 이는미래정보사용이아니라과거정보의신선도/동률선택문제다.

다른 예시:
-2012-01-17: 저장원천01-13, 최신적격원천01-16.
-2012-11-23: 저장원천11-21, 최신적격원천11-22.

## 영향 범위 — 읽기 전용 계수

아래는R0 전체2,495행에서최신적격원천보다오래된원천을선택한경우다. 날짜는원천별중복제거, feature_cells는특징셀수다. 세원천간같은날이겹칠수있어날짜수를합산해독립일수로해석하면안된다.

'''
    report+=table(summary,['source','affected_dates','feature_cells','different_value_cells'])
    report+='\n한국 대상의 연도별 노출:\n\n'+table(kcounts,['year','older_source_days','feature_cells','inherited_fallback_cells'])
    report+=f'\n한국원천의오래된선택은초기학습기간{a["KR_initial_stale_dates"]}일,평가기간{a["KR_eval_stale_dates"]}일이다. 한국후보의고정마스크가fallback이어서직접계승한날짜는각각{a["KR_initial_inherited_fallback_dates"]}일/{a["KR_eval_inherited_fallback_dates"]}일이다. 나머지경우한국당일값으로대체됐더라도비교기준R0가의도보다오래됐다는문제는남는다. 대만13/23은한국후보의비변경48컬럼에포함돼그기존정렬도계승한다. 이는이번한국코드가대만정렬을새로변경했다는뜻은아니다.\n\n'
    report+='R0의다른미국원천특징에서는이번최신원천불일치가발견되지않았다. 기존최고D/M0는SOX5특징만사용하므로이번아시아특징정렬문제의직접대상은아니다. 다만기존전체연구가완전히무영향이라고확대해주장하지않는다. 가격자체를조작하거나미래라벨을학습한증거는이번검사에서발견하지않았다.\n\n'
    report+='## 추가로 직접 확인한 사실\n\n-한국후보에서실제변경컬럼은s01의5개뿐이며나머지48컬럼값과결측위치는R0와같다(CSV수치허용오차명시).\n-고정마스크·native행계산·fallback의실제값은저장한국데이터와일치한다. fallback은기존R0그대로라그곳의오래된선택도그대로남는다.\n-한국당일채택값의현지마감+2시간을ZoneInfo로미동부origin과별도대조했다. 미국원천은모두이전원천일이며모델53입력에미국당일Close/Y/실현수익률컬럼은없다.\n-native rolling은csv원천행과statistics로별도재계산했다. 선택된실제원천행을기준으로하면저장R0의값계산은일치하지만,선택한행이항상최신인것은아니다.\n-48개월학습행·라벨성숙과학습자료만의중앙값/평균/분산을독립재계산했다. 저장계수와직접sigmoid로1,007일확률·클래스를재현했다. 새학습은하지않았다.\n\n'
    report+=f'직접sigmoid의최대확률오차는{a["max_direct_sigmoid_error"]:.3g}다. 계수의학습과정자체를새로재현한것은아니며,기존fit기록/해시와학습입력·전처리·예측의일치범위를확인했다. 초기FAIL을추가점검PASS로덮어쓰지않는다.\n\n'
    show=met.copy()
    for c in ['accuracy','recall_nonup','recall_up','BA','predicted_up_rate']:show[c]*=100
    report+='## 저장 한국 예측의 독립 재집계\n\n'+table(show,['period','n','TN','FP','FN','TP','correct','accuracy','recall_nonup','recall_up','BA','MCC','AUC','Brier','Log_loss','predicted_up_rate'])
    report+='\n이표는기존저장예측의산술확인이다. 새성능평가나수정정렬모델의성능은아니다. 기존구간·비교표도변경하지않았다. 대만실험은미실행이므로대만의Accuracy/CI/적용실적은보고할수없다. 이전계획의예상적용률과실제실행결과를혼동하지않는다.\n\n'
    report+='## 실제 원천 행 예시와 조건부 가정\n\nBOUNDARY_EXAMPLES.csv는학습/평가기간,여름/겨울,DST전후,2016-08거래시간연장,원천부재/fallback,연초첫관측,2019-11-14특별일과인접일,2020-12제한을보여준다. BOUNDARY_EXAMPLE_RAW_ROWS.csv는그날원천계산창의실제RAW행이다. EXAMPLE_ACTUAL_FALLBACK_INPUT_ROWS.csv는fallback에서실제로사용한과거관측계산창이다. 비채택일의가정상정규시각은실제가용성증거로해석하지않는다. 원천행부재만으로공식휴장을확정하지않는다.\n\n직접검증:원본해시,원천행/가격,날짜/마스크/계산산술,timezone변환,라벨성숙,전처리,저장예측지표. 미입증/가정:마감+2시간실제가용성,실제과거벤더전달,원래vintage동일성,특별세션전기간완전확인. 이번발견은직접구현검사에서나온동률선택문제로,이런일반적역사가용성한계와구분한다.\n\n'
    report+='## 수정안 — 미실행\n\n새버전에서available_date와source_date를함께명시정렬하고그날가용한최신source_date를선택하도록변경하는안을제안한다. 또는명시적그룹내source_date최댓값을선택한다. 동률의가격/중복충돌은별도검증한다. 미국휴장일로여러외국관측이하나의가용일에묶이는경계사례를회귀검증해야한다. 안정정렬만암묵적으로기대하는것보다최신원천선택을명시하는것이맞다.\n\n영향원천의R0입력을새경로에서재구성하고변경셀·결측·시각을먼저검증해야한다. 이후보정R0와같은입력계보의한국/대만후보를별도계획·예산으로비교해야하며,새학습없이계수/예측/Accuracy를고칠수는없다. 기존원본·모델·결과는계속보존한다. 이번에는수정데이터셋·수정모델·대만후보를만들지않았고자동재학습도없다.\n\n사용자의오류발견시중단조건에따라두단계작업을중단상태로보고하고종료한다.2021년이후평가·1W·Phase3·최종시험·신규자료·설치·추가탐색은없다.\n'
    (O/'RESULTS_REPORT.md').write_text(report,encoding='utf-8')
    before=pd.read_csv(O/'PROTECTED_BEFORE.csv');bm={r.path:(r.bytes,r.sha256) for r in before.itertuples()};after=snapshot();am={r['path']:(r['bytes'],r['sha256']) for r in after};changed=[p for p,x in bm.items() if am.get(p)!=x];added=sorted(set(am)-set(bm));assert not changed and not added
    final=dict(status='STOPPED_STAGE1_ERROR',reason='R0 latest-asof source-date tie selection mismatch',stage1_gate='FAIL',KR_saved_accuracy_arithmetic_confirmed=True,KR_correct=591,KR_TN=143,KR_TP=448,stage2_status='NOT_EXECUTED',new_fit_attempts=0,new_model_files=0,protected_before=len(before),protected_after=len(after),changed_existing_files=changed,added_outside_execution=added,old_results_preserved=True,no_corrections_applied=True,no_new_financial_data=True,no_installations=True)
    savejson(O/'FINAL_STATUS.json',final)
    files=sorted(p for p in O.rglob('*') if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','OUTPUT_MANIFEST.sha256']);savecsv(O/'OUTPUT_MANIFEST.csv',[dict(path=p.relative_to(O).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]);(O/'OUTPUT_MANIFEST.sha256').write_text(sha(O/'OUTPUT_MANIFEST.csv')+'  OUTPUT_MANIFEST.csv\n',encoding='ascii')
    print(json.dumps(final,ensure_ascii=False,indent=2));print('Sealed',len(files),'files; no further experiments.')
if __name__=='__main__':main()
