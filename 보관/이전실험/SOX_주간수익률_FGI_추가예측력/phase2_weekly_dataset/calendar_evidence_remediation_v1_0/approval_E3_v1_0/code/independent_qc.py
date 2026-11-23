"""등록 모듈을 import하지 않는 별도 정책/해시 검사. 외부 독립 심사 아님."""
import ast
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

OUT=Path(__file__).resolve().parents[1]
AUDIT=OUT.parent
ROOT=OUT.parents[3]

def get(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

def main():
    p=get(OUT/'D10_E3_APPROVED_POLICY.json');g=get(OUT/'D10_E3_GATE_STATUS.json')
    d=get(OUT/'D10_E3_DECISION_REGISTER.json');i=get(OUT/'INPUT_MANIFEST.json')
    c=get(OUT/'PRIOR_QC_COUNT_RECONCILIATION.json')
    checks=[]
    def check(name,ok,detail):checks.append({'name':name,'pass':bool(ok),'detail':detail})
    check('승인 ID·범위',p['policy_id']=='C_DGS10_H15_HISTORICAL_CALENDAR_E3_CONDITIONAL_v1'
          and p['status']=='APPROVED' and p['authorization_scope']=='POLICY_REGISTRATION_AND_DOCUMENT_QC_ONLY','명시적 사용자 지시 SHA256 별도 기록')
    check('기존 시차 정책 보완 관계',p['relationship']=='SUPPLEMENTS_NOT_REPLACES_EXISTING_TIMING_POLICY'
          and p['timing_policy_id']=='C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1','대체/삭제 아님')
    grid=rows(AUDIT/'audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv')
    main_grid=[r for r in grid if r['in_main_audit_period']=='True']
    candidates=[r['calendar_date'] for r in main_grid if r['evidence_grade']=='E3' and r['publication_candidate_under_rule']=='True']
    e3=p['E3'];e4=p['E4'];timing=p['timing']
    check('E1~E4 분류 불변',not p['evidence_classification_changed'] and
          dict(Counter(r['evidence_grade'] for r in main_grid))==d['main_evidence_counts_unchanged'],
          '원본 CSV 바이트도 보호해시로 확인')
    check('E3 범위 637일 정확성',len(candidates)==e3['candidate_count']==637 and candidates==e3['candidate_dates'],
          '본기간 기존 평일 후보 목록과 일대일 일치')
    check('E3 7개 필수 조건·미확인 처리',len(e3['all_conditions_required'])==7
          and [r['id'] for r in e3['all_conditions_required']]==[f'E3_C0{n}' for n in range(1,8)]
          and 'UNRESOLVED' in e3['condition_result_states'] and '자동 적격 처리 금지' in e3['unresolved_condition_handling'],
          '조건 미확인과 충족을 구분하는 정책만 등록')
    check('E3 자동 적격·실제 구현 없음',not e3['all_candidates_automatically_eligible']
          and not e3['date_by_date_eligibility_evaluated'] and e3['eligible_date_count'] is None
          and e3['excluded_date_count'] is None,'637은 승인 대상 후보 수이며 통과 수 아님')
    check('주말·일반 비게시일 미승격',not e3['weekend_or_general_nonpublication_dates_become_publication_dates']
          and not e3['blanket_every_weekday_published'],'E3 전체 2461일에 포괄 승인하지 않음')
    check('과거 발표 체계 및 달력 분리','주간' in e3['historical_regime_note'] and '일별' in e3['historical_regime_note']
          and not e3['board_calendar_equals_NYSE_calendar'],'2014 기록 밀도/2016 형식 변경 구분, Board/미국 증시 분리')
    dates=sorted(r['calendar_date'] for r in main_grid if r['evidence_grade']=='E4')
    check('E4 여섯 날짜 정확성',dates==e4['unresolved_dates']==['2011-12-26','2012-10-29','2016-01-22','2018-03-02','2019-01-19','2022-12-31'],dates)
    check('E4 불확실 발표·의존 관측 자동 적격 금지',not e4['unresolved_event_is_proven_available']
          and not e4['dependent_observations_automatically_eligible'] and not e4['conflict_resolution_claimed'],
          '충돌 해소를 주장하지 않음')
    check('E4 주 전체 삭제·이동·E3 대체 금지',e4['independent_eligible_same_week_observation_allowed']
          and not e4['whole_week_automatically_deleted'] and not e4['silently_shift_release_date']
          and not e4['automatically_replace_with_E3'],'주내 독립 적격 관측 허용')
    check('시차·DST·엄격 이전 보존','16:15' in timing['assumed_release_rule']
          and '다음 달력일 08:00' in timing['assumed_available_rule'] and timing['timezone']=='America/New_York'
          and timing['DST'] and timing['eligibility_comparison']=='available_at < prediction_origin'
          and timing['known_later_evidence_has_priority'],'문서 정책 검사이며 실제 관측시각 생성 아님')
    check('actual/assumed·빈티지 분리',timing['actual_release_at'] is None and timing['actual_available_at'] is None
          and timing['publication_status']==timing['vintage_status']=='UNVERIFIED'
          and timing['calendar_assumption_separate_from_timing_assumption']
          and timing['calendar_assumption_policy_id']!=timing['timing_assumption_policy_id'],'실제 미확인 시각은 null')
    check('B10 산식·bp·주 내부 선택',p['B10']['formula']=='B10_w = 100 × (R[w-1,O] - R[w-2,O])'
          and p['B10']['unit']=='bp' and not any(p['B10'][k] for k in ['cross_week_automatic_carry','future_fill','interpolation']),
          '원천 주 내부 최신 적격값; 실제 B10 계산 없음')
    expected={'D10_AUDIT':'COMPLETED','D10_TIMING_POLICY':'APPROVED','D10_E3_CALENDAR_POLICY':'APPROVED',
        'D10_E4_CONSERVATIVE_POLICY':'APPROVED','D10_CALENDAR_IMPLEMENTATION_QC':'PENDING',
        'D10_WEEKLY_B10_IMPLEMENTATION_QC':'PENDING','D10_GATE':'CALENDAR_POLICY_APPROVED_IMPLEMENTATION_PENDING',
        'D13_GATE':'PENDING_WEEKLY_MISSINGNESS_AUDIT'}
    check('게이트·D13 상태',all(g[k]==v for k,v in expected.items()) and not g['D10_FINAL_PASS'],expected)
    check('후속 검증 10항목·가용성 비교 범위',len(d['future_phase2B_checks'])==10
          and not d['future_checks_executed'] and d['availability_comparison_is_not_model_performance_analysis'],
          '모델 성능 분석은 별도 사전설계/승인 필요')
    old=get(AUDIT/'qc/D10_CALENDAR_QC.json')
    check('이전 9/9 대 본문 8 보고 차이 규명',len(old['tests'])==9 and all(old['tests'].values())
          and c['actual_final_checks']==9 and c['old_report_claimed_checks']==8
          and list(old['tests'])==c['eight_core_checks_plus_one_artifact_check']
          and '필수 산출물 존재' in old['tests'] and not c['prior_report_modified'],
          '핵심8+산출물존재1=최종9. 본문의 최종집계 누락 보고오류이며 기존 보고서 수정 없음')
    bad=[r for r,v in i['protected_files'].items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    check('보호 원본 SHA256',not bad,{'count':len(i['protected_files']),'mismatches':bad})
    timing_path=ROOT/'research_C/phase2_weekly_dataset/prebuild_D10_audit/approval_v1_0/D10_APPROVED_POLICY.json'
    check('기존 시차 정책 원본 해시',sha(timing_path)==i['existing_timing_policy_sha256'],'승인 원본 변경 0')
    check('실행권한 확대 없음',not any([p['phase2B_execution_authorized'],p['D13_rule_lock_authorized'],
          p['weekly_B10_generated'],p['XY_generated'],p['model_or_test_execution'],g['phase2B_execution_authorized']]),
          '정책/문서 QC만 승인')
    forbidden={'fit','fit_transform','predict','rolling','pct_change','resample'}
    calls=[]
    for path in (OUT/'code').glob('*.py'):
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in forbidden:
                calls.append(path.name+':'+node.func.attr)
    check('금지 계산 API 호출·주간 데이터 산출 없음',not calls and not list(OUT.rglob('*.csv')),
          {'forbidden_calls':calls,'note':'정책 JSON 내 후보 목록은 원본 목록 복사이며 날짜별 적격 판정 아님'})
    check('필수 참조 전체 열람·해시',len(i['required_reference_read_log'])==8
          and all(r['entire_file_read'] and sha(Path(r['path']))==r['sha256'] for r in i['required_reference_read_log']),
          '8개 필수 파일과 사용자 승인 원문 확인')
    result={'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL',
        'independence':'동일 Codex 작업 내 등록 코드 import 없이 별도 구현. 외부 심사 아님.',
        'checks':checks,'check_count':len(checks),'gate_pass':False}
    if '--check-only' not in sys.argv:
        with (OUT/'D10_E3_INDEPENDENT_QC.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
        lines=['# D10 E3 승인 정책 독립 QC','',result['independence'],'',f"**판정: {result['status']} ({len(checks)}개)**",'',
            '문서 정합성 PASS이며 달력/주간 B10 구현 QC나 최종 게이트 PASS가 아니다.','',
            '| 검사 | 결과 | 근거 |','|---|---|---|']
        for item in checks:
            detail=item['detail'] if isinstance(item['detail'],str) else json.dumps(item['detail'],ensure_ascii=False)
            lines.append('| '+item['name']+' | '+('PASS' if item['pass'] else 'FAIL')+' | '+detail.replace('|','/')+' |')
        with (OUT/'D10_E3_INDEPENDENT_QC.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'failures':[r for r in checks if not r['pass']]},ensure_ascii=False))
    if result['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
