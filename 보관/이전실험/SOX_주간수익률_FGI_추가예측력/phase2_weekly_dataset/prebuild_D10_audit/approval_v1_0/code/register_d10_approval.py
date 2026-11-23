"""D10 사용자 승인 등록과 문서 QC만 수행. 원본 및 금융 시계열 쓰기 금지."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

OUT=Path(__file__).resolve().parents[1]
AUDIT=OUT.parent
ROOT=OUT.parents[3]
LOCK=ROOT/'research_C/phase1_research_design/approval_lock_v1_1'
POLICY_ID='C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1'

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def write(name,content):
    with (OUT/name).open('x',encoding='utf-8',newline='\n') as f:
        f.write(content if isinstance(content,str) else json.dumps(content,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def check_protection(manifest):
    return [r for r,v in manifest['protected_files'].items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]

def prepare():
    if (OUT/'D10_INPUT_MANIFEST.json').exists():
        raise SystemExit('등록된 승인 버전을 덮어쓰지 않습니다.')
    previous=load(AUDIT/'inputs/PHASE2A_INPUT_MANIFEST.json')
    assert not check_protection(previous),'기존 보호 입력 불일치'
    am=load(AUDIT/'qc/PHASE2A_OUTPUT_MANIFEST.json')
    assert all(sha(AUDIT/r['path'])==r['sha256'] for r in am['files']),'기존 감사 산출물 불일치'
    protected=dict(previous['protected_files'])
    audit_paths=[AUDIT/r['path'] for r in am['files']]+[AUDIT/'qc/PHASE2A_OUTPUT_MANIFEST.json']
    for p in audit_paths:
        protected[p.relative_to(ROOT).as_posix()]={'bytes':p.stat().st_size,'sha256':sha(p)}
    refs=[ROOT/'Research_C_Study_Plan_v1_20261016.md',LOCK/'PHASE1_LOCKED_SPEC_v1_1.md',
          LOCK/'PHASE1_GATE_REGISTER.json',AUDIT/'reports/PHASE2A_D10_REPORT.md',
          AUDIT/'audit/D10_AVAILABILITY_POLICY_PROPOSAL.md',AUDIT/'qc/PHASE2A_INDEPENDENT_QC.md']
    read_log=[]
    for p in refs:
        body=p.read_text(encoding='utf-8-sig')
        read_log.append({'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,
                         'entire_file_read':True,'characters':len(body)})
    spec=load(LOCK/'PHASE1_LOCKED_SPEC_v1_1.json')
    old_gate=load(LOCK/'PHASE1_GATE_REGISTER.json')
    proposal=load(AUDIT/'audit/D10_POLICY_PROPOSAL.json')
    formula=spec['core_variables']['B10']['formula']
    assert proposal['formula']==formula
    manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'approval_provenance':{'source':'본 대화의 사용자 지시: 연구 C — D10 가정 정책 승인 및 게이트 상태 반영',
            'approval_date_kst':datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(),
            'approval_scope':'D10 전용 가정 및 현재 수정본 한계 조건부 승인, 별도 버전 등록·문서 QC만',
            'is_external_signature':False,'phase2B_authorized':False},
        'required_inputs_read':read_log,'protected_files':protected,
        'protection_scope':'이전 보호 입력1017개 및 Phase2-A 원본23개. 새 approval_v1_0 하위 폴더만 추가 허용.',
        'previous_audit_manifest_sha256':sha(AUDIT/'qc/PHASE2A_OUTPUT_MANIFEST.json'),
        'source_proposal_sha256':sha(AUDIT/'audit/D10_POLICY_PROPOSAL.json'),
        'prior_baselines_verified':True,'runtime':{'python':sys.version,'executable':sys.executable},
        'weekly_data_read_or_created':False}
    write('D10_INPUT_MANIFEST.json',manifest)
    policy={
        'schema_version':'1.0','study':'C','policy_id':POLICY_ID,'policy_status':'APPROVED',
        'approval_conditions':'역사 공개·빈티지 UNVERIFIED와 현재 수정본 사용 한계를 수용한 가정 기반 연구에 한정',
        'proposal_policy_id':proposal['policy_id'],'approval_provenance':manifest['approval_provenance'],
        'B10_formula':formula,'B10_formula_display':'B10_w = 100 × (R[w-1,O] - R[w-2,O])',
        'unit':'bp','source_series':'DGS10','source_raw_path':spec['core_variables']['B10']['raw_paths'],
        'Y_formula':spec['target']['formula'],'Y_frequency':spec['target']['frequency'],
        'origin':spec['origin'],'week_definition':'America/New_York 월요일00시~다음 월요일00시 미만',
        'rules':{
            'assumed_release':{'reference':'관측일 다음 실제 Federal Reserve Board H.15 게시 영업일',
                'time':'16:15:00','timezone':'America/New_York','uses_actual_historical_calendar':True,
                'same_day_publication_assumption':False},
            'assumed_available':{'reference':'가정 발표일 다음 달력일','time':'08:00:00',
                'timezone':'America/New_York','calendar_day_offset':1,'next_day_need_not_be_business_day':True},
            'DST':'America/New_York 현지 시각으로 계산 후 UTC 변환. 고정 UTC 오프셋 사용 금지.',
            'calendar_exceptions':'Board 공휴일·특별폐쇄·알려진 H.15 발표 지연 반영. NYSE/Reserve Banks 달력 대용 금지. 미해결 구간 임의 확정 금지.',
            'late_actual_evidence':'늦은 실제 공개·가용성 증거는 가정보다 우선. 알려진 늦은 시각을 가정으로 앞당기지 않는다. 실제 공개가 원점 이상이면 제외. 시각/예외 해결 불가 시 보류·제외 사유 보존.',
            'eligibility':{'operator':'<','right_operand':'prediction_origin','equality_eligible':False,
                'assumed_path':'assumed_available_at < prediction_origin 및 실제 늦은 공개 증거의 veto 통과',
                'verified_path':'직접 입증된 actual_available_at < prediction_origin',
                'actual_evidence_precedence':True},
            'timestamp_fields':{'actual_release_at':None,'actual_available_at':None,'assumed_release_at':None,
                'assumed_available_at':None,'unknown_actual_stays_null':True,
                'assumed_never_copied_to_actual':True,'schema_defaults_not_observation_rows':True},
            'status':{'availability_basis_for_assumption':'ASSUMED_CONSERVATIVE',
                'publication_status':'UNVERIFIED','vintage_status':'UNVERIFIED',
                'approval_does_not_verify_data':True},
            'R_selection':{'same_prediction_origin_for_both_weeks':True,'source_weeks':['w-1','w-2'],
                'choose':'각 주 내부에서 원점 이전 이용 가능한 최신 적격 DGS10 관측일',
                'empty_week_result':'NaN','cross_week_carry':False,'future_fill':False,
                'interpolation':False,'fixed_Friday':False},
            'D04_generic_policy_applied_to_DGS10':False},
        'required_lineage_fields':['observation_date','observation_week','prediction_origin',
            'raw_sha256','vintage_id','actual_release_at','actual_available_at','assumed_release_at',
            'assumed_available_at','availability_basis','publication_status','vintage_status',
            'assumption_policy_id','evidence_url','exclusion_reason'],
        'limitations':['現在 확보한 수정본 활용 가정 기반 역사적 표본외 연구이며 검증된 실시간 PIT 연구가 아니다.',
            '완충시간이 모든 역사적 발표·제공처 지연을 보장하지 않는다.',
            '개별 최초 게시·제공처 최초 반영·최초 빈티지 미검증은 UNVERIFIED로 유지한다.',
            '실제 역사 달력·예외와 주간 구현은 향후 별도 QC가 필요하다.'],
        'implementation_status':'PENDING','applied_to_actual_observations':False,
        'robustness_plan':[
            {'id':'D10_R1','analysis':'기본 가정 대비 추가 발표 지연','classification':'보조 강건성 분석',
             'status':'PLANNED_NOT_EXECUTED','additional_delay':None,'needs_pre_execution_detail_lock':True},
            {'id':'D10_R2','analysis':'DGS10 제외','classification':'별도 보조 민감도 실험, 주력 B10 구성 유지',
             'status':'PLANNED_NOT_EXECUTED','primary_B10_unchanged':True,'formula':None,
             'comparison_sample':None,'test_rule':None,'needs_pre_execution_detail_lock':True},
            {'id':'D10_R3','analysis':'확보 가능한 역사적 빈티지와 현재 수정본 비교',
             'classification':'빈티지 강건성 분석','status':'PLANNED_NOT_EXECUTED',
             'vintage_coverage':None,'needs_pre_execution_detail_lock':True}],
        'robustness_registration_before_final_test_results':True,
        'robustness_details_lock_before_execution':True,'phase2B_execution_authorized':False,
        'models_or_test_authorized':False,'original_Phase1_lock_modified':False}
    policy['limitations'][0]=policy['limitations'][0].replace('現在','현재')
    write('D10_APPROVED_POLICY.json',policy)
    gate={'study':'C','status_version':'D10_APPROVAL_v1.0','policy_id':POLICY_ID,
        'D10_AUDIT':'COMPLETED','D10_POLICY':'APPROVED','D10_IMPLEMENTATION_QC':'PENDING',
        'D10_GATE':'POLICY_APPROVED_IMPLEMENTATION_PENDING','D13_GATE':'PENDING_WEEKLY_MISSINGNESS_AUDIT',
        'D10_FINAL_PASS':False,'all_gates_passed':False,'phase2B_execution_authorized':False,
        'source_Phase1_gate_path':str(LOCK/'PHASE1_GATE_REGISTER.json'),
        'source_Phase1_gate_sha256':sha(LOCK/'PHASE1_GATE_REGISTER.json'),
        'source_Phase1_D10_status':old_gate['D10_GATE_STATUS'],
        'effective_status_note':'이번 사용자 승인 범위의 최신 D10 정책 상태는 본 파일을 조회한다. Phase1 LOCK 원본은 당시 이력으로 보존한다.',
        'precedence_scope':'D10 감사완료/정책승인 상태만 별도 반영. B10/Y/기타 Phase1 설계 및 D13을 대체하지 않음.',
        'blocks':['승인 없는 Phase2-B 실행','실제 구현 QC 전 D10 최종 PASS 선언',
                  'D13 상세 잠금 전 최종 시험오차·성능 열람'],
        'next_authorization_required':'사용자의 별도 Phase2-B 실행 지시',
        'execution_counts':{'weekly_B10_created':0,'weekly_XY_created':0,'asof_tables_created':0,
            'models_fit':0,'predictions':0,'test_metrics':0,'robustness_analyses':0,'D13_processing':0}}
    write('D10_GATE_STATUS.json',gate)
    write('D10_APPROVED_POLICY.md',f'''# 연구 C D10 승인 정책 v1.0

정책 ID: **{POLICY_ID}**. 상태: **APPROVED**. 근거: 이번 대화의 명시적인 사용자 승인. 조건은 현재 수정본을 활용한 가정 기반 역사적 표본외 연구와 역사적 공개시각·빈티지 UNVERIFIED 유지다.

## 승인 규칙

1. 관측일 다음 실제 Federal Reserve Board H.15 게시 영업일16:15 ET를 assumed_release_at으로 둔다.
2. 가정 발표일 다음 **달력일**08:00 ET를 assumed_available_at으로 둔다. 다음 날이 영업일일 필요는 없다.
3. America/New_York 및 DST를 적용한다. 고정 UTC 오프셋을 사용하지 않는다.
4. 연준 Board 공휴일·특별폐쇄·알려진 발표 지연을 반영한다. NYSE 또는 Reserve Banks 일정으로 대체하지 않는다. 실제 역사 달력 구현은 아직 하지 않았다.
5. 실제 늦은 발표/가용성 증거가 가정보다 우선한다. 원점 이후 공개를 앞선 가정으로 적격 처리하지 않는다. 예외를 해결할 수 없으면 임의 시각을 만들지 않고 보류/제외 사유를 기록한다.
6. 대상 주 첫 실제 미국 주식시장 거래일09:00 ET 원점에 대해 이용 가능시각은 엄격하게 `<`이어야 한다. 동시각은 제외한다.
7. 실제 시각 미확인 시 actual_available_at=null을 유지한다. 실제 release 시각도 증거 없으면 null이다.
8. assumed_available_at은 실제 확인시각으로 복사하지 않는다. 가정 경로는 ASSUMED_CONSERVATIVE로 표시한다.
9. 역사적 최초 게시시각 및 빈티지는 UNVERIFIED를 유지한다. 정책 승인은 데이터 검증 상태를 올리지 않는다.
10. 현재 수정본을 이용한 가정 기반 역사적 표본외 연구다. 당시 최초 수치·제공처 수신이 입증된 실시간 PIT 실험이라고 주장하지 않는다.

## B10 및 Y 불변

`{formula}`

표시 산식: `B10_w = 100 × (R[w-1,O] - R[w-2,O])`, 단위 bp. 같은 O에서 w−1과 w−2 각 주 **내부** 최신 적격 관측일을 선택한다. 주에 적격 관측이 없으면 NaN이다. 타 주 자동 이월, 미래값 채움, 보간, 금요일 강제는 금지한다.

SOX 비중첩 미국 달력 주 Y는 `{policy['Y_formula']}`를 유지한다. B1~B9·F1·정보집합·학습창·분할·알고리즘·시드 등 Phase1 v1.1의 다른 사양을 변경하지 않는다. D04 일별 EOD 가정을 DGS10에 전용하지 않는다.

## 강건성 계획 등록

- 추가 발표 지연: 계획만 등록. 추가 지연 길이는 아직 정하지 않았으며 실행 전 잠근다.
- DGS10 제외: **별도 보조 민감도 실험**이다. 주력 B10을 삭제하거나 변경하는 승인이 아니다. 상세 산식·비교표본·검정규칙을 실행 전에 추가 잠근다.
- 확보 가능한 역사 빈티지와 수정본 비교: 자료 범위와 비교 규칙을 후속 잠금한다. 이번에 빈티지를 수집하지 않았다.

세 계획 모두 최종 시험 결과 열람 전에 등록하며 현재 PLANNED_NOT_EXECUTED다. 유리한 결과에 맞춰 규칙을 고르지 않는다.

## 효력·게이트·실행 권한

D10 감사 COMPLETED, 정책 APPROVED, 구현 QC PENDING, 게이트 POLICY_APPROVED_IMPLEMENTATION_PENDING이다. D13은 PENDING_WEEKLY_MISSINGNESS_AUDIT다. 기존 Phase1 LOCK 및 Phase2-A 감사 원본의 당시 미승인 문구는 과거 기록으로 보존하며, 이번 D10 승인 상태는 같은 폴더 D10_GATE_STATUS.json을 참조한다.

정책 승인과 실제 달력/주간 구현 검증은 다르다. 문서 QC PASS는 D10 최종 PASS가 아니다. Phase2-B 및 이후 학습·시험 실행은 별도 사용자 승인이 필요하다. 이번에는 문서·상태 등록만 수행했다.
''')
    write('D10_APPROVAL_CHANGELOG.md',f'''# D10 승인 변경 이력

|항목|보존한 과거 기록|이번 별도 승인 버전|
|---|---|---|
|정책 ID|{proposal['policy_id']}|{POLICY_ID}|
|정책 상태|NOT_APPROVED_PROPOSAL_ONLY|APPROVED, 명시된 연구 한계 수용 조건|
|D10 감사|Phase1 당시 미실시 / Phase2-A 완료|COMPLETED|
|D10 게이트|{old_gate['D10_GATE_STATUS']}|POLICY_APPROVED_IMPLEMENTATION_PENDING|
|실제 구현 QC|미완료|PENDING 유지|
|D13|PENDING_WEEKLY_MISSINGNESS_AUDIT|동일, 처리하지 않음|
|B10·Y 산식|Phase1 승인식|변경 없음|
|실제/가정 시각·UNVERIFIED|분리 보존|동일, 승인으로 실제 증명되지 않음|
|수정본 사용 한계|별도 승인 제안|현재 수정본 기반 사후 가정 연구 한계 수용|
|강건성|검토 필요|추가 지연·DGS10 제외·빈티지 비교 계획만 등록, 상세 잠금 대기|
|Phase2-B 실행|미승인|미승인 유지|

원본 Phase1 게이트 및 Phase2-A 제안/권고는 수정하지 않았다. 새 상태는 본 승인 버전의 D10_GATE_STATUS.json에만 등록한다. 승인 증거는 이번 대화 사용자 지시이며 외부 서명·정책 구현 완료로 표현하지 않는다.
''')
    changes=check_protection(manifest)
    checks={
        'six_required_inputs_entirely_read':len(read_log)==6 and all(x['entire_file_read'] for x in read_log),
        'prior_baselines_verified':manifest['prior_baselines_verified'],
        'approved_policy_ID_exact':policy['policy_id']==POLICY_ID and policy['policy_status']=='APPROVED',
        'release_next_actual_Board_day_1615':policy['rules']['assumed_release']['time']=='16:15:00' and policy['rules']['assumed_release']['uses_actual_historical_calendar'],
        'available_next_calendar_day_0800':policy['rules']['assumed_available']['calendar_day_offset']==1 and policy['rules']['assumed_available']['time']=='08:00:00',
        'NY_timezone_and_DST':policy['origin']['timezone']=='America/New_York' and policy['origin']['dst'],
        'holiday_exception_and_known_late_veto_documented':bool(policy['rules']['calendar_exceptions']) and policy['rules']['eligibility']['actual_evidence_precedence'],
        'strict_before_not_equal':policy['rules']['eligibility']['operator']=='<' and not policy['rules']['eligibility']['equality_eligible'],
        'unknown_actual_time_null':policy['rules']['timestamp_fields']['actual_available_at'] is None and policy['rules']['timestamp_fields']['unknown_actual_stays_null'],
        'assumed_never_actual':policy['rules']['timestamp_fields']['assumed_never_copied_to_actual'],
        'publication_vintage_UNVERIFIED':policy['rules']['status']['publication_status']==policy['rules']['status']['vintage_status']=='UNVERIFIED',
        'B10_formula_unit_unchanged':formula==proposal['formula'] and policy['unit']==spec['core_variables']['B10']['unit'],
        'SOX_weekly_Y_unchanged':policy['Y_formula']==spec['target']['formula'] and policy['Y_frequency']=='NONOVERLAPPING_US_CALENDAR_WEEK',
        'no_cross_week_or_future_fill':not any(policy['rules']['R_selection'][k] for k in ['cross_week_carry','future_fill','interpolation','fixed_Friday']),
        'D04_not_substituted':policy['rules']['D04_generic_policy_applied_to_DGS10'] is False,
        'three_robustness_plans_only':len(policy['robustness_plan'])==3 and all(x['status']=='PLANNED_NOT_EXECUTED' and x['needs_pre_execution_detail_lock'] for x in policy['robustness_plan']),
        'exclusion_auxiliary_only':policy['robustness_plan'][1]['primary_B10_unchanged'],
        'D10_states_exact':all(gate[k]==v for k,v in {'D10_AUDIT':'COMPLETED','D10_POLICY':'APPROVED','D10_IMPLEMENTATION_QC':'PENDING','D10_GATE':'POLICY_APPROVED_IMPLEMENTATION_PENDING'}.items()),
        'D13_pending_unchanged':gate['D13_GATE']==old_gate['D13_GATE_STATUS'],
        'not_final_gate_PASS':not gate['D10_FINAL_PASS'] and not gate['all_gates_passed'],
        'no_Phase2B_authorization_or_execution':not gate['phase2B_execution_authorized'] and all(v==0 for v in gate['execution_counts'].values()),
        'protected_files_unchanged':not changes}
    qc={'qc_status':'PASS' if all(checks.values()) else 'FAIL','scope':'승인 내용·문서·상태·해시 검증만, 실제 구현 QC 아님',
        'checks':checks,'test_count':len(checks),'failures':[k for k,v in checks.items() if not v],
        'protected_files_checked':len(protected),'changed_protected_files':changes,
        'D10_IMPLEMENTATION_QC':'PENDING','execution_counts':gate['execution_counts']}
    write('D10_APPROVAL_QC.json',qc)
    print(json.dumps({'stage':'prepare','qc_status':qc['qc_status'],'tests':len(checks),'protected':len(protected),'failures':qc['failures']},ensure_ascii=False))
    assert qc['qc_status']=='PASS'

def seal():
    if (OUT/'D10_OUTPUT_MANIFEST.json').exists():
        raise SystemExit('봉인된 버전을 덮어쓰지 않습니다.')
    m=load(OUT/'D10_INPUT_MANIFEST.json'); q=load(OUT/'D10_APPROVAL_QC.json'); i=load(OUT/'D10_APPROVAL_INDEPENDENT_QC.json')
    assert q['qc_status']==i['qc_status']=='PASS'
    assert not check_protection(m)
    write('D10_APPROVAL_REPORT.md',f'''# 연구 C D10 정책 승인 반영 보고서

## 승인 결과

정책 **{POLICY_ID}**를 승인 버전 v1.0으로 별도 등록했다. 근거는 이번 사용자 명시 지시다. 기존 제안 ID의 _PROPOSAL을 제거하고 정책 APPROVED로 기록했다. 현재 수정본을 사용하는 가정 기반 역사적 표본외 연구라는 한계를 유지한다.

주요 규칙은 관측일 다음 실제 Board H.15 게시 영업일16:15 ET 가정 발표 → 다음 달력일08:00 ET 가정 이용 가능이다. America/New_York/DST·Board 공휴일·특별폐쇄·알려진 지연을 반영하고 실제 늦은 증거를 우선한다. 원점09:00보다 엄격히 이전인 경우만 적격이다. 실제 미확인 시각은 null, 역사 게시시각·빈티지는 UNVERIFIED다. 승인한 가정은 실제 공개 증명이 아니다.

B10 산식·bp 단위·각 주 내부 최신 적격값 선택, SOX 비중첩 주간 Y와 Phase1 v1.1의 나머지 설계는 그대로다. 주간에 적격값이 없으면 NaN이며 타 주 이월·보간·미래채움을 하지 않는다. D04 가정을 DGS10에 전용하지 않았다.

## 현재 게이트

|항목|현재 승인 기록|
|---|---|
|D10_AUDIT|COMPLETED|
|D10_POLICY|APPROVED|
|D10_IMPLEMENTATION_QC|PENDING|
|D10_GATE|POLICY_APPROVED_IMPLEMENTATION_PENDING|
|D13_GATE|PENDING_WEEKLY_MISSINGNESS_AUDIT|
|D10 최종 PASS|아님|
|Phase2-B 실행 승인|없음|

기존 Phase1 게이트 파일은 당시 상태의 원본으로 유지했다. **이번 승인 이후 D10 정책 상태는 이 폴더 D10_GATE_STATUS.json을 조회한다.** 승인기록의 우선 범위는 D10 정책/감사 상태뿐이며 원래 B10/Y나 다른 설계를 대체하지 않는다.

## 향후 강건성 계획

추가 발표 지연, DGS10 제외 보조 실험, 확보 가능한 빈티지·수정본 비교를 최종 시험 결과 열람 전 계획으로 등록했다. 이번에 어느 것도 실행하지 않았다. 추가 지연 크기와 분석 세부는 미정이다. 특히 DGS10 제외는 주력 B10 변경 승인이 아니며 상세 산식·비교표본·검정규칙을 실행 전에 추가 잠가야 한다.

## QC와 보존

- 자동 문서 QC **{q['qc_status']} {q['test_count']}/{q['test_count']}**.
- 독립 문서 QC **{i['qc_status']} {i['test_count']}/{i['test_count']}**. 동일 Codex 작업 내 별도 구현 검사이며 외부 심사 아님.
- 보호 입력 **{len(m['protected_files'])}개** SHA-256 불변: 기존1017개 + Phase2-A 원본23개. RAW·freeze·Phase0·Phase1 LOCK·감사 원본 변경0건.
- 실제 D10 구현 QC는 **PENDING**이다. 문서 및 소규모 시각 논리 테스트 통과가 전수 역사 달력·주간 B10 구현 통과를 뜻하지 않는다.
- 주간 X/Y·B10·실제 as-of·학습·예측·최종시험·강건성·D13 실행0회. 승인 폴더 밖 산출물을 만들지 않았다.

입력 파일별 경로·SHA-256은 D10_INPUT_MANIFEST.json, 코드와 모든 산출물 해시는 D10_OUTPUT_MANIFEST.json에 기록한다. 출력 manifest 자체는 순환 참조 방지를 위해 파일 내 해시에서 제외한다. 외부 재확인용 해시는 D10_OUTPUT_MANIFEST.sha256에 기록한다.

## 생성 파일 및 종료

D10_APPROVED_POLICY.md/.json, D10_GATE_STATUS.json, D10_APPROVAL_CHANGELOG.md, D10_APPROVAL_QC.json, D10_APPROVAL_INDEPENDENT_QC.md, D10_APPROVAL_REPORT.md, D10_APPROVAL_HANDOFF.md, D10_INPUT_MANIFEST.json을 생성했다. 독립QC JSON, 출력 해시 manifest와 code의 재현 코드도 보존한다.

승인 등록·검증만 완료하고 종료한다. Phase2-B 실행은 별도 사용자 지시를 기다린다. D13은 미처리 상태다.
''')
    write('D10_APPROVAL_HANDOFF.md',f'''# D10 승인 v1.0 인수인계

승인 정책: `{POLICY_ID}`. 최신 D10 승인 상태는 D10_GATE_STATUS.json, 상세 규칙은 D10_APPROVED_POLICY.json/.md를 읽는다. Phase1 LOCK 및 Phase2-A 감사 제안 원본은 과거 기록으로 보존했다.

D10 감사 COMPLETED, 정책 APPROVED, 구현 QC PENDING, 게이트 POLICY_APPROVED_IMPLEMENTATION_PENDING이다. D13은 PENDING_WEEKLY_MISSINGNESS_AUDIT다. D10 최종 PASS가 아니며 Phase2-B 실행 권한도 없다.

정책은 관측일 다음 실제 Board H.15 게시 영업일16:15 ET → 다음 달력일08:00 ET 가정이다. 실제 늦은 증거 우선, strict `<09:00` 원점, America/New_York/DST, 실제시각 미확인 null, 게시/빈티지 UNVERIFIED, 현재 수정본의 연구 한계를 유지한다. 같은 O에서 각 주 내부 최신 적격값만 선택하며 타 주 이월·보간·미래값 사용 금지다. B10·Y 불변이다.

후속 사용자 지시가 있을 때만 Phase2-B를 시작한다. 그때 실제 역사 Board H.15 게시 달력·지연 예외·실제/가정 시각 분리·주간 B10 선택을 구현하고 별도 구현 QC를 수행해야 한다. 현재 문서 QC를 구현 QC로 대체하지 않는다. D13 실제 주간 결측 감사와 세부정책 잠금도 별도 단계다.

추가 발표 지연·DGS10 제외 보조 실험·빈티지 비교는 계획만 등록됐다. 실행 전 추가 지연 길이 및 산식·비교표본·검정규칙 등을 별도 잠근다. 기존 주력 B10 변경 승인이 아니다. 시험 결과를 보고 정책을 바꾸지 않는다.

재현 코드: code/register_d10_approval.py prepare → code/independent_d10_approval_qc.py → code/register_d10_approval.py seal. Python은 D10_INPUT_MANIFEST.json의 기존 연구 C 환경을 사용한다. 기존 승인 폴더 재실행은 거부한다. 새 재현 버전은 같은 디렉터리 깊이의 새 폴더에 code만 복사해 수행하며 봉인된 기존 버전을 수정하지 않는다. 과거 감사 manifest가 허용한 원본만 입력으로 사용한다.

보호 입력 {len(m['protected_files'])}개 불변. 문서 QC 자동{q['test_count']}개/독립{i['test_count']}개 PASS. 실행 범위는 문서 등록뿐이다. 사용자 검토를 기다리며 중단한다.
''')
    assert not check_protection(m)
    files=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file()]
    out_manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'policy_id':POLICY_ID,'files':files,
        'excluded_from_files':['D10_OUTPUT_MANIFEST.json','D10_OUTPUT_MANIFEST.sha256'],
        'self_hash_note':'manifest 자체 해시는 별도 .sha256에 기록. 그 checksum 파일은 자기 해시를 포함하지 않는다.',
        'protected_inputs_rechecked':len(m['protected_files']),'protected_input_changes':[],
        'document_QC':'PASS','independent_document_QC':'PASS','D10_IMPLEMENTATION_QC':'PENDING',
        'D10_GATE':'POLICY_APPROVED_IMPLEMENTATION_PENDING','phase2B_executed':False,
        'total_file_count_including_manifest_and_checksum':len(files)+2}
    write('D10_OUTPUT_MANIFEST.json',out_manifest)
    write('D10_OUTPUT_MANIFEST.sha256',sha(OUT/'D10_OUTPUT_MANIFEST.json')+'  D10_OUTPUT_MANIFEST.json\n')
    print(json.dumps({'stage':'seal','files':len(files)+2,'protected_unchanged':len(m['protected_files']),
        'automatic_QC':q['qc_status'],'independent_QC':i['qc_status'],'D10_GATE':out_manifest['D10_GATE']},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','seal'])
    args=parser.parse_args()
    {'prepare':prepare,'seal':seal}[args.stage]()
