"""문서 자동 QC·보고서·출력 해시 봉인. 등록 모듈과 독립 검사 모듈을 import하지 않는다."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[3]
def get(rel):return json.loads((OUT/rel).read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(rel,obj):
    with (OUT/rel).open('x',encoding='utf-8',newline='\n') as f:
        f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def main():
    p=get('D10_E3_APPROVED_POLICY.json');g=get('D10_E3_GATE_STATUS.json')
    i=get('INPUT_MANIFEST.json');ind=get('D10_E3_INDEPENDENT_QC.json')
    d=get('D10_E3_DECISION_REGISTER.json');c=get('PRIOR_QC_COUNT_RECONCILIATION.json')
    changed=[r for r,v in i['protected_files'].items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    checks={
        '승인 정책 등록':p['status']=='APPROVED',
        '시차정책 보완 관계':p['relationship']=='SUPPLEMENTS_NOT_REPLACES_EXISTING_TIMING_POLICY',
        '분류 불변':not p['evidence_classification_changed'],
        'E3 7조건 필수':len(p['E3']['all_conditions_required'])==7,
        '637후보 일괄 적격 없음':len(p['E3']['candidate_dates'])==637 and not p['E3']['all_candidates_automatically_eligible'],
        '실제 날짜 조건 판정 미실행':not p['E3']['date_by_date_eligibility_evaluated'],
        '주말 비게시일 미승격':not p['E3']['weekend_or_general_nonpublication_dates_become_publication_dates'],
        'E4 6일 보수 정책':len(p['E4']['unresolved_dates'])==6 and not p['E4']['unresolved_event_is_proven_available'],
        '주 전체 삭제 금지':not p['E4']['whole_week_automatically_deleted'] and p['E4']['independent_eligible_same_week_observation_allowed'],
        '실제 가정 분리':p['timing']['actual_available_at'] is None and p['timing']['calendar_assumption_separate_from_timing_assumption'],
        '빈티지 미확인 유지':p['timing']['publication_status']==p['timing']['vintage_status']=='UNVERIFIED',
        '구현 QC 대기·최종PASS 아님':g['D10_CALENDAR_IMPLEMENTATION_QC']==g['D10_WEEKLY_B10_IMPLEMENTATION_QC']=='PENDING' and not g['D10_FINAL_PASS'],
        'D13 대기 유지':g['D13_GATE']=='PENDING_WEEKLY_MISSINGNESS_AUDIT',
        '후속 10항목 등록':len(d['future_phase2B_checks'])==10 and not d['future_checks_executed'],
        '이전 QC 집계 규명':c['actual_final_checks']==c['actual_passed_checks']==9 and c['old_report_claimed_checks']==8,
        '원본 보호 해시 불변':not changed,
        '독립 검사 PASS':ind['status']=='PASS',
        'Phase2B·주간변수·모델 미실행':not any(p[k] for k in ['phase2B_execution_authorized','weekly_B10_generated','XY_generated','model_or_test_execution'])}
    assert all(checks.values()),checks
    put('D10_E3_APPROVAL_QC.json',{'status':'PASS','scope':'정책등록 및 문서 정합성만',
        'checks':checks,'check_count':len(checks),'protected_file_count':len(i['protected_files']),
        'protected_mismatches':changed,'calendar_or_weekly_B10_implementation_completed':False,
        'independent_check_count':ind['check_count'],'D10_final_pass':False})
    put('D10_E3_APPROVAL_REPORT.md',f'''# 연구 C — D10 역사적 게시달력 E3 조건부 가정 승인 보고서

작성일 2026-10-17 KST. **정책 등록 및 문서 QC 완료 / 실제 구현 미실행**.

## 승인 정책과 기존 정책 관계

신규 `{p['policy_id']}`는 APPROVED다. 기존 `C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1`을 대체하지 않고 역사적 게시달력 근거 정책으로 보완한다. 두 정책을 함께 적용하도록 등록했다. B10 산식 `B10_w = 100 × (R[w-1,O] - R[w-2,O])`, bp 단위 및 각 원천 주 내부 최신 적격 관측 선택은 불변이다. 타 주 자동 이월·보간·미래 채움은 금지한다.

## E3 조건부 승인

기존 본기간 평일 게시 후보 **637일**은 승인 범위일 뿐, 적격 판정이 끝난 날짜 수가 아니다. 당시 H15 규칙 부합, Board 게시 영업일, 공식 휴일·폐쇄 및 알려진 지연·누락·정정과 비충돌, E1/E2 우선, 미검증 상태 보존, 게시 가능일과 실제 게시 확인 구분의 **7조건을 모두 충족할 때만** ASSUMED_CALENDAR를 허용한다.

날짜별 조건은 SATISFIED/FAILED/UNRESOLVED로 추적하며 미확인이면 자동 적격 처리하지 않는다. 이번에는 실제 조건 판정을 하지 않아 적격·제외 수는 null이다. 637일을 VERIFIED로 바꾸지 않았다. E3 주말 및 일반 비게시일의 게시일 승격은 금지한다. 2010 예열 구간에 대한 포괄 가정 승인도 포함하지 않는다.

2011~2014년 주간 발표와 일별 갱신 체계를 구분하고 모든 평일 실제 게시를 확정하지 않는다. Board 게시일과 미국 증시 거래일·연방휴일은 각각 검토해야 한다. 기존 E1~E4 분류는 바이트 단위로 보존했다.

## E4 보수적 처리

2011-12-26, 2012-10-29, 2016-01-22, 2018-03-02, 2019-01-19, 2022-12-31의 충돌이 미해결이면 해당 발표를 이용 가능성이 입증된 이벤트로 보지 않는다. 그 발표에 의존한 관측도 자동 적격 처리하지 않는다. 같은 원천 주의 독립적으로 적격인 다른 관측은 기존 B10 정의에 따라 사용할 수 있다. 주 전체 자동 삭제·발표일 조용한 이동·E3 자동 대체는 금지한다.

## 시차·실제/가정 정보 보존

관측일 다음 H15 게시 영업일16:15 ET 가정 발표, 그다음 달력일08:00 ET 가정 이용 가능을 유지한다. America/New_York/DST를 적용하고 실제 알려진 늦은 근거를 우선한다. 이용 가능시각은 대상 주 첫 실제 미국 세션09:00 ET 원점보다 엄격히 이전이어야 한다. 실제 미확인 시각은 null이며 publication_status/vintage_status는 UNVERIFIED다. 달력 가정과 시각 가정의 정책 ID·근거를 분리하도록 명세했다. 실제 관측별 시각표는 만들지 않았다.

## 현재 게이트

| 항목 | 상태 |
|---|---|
| D10_AUDIT | COMPLETED |
| D10_TIMING_POLICY | APPROVED |
| D10_E3_CALENDAR_POLICY | APPROVED |
| D10_E4_CONSERVATIVE_POLICY | APPROVED |
| D10_CALENDAR_IMPLEMENTATION_QC | PENDING |
| D10_WEEKLY_B10_IMPLEMENTATION_QC | PENDING |
| D10_GATE | CALENDAR_POLICY_APPROVED_IMPLEMENTATION_PENDING |
| D13_GATE | PENDING_WEEKLY_MISSINGNESS_AUDIT |

최종 D10 PASS는 실제 달력·주간 B10 정보시점 QC 이후에만 검토한다. 기존 BLOCKED는 당시 실행 결과로 보존했고 원본 게이트는 변경하지 않았다. 최신 승인 상태의 조회 위치만 이 폴더 `D10_E3_GATE_STATUS.json`으로 별도 명시했다.

## 이전 자동 QC 8/9 차이 규명

이전 `qc/D10_CALENDAR_QC.json`에는 **9개 검사 전부 true**, 요약 메시지도 9/9다. 기존 본문에는 8개로 적혀 있다. JSON 검사명과 생성 코드의 집계 순서를 대조하면 핵심 정합성 8개에 마지막 **필수 산출물 존재** 검사가 추가돼 최종 9개다. 본문의 무조건적인 8개 통과 표기는 최종 집계 누락에 따른 **보고 오류**다. 검사 실패나 성능 수치 변경이 아니며, 다른 기준이라고 사후 정당화하지 않는다. 기존 보고서는 수정하지 않았다. 9개 전체 검사명과 원본 QC 해시는 `PRIOR_QC_COUNT_RECONCILIATION.json`에 있다.

## 자동·독립 QC 및 보호

이번 자동 QC **{len(checks)}/{len(checks)} PASS**, 등록 코드 import 없이 별도 구현 독립 QC **{ind['check_count']}/{ind['check_count']} PASS**. 동일 Codex 작업 내 별도 구현이며 외부 독립 심사가 아니다. 정책 의미·후보 범위·E4 처리·상태·산식·시차·금지 계산·입력 해시를 검사했다. 실제 게시달력이나 B10 구현 정확성을 검증했다는 뜻은 아니다.

기존 보호파일 **{len(i['protected_files']):,}개 SHA-256 불변**, 불일치 0개. 이전 감사 보호 1,076개에 이전 감사 폴더의 파일 152개를 추가해 총 1,228개다. 기존 감사·승인·RAW·freeze·LOCK·Phase2-B 파일 수정/삭제 0건. 새 승인 폴더만 작성했고 네트워크·API 키를 사용하지 않았다. 입력 manifest와 출력 manifest/별도 sha256에 해시를 기록했다.

## 후속 조건과 종료

Phase 2-B 재개는 별도 사용자 실행 승인이 필요하다. 그 뒤 E1~E4 게시달력, E3 충족·제외 사유, E4 영향 관측/주간 후보, Board 휴일·폐쇄·지연, 각 DGS10 가정 시점, strict-before, B10 유효주·결측, E3 허용·미허용 표본가용성, 공통표본 결측의 10개 항목을 검증하도록 인수인계했다. 표본가용성 QC를 모델 성능 비교로 확장하지 않는다.

실제 주간 B10, SOX Y, X/F1, 통합 데이터셋, D13 상세 규칙, 모델 학습·튜닝·예측·최종 시험 열람은 수행하지 않았다. 이번 정책 등록·문서 QC에서 종료한다.
''')
    expected=['D10_E3_APPROVED_POLICY.md','D10_E3_APPROVED_POLICY.json','D10_E3_DECISION_REGISTER.json',
        'D10_E3_GATE_STATUS.json','D10_E3_APPROVAL_CHANGELOG.md','D10_E3_APPROVAL_QC.json',
        'D10_E3_INDEPENDENT_QC.md','D10_E3_APPROVAL_REPORT.md','D10_E3_APPROVAL_HANDOFF.md','INPUT_MANIFEST.json','README.md']
    assert all((OUT/f).is_file() for f in expected)
    files=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
        for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in {'OUTPUT_MANIFEST.json','OUTPUT_MANIFEST.sha256'}]
    put('OUTPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'files':files,'excludes':['OUTPUT_MANIFEST.json','OUTPUT_MANIFEST.sha256'],
        'required_artifacts_present':True,'protected_count':len(i['protected_files']),
        'protected_changed':0,'policy_registration_only':True})
    put('OUTPUT_MANIFEST.sha256',sha(OUT/'OUTPUT_MANIFEST.json')+'  OUTPUT_MANIFEST.json\n')
    print(json.dumps({'automatic_qc':len(checks),'independent_qc':ind['check_count'],
        'protected':len(i['protected_files']),'sealed_files':len(files),'status':'PASS'},ensure_ascii=False))

if __name__=='__main__':main()
