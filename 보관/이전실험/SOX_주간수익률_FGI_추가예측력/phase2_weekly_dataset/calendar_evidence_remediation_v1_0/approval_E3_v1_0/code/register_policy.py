"""사용자 승인 정책 등록 전용. 실제 게시달력·관측 적격성·B10·X/Y는 구현하지 않는다."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parents[1]
AUDIT=OUT.parent
ROOT=OUT.parents[3]
POLICY='C_DGS10_H15_HISTORICAL_CALENDAR_E3_CONDITIONAL_v1'
TIMING='C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1'
INSTRUCTION=Path(r'C:\Users\rudck\.codex\attachments\bb9fe46e-18b7-45ab-907d-c241ed49922c\Pasted text.txt')
E4=['2011-12-26','2012-10-29','2016-01-22','2018-03-02','2019-01-19','2022-12-31']

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def put(rel,obj):
    with (OUT/rel).open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def csvrows(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

def main():
    if (OUT/'INPUT_MANIFEST.json').exists():raise SystemExit('기존 승인 실행 보존. 덮어쓰기 금지.')
    prior=read(AUDIT/'qc/INPUT_MANIFEST.json')
    protected=dict(prior['protected_files'])
    seal=read(AUDIT/'qc/OUTPUT_MANIFEST.json')
    assert sha(AUDIT/'qc/OUTPUT_MANIFEST.json')==(AUDIT/'qc/OUTPUT_MANIFEST.sha256').read_text().split()[0]
    for item in seal['files']:
        p=AUDIT/item['path'];assert sha(p)==item['sha256']
    for p in AUDIT.rglob('*'):
        if p.is_file() and OUT not in p.parents:
            protected[p.relative_to(ROOT).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    changed=[r for r,v in protected.items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    assert not changed,changed
    base=ROOT/'research_C/phase2_weekly_dataset'
    approval=base/'prebuild_D10_audit/approval_v1_0'
    refs=[ROOT/'research_C/phase1_research_design/approval_lock_v1_1/PHASE1_LOCKED_SPEC_v1_1.md',
        approval/'D10_APPROVED_POLICY.md',approval/'D10_GATE_STATUS.json',
        base/'build_v1_0/reports/PHASE2B_REPORT.md',
        AUDIT/'reports/D10_CALENDAR_REMEDIATION_REPORT.md',
        AUDIT/'audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv',
        AUDIT/'audit/H15_CALENDAR_GAP_REGISTER.csv',AUDIT/'audit/H15_EXCEPTION_AND_DELAY_REGISTER.csv']
    readlog=[]
    for p in refs:
        body=p.read_text(encoding='utf-8-sig')
        detail={'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,'characters':len(body),'entire_file_read':True}
        if p.suffix=='.csv':detail['rows_read']=len(csvrows(p))
        readlog.append(detail)
    instruction=INSTRUCTION.read_text(encoding='utf-8-sig')
    put('USER_APPROVAL_INSTRUCTION.txt',instruction)
    put('INPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'정책 승인 등록·문서 QC만','required_reference_read_log':readlog,
        'approval_instruction':{'original_path':str(INSTRUCTION),'sha256':sha(INSTRUCTION),'entire_file_read':True},
        'protected_files':protected,'protected_count':len(protected),'baseline_mismatches':changed,
        'prior_output_manifest_sha256':sha(AUDIT/'qc/OUTPUT_MANIFEST.json'),
        'existing_timing_policy_sha256':sha(approval/'D10_APPROVED_POLICY.json'),
        'note':'.env와 API 키는 읽거나 저장하지 않음. 기존 감사와 승인 폴더는 바이트 보존.'})
    grid=csvrows(AUDIT/'audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv')
    selected=[r for r in grid if r['in_main_audit_period']=='True']
    candidates=[r['calendar_date'] for r in selected if r['evidence_grade']=='E3' and r['publication_candidate_under_rule']=='True']
    assert len(candidates)==637
    assert sorted(r['calendar_date'] for r in selected if r['evidence_grade']=='E4')==E4
    checks=[
        {'id':'E3_C01','requirement':'당시 적용되던 H15 주간 발표·일별 갱신 체계와 부합'},
        {'id':'E3_C02','requirement':'게시 가능한 Federal Reserve Board 영업일임을 날짜별 판정'},
        {'id':'E3_C03','requirement':'공식 확인 휴일·특별폐쇄와 충돌하지 않음'},
        {'id':'E3_C04','requirement':'알려진 발표 지연·누락·정정 근거와 충돌하지 않음'},
        {'id':'E3_C05','requirement':'독립 E1/E2 근거가 있으면 해당 근거를 우선 적용'},
        {'id':'E3_C06','requirement':'실제 게시 미검증 상태를 유지하고 VERIFIED로 승격하지 않음'},
        {'id':'E3_C07','requirement':'게시 가능일 가정과 실제 게시 확인 정보를 별도 필드로 보존'}]
    policy={'policy_id':POLICY,'status':'APPROVED','approval_date_kst':'2026-10-17',
        'study':'C','authorization_scope':'POLICY_REGISTRATION_AND_DOCUMENT_QC_ONLY',
        'relationship':'SUPPLEMENTS_NOT_REPLACES_EXISTING_TIMING_POLICY','timing_policy_id':TIMING,
        'B10':{'formula':'B10_w = 100 × (R[w-1,O] - R[w-2,O])','unit':'bp',
            'selection':'각 원천 주 내부에서 원점 이전 최신 적격 관측 선택',
            'cross_week_automatic_carry':False,'future_fill':False,'interpolation':False},
        'evidence_classification_changed':False,
        'E1':{'rule':'개별 공식 자료에서 확인한 발표일 우선','exact_first_release_time_proven':False},
        'E2':{'rule':'FRED/ALFRED release-level 날짜 근거 사용',
            'DGS10_first_vintage_or_actual_time_automatically_proven':False},
        'E3':{'approval':'CONDITIONAL','calendar_status':'ASSUMED_CALENDAR',
            'candidate_count':637,'candidate_dates':candidates,
            'scope':'본 감사기간의 기존 E3 평일 게시 후보만. 2010 예열이나 다른 E3 날짜의 포괄 승인이 아님.',
            'all_conditions_required':checks,'condition_result_states':['SATISFIED','FAILED','UNRESOLVED'],
            'unresolved_condition_handling':'조건 충족을 입증/정당화하기 전 자동 적격 처리 금지; 보류 사유 기록',
            'all_candidates_automatically_eligible':False,'date_by_date_eligibility_evaluated':False,
            'eligible_date_count':None,'excluded_date_count':None,
            'weekend_or_general_nonpublication_dates_become_publication_dates':False,
            'blanket_every_weekday_published':False,
            'historical_regime_note':'2011~2014 주간 게시·화~금 일별 갱신 구분. ALFRED 기록 부재는 일별 갱신 부재와 같지 않음. 2014 기록 밀도 변화와 2016 형식 변경을 구분.',
            'board_calendar_equals_NYSE_calendar':False},
        'E4':{'approval':'APPROVED_CONSERVATIVE_HANDLING','unresolved_dates':E4,
            'unresolved_event_is_proven_available':False,
            'dependent_observations_automatically_eligible':False,
            'independent_eligible_same_week_observation_allowed':True,
            'whole_week_automatically_deleted':False,'silently_shift_release_date':False,
            'automatically_replace_with_E3':False,'conflict_resolution_claimed':False},
        'timing':{'assumed_release_rule':'관측일 다음 H15 게시 영업일 16:15 America/New_York',
            'assumed_available_rule':'가정 발표일 다음 달력일 08:00 America/New_York',
            'prediction_origin':'대상 주 첫 실제 미국 거래일 09:00 America/New_York',
            'timezone':'America/New_York','DST':True,'eligibility_comparison':'available_at < prediction_origin',
            'known_later_evidence_has_priority':True,'actual_release_at':None,'actual_available_at':None,
            'publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED',
            'calendar_assumption_separate_from_timing_assumption':True,
            'calendar_assumption_policy_id':POLICY,'timing_assumption_policy_id':TIMING},
        'future_lineage_required':['evidence_grade','calendar_assumption_policy_id','timing_assumption_policy_id',
            'calendar_condition_results','calendar_eligibility_reason','source_observation_date',
            'actual_release_at','actual_available_at','assumed_release_at','assumed_available_at',
            'publication_status','vintage_status','known_late_evidence'],
        'phase2B_execution_authorized':False,'D13_rule_lock_authorized':False,
        'weekly_B10_generated':False,'XY_generated':False,'model_or_test_execution':False}
    put('D10_E3_APPROVED_POLICY.json',policy)
    state={'D10_AUDIT':'COMPLETED','D10_TIMING_POLICY':'APPROVED',
        'D10_E3_CALENDAR_POLICY':'APPROVED','D10_E4_CONSERVATIVE_POLICY':'APPROVED',
        'D10_CALENDAR_IMPLEMENTATION_QC':'PENDING','D10_WEEKLY_B10_IMPLEMENTATION_QC':'PENDING',
        'D10_GATE':'CALENDAR_POLICY_APPROVED_IMPLEMENTATION_PENDING',
        'D13_GATE':'PENDING_WEEKLY_MISSINGNESS_AUDIT','D10_FINAL_PASS':False,
        'phase2B_execution_authorized':False,'prior_BLOCKED_record_preserved':True,
        'effective_scope':'이번 승인 정책 상태만 신규 등록. 과거 원본 게이트는 이력으로 유지.',
        'policy_id':POLICY,'timing_policy_id':TIMING}
    put('D10_E3_GATE_STATUS.json',state)
    future=[
        'E1~E4 근거별 게시달력 생성 결과', 'E3 637개 후보 중 조건 충족 날짜 수',
        'E3 제외 날짜와 조건별 제외 사유', 'E4 6개의 영향 관측 및 주간 후보',
        'Board 공휴일·특별폐쇄·지연 처리 정확성', 'DGS10 각 관측의 가정 발표일·이용 가능시각',
        '원점 이전 엄격한 적격성', 'B10 유효 주간 수와 결측',
        'E3 허용·미허용의 표본가용성 비교', '최종 공통표본의 결측 패턴']
    put('D10_E3_DECISION_REGISTER.json',{'policy_id':POLICY,'status':'APPROVED',
        'user_approval_sha256':sha(INSTRUCTION),
        'decisions':{'E3':'637개 후보에 날짜별 7조건 충족 시 가정 허용. 실제 적격 판정은 미실행.',
            'E4':'미해결 이벤트 및 이에 의존한 관측 자동 적격 금지. 독립 적격 주내 관측은 사용 가능.',
            'scope':'정책 등록·문서 QC만','past_records':'원본 보존','D13':'미확정 상태 유지'},
        'future_phase2B_checks':future,'future_checks_executed':False,
        'availability_comparison_is_not_model_performance_analysis':True,
        'additional_execution_approval_required':True,
        'main_evidence_counts_unchanged':dict(Counter(r['evidence_grade'] for r in selected))})
    conditions='\n'.join(f"{i+1}. {r['requirement']}" for i,r in enumerate(checks))
    put('D10_E3_APPROVED_POLICY.md',f'''# D10 역사적 게시달력 E3 조건부 승인 정책

정책 ID: **{POLICY}**. 상태: **APPROVED**. 승인일 2026-10-17 KST.

이번 명시적 사용자 지시를 근거로 정책 등록 및 문서 QC만 수행한다. 기존 `{TIMING}`의 보완 정책이며 이를 대체하지 않는다. 실제 게시달력과 B10·X/Y를 이번에 생성하지 않는다.

## E1/E2 보존

E1 개별 공식 자료의 입증된 발표일을 우선한다. E2는 FRED/ALFRED release-level 날짜 근거다. 어느 등급도 DGS10 개별 관측의 최초 공개시각·빈티지를 자동 입증하지 않는다. 기존 등급은 바꾸지 않는다.

## E3 조건부 허용

기존 감사 본기간 2011-01-01~2026-10-09의 평일 게시 후보 **637일**만 대상으로 다음 조건을 모두 충족할 경우 ASSUMED_CALENDAR를 허용한다.

{conditions}

637일을 일괄 적격 처리하지 않는다. 날짜별 조건은 SATISFIED/FAILED/UNRESOLVED로 추적하도록 규정한다. 조건이 미확인이면 자동 적격 처리하지 않고 근거와 보류 사유를 기록한다. 이번에는 조건별 실제 날짜 판정을 하지 않았으므로 충족·제외 수는 null이다.

2011~2014년 주간 발표·일별 갱신 체계를 구분한다. 당시 화~금 갱신 가능성을 검토할 수 있지만 모든 평일 실제 게시를 확정하지 않는다. ALFRED 2014 기록 밀도 변화와 연준 2016 형식 변경은 별개다. E3 주말 및 일반 비게시일을 이번 승인으로 새 게시일로 만들지 않는다. Board 게시 영업일을 미국 주식 거래일이나 연방휴일과 자동 동치로 취급하지 않는다. 2010 예열의 포괄 가정 승인은 포함하지 않는다.

## E4 보수적 처리

대상 6일: {', '.join(E4)}.

충돌 미해결 발표를 이용 가능성이 입증된 이벤트로 취급하지 않고, 그 불확실한 발표에 의존하는 관측을 자동 적격 처리하지 않는다. 같은 원천 주 내부에 독립적으로 적격인 다른 관측이 있으면 기존 정의대로 사용할 수 있다. 주 전체 자동 삭제, 발표일의 조용한 이동, E3 자동 대체를 금지한다. 충돌이 해소됐다고 표시하지 않는다.

## 시차·산식 유지

관측일 다음 H15 게시 영업일16:15 ET는 assumed_release_at, 다음 달력일08:00 ET는 assumed_available_at이다. America/New_York/DST 및 알려진 더 늦은 근거 우선을 유지한다. 대상 주 첫 미국 세션09:00 ET 원점보다 엄격히 이전이어야 한다. 미확인 actual_release_at/actual_available_at은 null, publication_status/vintage_status는 UNVERIFIED다. 달력 가정과 시각 가정의 정책 ID·근거를 각각 저장한다.

`B10_w = 100 × (R[w-1,O] - R[w-2,O])`, 단위 bp. 각 원천 주 내부 최신 적격 관측을 선택한다. 적격값 없는 주는 결측이며 타 주 자동 이월·미래값 채움·보간은 금지한다. 실제 변수 계산은 하지 않았다.

## 게이트 및 실행 범위

D10_GATE=CALENDAR_POLICY_APPROVED_IMPLEMENTATION_PENDING. 달력 구현 QC와 주간 B10 구현 QC는 PENDING이다. D13_GATE=PENDING_WEEKLY_MISSINGNESS_AUDIT. 기존 BLOCKED 기록은 당시 결과로 보존한다. 정책 승인·문서 QC PASS는 실제 달력/변수 구현 성공이나 최종 D10 PASS가 아니다.

후속 Phase 2-B는 별도 실행 승인이 필요하다. 모델 학습·시험·D13 확정은 승인하지 않았다.
''')
    oldqc=read(AUDIT/'qc/D10_CALENDAR_QC.json')
    report=(AUDIT/'reports/D10_CALENDAR_REMEDIATION_REPORT.md').read_text(encoding='utf-8')
    assert len(oldqc['tests'])==9 and all(oldqc['tests'].values())
    discrepancy={'actual_final_checks':9,'actual_passed_checks':9,'old_report_claimed_checks':8,
        'old_report_8_text_present':'자동 QC 8개' in report,
        'eight_core_checks_plus_one_artifact_check':list(oldqc['tests']),
        'omitted_final_check':'필수 산출물 존재',
        'determination':'최종 JSON은 핵심 8개+필수 산출물 존재 1개=9개. 본문의 무조건적인 8개 통과 표기는 최종 집계 누락에 따른 보고 오류. 수치 조정이나 QC 실패 아님.',
        'prior_report_modified':False,'source_qc_sha256':sha(AUDIT/'qc/D10_CALENDAR_QC.json')}
    put('PRIOR_QC_COUNT_RECONCILIATION.json',discrepancy)
    put('D10_E3_APPROVAL_CHANGELOG.md','''# 승인 변경 이력

2026-10-17 KST: 사용자 A안 명시 승인으로 E3 조건부 달력 가정과 E4 보수적 처리 정책을 신규 등록했다. 기존 시차 정책·산식·등급·RAW·감사·LOCK 및 BLOCKED 결과는 변경하지 않았다.

이전 권고의 추가 달력 승인 필요 상태를 이번 승인 범위에서 해소했다. 실제 구현 QC는 여전히 PENDING이며 Phase 2-B 실행권한은 부여되지 않았다. 과거 원본의 미승인 문구는 당시 이력이다. 현재 정책 상태는 이 폴더의 신규 게이트 파일을 참조한다.

이전 자동 QC 최종 JSON은 9/9다. 본문 8개 표기는 핵심 8개 외 마지막 필수 산출물 확인 1개를 최종 합계에 누락한 보고 오류다. 기존 보고서는 수정하지 않았으며 PRIOR_QC_COUNT_RECONCILIATION.json에 검사명과 해시를 기록했다.
''')
    put('D10_E3_APPROVAL_HANDOFF.md','# D10 E3 승인 인수인계\n\n정책 APPROVED; 실제 구현·주간 B10 QC는 PENDING이다. Phase 2-B 자동 재개 금지. 기존 차단 결과는 이력으로 보존한다.\n\n## 별도 실행 승인 후 검증할 항목\n\n'+
        '\n'.join(f'{i+1}. {x}' for i,x in enumerate(future))+'''

E3 허용·미허용 비교는 표본가용성 QC에 한한다. 모델 성능·강건성 비교는 별도 사전설계와 사용자 승인 전 실행하지 않는다. E3 조건 미확인 날짜는 자동 적격 처리하지 않는다. E4 영향 관측과 주내 독립 적격 관측을 구분하며 주 전체 자동 삭제는 금지한다.

실제/가정 시각, 두 정책 ID, 실제 원천 관측일과 조건별 근거·제외 사유를 따로 보존한다. Board/주식시장/연방휴일 달력, 구 주간·일별 갱신 체계, DST 및 엄격한 원점 이전을 확인한다. 기존 B10 bp 정의와 원천 주 내부 선택은 불변이다.

D10 최종 PASS는 실제 달력 구현 및 B10 정보시점 QC 이후에만 검토한다. D13 미확정 사항은 이번 승인 범위에 없다.
''')
    put('README.md','''# 연구 C — E3 조건부 달력 가정 승인 v1.0

정책 등록·문서 QC만 수행한 별도 승인 버전이다. D10_E3_APPROVAL_REPORT.md와 D10_E3_APPROVAL_HANDOFF.md를 먼저 읽는다. 원본 감사·승인·LOCK·RAW는 보존했다.

JSON/MD 승인 정책, 결정 등록부, 현재 게이트 상태, 변경 이력, 자동·독립 QC, 입력·출력 해시를 보관한다. USER_APPROVAL_INSTRUCTION.txt는 이번 지시 원문 사본이다. code에는 등록 및 별도 검사 코드가 있다.

실행 환경은 기존 research_C/phase0_raw_audit/.venv/Scripts/python.exe이다. 외부 네트워크·API 키·추가 패키지는 필요하지 않다. 등록은 register_policy.py, 별도 검사는 independent_qc.py, 보고서/봉인은 finish_registration.py 순서다. 기존 산출물 덮어쓰기는 차단한다. independent_qc.py --check-only는 기존 결과를 변경하지 않는 재검사다.

OUTPUT_MANIFEST.json은 자기 자신과 별도 OUTPUT_MANIFEST.sha256을 제외한 신규 파일 전수 해시를 담고 JSON 자체는 별도 sha256으로 봉인한다. 입력 manifest의 보호범위에는 이전 감사 출력과 그 이전 보호파일이 포함된다. 상위 감사 출력 manifest는 상위 실행에서 봉인한 파일 목록만 검증하며, 이번 신규 하위 승인 폴더는 별도의 출력 manifest로 관리한다.

637개 후보에 대한 실제 조건 판정·게시달력 생성·B10/X/Y·모델·최종 시험·D13 확정은 미실행이다. 후속 실행에는 별도 승인이 필요하다.
''')
    print(json.dumps({'registered':POLICY,'protected':len(protected),'candidate_scope':len(candidates),'date_eligibility_evaluated':False},ensure_ascii=False))

if __name__=='__main__':main()
