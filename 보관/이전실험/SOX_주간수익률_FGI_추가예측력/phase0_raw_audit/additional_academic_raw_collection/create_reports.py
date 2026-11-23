"""Create Phase 0d collection reports from actual saved results, never expected counts."""
from pathlib import Path
import json,csv,hashlib
RUN=Path(__file__).resolve().parent
ROOT=RUN.parents[2]
def read(name):return json.loads((RUN/name).read_text(encoding='utf-8'))
def main():
    results=read('ACADEMIC_RAW_COLLECTION_QC.json')['datasets']; qc=read('ACADEMIC_RAW_INDEPENDENT_QC.json')
    successful=[r for r in results if r['status']=='SUCCESS']; failed=[r for r in results if r['status']!='SUCCESS']
    collection=read('ACADEMIC_RAW_COLLECTION_QC.json')
    collection['collection_status']='COMPLETE' if len(successful)==10 else 'PARTIAL'
    collection['data_integrity_status']=qc['status']
    collection['historical_availability_status']='CONDITIONAL; historical publication/vintage UNVERIFIED'
    missing_notes=[]
    for ds in collection['datasets']:
        if ds['status']!='SUCCESS':continue
        for out in ds['outputs']:
            with (ROOT/out['file']).open(encoding='utf-8') as f:
                next(f); reader=csv.DictReader(f)
                out['missing_observation_dates']=[r['Date'] for r in reader if any(v=='' for k,v in r.items() if k!='Date')]
            if out['missing_observation_dates']:
                missing_notes.append(ds['dataset_id']+': '+', '.join(out['missing_observation_dates']))
    collection['independent_validation']={'status':qc['status'],'protected_files_checked':qc['protected_files_checked'],
       'protected_changed':qc['protected_changed'],'additional_existing_research_files_checked':qc['additional_existing_research_files_checked'],
       'additional_existing_research_changed':qc['additional_existing_research_changed'],'source_values_match':all(r['status']=='PASS' for r in qc['datasets'])}
    (RUN/'ACADEMIC_RAW_COLLECTION_QC.json').write_text(json.dumps(collection,indent=2,ensure_ascii=False),encoding='utf-8')
    table=['| 번호 / 자료 | 표 | 행 수 | 시작일 | 종료일 | 결측 셀 | 중복 |','|---|---|---:|---|---|---:|---:|']
    for ds in successful:
        for out in ds['outputs']:table.append(f"| {ds['dataset_id']} | {out['table']} | {out['rows']:,} | {out['min_date']} | {out['max_date']} | {out['missing_cells']} | {out['duplicate_dates']} |")
    for ds in failed: table.append(f"| {ds['dataset_id']} | {ds['status']} | — | — | — | — | — |")
    lines=['# 연구 C Phase 0d 추가 RAW 수집 보고서','',f"실행일: 2026-10-16. 수집 성공 **{len(successful)}/10종**. 독립 데이터 QC **{qc['status']}**.",
           '연구 C 후보 원천의 수집·정규화·무결성 감사만 수행했다. 설명변수 채택, 주간 X/Y, 모델 학습은 수행하지 않았다.',
           '역사적 시점가용성은 CONDITIONAL이다. 과거 게시시각·최초 빈티지는 UNVERIFIED로 남긴다.','',
           '## 실제 수집 결과','',*table,'',
           '기존 실제 RAW는 37종, 최종 번호는 42였다. 신규 번호는 43~52로 예약했으며 빈 번호는 재사용하지 않았다. 성공한 자료만 해당 data/raw/<dataset_id>/에 게시했다.',
           'French 49개 업종 VW/EW는 같은 지표가 아니므로 서로 다른 canonical CSV로 보존했다. 49개 업종 전체를 유지했으며 서로 다른 자료를 합치지 않았다.',
           '원본 ZIP·ZIP 내부 CSV의 전체 역사와 실제 HTTP 응답은 source_original/에 보존했다. canonical은 2010년부터이며, 연구 분석 후보는 2011년 이후다.',
           '모든 canonical CSV는 1행 # SOURCE, 2행 header 형식이다. pandas에서는 comment="#"로 읽는다.','',
           '### 원천 결측 상세','',
           *[f'- {note}; 원본에도 결측이며 보간·0 대체하지 않았다.' for note in missing_notes],'',
           '## 원천별 활용 후보와 한계','',
           '- 43: 업종 수익률 후보. Chips·Hardw·Softw·LabEq를 포함한 모든 49개 원래 업종명을 유지했다. 아직 변수 선택하지 않았다.',
           '- 44·45: 일반 위험요인과 모멘텀의 통제 후보. 게시된 수익률 척도를 그대로 보존하고 100으로 나누지 않았다.',
           '- 46 SOXX: 반도체 ETF 후보. 47 SMH는 선택적 확장 후보다. ETF 거래량을 SOX 전체 거래량으로 해석하지 않는다.',
           '- 48~52: 고용·물가 거시 후보. 주간/월간의 원래 주기와 단위를 유지한다. 발표일 매핑이나 일별 보간은 하지 않았다.',
           '- 수집한 모든 현재 이력의 역사적 최초 빈티지와 실제 과거 이용 가능성은 미확인이다. 특히 macro 관측일을 발표일로 사용하면 안 된다.','',
           '## 실패 및 접근 제약','']
    if failed:
        for r in failed:
            lines += [f"### {r['dataset_id']} — 실패",'',*[f"- 시도 {e.get('attempt','')}: {e.get('type','')} — {e.get('message','')}" for e in r.get('errors',[])],'']
        lines += ['FRED의 날짜 지정 공식 CSV는 각 3회 시도했으며 연결 초기화/응답 시간 초과가 발생했다. 표준 전체 이력 CSV 링크의 단일 추가 확인 결과는 FRED_FULL_HISTORY_FALLBACK.json에 보존했다. 실패 자료는 빈 RAW나 대체 자료로 성공 처리하지 않았다.','']
    else:lines += ['실패 자료 없음. 초기 요청의 오류 및 공식 CSV 대체 URL 확인 이력은 FETCH_RESULTS.json에 보존했다.','']
    lines += ['## QC와 보호','',
              f"기존 보호 파일 {qc['protected_files_checked']}개 SHA-256 변경 {len(qc['protected_changed'])}건. 신규 manifest 파일 {qc['manifest_files_checked']}개 해시 재검증.",
              f"별도로 기존 연구 C·KFGI 자료 {qc['additional_existing_research_files_checked']}개를 게시 전후 대조했으며 변경 {len(qc['additional_existing_research_changed'])}건이다. 기존 D1 무결성 문제를 재조사하지 않았다.",
              f"독립 비교 숫자 셀 {sum(r['compared_numeric_cells'] for r in qc['datasets']):,}개. 독립 코드에서 원본을 다시 파싱해 날짜·열·값·해시를 대조했다.",
              'French는 ZIP CRC·추출 CSV 원본 바이트·VW/EW 개별 일별 블록과 Decimal 값을 대조했다. Yahoo는 yfinance 반환표뿐 아니라 실제 chart JSON의 timestamp·OHLC·adjclose·volume을 직접 대조했다.',
              '원래 결측·휴일은 임의 보완하지 않았다. French -99.99/-999는 공식 결측 표지로만 해석한다. 원본에는 그대로 남기고 canonical에만 빈 셀로 표현한다.',
              '이 PASS는 원본→canonical 변환·보존의 검사 결과이며 역사적 point-in-time 이용 가능성 승인이나 연구설계 동결을 뜻하지 않는다.','',
              '## 파일과 재현 순서','',
              '- COLLECTION_PLAN.json, EXISTING_RAW_INVENTORY.json, PROTECTED_INPUT_HASHES.json: 사전 dry-run과 기존 RAW 해시.',
              '- fetch_sources.py --dry-run → --collect: 최초 인벤토리 후 실제 수집. 같은 실행 폴더에서 dry-run을 재실행하면 덮어쓰기 방지를 위해 중단한다.',
              '- fred_public_csv_fallback.py: 날짜 지정 FRED 실패분의 공식 전체 이력 링크 단일 확인. 최초 수집 완료 후 --merge로 FETCH_RESULTS.json에 결과 반영.',
              '- publish_raw.py: 검증 후 새 RAW 폴더만 게시. 기존 폴더가 있으면 중단.',
              '- independent_qc.py: 별도 원본 파서·HTTP JSON·해시 대조.',
              '- create_reports.py: 실제 QC 결과 기반 보고서 작성.',
              '- ENVIRONMENT.json, requirements-lock.txt, CODE_SHA256.json: 실제 환경 및 코드 해시.',
              '후속 Phase 1, 주간 특성/라벨, 머신러닝은 수행하지 않고 종료한다.']
    (RUN/'ACADEMIC_RAW_COLLECTION_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    availability='''# 연구 C Phase 0d 시점가용성·단위·이용제약 감사

2026-10-16 확인. 공개 데이터 접근 성공과 역사적 실시간 가용성은 별개다. UNVERIFIED는 자료가 거짓이라는 뜻이 아니라 필요한 시각/빈티지 증거를 확보하지 못했다는 뜻이다.

| 원천 | 원래 주기/단위 | 관측 날짜 | 발표·게시시각 | 수정 및 빈티지 | 판정 |
|---|---|---|---|---|---|
| French 49 industry VW/EW | 일별, 수익률 %의 게시 척도; 수치 무변환 | 미국 포트폴리오 수익률 일자 | 해당 날짜에 다운로드 가능했다고 확인하지 못함; 역사적 파일 게시시각 UNVERIFIED | 라이브러리가 매 갱신 시 전체 역사 재구성. CRSP 수정으로 과거 수익률 변경 가능 | UNVERIFIED historical PIT |
| FF5 + RF / Momentum | 일별, 수익률 % 게시 척도; 무변환 | 일별 팩터 수익률 날짜 | 미국 시장 종료와 학술 파일 공개는 별개. 정확한 과거 게시시각 UNVERIFIED | 현재 CRSP 기반 재계산 이력; 현재 archive != 최초 빈티지 | UNVERIFIED historical PIT |
| SOXX / SMH | 일별 USD OHLC/Adj Close, shares Volume | America/New_York 거래일 | 정규장 종료와 Yahoo 일별 데이터 확정·게시 시각은 별개; 과거 정확한 게시시각 UNVERIFIED | auto_adjust=False. Close에도 과거 분할 영향 가능; Adj Close는 배당/분할 조정 이력이 다운로드 시점에 수정 가능 | UNVERIFIED historical PIT |
| ICSA | 주간 ending Saturday, Number, SA | 청구 대상 주 토요일 | 일반적으로 다음 목요일 08:30 ET; 공식 개별 release로 확인 필요. 관측 토요일 != 발표일 | 전주 수치 추가 보고 수정 및 연간 계절조정 개정; ALFRED 빈티지 접근 확인 | UNVERIFIED complete release calendar |
| CPIAUCSL / CPILFESL | 월간, 1982-84=100, SA | 기준월 첫날 날짜표지 | 실제 발표는 이후 월의 지정일 08:30 ET; 단순 +1월 고정 금지 | 연간 계절조정 재산정으로 과거 5년 수정 가능. ALFRED 후보 확인; CPILFESL vintage 다운로드 페이지 존재 확인 | UNVERIFIED complete historical vintages |
| PAYEMS | 월간, 천 명, SA | 기준월 첫날 표지 | Employment Situation 지정 발표일 08:30 ET | 앞선 두 달 수치 수정 및 연간 벤치마크/계절조정 수정; ALFRED 빈티지 접근 확인 | UNVERIFIED complete release calendar |
| UNRATE | 월간, %, SA | 기준월 첫날 표지 | Employment Situation 지정 발표일 08:30 ET | 계절조정 재산정 및 인구통제 처리의 영향 유의. PAYEMS와 다른 가계조사 통계; ALFRED 접근 확인 | UNVERIFIED complete release calendar |

## 공식 근거와 확인 범위

- [French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html): 월별 자료 갱신 시 전체 이력을 재구성하고 CRSP 개정으로 역사 값이 바뀔 수 있다는 설명. 결측 표지 -99.99/-999. 2025년부터 CRSP FIZ에서 CIZ로 변경된 이력도 명시되어 있다. 월별 CIZ 설명을 일별 산식 변경으로 임의 확대 해석하지 않는다.
- [49 Industry 설명](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_49_ind_port.html): NYSE/AMEX/Nasdaq 주식 SIC 기반 업종분류 및 연간 June 재구성. ETF 지수 수익률이 아니다.
- [FF5 설명](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html): RF는 2024-05까지 Ibbotson, 2024-06부터 ICE BofA 1-month Treasury Bill Index 계열로 원천 전환. 팩터 구성과 전환 이력 유지.
- [Daily Momentum 설명](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html): 매일 구성되는 과거 2~12개월 수익률 포트폴리오 차이. 원본 값을 사용하며 본 작업에서 모멘텀을 새로 계산하지 않는다.
- French 수익률의 % 척도를 그대로 유지했다. 각 CSV 헤더에 모든 단위 설명이 반복되지는 않으므로 원본 preamble 및 공식 설명을 함께 보관한다. 1.00을 0.01로 변환하지 않았다.
- [ICSA 공식 계열](https://fred.stlouisfed.org/series/ICSA), [CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL), [CPILFESL](https://fred.stlouisfed.org/series/CPILFESL), [PAYEMS](https://fred.stlouisfed.org/series/PAYEMS), [UNRATE](https://fred.stlouisfed.org/series/UNRATE): 주기·단위·계절조정·원기관 확인. 계열 페이지를 읽을 수 있다는 사실은 CSV 다운로드 성공을 뜻하지 않는다.
- [DOL 2026-03-19 공식 발표](https://www.dol.gov/sites/dolgov/files/OPA/newsreleases/ui-claims/20260478.pdf): 08:30 ET 공개 및 계절조정 개정 사례. 모든 역사 주간의 발표일이 목요일이라고 확정한 것은 아니다.
- [BLS CPI seasonal adjustment](https://www.bls.gov/cpi/seasonal-adjustment/): 연간 계절조정과 과거 5년 개정.
- [BLS 2026-09월 CPI 발표](https://www.bls.gov/news.release/archives/cpi_10142026.htm): 2026-10-14 08:30 ET; 기준월 9월과 구분한다.
- [BLS 2026-09월 고용 발표](https://www.bls.gov/news.release/archives/empsit_10022026.htm): 2026-10-02 08:30 ET; PAYEMS·UNRATE 기준월과 구분한다. 이 공개 사례를 전체 이력의 실제 발표일 증명으로 사용하지 않는다.
- ALFRED: https://alfred.stlouisfed.org/series?seid=ICSA 및 CPIAUCSL/PAYEMS/UNRATE 계열의 vintage 페이지를 확인했다. CPILFESL series 페이지는 오류였으나 [공식 vintage 다운로드 페이지](https://alfred.stlouisfed.org/series/downloaddata?seid=CPILFESL)에서 과거 빈티지 선택 가능성을 확인했다. 전체 vintage 다운로드, 최초발표값 구축 및 시점정렬은 미실시.
- FRED 화면의 updated timestamp는 FRED 반영시각이며 원기관 최초 발표시각과 동일하다고 간주하지 않는다.

## 조정·단위·해석

French 각 일별 수익률은 게시된 숫자 그대로이며 VW와 EW를 서로 이어붙이지 않았다. 원본 전기간과 2010년 이후 canonical을 구분한다. 전체 업종 중 실제 X 선택은 후속 승인 사항이다.

SOXX·SMH는 source_original에 실제 Yahoo HTTP chart JSON과 yfinance 반환 스냅샷을 각각 구분해 저장했다. 진행 중인 미국 거래일은 제외했다. 배당/분할/자본이득 이벤트는 별도 actions CSV이며 가격 또는 거래량의 추가 변환은 하지 않았다. 원천이 제공하는 Close가 완전한 미조정 틱 이력이라는 보장은 없다. ETF 거래량은 해당 ETF 지분 거래량이며 SOX 지수 구성종목 전체 거래량이 아니다.

ICSA·물가·고용의 현재 수정치를 과거 09:00 ET에 이미 알고 있던 값으로 쓰면 누출 가능성이 있다. 향후 실제 release calendar, 당시 vintage와 공표 직후 제공처 반영 지연을 별도로 설계해야 한다. 이번에는 날짜 매핑, forward-fill, 주간 결합을 하지 않았다.

## 이용조건

French의 공식 공개 ZIP 링크는 인증 없이 다운로드되었지만 공개 접근이 무제한 재배포 라이선스 확인을 뜻하지 않는다. 학술 출처를 표기하고 외부 배포 전에 CRSP/데이터 제공자 이용조건을 추가 확인해야 한다. 포괄적 재배포 허용 여부는 UNVERIFIED다.

Yahoo/yfinance는 다운로드 방식일 뿐 데이터 재배포 권리를 부여하지 않는다. 개인 연구 목적 보관 범위로 취급하고 상업적 이용·외부 재배포는 별도 약관 검토가 필요하다. 허용되지 않은 인증 우회나 프록시는 사용하지 않았다.

[FRED legal notices](https://fred.stlouisfed.org/legal/) 및 각 series notes의 원기관 권리조건이 우선한다. 본 다섯 계열은 DOL/BLS 원천의 미국 정부 통계이며, FRED 웹사이트/서비스 약관과 개별 통계의 권리는 구분한다. ALFRED 전체 이력의 접근 가능성 조사와 이용허가 확정은 별개다.

## 연구 C 공통표본 제약

French 현재 파일은 2026-08-31까지, ETF는 수집 시점 이전의 완료된 미국 일별 관측까지만 존재한다. 월간/주간 macro는 빈티지·발표 지연을 반영해야 하므로 단순 날짜 공통 교집합을 최종 공통표본이라고 할 수 없다. FRED 5종은 날짜 지정 URL 요청이 실패했으나 공식 전체 이력 CSV 링크에서 모두 확보했다. 웹 화면의 최신값을 복사해 RAW로 대체하지 않았다.

모든 후보의 최초 역사적 공개시각과 vintage는 아직 완전히 검증되지 않았다. 자료 수집 완료와 예측 실험 준비 완료를 구별하며 Phase 1을 시작하지 않는다.
'''
    (RUN/'ACADEMIC_RAW_AVAILABILITY_AUDIT.md').write_text(availability,encoding='utf-8')
    # Capture reproducibility hashes after all reports/codes have been written.
    codes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RUN.glob('*.py')}
    (RUN/'CODE_SHA256.json').write_text(json.dumps(codes,indent=2),encoding='utf-8')
    print('Reports saved; successes:',len(successful),'failures:',len(failed))
if __name__=='__main__':main()
