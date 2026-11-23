"""승인 내용 독립 문서 QC. 등록기 import/금융 데이터 계산/외부 접속 없음."""
import ast
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE=Path(__file__).resolve().parents[1]
PROJECT=HERE.parents[3]
PARENT=HERE.parent

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def hash_file(p):
    h=hashlib.sha256()
    with p.open('rb') as stream:
        while block:=stream.read(131072):
            h.update(block)
    return h.hexdigest()

def main():
    if (HERE/'D10_APPROVAL_INDEPENDENT_QC.md').exists():
        raise SystemExit('기존 독립 QC 덮어쓰기 금지')
    policy=read(HERE/'D10_APPROVED_POLICY.json')
    state=read(HERE/'D10_GATE_STATUS.json')
    manifest=read(HERE/'D10_INPUT_MANIFEST.json')
    original_spec=read(PROJECT/'research_C/phase1_research_design/approval_lock_v1_1/PHASE1_LOCKED_SPEC_v1_1.json')
    original_gate=read(PROJECT/'research_C/phase1_research_design/approval_lock_v1_1/PHASE1_GATE_REGISTER.json')
    audit_manifest=read(PARENT/'qc/PHASE2A_OUTPUT_MANIFEST.json')
    proposal=read(PARENT/'audit/D10_POLICY_PROPOSAL.json')
    tests=[]
    def test(name,condition,explanation):
        tests.append({'name':name,'pass':bool(condition),'method_ko':explanation})
    test('승인 ID·근거·조건',policy['policy_id']=='C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1' and
         policy['proposal_policy_id']=='C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1_PROPOSAL' and
         policy['policy_status']=='APPROVED' and not policy['approval_provenance']['is_external_signature'],
         '사용자 지시와 ID 상수 별도 대조. 과거 제안을 승인 버전으로 등록하며 외부 서명이라 주장하지 않음.')
    release=policy['rules']['assumed_release']; available=policy['rules']['assumed_available']
    test('승인 규칙1 다음 Board 게시일16:15',release['time']=='16:15:00' and '관측일 다음 실제' in release['reference'] and
         'Board H.15' in release['reference'] and release['uses_actual_historical_calendar'] and not release['same_day_publication_assumption'],
         '정책 필드를 지시와 대조. 실제 역사 달력 구현·실행은 안 함.')
    test('승인 규칙2 다음 달력일08:00',available['reference']=='가정 발표일 다음 달력일' and
         available['time']=='08:00:00' and available['calendar_day_offset']==1 and available['next_day_need_not_be_business_day'],
         '다음 영업일로 변형하지 않음.')
    ny=ZoneInfo('America/New_York')
    release_fixture=datetime(2026,10,2,16,15,tzinfo=ny)
    availability_fixture=datetime.combine(release_fixture.date()+timedelta(days=1),datetime.min.time(),ny).replace(hour=8)
    test('달력일 규칙의 소규모 논리검사',availability_fixture.weekday()==5 and availability_fixture.isoformat()=='2026-10-03T08:00:00-04:00',
         '금요일 가정발표의 다음날 토요일08시. 실제 금리·B10·전수 매핑 없음.')
    expected=[(datetime(2026,1,9,16,15,tzinfo=ny),21),(datetime(2026,10,2,16,15,tzinfo=ny),20),
              (datetime(2026,3,9,9,tzinfo=ny),13),(datetime(2026,11,2,9,tzinfo=ny),14)]
    test('승인 규칙3 NY·DST',release['timezone']==available['timezone']==policy['origin']['timezone']=='America/New_York' and
         policy['origin']['dst'] and all(t.astimezone(timezone.utc).hour==hour for t,hour in expected),
         '겨울/여름·DST전환 뒤 UTC 예상시각을 별도 비교. 금융 데이터는 읽지 않음.')
    test('승인 규칙4 역사 휴일·폐쇄·지연','공휴일' in policy['rules']['calendar_exceptions'] and
         '특별폐쇄' in policy['rules']['calendar_exceptions'] and '발표 지연' in policy['rules']['calendar_exceptions'],
         '달력·예외 반영 의무만 등록. 달력이 이미 전수 구현됐다고 표시하지 않음.')
    test('승인 규칙5 늦은 실제 증거 우선',policy['rules']['eligibility']['actual_evidence_precedence'] and
         '늦은' in policy['rules']['late_actual_evidence'] and '제외' in policy['rules']['late_actual_evidence'],
         'known-late veto 유지. 가정이 실제 지연을 덮지 않음.')
    origin=datetime(2026,10,5,9,tzinfo=ny)
    boundary_cases=[(origin-timedelta(microseconds=1),True),(origin,False),(origin+timedelta(microseconds=1),False)]
    test('승인 규칙6 엄격한 원점 이전',policy['rules']['eligibility']['operator']=='<' and
         not policy['rules']['eligibility']['equality_eligible'] and policy['origin']['time']=='09:00:00' and
         all((stamp<origin)==wanted for stamp,wanted in boundary_cases),'원점 전·동시·후 수치 비교. 동시각은 부적격.')
    times=policy['rules']['timestamp_fields']
    test('승인 규칙7 실제 미확인 null',times['actual_available_at'] is None and times['actual_release_at'] is None and
         times['unknown_actual_stays_null'] and times['schema_defaults_not_observation_rows'],
         '스키마 기본값을 관측별 실제 시각처럼 저장하지 않음.')
    test('승인 규칙8 가정/실제 분리',times['assumed_never_copied_to_actual'] and
         policy['rules']['status']['availability_basis_for_assumption']=='ASSUMED_CONSERVATIVE',
         'actual/assumed 열 별도. 승인으로 VERIFIED_ACTUAL로 승격하지 않음.')
    test('승인 규칙9 UNVERIFIED 유지',policy['rules']['status']['publication_status']==policy['rules']['status']['vintage_status']=='UNVERIFIED' and
         policy['rules']['status']['approval_does_not_verify_data'],'과거 공개와 빈티지 검증 상태 그대로.')
    test('승인 규칙10 수정본의 연구 한계',any('현재' in x and '수정본' in x and '가정' in x for x in policy['limitations']) and
         any('PIT' in x for x in policy['limitations']),'현재 수정본 기반 가정 연구를 실시간 검증 연구로 표현하지 않음.')
    test('B10·단위·주간Y 원본 동일',policy['B10_formula']==proposal['formula']==original_spec['core_variables']['B10']['formula'] and
         policy['unit']==original_spec['core_variables']['B10']['unit']=='bp' and policy['Y_formula']==original_spec['target']['formula'] and
         policy['Y_frequency']==original_spec['target']['frequency']=='NONOVERLAPPING_US_CALENDAR_WEEK',
         '원본 JSON 직접 비교. 금융 변수 재계산 없음.')
    r=policy['rules']['R_selection']
    test('주 내부 선택 및 이월·보간 금지',r['same_prediction_origin_for_both_weeks'] and r['source_weeks']==['w-1','w-2'] and
         r['empty_week_result']=='NaN' and all(r[k] is False for k in ['cross_week_carry','future_fill','interpolation','fixed_Friday']),
         '같은 O에서 각 원천 주 내부 최신 적격값. 대상 주가 비었다고 다른 주를 붙이지 않음.')
    test('D04 전용 금지',policy['rules']['D04_generic_policy_applied_to_DGS10'] is False and
         'B10' in original_spec['information_availability']['not_automatically_applicable_to'],
         '승인 정책은 별도 DGS10 정책이며 일반 EOD 가정이 아님.')
    rs=policy['robustness_plan']
    test('강건성3개 계획·실행 전 세부잠금',len(rs)==3 and all(x['status']=='PLANNED_NOT_EXECUTED' and
         x['needs_pre_execution_detail_lock'] for x in rs) and rs[0]['additional_delay'] is None and
         all(rs[1][k] is None for k in ['formula','comparison_sample','test_rule']) and
         policy['robustness_registration_before_final_test_results'] and policy['robustness_details_lock_before_execution'],
         '지연 크기/비교표본/검정값을 임의 확정하지 않음. 시험 결과 열람 전 계획 등록.')
    test('DGS10 제외는 보조실험',rs[1]['primary_B10_unchanged'] and '보조' in rs[1]['classification'],
         '주력 B10 삭제·변경 승인 아님.')
    wanted={'D10_AUDIT':'COMPLETED','D10_POLICY':'APPROVED','D10_IMPLEMENTATION_QC':'PENDING',
            'D10_GATE':'POLICY_APPROVED_IMPLEMENTATION_PENDING','D13_GATE':'PENDING_WEEKLY_MISSINGNESS_AUDIT'}
    test('게이트5상태 정확·최종PASS 금지',all(state[k]==v for k,v in wanted.items()) and not state['D10_FINAL_PASS'] and
         not state['all_gates_passed'] and policy['implementation_status']=='PENDING',
         '문서 QC 통과와 실제 주간 구현 QC PENDING을 구별.')
    test('원본 게이트·D13 승계',original_gate['D10_GATE_STATUS']=='PENDING_PHASE2_PREBUILD_AUDIT' and
         state['D13_GATE']==original_gate['D13_GATE_STATUS'] and
         state['source_Phase1_gate_sha256']==hash_file(PROJECT/'research_C/phase1_research_design/approval_lock_v1_1/PHASE1_GATE_REGISTER.json'),
         '원본은 당시 기록으로 보존. 새 D10 상태 참조 범위와 경로 별도 명시.')
    baseline_mismatches=[row['path'] for row in audit_manifest['files'] if hash_file(PARENT/row['path'])!=row['sha256']]
    protected_mismatches=[rel for rel,rec in manifest['protected_files'].items()
                          if not (PROJECT/rel).is_file() or hash_file(PROJECT/rel)!=rec['sha256']]
    test('감사23개·보호파일 전체해시',not baseline_mismatches and not protected_mismatches and
         len(manifest['protected_files'])==1040 and
         hash_file(PARENT/'qc/PHASE2A_OUTPUT_MANIFEST.json')==manifest['previous_audit_manifest_sha256'],
         '원본1017개와 감사23개를 직접 스트리밍 재해시. 추가 승인 디렉터리는 원본 manifest의 새 파일로 오인하지 않음.')
    test('필수 입력6개 경로·해시',len(manifest['required_inputs_read'])==6 and all(
         x['entire_file_read'] and hash_file(Path(x['path']))==x['sha256'] for x in manifest['required_inputs_read']),
         '필수 문서 실제 절대경로·현재 원본 해시 확인.')
    writer=(HERE/'code/register_d10_approval.py').read_text(encoding='utf-8')
    tree=ast.parse(writer)
    imports=[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    imports += [n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
    test('학습·시계열 생성 코드 없음',not any(x and x.startswith(('pandas','numpy','sklearn','statsmodels','xgboost','lightgbm','requests')) for x in imports)
         and not set(calls).intersection({'fit','fit_transform','predict','resample','rolling','to_csv','read_csv'}),
         '등록 코드 AST와 import 검사. 전수 OS 실행감시가 아닌 동일 작업 범위 검사.')
    forbidden_outputs=[str(p) for p in HERE.rglob('*') if p.is_file() and p.suffix.lower() in {'.csv','.parquet','.pkl','.joblib','.npy'}]
    sibling_folders=[p.name for p in PARENT.parent.iterdir() if p.is_dir() and p!=PARENT]
    test('Phase2B·모델·강건성 미실행',not state['phase2B_execution_authorized'] and not policy['phase2B_execution_authorized'] and
         not policy['models_or_test_authorized'] and not policy['applied_to_actual_observations'] and
         all(v==0 for v in state['execution_counts'].values()) and not forbidden_outputs and not sibling_folders,
         '승인 권한·실행기록·산출물·코드를 함께 검사. Phase2-A 외 새 주간 데이터셋 경로 없음.')
    result={'qc_status':'PASS' if all(t['pass'] for t in tests) else 'FAIL','test_count':len(tests),
        'checks':tests,'failures':[t['name'] for t in tests if not t['pass']],
        'method':'동일 Codex 작업 내 독립 문서·정책 검증. 등록기를 import하지 않으며 외부 심사가 아니다.',
        'D10_IMPLEMENTATION_QC':'PENDING','protected_files_checked':len(manifest['protected_files']),
        'protected_hash_mismatches':protected_mismatches,'original_audit_hash_mismatches':baseline_mismatches,
        'implementation_QC_not_performed':True}
    with (HERE/'D10_APPROVAL_INDEPENDENT_QC.json').open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    lines=['# D10 정책 승인 독립 QC','',result['method'],'',
           f"승인 문서 QC: **{result['qc_status']}**, {len(tests)}개. 실제 D10_IMPLEMENTATION_QC는 **PENDING**.",'',
           '|검사|결과|독립 방법·범위|','|---|---|---|']
    lines += [f"|{t['name']}|{'PASS' if t['pass'] else 'FAIL'}|{t['method_ko']}|" for t in tests]
    lines += ['','실제 주간 B10·X/Y를 생성하지 않았다. 소규모 시각 논리 검사는 승인 문구의 정합성 확인이며 전수 역사 Board 일정이나 실제 주간 구현 검증이 아니다.',
              '이 보고서가 PASS여도 D10 최종 게이트 PASS나 Phase2-B 실행 승인으로 해석하지 않는다.']
    with (HERE/'D10_APPROVAL_INDEPENDENT_QC.md').open('x',encoding='utf-8') as f:
        f.write('\n'.join(lines)+'\n')
    print(json.dumps({'qc_status':result['qc_status'],'tests':len(tests),'failures':result['failures']},ensure_ascii=False))
    if result['qc_status']!='PASS':
        raise SystemExit(1)

if __name__=='__main__':
    main()
