"""수집/등급 생성 코드를 가져오지 않는 저장 근거 독립 검사. 외부 심사가 아니다."""
import ast
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parents[2]

def load(rel):
    return json.loads((OUT / rel).read_text(encoding='utf-8-sig'))

def rows(rel):
    with (OUT / rel).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    checks = []
    def check(name, condition, detail):
        checks.append({'검사': name, '통과': bool(condition), '근거': detail})
    reg = load('sources/H15_SOURCE_REGISTER.json')
    api = load('sources/FRED_API_COLLECTION.json')
    check('H15 release ID', reg['release_id'] == api['release_id'] == 18,
          '공식 H.15 목록 rid=18 및 API 파라미터 대조')
    api_dates = {}
    for run in api['runs']:
        ds = []
        offsets = []
        valid = True
        for page in run['pages']:
            raw = load(page['body_file'])
            offsets.append(raw['offset'])
            valid &= digest(OUT / page['body_file']) == page['sha256']
            valid &= raw['count'] == run['count'] and raw['limit'] == 1000
            valid &= page['public_parameters']['release_id'] == 18
            ds.extend(item['date'] for item in raw['release_dates'])
        api_dates[run['include_release_dates_with_no_data']] = set(ds)
        check('API 페이지 완전성 ' + str(run['include_release_dates_with_no_data']),
              valid and offsets == list(range(0, run['count'], 1000))
              and len(ds) == run['count'] and ds == sorted(set(ds)),
              {'rows': len(ds), 'offsets': offsets, 'duplicates': len(ds)-len(set(ds))})
    txt = (OUT/'sources/originals/alfred_release_dates_txt_retry_default.body').read_text(encoding='utf-8-sig')
    alfred = re.findall(r'^\s*(\d{4}-\d{2}-\d{2})\s*$', txt, flags=re.M)
    check('ALFRED 전수 목록', len(alfred) == 4039 and alfred == sorted(set(alfred)),
          {'rows': len(alfred), 'min': min(alfred), 'max': max(alfred)})
    past_true = {d for d in api_dates[True] if d <= '2026-10-16'}
    check('API와 ALFRED 대조', past_true == set(alfred) and api_dates[False] <= set(alfred),
          {'true_future': len(api_dates[True]-past_true),
           'ALFRED_minus_false': sorted(set(alfred)-api_dates[False])})
    cross = load('audit/SOURCE_CROSSCHECK_DETAILS.json')
    # 공개 달력의 원시 페이지별 날짜를 독립 집합으로 모아 TXT와 대조한다.
    public_2011 = set()
    for page in cross['public_calendar_pages']:
        if 'alfred.stlouisfed.org' in page['url']:
            public_2011.update(d for d in page['dates'] if d.startswith('2011-'))
    check('과거 ALFRED 공개 달력 페이지 대조', public_2011 == {d for d in alfred if d.startswith('2011-')},
          {'2011_dates': len(public_2011), 'FRED_과거요청_연도불일치_격리': True})
    bad_sources = []
    for item in reg['sources']:
        if item.get('body_file') and digest(OUT/item['body_file']) != item['sha256']:
            bad_sources.append(item.get('id', item['body_file']))
    check('원천 응답 바이트 SHA256', not bad_sources,
          {'수집시도': len(reg['sources']), '해시불일치': bad_sources})
    grid = rows('audit/H15_PUBLICATION_CALENDAR_EVIDENCE.csv')
    ds = [r['calendar_date'] for r in grid]
    start, end = date(2010,1,1), date(2026,10,16)
    expected = [(start+timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
    check('달력 날짜 전수·정렬·중복', ds == expected, {'rows': len(ds), 'main_end': '2026-10-09'})
    main_rows = [r for r in grid if '2011-01-01' <= r['calendar_date'] <= '2026-10-09']
    check('감사 본기간 구분', len(main_rows) == 5761 and all(
        (r['in_main_audit_period'] == 'True') == ('2011-01-01' <= r['calendar_date'] <= '2026-10-09') for r in grid),
        '2010 예열 및 2026-10-10~16 참고 구간 별도 표시')
    docs = load('audit/H15_OFFICIAL_DOCUMENT_EXTRACTS.json')['documents']
    doc_dates = {r['release_date'] for r in docs}
    src_by_id = {r.get('id'): r for r in reg['sources'] if r.get('http_status') == 200}
    doc_valid = True
    for doc in docs:
        raw = OUT/src_by_id[doc['source_id']]['body_file']
        text = re.sub('<[^>]+>', ' ', raw.read_text(encoding='utf-8', errors='replace'))
        text = re.sub(r'\s+', ' ', text)
        d = date.fromisoformat(doc['release_date'])
        # release date는 HTML 텍스트에 명시되어야 한다. 날짜를 URL에서만 추론하지 않는다.
        date_pattern = rf'{d.strftime("%B")}\s+0?{d.day},?\s+{d.year}'
        doc_valid &= bool(re.search(date_pattern, text, flags=re.I))
        doc_valid &= digest(raw) == doc['body_sha256']
        doc_valid &= all(obs < doc['release_date'] for obs in doc['observation_dates_verified'])
    check('개별 공식 게시자료와 관측일 구분', doc_valid and len(docs) == 7,
          {'문서': len(docs), '본기간문서': sum('2011-01-01'<=d<='2026-10-09' for d in doc_dates),
           '관측일확인불가': ['2010-01-04','2011-01-10']})
    grade_errors = []
    for r in grid:
        grade = r['evidence_grade']; d = r['calendar_date']
        valid = grade in {'E1','E2','E3','E4'}
        if grade == 'E1': valid &= d in doc_dates and r['official_release_document_found']=='True'
        if grade == 'E2': valid &= d in set(alfred) or d in api_dates[False]
        if grade == 'E3': valid &= r['calendar_evidence_status']=='ASSUMED_CALENDAR' and r['calendar_assumption_authorized']=='False'
        if grade == 'E4': valid &= r['calendar_evidence_status']=='UNRESOLVED' and r['conflict_flag']=='True'
        if not valid: grade_errors.append(d)
    check('E1~E4 근거 등급', not grade_errors, {'오류': grade_errors})
    check('실제/가정 시각 미생성 및 미검증 상태', all(
        all(r[k] == 'null' for k in ['actual_release_at','actual_available_at','assumed_release_at','assumed_available_at'])
        and r['publication_status'] == r['vintage_status'] == 'UNVERIFIED' for r in grid),
        '달력 감사에서 실제 관측별 가정시각 적용까지 수행하지 않음')
    gap = rows('audit/H15_CALENDAR_GAP_REGISTER.csv')
    check('근거 공백의 누락 없음', {r['calendar_date'] for r in gap} ==
          {r['calendar_date'] for r in grid if r['evidence_grade'] in {'E3','E4'}},
          {'공백등록행': len(gap)})
    year_errors = []
    for annual in rows('audit/H15_YEARLY_COVERAGE.csv'):
        y = annual['year']
        chosen = [r for r in grid if r['calendar_date'].startswith(y) and
                  (y == '2010' or r['in_main_audit_period']=='True')]
        counter = Counter(r['evidence_grade'] for r in chosen)
        if len(chosen)!=int(annual['dates']) or any(counter[g]!=int(annual[g]) for g in ['E1','E2','E3','E4']):
            year_errors.append(y)
    check('연도별 등급 독립 집계', not year_errors, {'오류연도': year_errors})
    bydate = {r['calendar_date']: r for r in grid}
    conflicts = sorted(r['calendar_date'] for r in main_rows if r['evidence_grade']=='E4')
    check('충돌 날짜 무보정 보존', conflicts == ['2011-12-26','2012-10-29','2016-01-22','2018-03-02','2019-01-19','2022-12-31'], conflicts)
    check('휴일 달력 분리', all(r['US_equity_date_basis']=='SOX_RAW_DATE_ONLY_NOT_INDEPENDENT_EXCHANGE_CALENDAR' for r in grid)
          and bydate['2011-10-10']['US_equity_RAW_date_present']=='True'
          and bydate['2011-11-11']['US_equity_RAW_date_present']=='True',
          'Columbus/Veterans 주식시장 관측일과 연방휴일 참조를 별도 필드로 보존')
    check('지연·폐쇄·예정 발행 예외 구분',
          bydate['2012-10-30']['nonpublication_due_to_specific_notice']=='True'
          and bydate['2018-03-02']['special_closure_status']=='OFFICIAL_CLOSURE_H15_PLANNED'
          and bydate['2025-01-06']['special_closure_status']=='OFFICIAL_CLOSURE_H15_PLANNED'
          and bydate['2024-12-24']['nonpublication_due_to_specific_notice']=='True',
          '폐쇄를 일괄 비게시일로 판정하지 않고 명시적인 이월·예외만 기록')
    check('2016 이전 자료체계 구분', len([d for d in alfred if d.startswith('2011-')])==53
          and len([d for d in alfred if d.startswith('2015-')])==249,
          'ALFRED 2014 기록 밀도 변화는 연준 2016-10-11 형식 변경과 별개')
    ny = ZoneInfo('America/New_York')
    winter = datetime(2026,1,5,9,tzinfo=ny)
    summer = datetime(2026,7,6,9,tzinfo=ny)
    check('DST 및 엄격한 선행 조건 논리검사',
          winter.astimezone(timezone.utc).hour==14 and summer.astimezone(timezone.utc).hour==13
          and not winter < winter and winter-timedelta(microseconds=1)<winter,
          '가상 시각만 사용. 실제 DGS10 관측의 이용 가능시각을 생성한 검사가 아님')
    inp = load('qc/INPUT_MANIFEST.json')
    changed = [rel for rel, item in inp['protected_files'].items()
               if not (ROOT/rel).is_file() or digest(ROOT/rel)!=item['sha256']]
    check('원본 보호 SHA256', not changed, {'대상': len(inp['protected_files']), '불일치': changed})
    recommendation = load('audit/D10_CALENDAR_GATE_RECOMMENDATION.json')
    check('정책·게이트·D13 불변', not changed and recommendation['recommendation_only']
          and not recommendation['D10_gate_automatically_passed'] and recommendation['D13_unchanged'],
          '기존 게이트·정책 파일은 보호목록 바이트로 검사')
    # 실행 코드 AST의 모델/시계열 특성 계산 API 금지 검사. 본 QC 코드는 대상에서 제외한다.
    forbidden = {'fit','fit_transform','predict','pct_change','rolling'}
    violations = []
    for path in (OUT/'code').glob('*.py'):
        if path.name in {'independent_qc.py','finalize_audit.py'}: continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden:
                violations.append(path.name+':'+node.func.attr)
    check('주간 B10·X/Y 및 모델 미실행', not violations and not recommendation['weekly_B10_XY_or_models_executed'],
          {'금지계산호출': violations, '기존산출물': '보호 해시 일치로 확인'})
    # 비밀 값은 비교만 하고 출력/해시에 포함하지 않는다.
    secrets = []
    env = ROOT/'.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*FRED_API_KEY\s*=\s*(.*?)\s*$',line)
            if match and match[1].strip('"\''): secrets.append(match[1].strip('"\''))
    leaked = any(secret.encode() in p.read_bytes() for p in (OUT/'sources').rglob('*') if p.is_file() for secret in secrets)
    check('API 비밀 미기록', not leaked and not api['secret_saved_or_printed'],
          '로컬 승인 키는 값 출력 없이 저장 응답과 비교. .env는 보호목록에서 제외된 사용자 승인 변경')
    result = {'status': 'PASS' if all(r['통과'] for r in checks) else 'FAIL',
              'independence': '동일 Codex 작업 내 수집/매핑 모듈을 가져오지 않은 별도 구현. 외부 심사 아님.',
              'checks': checks, 'main_evidence_counts': dict(Counter(r['evidence_grade'] for r in main_rows)),
              'calendar_gate_pass': False, 'protected_files': len(inp['protected_files'])}
    if '--check-only' in sys.argv:
        print(json.dumps({'status':result['status'],'checks':len(checks),'failures':[r for r in checks if not r['통과']]},ensure_ascii=False))
        if result['status']!='PASS': raise SystemExit(1)
        return
    dest=OUT/'qc/D10_CALENDAR_INDEPENDENT_QC.json'
    with dest.open('x',encoding='utf-8') as stream: json.dump(result,stream,ensure_ascii=False,indent=2)
    lines=['# D10 역사적 게시달력 독립 QC', '', '**판정: '+result['status']+'**', '',result['independence'], '',
           'QC PASS는 감사 산출물의 정합성만 의미한다. 역사적 최초 공개시각 검증이나 D10 게이트 PASS가 아니다.', '',
           '| 검사 | 결과 | 근거 |','|---|---|---|']
    for r in checks:
        detail=json.dumps(r['근거'],ensure_ascii=False) if not isinstance(r['근거'],str) else r['근거']
        lines.append('| '+r['검사']+' | '+('PASS' if r['통과'] else 'FAIL')+' | '+detail.replace('|','/')+' |')
    (OUT/'qc/D10_CALENDAR_INDEPENDENT_QC.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'checks':len(checks),'failures':[r for r in checks if not r['통과']]},ensure_ascii=False))
    if result['status']!='PASS': raise SystemExit(1)

if __name__=='__main__': main()
