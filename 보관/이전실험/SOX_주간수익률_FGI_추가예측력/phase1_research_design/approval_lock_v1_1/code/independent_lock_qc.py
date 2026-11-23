"""Independent direct comparison to source draft/approval; no builder/QC imports."""
from pathlib import Path
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo
import json,csv,hashlib,math
L=Path(__file__).resolve().parents[1];O=L.parent;ROOT=O.parents[1]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    entries=[]
    def ck(name,result,evidence):entries.append({'check':name,'pass':bool(result),'evidence':evidence})
    spec=load(L/'PHASE1_LOCKED_SPEC_v1_1.json');approved=load(L/'PHASE1_APPROVED_DECISIONS.json');gates=load(L/'PHASE1_GATE_REGISTER.json')
    a={r['decision_id']:r for r in approved['decisions']};user=(L/'inputs/USER_APPROVAL_INSTRUCTION.txt').read_text(encoding='utf-8-sig')
    ck('all_user_decision_ids',{f'D{i:02}' for i in range(1,15)}==set(a) and all(f'D{i:02}' in user for i in range(1,15)),'Read all approval text and verify every decision is present exactly once in JSON.')
    ck('conditional_decisions_not_flattened',all(a[d]['approval_status']=='APPROVED_CONDITIONAL' for d in ['D02','D08','D09','D10']) and a['D04']['approval_status']=='APPROVED','D04 is explicitly approved A; conditional wording in user instruction retained.')
    ck('D04_D14_noncontradiction',spec['information_availability']['time_fields']['availability_basis']==['VERIFIED_ACTUAL','ASSUMED_CONSERVATIVE','UNAVAILABLE'] and spec['origin']['strict_comparator']=='<' and spec['fgi']['actual_historical_posting_status']=='UNVERIFIED','Assumed eligibility is separate from real strict-before proof; no verification upgrade.')
    # Synthetic clock-only fixture. It is not an actual RAW/as-of calculation.
    ny=ZoneInfo('America/New_York');assumed=datetime(2026,1,20,8,tzinfo=ny);origin=datetime(2026,1,20,9,tzinfo=ny)
    fixture={'actual_release_at':None,'actual_available_at':None,'assumed_available_at':assumed.isoformat(),'availability_basis':'ASSUMED_CONSERVATIVE'}
    ck('synthetic_holiday_clock_and_equality',assumed<origin and not origin<origin and fixture['actual_release_at'] is None and datetime(2026,7,15,9,tzinfo=ny).astimezone(timezone.utc).hour==13,'Toy fixture skips a supplied mock holiday; actual timestamps remain null, equal-to-origin is ineligible; DST test is clock-only.')
    mock_sessions=[date(2026,1,9),date(2026,1,12),date(2026,1,13),date(2026,1,14),date(2026,1,15),date(2026,1,16),date(2026,1,20)]
    targets=mock_sessions[1:6];shifted=[mock_sessions[mock_sessions.index(d)-1] for d in targets]
    ck('one_session_shift_not_drop_friday',len(shifted)==len(targets)==5 and shifted[0]==mock_sessions[0] and shifted[-1]==mock_sessions[4] and spec['information_availability']['sensitivity_fgi_source_shift_sessions']==1,'Supplied synthetic session list only; preserve target count, shift source one session; no financial scores/weekly matrix produced.')
    ck('80pct_expected_sessions_threshold',[math.ceil(.8*n) for n in [1,2,3,4,5]]==[1,2,3,4,4] and spec['fgi']['complete_case_sensitivity_fraction']==1,'Arithmetic-only coverage thresholds. Denominator is expected sessions and not only observed rows.')
    original=load(O/'design/PHASE1_RESEARCH_SPEC_DRAFT.json')
    ck('unchanged_weekly_Y_and_information_sets',spec['target']['formula']==original['confirmed']['target'] and spec['information_sets']['C-M0']['features']==original['information_sets']['C-M0'] and spec['information_sets']['C-M1']['features']==original['information_sets']['C-M1'],'Compare source draft arrays/formula directly; no daily Y or PCA imported.')
    with (O/'design/PHASE1_FEATURE_DICTIONARY.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    source={r['variable_id']:r for r in rows};diff=[]
    for fid,r in spec['core_variables'].items():
        for key in ['formula','raw_paths','source_columns','unit','missing_holiday_policy','warmup']:
            if r[key]!=source[fid][key]:diff.append((fid,key))
    ck('B10_RSI_other_formulas_unchanged',not diff,str(diff)+'; old approval annotations are explicitly source-history, new status is separate.')
    asearch=load(L/'PHASE1_LOCKED_SEARCH_CONFIG_v1_1.json')['algorithms'];osearch=load(O/'design/PHASE1_SEARCH_BUDGET_DRAFT.json')['algorithms']
    old_flat={(alg,r['candidate_id']):r for alg,items in osearch.items() for r in items};new_flat={(alg,r['candidate_id']):r for alg,items in asearch.items() for r in items}
    ck('exact18_candidate_parameter_records',new_flat==old_flat and len(new_flat)==18,'Independent flatten by algorithm/candidate_id; all hyperparameters preserved, no candidates resampled.')
    ck('Ridge_primary_development_only',spec['learning']['primary_algorithm']=='Ridge' and '2017-2020' in spec['learning']['primary_window_selector'] and not spec['split']['test_results_for_selection'],'Ridge pair uses Ridge M0 development-selected window; all five algorithms still reported.')
    ck('approved_sensitivity_overrides_old_values',spec['inference']['HAC']['sensitivity_lags']==[2,8] and spec['inference']['MBB']['sensitivity_block_weeks']==[4,12],'Explicit latest user values supersede draft1/8 and4/13; no performance consulted.')
    d10=gates['gates']['D10'];d13=gates['gates']['D13']
    ck('D10_prevents_ungated_dataset_build',d10['gate_status']=='PENDING_PHASE2_PREBUILD_AUDIT' and 'substantive_weekly_XY_build' in d10['blocks'] and not d10['passed'] and not d10['audit_executed'] and not d10['generic_D04_assumption_exemption'],'Gate policy inspected only. H15 availability audit itself was not performed.')
    ck('D13_details_deferred_before_error_access',d13['detail_status']=='DEFERRED_LOCK' and all(v is None for v in d13['unresolved'].values()) and not d13['passed'] and 'Phase4 final-test prediction errors or performance results' in d13['must_lock_before'],'No minimum n/redraw rule invented. Requires actual Phase2 missingness then separate pre-error lock.')
    ck('no_Phase2_permission',not spec['phase2_execution_approved'] and all(v==0 for v in spec['execution_counts'].values()) and not any(p.name.startswith(('phase2_','phase3_','phase4_','phase5_')) and p.is_dir() for p in O.parent.iterdir()),'No future Phase directory and no research pipeline invocation. Not OS-wide process surveillance.')
    snapshot=load(L/'inputs/PHASE1_LOCK_INPUT_MANIFEST.json');bad=[];index=[]
    for rel,item in snapshot['protected_files'].items():
        p=ROOT/rel
        if not p.is_file():bad.append(rel);continue
        with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
        if h!=item['sha256']:
            if rel=='RESEARCH_PROJECT_INDEX.md' and hashlib.sha256(p.read_bytes()[:item['bytes']]).hexdigest()==item['sha256']:index.append(rel)
            else:bad.append(rel)
    ck('independent_hashes_originals_preserved',not bad,f"Checked {len(snapshot['protected_files'])}; unauthorized={bad}; authorized index append={index}")
    ck('partial_lock_not_false_full_lock',spec['status']=='PHASE1_DESIGN_LOCKED_WITH_GATES' and not spec['all_gates_passed'],'All accepted parts locked; D10/D13 not passed and no Phase2 authorization implied.')
    passed=all(r['pass'] for r in entries)
    out={'qc_status':'QC_PASS' if passed else 'QC_FAIL','overall_status':spec['status'],'test_count':len(entries),'checks':entries,'unauthorized_changes':bad,'authorized_index_append':index,
      'scope':'Independent code paths by same agent; no builder/automatic-QC imports and no external reviewer claim. Synthetic clocks/session lists are not historical as-of mapping. D10/D13 factual audits not performed.'}
    if not (L/'qc/LOCK_FINALIZATION.json').exists():
        (L/'qc/PHASE1_LOCK_INDEPENDENT_QC.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
    text='# Phase1 v1.1 독립 LOCK QC\n\n'+out['qc_status']+'; 전체 상태 '+spec['status']+'.\n\n|검사|결과|근거/범위|\n|---|---|---|\n'
    text+='\n'.join(f"|{r['check']}|{'PASS' if r['pass'] else 'FAIL'}|{r['evidence']}|" for r in entries)
    text+='\n\n검증코드는 작성코드/자동QC를 import하지 않는다. 동일 에이전트의 별도 구현 검증이며 외부 연구자 심사는 아니다. 실제 공개시각·빈티지의 사실 검증, D10 사전감사, D13 결손감사·규칙 잠금은 수행하지 않았다. 합성 날짜/관측률 검사는 승인된 논리의 예시이며 실제 주간 X/Y를 생성하지 않았다.\n'
    if not (L/'qc/LOCK_FINALIZATION.json').exists():
        (L/'qc/PHASE1_LOCK_INDEPENDENT_QC.md').write_text(text,encoding='utf-8')
    print(json.dumps({'independent_qc':out['qc_status'],'checks':len(entries),'failed':[r['check'] for r in entries if not r['pass']]}))
    assert passed
if __name__=='__main__':main()
