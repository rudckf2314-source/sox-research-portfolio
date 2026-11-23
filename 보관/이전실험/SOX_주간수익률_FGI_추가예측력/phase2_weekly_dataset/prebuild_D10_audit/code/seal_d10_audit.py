"""독립 QC 후 한국어 최종보고서·인수인계·출력 해시 생성. 입력 원본은 쓰지 않는다."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]

def load(rel):
    return json.loads((OUT/rel).read_text(encoding='utf-8'))

def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def write_new(rel,text):
    with (OUT/rel).open('x',encoding='utf-8',newline='\n') as f:
        f.write(text)

def main():
    if (OUT/'qc/PHASE2A_OUTPUT_MANIFEST.json').exists():
        raise SystemExit('이미 봉인된 감사 결과를 덮어쓰지 않습니다.')
    a=load('qc/PHASE2A_QC.json')
    b=load('qc/PHASE2A_INDEPENDENT_QC.json')
    m=load('inputs/PHASE2A_INPUT_MANIFEST.json')
    s=load('audit/D10_RAW_STATISTICS.json')
    p=load('audit/D10_POLICY_PROPOSAL.json')
    g=load('audit/D10_GATE_RECOMMENDATION.json')
    assert a['qc_status']==b['qc_status']=='PASS'
    changes=[r for r,v in m['protected_files'].items() if not (ROOT/r).exists() or digest(ROOT/r)!=v['sha256']]
    assert not changes,changes
    register=load('audit/OFFICIAL_EVIDENCE_REGISTER.json')
    register['sources'].append({'id':'E09','title':'Federal Reserve October 2026 release calendar',
        'url':'https://www.federalreserve.gov/newsevents/2026-october.htm',
        'confirmed':'통계일정에 H.15 16:15와 실제 예정일 목록 표시. 2026-10-12 휴일의 daily/weekly release는10-13 이월 안내.',
        'limits':'사전 예정 일정이지 실제 수신 로그나 과거 전체 최초 빈티지 증거가 아니다.'})
    (OUT/'audit/OFFICIAL_EVIDENCE_REGISTER.json').write_text(json.dumps(register,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (OUT/'audit/D10_RELEASE_TIMING_AUDIT.md').open('a',encoding='utf-8') as f:
        f.write('\n## 추가 공식 일정 대조\n\n[E09 2026-10 공식 통계 일정](https://www.federalreserve.gov/newsevents/2026-october.htm)에서도 H.15 16:15와10-12 휴일 발표의10-13 이월을 확인했다. 사전 일정은 실제 수신 증거가 아니다.\n')
    with (OUT/'logs/PHASE2A_WORK_LOG.md').open('a',encoding='utf-8') as f:
        f.write(f'\n- 독립 QC 첫 시도에서 정적 검사기가 보고서 문자열 join을 데이터 병합 join으로 오인했다. 실패 기록은 logs/INDEPENDENT_QC_ATTEMPT1.json/.md에 보존했다. 문자열 상수 join만 제외하도록 검사기를 수정한 뒤 재실행하여 {b["test_count"]}개 전부 PASS. 원천 데이터·정책·수치는 변경하지 않았다.\n- 최종 공식 일정 E09 추가 대조. 전체 공식 근거9개. 독립 QC 후 보호 입력 {len(m["protected_files"])}개 재해시 변경0.\n')
    source_counts=s['study_source_date_audit_20110101_20261009']
    report=f'''# 연구 C Phase 2-A D10 사전감사 최종 보고서

작성일: 2026-10-17 KST. 범위: DGS10 원천·공표시점 사전감사만.

## 1. 결론

**D10 권고: {g['recommendation']}.** 기존 B10 산식은 유지 가능하나, 전체 역사 최초 공개시각·FRED 수신·최초 빈티지가 입증되지는 않았다. 별도 DGS10 가정 정책과 현재 수정본 사용 한계를 사용자 검토 대상으로 제안한다. 실제 증거만 요구하면 현 RAW만으로 장기 연구표본을 확정할 수 없다.

이것은 감사 권고다. 원래 연구 상태 **PHASE1_DESIGN_LOCKED_WITH_GATES**, D10 **PENDING_PHASE2_PREBUILD_AUDIT**, D13 **PENDING_WEEKLY_MISSINGNESS_AUDIT**를 변경하지 않았다. 감사 완료와 게이트 통과를 구별한다. Phase 2-B 실행 권한은 없다.

## 2. DGS10 실제 공표규칙과 확인 범위

[H.15 현행 공식 페이지](https://www.federalreserve.gov/releases/h15/)는 월~금16:15 게시와 휴일/Board 폐쇄 제외를 명시한다. 연구 시계는 America/New_York로 처리하며 DST를 반영한다. 확인한10-16 release의 최신 관측은10-15다. [공식10월 일정](https://www.federalreserve.gov/newsevents/2026-october.htm)에서10-12 휴일의 발표가10-13으로 이월되는 것도 확인했다. 일정표와 실제 수신시각은 다르다.

관측일과 발표일은 동일하지 않다. 통상 다음 게시 영업일 경로라면 금요일 금리는 월요일 오후 공개이므로 월요일09시에 사용할 수 없다. 월요일 Board 휴일이면 화요일 오후가 될 수 있어 화요일09시에도 불가하다. 같은 원천 주의 더 이른 적격 관측을 찾아야 한다. 실제 주식시장 첫 세션 원점과 Board 게시 달력을 분리해야 한다.

[H.15 공지](https://www.federalreserve.gov/feeds/h15.html)에 10년물 자체의 정정과 특별폐쇄 지연이 있다. 2016 전후 weekly/daily 게시구조·평균자료 게시 변화가 확인됐으므로 현행 규칙을2011~2026 모든 개별 실제시각으로 소급 확정하지 않는다. 상세 근거9개 및 확인/미확인 구분은 [공표시점 감사](../audit/D10_RELEASE_TIMING_AUDIT.md), [근거 목록](../audit/OFFICIAL_EVIDENCE_REGISTER.json)에 있다.

## 3. RAW 검증

|항목|실제 결과|
|---|---|
|파일|`{s['raw_path']}`|
|원천|Federal Reserve Board H.15 / FRED, DGS10|
|정의·단위|10년 만기 일정 국채 시장수익률, 연율 %, 일간, 비계절조정|
|관측기간|{s['min_date']}~{s['max_date']}|
|전체 원천행 / 금리 유효|{s['rows']:,} / {s['valid_values']:,}|
|금리 결측|{s['missing_values']}개, {s['missing_rate_pct']:.4f}%|
|Date 결측 / 중복|{s['missing_date']} / {s['duplicate_dates']}|
|오름차순|{s['ascending']}|
|금리 최저 / 최고|{s['min_value']} / {s['max_value']}%|
|비숫자 / 비유한 / 0이하|0 / {s['non_finite_values']} / {s['negative_or_zero_values']}|
|유효 날짜 사이 최대 간격|{s['max_gap_between_valid_dates_days']}달력일, {s['max_gap_dates'][0]}→{s['max_gap_dates'][1]}|
|보존 HTTP 원본 대조|날짜 헤더 변경 외 날짜·관측값·공란 전부 동일|

휴일 공란은 오류나0으로 처리하지 않았다. 원천 결측을 채우지 않았으며 모든 공란의 원인을 휴일로 확정한 것도 아니다. 원천 SHA-256: `{s['sha256']}`. 보존 응답 SHA-256은 SOURCE와 일치한다. 상세 통계·원천 메타데이터는 [원천 감사](../audit/D10_SOURCE_AUDIT.md)와 [통계 JSON](../audit/D10_RAW_STATISTICS.json)에 있다.

## 4. 기존 B10 정의와 누출 통제

`{p['formula']}`

금리 퍼센트포인트 차이에100을 곱한 bp이며 비율 수익률이 아니다. 동일한 O에서 w−1과 w−2 **각각의 주 안**에 속하는 최신 적격 관측을 고른다. 금요일 고정, 타 주 이월, 임의 보간은 하지 않는다. 해당 주에 적격 관측이 없으면 NaN이다.

실제 적격 조건은 `actual_available_at < prediction_origin`이다. 관측일을 공개일로 보거나 현재 수정본을 당시 수치로 간주하는 것이 주요 누출/빈티지 위험이다. 정확한 시각 미확인 시 actual_release_at/actual_available_at은 null이다. FRED 페이지의 현재 업데이트 시각을 전 기간의 고정 지연이나 최초 시각으로 쓰지 않는다. [FRED real-time 설명](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)의 현재 수정본과 과거 vintage 구분을 유지한다. ALFRED 날짜 정보도09시 이전 수신을 단독 입증하지 않는다.

## 5. 사용자 승인 필요 정책

[D10 전용 제안](../audit/D10_AVAILABILITY_POLICY_PROPOSAL.md), 정책 ID `{p['policy_id']}`:

1. 관측일의 다음 Board H.15 게시 영업일16:15 ET를 가정 발표시각으로 둔다.
2. 그 다음 달력일08:00 ET를 공급자 이용 가능시각으로 가정해 약15시간45분 완충을 둔다.
3. 이 시각은 assumed 열에만 저장한다. 역사 실제시각·빈티지 UNVERIFIED를 유지한다. 완충이 모든 지연을 보장하지 않는다.
4. 실제 역사 Board 휴일·특별폐쇄·해당 H.15 예외를 확인한다. 알려진 늦은 발표가 있으면 가정보다 우선하며, usable release 근거가 없으면 제외한다.
5. 최초 vintage 대신 현재 수정본을 쓰는 한계를 별도 수용해야 한다. 실제 입증 경로를 택할 경우 추가 역사자료 확보가 필요하다.

**제안은 아직 승인/적용되지 않았다.** D04 EOD 정책을 DGS10에 전용하지 않았으며, B10 삭제·변수 교체도 제안하지 않았다.

## 6. 예상 표본 영향

2011-01-01~2026-10-09의 원천 날짜에는 {source_counts['rows']:,}행, 유효 {source_counts['valid']:,}개, 공란 {source_counts['missing']}개가 있다. 이는 연구 주간 표본 수가 아니다. 주말·휴일을 포함한 유효 날짜 최대 간격은4일이며 장기 날짜 단절은 발견하지 않았다.

공란 또는 금요일 부적격이어도 같은 주의 더 이른 적격 관측이 있으면 B10을 유지할 수 있다. 반대로 실제 공개 확인 실패·지연·예외로 한 기준 주에 값이 없으면 B10이 결측이 된다. **정확한 주간 유효수와 공통표본 손실은 미산출/UNVERIFIED**다. 원천의180개 공란을180주 손실로 세지 않는다. 전수 주간 R/B10 및 기타 X/Y를 만들지 않았다. [표본 영향 사전점검](../audit/D10_SAMPLE_IMPACT_PRECHECK.md)에 연도별 분포와 위험을 기록했다.

## 7. 자동·독립 QC와 보호 확인

- 자동 QC **{a['qc_status']} ({a['test_count']}/{a['test_count']})**: 원천 정의·해시·날짜·일별 결측·논리 예시·실제/가정 구분·B10 보존·범위 검사.
- 독립 QC **{b['qc_status']} ({b['test_count']}/{b['test_count']})**: 작성 코드를 import하지 않고 stdlib csv/Decimal로 원본과 보존 응답을 다시 검사, UTC·strict 경계·정책·보호 해시 별도 대조.
- 이는 동일 Codex 작업 내 독립 구현 검사이며 외부 심사가 아니다. QC PASS는 역사적 최초 공개시각·빈티지 실증 PASS를 의미하지 않는다.
- 보호 입력 **{len(m['protected_files']):,}개 해시 불변**, 이 중 RAW {a['protected_raw_files_checked']}개, Phase1 v1.1 LOCK {a['protected_phase1_lock_files_checked']}개다. 종전 승인된 루트 인덱스 추가 이력은 새 변조와 구별했다. 이번 원본 변경0건.
- 독립 QC 첫 정적 검사에서 문서 문자열 join을 데이터 병합으로 오인했다. 검사기만 수정 후 전항목 통과했으며 첫 실패 기록도 logs에 보존했다. 수치·원천·정책 변경은 없다.
- 주간 B10, SOX Y, X/Y 데이터셋, 실제 as-of 병합, 모델 fit/예측/평가, D13 처리 **모두0회**다.

검증 세부는 [자동 QC](../qc/PHASE2A_QC.json), [독립 QC](../qc/PHASE2A_INDEPENDENT_QC.md)에 있다. 입력·코드·출력 SHA-256은 각 manifest에 보관한다. 출력 manifest는 자체 파일 해시를 제외한다.

## 8. 인수인계와 중단

필요한 사용자 결정은 DGS10 전용 가정 및 수정본 사용 한계 수용 여부, 실제 증거 확보 경로 선택, 이후 별도 Phase2-B 승인이다. D10 원본 게이트는 자동 PASS로 바꾸지 않는다. D13 정책도 손대지 않았다. Phase 2-A 감사만 완료하고 종료한다.
'''
    write_new('reports/PHASE2A_D10_REPORT.md',report)
    write_new('reports/PHASE2A_HANDOFF.md',f'''# 연구 C Phase 2-A 인수인계

## 완료와 현재 상태

D10 원천·공표시점 감사 완료. 권고 **CONDITIONAL_RECOMMENDED**. 자동QC24/24 PASS, 동일 Codex 별도 구현 독립QC21/21 PASS. 원본 보호 {len(m['protected_files'])}개 해시 불변. 기존 PHASE1_DESIGN_LOCKED_WITH_GATES와 D10/D13 원본 상태는 그대로다. 본 감사는 통과 권고/정책 제안이며 원본 게이트 수정이 아니다.

## 먼저 읽을 자료

- reports/PHASE2A_D10_REPORT.md
- audit/D10_RELEASE_TIMING_AUDIT.md 및 OFFICIAL_EVIDENCE_REGISTER.json
- audit/D10_AVAILABILITY_POLICY_PROPOSAL.md 및 D10_POLICY_PROPOSAL.json
- audit/D10_SAMPLE_IMPACT_PRECHECK.md
- qc/PHASE2A_QC.json 및 PHASE2A_INDEPENDENT_QC.md
- inputs/PHASE2A_INPUT_MANIFEST.json 및 qc/PHASE2A_OUTPUT_MANIFEST.json

## 핵심 인계

B10 승인 산식은 유지했다. 금요일 DGS10 관측은 통상 다음 Board 게시일 오후 공표 경로이므로 월요일09시에 자동 사용하지 않는다. 같은 원천 주의 더 이른 적격 관측을 판정해야 하며, 그 주 적격값이 없으면 결측이다. 원본에는 개별 최초 공개/수신/vintage가 없고 과거 정정 사례도 있어 UNVERIFIED를 유지한다. 실제 시각 null을 보존한다.

다음 Board 게시 영업일16:15 + 다음 달력일08:00 ET 완충은 **미승인 제안**이다. 실제 게시 증명이나 D04 정책 승계가 아니다. 역사 Board 달력/특별폐쇄/누락·정정 예외 점검, 현재 수정본의 한계 수용이 필요하다. 정확한 주간 공통표본 손실은 아직 계산하지 않았다.

## 이후 승인 전 금지

Phase2-B B10·주간 X/Y·as-of 테이블 생성, D13 처리, 학습/예측/시험/성과 열람을 시작하지 않는다. 사용자 정책 검토 및 별도 실행 승인을 기다린다. 새 제안을 승인하더라도 기존 동결 설계/RAW를 조용히 덮어쓰지 않고 별도 승인기록으로 관리한다.

## 재현

사용 Python: `{m['runtime']['executable']}`. run_d10_audit.py는 일별 RAW 감사와 문서 작성, independent_d10_qc.py는 별도 원천 검사, seal_d10_audit.py는 보고서·최종 해시 생성이다. 기존 실행 폴더 재실행/덮어쓰기를 거부한다. 새 재현은 동일 프로젝트 깊이의 감사 사본 경로에서 새 출력 경로를 명시적으로 준비해야 한다. 기존 봉인 폴더에서 다시 실행하지 않는다.
''')
    required=['README.md','inputs/PHASE2A_INPUT_MANIFEST.json','audit/D10_SOURCE_AUDIT.md','audit/D10_RELEASE_TIMING_AUDIT.md',
              'audit/D10_AVAILABILITY_POLICY_PROPOSAL.md','audit/D10_SAMPLE_IMPACT_PRECHECK.md','audit/D10_GATE_RECOMMENDATION.json',
              'qc/PHASE2A_QC.json','qc/PHASE2A_INDEPENDENT_QC.md','reports/PHASE2A_D10_REPORT.md','reports/PHASE2A_HANDOFF.md','logs/PHASE2A_WORK_LOG.md']
    assert all((OUT/r).is_file() for r in required)
    changed=[r for r,v in m['protected_files'].items() if not (ROOT/r).exists() or digest(ROOT/r)!=v['sha256']]
    assert not changed,changed
    files=[{'path':x.relative_to(OUT).as_posix(),'bytes':x.stat().st_size,'sha256':digest(x)}
           for x in sorted(OUT.rglob('*')) if x.is_file()]
    manifest={'sealed_at_utc':datetime.now(timezone.utc).isoformat(),'audit_recommendation':g['recommendation'],
              'original_gate_modified':False,'automatic_QC':a['qc_status'],'independent_QC':b['qc_status'],
              'input_manifest_sha256':digest(OUT/'inputs/PHASE2A_INPUT_MANIFEST.json'),
              'protected_inputs_final_recheck':len(m['protected_files']),'protected_input_changes':changed,
              'required_deliverables_present':True,'self_excluded_from_hash':True,'files':files,
              'file_count_including_this_manifest':len(files)+1,'execution_counts':a['execution_counts'],
              'known_QC_implementation_correction':'문자열 join 오탐 보정. 첫 시도 기록 보존. 원천 수치나 정책 수정 없음.'}
    write_new('qc/PHASE2A_OUTPUT_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'files_including_manifest':len(files)+1,'output_hashes_verified':len(files),
                      'protected_inputs_unchanged':len(m['protected_files']), 'report':str(OUT/'reports/PHASE2A_D10_REPORT.md'),
                      'recommendation':g['recommendation']},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
