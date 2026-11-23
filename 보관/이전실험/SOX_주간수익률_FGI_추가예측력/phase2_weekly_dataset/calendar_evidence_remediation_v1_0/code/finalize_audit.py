"""저장된 감사 근거를 집계해 한국어 보고서와 무결성 봉인을 작성한다. 금융 특성 계산 없음."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[2]

def load(rel):
    return json.loads((OUT/rel).read_text(encoding='utf-8-sig'))

def rows(rel):
    with (OUT/rel).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def write(rel, data):
    with (OUT/rel).open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(data if isinstance(data,str) else json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def table(headers, data):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(str(v).replace('|','/') for v in r)+' |' for r in data])

def main():
    inp=load('qc/INPUT_MANIFEST.json')
    grid=rows('audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv')
    main_grid=[r for r in grid if r['in_main_audit_period']=='True']
    yearly=rows('audit/H15_YEARLY_COVERAGE.csv')
    reg=load('sources/H15_SOURCE_REGISTER.json')
    cross=load('audit/SOURCE_CROSSCHECK_DETAILS.json')
    docs=load('audit/H15_OFFICIAL_DOCUMENT_EXTRACTS.json')['documents']
    independent=load('qc/D10_CALENDAR_INDEPENDENT_QC.json')
    recommendation=load('audit/D10_CALENDAR_GATE_RECOMMENDATION.json')
    counts=dict(Counter(r['evidence_grade'] for r in main_grid))
    candidates=[r for r in main_grid if r['evidence_grade']=='E3' and r['publication_candidate_under_rule']=='True']
    changed=[r for r,v in inp['protected_files'].items() if not (ROOT/r).is_file() or sha(ROOT/r)!=v['sha256']]
    # 同日の観測なしの監査のみ。利率の差・週次集計・利用可能値の選択は行わない。
    raw=ROOT/'data/raw/15_dgs10/15_dgs10_RAW_20100101_20261014.csv'
    with raw.open(encoding='utf-8-sig',newline='') as stream:
        raw_rows=list(csv.DictReader(line for line in stream if not line.startswith('#')))
    date_col='Date' if 'Date' in raw_rows[0] else 'observation_date'
    obs={r[date_col]:r['DGS10'] for r in raw_rows}
    absent=[]
    for r in main_grid:
        if r['in_ALFRED']=='True' and (r['calendar_date'] not in obs or obs[r['calendar_date']] in {'','.','NaN','nan'}):
            absent.append({'release_record_date':r['calendar_date'],
                'same_date_DGS10_observation':'ABSENT_OR_MISSING', 'evidence_grade':r['evidence_grade'],
                'interpretation':'同日観測欠損はH15発表なしの証拠ではない'.replace('同日観測欠損はH15発表なしの証拠ではない',
                '동일 날짜 관측 결측은 H15 발표 부재의 증거가 아님'),
                'source_url':r['evidence_url']})
    rel='audit/H15_RELEASE_WITHOUT_SAME_DATE_DGS10_OBSERVATION.csv'
    with (OUT/rel).open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['release_record_date','same_date_DGS10_observation','evidence_grade','interpretation','source_url'])
        writer.writeheader();writer.writerows(absent)
    required=['README.md','sources/H15_SOURCE_REGISTER.json','sources/FRED_ALFRED_RELEASE_DATES.csv',
        'sources/SOURCE_COLLECTION_LOG.md','audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv',
        'audit/H15_CALENDAR_GAP_REGISTER.csv','audit/H15_EXCEPTION_AND_DELAY_REGISTER.csv',
        'audit/H15_YEARLY_COVERAGE.csv','audit/H15_SOURCE_CONFLICTS.md',
        'audit/D10_CALENDAR_GATE_RECOMMENDATION.json','qc/D10_CALENDAR_INDEPENDENT_QC.md',
        'qc/INPUT_MANIFEST.json','reports/D10_CALENDAR_REMEDIATION_REPORT.md',
        'reports/D10_CALENDAR_REMEDIATION_HANDOFF.md','logs/WORK_LOG.md']
    facts={'main_calendar_dates':len(main_grid),'main_evidence_counts':counts,
        'rule_only_weekday_publication_candidates':len(candidates),
        'source_attempts':len(reg['sources']),'individual_official_documents':len(docs),
        'same_date_observation_absent':len(absent),'protected_files':len(inp['protected_files']),
        'changed_protected_files':changed,'independent_checks':len(independent['checks'])}
    tests={
        '본기간 날짜 5761개':len(main_grid)==5761,
        '등급 집계·권고 일치':counts==recommendation['main_evidence_counts'],
        '연도별 일수 합계':sum(int(r['dates']) for r in yearly if r['year']!='2010')==len(main_grid),
        '평일 후보 집계':sum(int(r['rule_only_weekday_publication_candidates']) for r in yearly if r['year']!='2010')==len(candidates)==637,
        '기존 보호파일 불변':not changed,
        '독립 QC 통과':independent['status']=='PASS',
        '게이트 자동 승인 없음':recommendation['D10_gate_automatically_passed'] is False,
        '후속 데이터·모델 미생성':recommendation['weekly_B10_XY_or_models_executed'] is False}
    if not all(tests.values()):
        write('qc/D10_CALENDAR_QC.json',{'status':'FAIL','tests':tests,'facts':facts})
        raise SystemExit('정합성 실패. 보고서 확정 중단.')
    year_table=table(['연도','달력일','E1','E2','E3','E4','규칙만 있는 평일 게시 후보'],
        [[r[k] for k in ['year','dates','E1','E2','E3','E4','rule_only_weekday_publication_candidates']]
         for r in yearly if r['year']!='2010'])
    conflict_rows=[r for r in main_grid if r['evidence_grade']=='E4']
    conflicts=table(['날짜','문제'],[
        ['2011-12-26','OPM 원문 Tuesday 표기와 실제 월요일 불일치. 자동 수정하지 않음.'],
        ['2012-10-29','ALFRED/API 발표일 기록과 Sandy 폐쇄 공지 충돌. 10/30 폐쇄도 별도 기록.'],
        ['2016-01-22','ALFRED/API true 기록은 있으나 false에는 없고 오후 Board 폐쇄·발표 이월 공지가 존재.'],
        ['2018-03-02','공식 폐쇄 공지는 H15 예정 발행을 명시하지만 ALFRED/API 기록이 없음.'],
        ['2019-01-19','토요일 ALFRED/API true 기록. false에는 없어 통상 영업일 게시로 확정할 수 없음.'],
        ['2022-12-31','OPM 2022 표의 Friday December 31과 실제 토요일 불일치. 의도된 연도를 임의 보정하지 않음.']])
    write('audit/H15_SOURCE_CONFLICTS.md',f'''# H.15 원천 대조 및 충돌 기록

본 파일은 충돌을 드러내는 감사 기록이다. 자료 삭제·자동 날짜 보정·게이트 변경은 없다.

## API 조회 조건에 따른 차이

`include_release_dates_with_no_data=false` 4,024개, `true` 4,090개. true 중 2026-10-16까지 4,039개는 ALFRED TXT와 일치한다. 나머지 51개는 미래 예정일이며 역사적 게시 확인에 사용하지 않았다.

ALFRED에 있고 API false에 없는 15개 날짜: {', '.join(cross['ALFRED_minus_API_false'])}.

이는 no-data 포함 여부의 차이이며 모든 날짜를 오류라고 단정하지 않는다. 다만 2016-01-22, 2019-01-19처럼 별도 공지·요일 문제까지 있는 날짜는 E4로 보존했다. ALFRED 설명상 release date는 원천 발표일 우선, 없으면 제공업체 날짜, 그마저 없으면 최초 FRED 이용 날짜를 쓸 수 있다. 발표 계열 중 일부 수정 날짜를 포함하며 DGS10 개별 관측의 게시·수신시각을 증명하지 않는다.

## 본기간 E4 6개

{conflicts}

## 요청 기간·페이지네이션·접근 실패

FRED 공개 달력의 `y=2011` 요청 및 별도 과거 범위 요청이 2025년 자료를 반환했다. 응답의 제목·실제 날짜를 확인했으므로 2011년 근거로 사용하지 않았다. ALFRED 2011 달력은 2페이지 53개를 확인했다. FRED 2025·2026 달력은 각 5페이지의 표시 범위와 총수를 대조했다. 2026 달력의 미래 예정일은 실제 과거 게시와 구분했다.

API의 각 조건은 offset 0/1000/2000/3000/4000으로 5페이지를 확인했다. 초기 연결실패·ReadTimeout과 HTTP 404는 접근 결과이며 자료 부재의 증거가 아니다. 실패 기록도 보존했다.

## 개별 자료·관측일의 차이

개별 연준 문서는 총 7개(본기간 5개, 2010 예열 1개, 2026-10-16 참고 1개)를 확보했다. 본기간 발표일 기록 중 개별 연준 문서를 이번 수집에서 확보하지 못한 날짜는 {cross['recorded_dates_without_official_document_count_main']:,}개다. 이는 문서가 존재하지 않는다는 판정이 아니다. 확보한 개별 문서 중 API false에 없는 날짜: {cross['official_docs_absent_API_false']}.

ALFRED 발표 기록일과 같은 날짜에 DGS10 유효 관측이 없는 경우는 {len(absent)}개다. 목록은 `{rel}`에 저장했다. H.15 발표일과 금리 관측일은 별개이므로 동시 발생을 요구하거나 관측일을 발표일로 대체하지 않는다.

## 달력 분리와 불완전성

OPM 연방휴일은 Board 휴일과 자동 동치가 아니다. K8의 현행 표를 과거 전기간 확정 근거로 소급하지 않았다. SOX RAW의 Date는 미국 주식 거래일 참조이며 거래소 캘린더 독립 인증이 아니다. Columbus Day·Veterans Day에도 SOX 관측이 존재하는 사례를 별도 보존했다.

ALFRED 기록은 2014-04-02 전후 밀도가 바뀐다. 연준의 2016-10-11 H.15 PDF·평균 공표 형식 변경과 같은 사건으로 취급하지 않는다. 구 체계의 주간 게시와 화~금 일별 갱신을 기록했고, 현행 16:15 ET 규칙을 모든 과거 실제 시각으로 확정하지 않았다.

공지에 예정 재개일이 있어도 실제 게시·수신시각과 같다고 처리하지 않는다. DDP 중단과 H15 웹 게시 중단도 분리한다. 모든 관측별 실제 timestamp 및 최초 빈티지 상태는 미검증이다.
''')
    report=f'''# 연구 C — D10 역사적 H.15 게시달력 근거 보완 보고서

작성일: 2026-10-17 KST. 범위: 역사적 게시달력 근거 수집·대조·QC·권고만.

**권고: `PARTIAL_EVIDENCE_ADDITIONAL_APPROVAL_REQUIRED`**

자동 QC PASS, 동일 작업 내 별도 구현 독립 QC 23/23 PASS. 이는 감사 정합성의 통과이며 D10 게이트 PASS나 최초 공개시각 검증을 뜻하지 않는다. 기존 Phase 2-B의 `BLOCKED_D10_CALENDAR_OR_RELEASE_EVIDENCE` 기록과 모든 원본 게이트는 변경하지 않았다.

## 1. 입력·작업 범위

Phase 1 LOCK, Phase 2-A 감사, D10 승인 MD/JSON, 기존 Phase 2-B 차단 보고서 및 독립 QC를 전체 열람하고 SHA-256을 기록했다. `qc/INPUT_MANIFEST.json` 참조. 주간 B10, SOX Y, B1~B10/F1, X/Y 병합, 모델 학습·튜닝·예측·시험 조회, D13 확정은 수행하지 않았다.

본 감사기간은 2011-01-01~2026-10-09의 **5,761개 달력일**이다. 2010년 365일은 선행 근거, 2026-10-10~16은 수집 당시 참고 구간으로 분리했다. 달력일 수는 주간 모델링 표본 수가 아니다.

## 2. 실제 확보 근거

- [FRED 공식 API 문서](https://fred.stlouisfed.org/docs/api/fred/release_dates.html)의 H.15 release_id=18을 사용했다. 사용자가 추가한 로컬 키로 조회했으며 키·키 포함 URL·비밀 오류내용을 저장하지 않았다.
- API no-data=false **4,024개**, true **4,090개**를 각각 5페이지로 수집해 count/limit/offset, 중복 0, 오름차순을 검증했다. 원본 JSON 10개를 보존했다.
- [ALFRED 공식 발표일 TXT](https://alfred.stlouisfed.org/release/downloaddates?rid=18&ff=txt) **4,039개**, 1996-12-09~2026-10-16을 원본 바이트로 확보했다. API true의 과거 4,039개와 일치한다. true에만 있는 미래 예정일 51개는 과거 게시 확인에서 제외했다.
- API false와 ALFRED의 차이 15개는 no-data 조회 의미와 별도 공지를 함께 검토했다. 발표일 목록은 release-level이며 개별 DGS10 최초 빈티지·정확한 게시시각을 입증하지 않는다.
- 개별 Federal Reserve H.15 자료 **7개**: 2010-01-04, 2011-01-10, 2012-06-25, 2014-01-06, 2015-03-02, 2016-01-19, 2026-10-16. 본기간 E1은 5개다. 2010/2011 문서는 발표일만 확인했으며 DGS10 관측일 추출은 미확인으로 남겼다. 나머지 5개 문서는 명시적인 표 헤더와 10-year 항목을 대조했다.
- [연준 H.15 공지](https://www.federalreserve.gov/feeds/h15.html), 공식 월별 달력, [Board 휴일표](https://www.federalreserve.gov/aboutthefed/k8.htm), [OPM 휴일자료](https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/), 거래소 안내를 별도로 수집했다. 전체 응답/실패 시도는 {len(reg['sources'])}건이며 URL·UTC 수집시각·HTTP 결과·원본 SHA-256을 등록했다.

## 3. 연도별 근거 커버리지

E1=개별 공식 문서, E2=공식 발표일 기록, E3=규칙 기반 추정, E4=충돌/미해결. 한 날짜에 최종 등급 하나만 부여했다. E3에는 주말·일반 비게시일 추정도 포함되므로 전부 결측 거래일로 해석하면 안 된다.

{year_table}

2026년은 10월 9일까지 282일이다. 본기간 합계: **E1 5 / E2 3,289 / E3 2,461 / E4 6**. E1/E2도 정확한 실제 공개시각·수신시각 확인이 아니다. E3의 규칙상 평일 게시 후보는 **637일**이며 2011년 198일, 2012년 197일, 2013년 196일, 2014년 45일, 2015년 1일이다. 나머지 E3를 누락 발표일이나 손실 주간 표본으로 계산하지 않았다. 달력 가정은 승인되지 않은 `ASSUMED_CALENDAR`로 보존했다.

`H15_YEARLY_COVERAGE.csv`에는 공식 문서 수, release 기록 수, 규칙상 비게시일, 특별폐쇄·지연 공지 수도 따로 있다. 이들 보조 지표는 서로 중첩하므로 E1~E4와 더하지 않는다. 날짜 전수는 `H15_PUBLICATION_CALENDAR_EVIDENCE.csv`, E3/E4 전체는 `H15_CALENDAR_GAP_REGISTER.csv`에 있다.

## 4. 예외·충돌 및 과거 발표체계

공지·월별 추가 근거 이벤트 43개를 보존했다. 이는 43개 DGS10 지연 사례라는 뜻이 아니다. Treasury 누락·정정, Board 폐쇄, 예정 발행 예외, DDP 채널 중단, 형식 변경 등이 포함된다.

2012 Sandy 10/29 공지와 10/30 영향일을 분리했다. 2016-01-22·25·26 폐쇄/지연, 2018-12-05 및 12/24, 2020-12-24, 2024-12-24, 2025-01-09 이월 근거를 확인했다. 2018-03-02와 2025-01-06·07처럼 폐쇄에도 H15/통계자료 예정 발행이라는 예외도 보존했다. 재개 예정일은 실제 재개 timestamp로 승격하지 않았다.

{conflicts}

2011-03-10 및 2014-01-14의 10년 금리 정정과 2018·2020·2023년 Treasury 누락/정정 공지는 현재 수정본과 과거 게시값이 다를 수 있음을 보여준다. DDP만 중단되고 H15 웹 자료는 가용했던 공지도 있어 채널을 구분했다.

구 H15 문서는 월요일 주간 자료와 화~금 일별 갱신, 월요일 휴일 시 화요일 주간 자료 등 별도 체계를 설명한다. ALFRED의 2014-04-02 전후 기록 밀도 변화와 연준의 2016-10-11 PDF/주·월평균 공표 형식 변경은 별개다. 2011년 목록 53개를 모든 일별 게시가 53회뿐이었다는 의미로 해석할 수 없다. 현행 일반 16:15 ET 게시규칙을 2011~2026년 매일의 실제 게시시각으로 소급하지 않았다.

## 5. 승인 정책과 미검증 상태

`C_DGS10_H15_NEXT_BOARD_DAY_PLUS_OVERNIGHT_v1`은 불변이다. 관측일 다음 실제 Board H15 게시 영업일 16:15 ET는 **가정 발표시각**, 다음 달력일 08:00 ET는 **가정 이용 가능시각**이며, 알려진 더 늦은 실제 근거가 우선한다. 예측원점은 대상 주 첫 미국 세션 09:00 America/New_York이고 이용 가능시각은 엄격히 이전이어야 한다.

`B10_w = 100 × (R[w-1,O] − R[w-2,O])`, 단위 bp, 주 내부 최신 적격값 선택 규칙을 유지했다. 다른 주 자동 이월·미래 보간은 허용하지 않는다. 이번에는 실제 관측에 정책을 적용하거나 B10을 산출하지 않아 실제/가정 timestamp 열 모두 `null`이다. `publication_status`, `vintage_status`는 `UNVERIFIED`다.

DST는 America/New_York의 09:00이 겨울 UTC14:00, 여름 UTC13:00임을 별도 논리 검사했다. 일반 시각 규칙과 실제 과거 공개시각 검증은 구분했다. FRED 공개 달력의 시각은 Central Time이므로 ET 실제 수신시각으로 쓰지 않았다.

## 6. 완전성 질문에 대한 답

**Q1. 전수 Board 게시달력 재구성 가능?** 현재 근거만으로는 불가능하다. 상당한 E1/E2 날짜는 확보했지만 637개 평일 후보와 6개 충돌이 남았다. E3를 포함한 후보 달력은 만들 수 있어도 최종 승인·전수 검증 달력은 아니다.

**Q2. 2011~2016과 이후 차이?** 주간 자료/일별 갱신 및 2016 형식 변경이 있다. ALFRED의 과거 기록 밀도만으로 당시 일별 갱신 여부를 단정할 수 없다.

**Q3. 폐쇄·지연 처리 가능?** 확보한 명시적 폐쇄일·이월 예정일은 반영할 수 있지만 예외의 전수성과 실제 재개시각은 미확인이다. 누락/정정된 개별 DGS10 관측의 최초 이용 가능성은 별도 구현에서 보수적으로 다뤄야 한다.

**Q4. 부족 날짜 수·집중 구간?** E3 전체 2,461개 중 평일 게시 후보 637개가 주로 2011~2014년 1분기에 집중한다. E4는 위 6개 날짜다. 주말·휴일 규칙상 비게시일은 별도 표시했다. 주간 표본 손실은 B10을 계산하지 않아 확정하지 않았다.

**Q5. 기존 승인만으로 진행 가능?** 현재 수정본 및 보수적 시각 가정 승인은 유지되지만, 역사적 게시일 자체의 E3 추정을 자동 허용하는 근거는 아니다. 달력 추정 허용 범위와 E4·재개 미확인 사례 처리에 대한 추가 사용자 승인이 필요하다. 승인 후에도 후속 구현 QC 및 Phase 2-B 실행은 별도 승인 범위다.

## 7. QC·보호·재현성

자동 QC 8개 및 수집/매핑 모듈을 가져오지 않은 독립 QC 23개가 통과했다. 후자는 동일 Codex 작업 내 별도 구현이며 외부 심사가 아니다. API 페이지·정렬·중복, 원본 응답 해시, 날짜 전수, 등급, 연도 집계, 휴일 분리, 예외, DST, 미확인 상태, 금지 계산 및 보호파일을 확인했다.

기존 보호파일 **{len(inp['protected_files']):,}개 SHA-256 불변**, 불일치 0개. 여기에는 RAW·freeze·Phase 0/1·D10 감사/승인·기존 Phase 2-B 결과가 포함된다. 사용자가 승인해 추가한 .env 키는 변경 전 보호목록에 없으며 새 무단변경으로 판단하지 않았다. 비밀은 manifest에도 기록하지 않았다.

원천 응답은 `sources/originals/`, HTTP·해시는 `sources/H15_SOURCE_REGISTER.json`, 입력 해시는 `qc/INPUT_MANIFEST.json`, 출력 해시는 `qc/OUTPUT_MANIFEST.json` 및 별도 SHA-256 파일에 있다. 저장 근거를 이용한 오프라인 독립 QC가 가능하다. 공식 페이지/API는 나중에 수정될 수 있어 재다운로드가 현재 저장 바이트와 같다는 보장은 없다.

## 8. 권고·인수인계

**권고는 `PARTIAL_EVIDENCE_ADDITIONAL_APPROVAL_REQUIRED`다.** 기존 D10 게이트를 PASS로 바꾸지 않았고 D13은 미처리다. 다음 사용자 검토는 (1) 637개 규칙상 평일 후보를 E3 가정으로 허용할 범위, (2) E4 6개와 실제 재개 미확인 사례의 추가 근거 확보/보수적 처리 방침, (3) 그 정책 확정 후 별도 Phase 2-B 재개 여부다. 이미 승인된 현재 수정본 사용을 재승인해 달라는 요청과는 구분한다.

작업은 이 감사에서 종료한다. 주간 B10/X/Y·모델·시험 계산은 시작하지 않았다.
'''
    write('reports/D10_CALENDAR_REMEDIATION_REPORT.md',report)
    write('reports/D10_CALENDAR_REMEDIATION_HANDOFF.md',f'''# D10 달력 근거 보완 인수인계

권고: `PARTIAL_EVIDENCE_ADDITIONAL_APPROVAL_REQUIRED`. 원본 게이트 변경 없음.

본기간 5,761일: E1 5, E2 3,289, E3 2,461, E4 6. E3 평일 게시 후보 637일은 미승인 달력 가정이다. 주간 표본 수가 아니다. API false 4,024, true 4,090; ALFRED 4,039와 true 과거분 일치. 미래 예정일 51개 제외.

확인 대상: `reports/D10_CALENDAR_REMEDIATION_REPORT.md`, `audit/H15_SOURCE_CONFLICTS.md`, 날짜별 근거/공백/예외 CSV, 자동·독립 QC.

정책 ID와 B10 수식은 불변. actual 시각은 null이고 publication/vintage는 UNVERIFIED다. D10 게이트 자동 PASS 및 D13 처리는 없다. 보호파일 {len(inp['protected_files'])}개 변경 0건.

사용자 승인 대기: E3 일정 추정 허용 범위, E4 및 재개 미확인 처리, 이후 별도 Phase 2-B 재개 지시. 현재 수정본·보수적 가정의 기존 승인은 유지한다.

후속 담당자는 입력·출력 manifest를 먼저 검증한다. 기존 build_v1_0을 덮어쓰지 않고, 별도 승인 이후 새 실행 버전에서 구현 QC를 수행해야 한다. 이번 작업에서는 주간 B10/X/Y, 모델, 최종 시험을 실행하지 않았다.
''')
    write('README.md','''# 연구 C — 역사적 H.15 게시달력 근거 보완

공식 발표일 수집·대조·근거 공백·예외 감사 전용이다. 최종 승인 게시달력이나 주간 데이터셋이 아니다.

먼저 `reports/D10_CALENDAR_REMEDIATION_REPORT.md`와 `reports/D10_CALENDAR_REMEDIATION_HANDOFF.md`를 읽는다. 권고는 PARTIAL_EVIDENCE_ADDITIONAL_APPROVAL_REQUIRED이며 원본 게이트·정책 변경 없음.

- sources: 원본 HTTP 응답, 메타데이터, API/ALFRED 발표일 및 수집 실패 기록
- audit: 날짜별 E1~E4, 연도별 집계, 충돌·예외·권고
- qc: 입력 1,076개 해시, 자동/독립 QC, 출력 봉인
- code: 수집·분석·독립 검사·보고서 코드
- logs: 최초 분석 스냅샷 및 작업 이력

Python은 `research_C/phase0_raw_audit/.venv/Scripts/python.exe`를 사용했다. Python 3.13, requests, beautifulsoup4, pandas는 기존 환경 버전으로 실행했으며 이번 작업에서 패키지 설치·갱신은 하지 않았다. 정확한 런타임은 입력 manifest에 있다.

수집 순서: collect_evidence.py prepare → collect_evidence.py collect → retry_sources.py → collect_fred_api.py → collect_supplement.py → analyze_calendar.py → collect_gap_documents.py → refine_evidence.py → independent_qc.py → finalize_audit.py. API 수집은 승인된 로컬 환경/.env FRED_API_KEY가 있어야 한다. 키를 출력하거나 배포하지 않는다.

스크립트는 기존 완료 파일 덮어쓰기를 차단한다. 새로운 수집은 별도 실행 폴더와 신규 입력 manifest로 수행한다. 현재 저장 응답을 검증할 때는 출력 manifest 해시 대조와 독립 검사 코드를 사용한다. 독립 검사 결과 파일도 보존하므로 다시 실행하려면 별도 검토 폴더에서 결과를 기록하도록 경로를 지정해야 한다. 공개 사이트가 바뀌어도 저장 스냅샷은 당시 근거로 남는다.

SHA-256은 원천 register·입력/출력 manifest로 추적한다. OUTPUT_MANIFEST.json은 자기 자신과 봉인 파일을 제외한 모든 파일을 포함하고, JSON 자체 해시는 OUTPUT_MANIFEST.sha256에 기록한다.

주간 B10, X/Y, D13 결정, 학습·튜닝·예측·시험은 미실행이다.
''')
    write('logs/WORK_LOG.md','''# 작업 기록

2026-10-17 KST, 동일 Codex 작업 내 감사.

1. 사용자 지시와 LOCK/감사/승인/차단 보고서 6개를 열람하고 기존 1,076개 보호파일의 기준 해시를 확인했다.
2. 전용 신규 폴더에서 공식 HTTP 응답을 수집했다. 기본 샌드박스 네트워크 거부·초기 연결실패·ReadTimeout은 자료 부재로 처리하지 않았다. 허용된 공식 공개 URL을 재시도해 ALFRED TXT와 문서·달력을 확보했다. 404 및 초기 실패 메타데이터도 보존했다.
3. 사용자가 FRED_API_KEY를 .env에 추가한 후 승인된 로컬 키로 API 두 조건을 각 5페이지 수집했다. 비밀·키 포함 URL·오류본문은 저장하지 않았다. 초기 키 없음 기록은 과거 이력으로 보존했다.
4. FRED의 과거 달력 요청이 다른 연도를 반환한 것을 식별해 해당 응답을 과거 근거로 쓰지 않았다. ALFRED 2011 2페이지, FRED 2025/2026 5페이지씩 별도 대조했다.
5. 최초 분석 후 추가 연준 월별 달력 8건을 요청했고 7건 성공/1건 404였다. 초기 새 분석 결과는 logs/INITIAL_*로 보존하고 추가 폐쇄·예정발행·이월 근거로 정련했다. 2012-10-29 공지의 10/30 영향일을 분리하고, 2018-03-02 예정발행과 기록 부재 충돌을 E4로 남겼다. 변경 상세는 audit/REFINEMENT_RECORD.json에 있다.
6. 별도 구현 23개 독립 검사가 통과했다. 공식 목록을 최초 공개시각으로 승격하지 않고 E3 추정/E4 충돌을 그대로 보고했다.
7. 한국어 보고서·충돌표·인수인계와 입력/출력 봉인을 작성했다. 원본 보호해시 재검증, 주간 B10/X/Y 및 모델 계산 미실행 상태를 확인했다.

재개 지시는 없다. 원본 게이트·D10 정책·D13 및 Phase 2-B 기존 결과는 변경하지 않았다.
''')
    tests['필수 산출물 존재']=all((OUT/r).is_file() for r in required)
    write('qc/D10_CALENDAR_QC.json',{'status':'PASS' if all(tests.values()) else 'FAIL',
        'scope':'감사 산출물 정합성; 게이트 PASS 아님','tests':tests,'facts':facts,
        'recommendation':recommendation['recommendation'],'actual_release_timestamps_verified':False})
    if not all(tests.values()): raise SystemExit('필수 파일 누락')
    output=[]
    for path in sorted(OUT.rglob('*')):
        if path.is_file() and path.name not in {'OUTPUT_MANIFEST.json','OUTPUT_MANIFEST.sha256'}:
            output.append({'path':path.relative_to(OUT).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)})
    write('qc/OUTPUT_MANIFEST.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'자기 자신 및 별도 봉인 해시 파일을 제외한 신규 감사 파일 전수',
        'files':output,'protected_files_unchanged':len(inp['protected_files']),'weekly_XY_generated':False})
    write('qc/OUTPUT_MANIFEST.sha256',sha(OUT/'qc/OUTPUT_MANIFEST.json')+'  OUTPUT_MANIFEST.json\n')
    print(json.dumps({'status':'PASS','facts':facts,'output_files_sealed':len(output)},ensure_ascii=False))

if __name__=='__main__': main()
