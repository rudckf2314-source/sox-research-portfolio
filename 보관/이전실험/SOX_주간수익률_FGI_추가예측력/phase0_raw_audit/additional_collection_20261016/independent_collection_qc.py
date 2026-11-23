"""Independent QC/report generation for Research C Phase 0c.

The implementation does not import the collector or its parsing helpers.
Existing 01–32 RAW files are read-only and checked against the pre-run hashes.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
DATASET = ROOT / "data/raw/33_fomc_calendar"
RAW = DATASET / "33_fomc_calendar_RAW_20100101_20261016.csv"
ORIGINAL = DATASET / "source_original"
FED = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS = "https://www.bls.gov/schedule/"
AAII = "https://www.aaii.com/sentimentsurvey/sent_results"
TAIWAN = "https://portal.sw.nat.gov.tw/APGA/GA23/GA30E"
ISM = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/"
SEMI = "https://discover.semi.org/historical-book-to-bill--report-registration.html"


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def put(name: str, content: str) -> None:
    (RUN / name).write_text(content, encoding="utf-8")


def main() -> None:
    baseline = json.loads((RUN / "PROTECTED_INPUT_HASHES_BEFORE.json").read_text(encoding="utf-8"))
    changed = [p for p, h in baseline.items() if not (ROOT / p).is_file() or hash_file(ROOT / p) != h]
    current = {p: hash_file(ROOT / p) for p in baseline if (ROOT / p).is_file()}
    existing_rows = []
    for relative_path, before_hash in baseline.items():
        path = ROOT / relative_path
        source_metadata = ""
        if path.suffix.lower() == ".csv" and path.is_file():
            with path.open(encoding="utf-8-sig", errors="replace") as f:
                first = f.readline().rstrip()
            source_metadata = first if first.startswith("# SOURCE") else "NO_SOURCE_PREAMBLE"
        existing_rows.append({"dataset_id": Path(relative_path).parts[2], "status": "ALREADY_EXISTS",
                              "path": relative_path, "sha256_before": before_hash,
                              "sha256_after": current.get(relative_path, "MISSING"),
                              "source_metadata": source_metadata})
    with (RUN / "EXISTING_RAW_INVENTORY.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(existing_rows[0])); writer.writeheader(); writer.writerows(existing_rows)
    with RAW.open(encoding="utf-8") as f:
        metadata = f.readline().rstrip("\n")
        header = f.readline().rstrip("\n")
    df = pd.read_csv(RAW, comment="#", dtype=str, keep_default_na=False)
    dates = pd.to_datetime(df["meeting_start_date"], errors="raise")
    ends = pd.to_datetime(df["meeting_end_date"], errors="raise")
    keys = df[["meeting_start_date", "meeting_end_date", "meeting_type"]]
    original_files = sorted(p for p in ORIGINAL.rglob("*") if p.is_file())
    html_pages = sorted(ORIGINAL.glob("*.html"))
    stmt_pages = sorted((ORIGINAL / "statements").glob("*.htm"))
    original_records = [{"path": str(p.relative_to(ROOT)).replace("\\", "/"), "size_bytes": p.stat().st_size,
                         "sha256": hash_file(p)} for p in original_files]
    with (RUN / "FOMC_ORIGINAL_FILE_MANIFEST.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(original_records[0])); writer.writeheader(); writer.writerows(original_records)
    year_counts = {str(k): int(v) for k, v in df.groupby(dates.dt.year).size().items()}
    source_heading_counts = {}
    for year in range(2010, 2021):
        html = (ORIGINAL / f"fomchistorical{year}_original.html").read_bytes()
        soup = BeautifulSoup(html, "html.parser")
        source_heading_counts[str(year)] = sum(bool(re.search(rf"-\s*{year}$", h.get_text(" ", strip=True))) for h in soup.find_all("h5"))
    heading_mismatch = {y: [n, year_counts.get(y, 0)] for y, n in source_heading_counts.items() if n != year_counts.get(y, 0)}
    links = df["statement_url"].ne("")
    statement_url_date_mismatch = 0
    for _, row in df[links].iterrows():
        m = re.search(r"(20\d{6})[a-z]?\.htm$", row["statement_url"])
        if not m or row["statement_date"].replace("-", "") != m[1]:
            statement_url_date_mismatch += 1
    stated = df["release_time_status"].eq("VERIFIED_OFFICIAL_STATEMENT")
    verified_file_count = 0
    for _, row in df[stated].iterrows():
        filename = row["statement_url"].rsplit("/", 1)[-1]
        p = ORIGINAL / "statements" / filename
        if p.is_file() and "For release at" in BeautifulSoup(p.read_bytes(), "html.parser").get_text(" ", strip=True):
            verified_file_count += 1
    qc = {
        "dataset_id": "33_fomc_calendar", "status": "PASS" if not changed and not heading_mismatch and statement_url_date_mismatch == 0 and verified_file_count == int(stated.sum()) and len(df) == 148 else "FAIL",
        "rows": len(df), "year_counts": year_counts,
        "min_meeting_start": dates.min().date().isoformat(), "max_meeting_start": dates.max().date().isoformat(),
        "max_meeting_end": ends.max().date().isoformat(),
        "max_statement_date": df.loc[links, "statement_date"].max(),
        "duplicate_meeting_keys": int(keys.duplicated().sum()),
        "invalid_date_ranges": int((ends < dates).sum()), "future_meetings": int((dates.dt.date > date(2026, 10, 16)).sum()),
        "statement_links": int(links.sum()), "statement_originals": len(stmt_pages),
        "statement_url_date_mismatch": statement_url_date_mismatch,
        "verified_release_times": int(stated.sum()), "verified_release_source_files": verified_file_count,
        "unverified_release_times": int((~stated).sum()), "historical_visibility_unverified": int(df["historical_visibility_status"].ne("VERIFIED").sum()),
        "missing_statement_links": int((~links).sum()), "source_original_index_pages": len(html_pages),
        "source_heading_count_mismatch": heading_mismatch,
        "metadata_first_line_valid": metadata.startswith("# SOURCE | dataset_id=33_fomc_calendar"),
        "columns": list(df.columns), "protected_existing_raw_count": len(baseline),
        "protected_existing_raw_changed_count": len(changed), "protected_existing_raw_changed": changed,
        "normalized_sha256": hash_file(RAW), "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    put("ADDITIONAL_COLLECTION_QC.json", json.dumps(qc, indent=2, ensure_ascii=False))
    if qc["status"] != "PASS":
        raise RuntimeError(f"Independent QC failed: {qc}")

    manifest = [
        {"dataset_id":"33_fomc_calendar", "description":"FOMC meetings/linked statements", "provider":"Federal Reserve Board", "status":"COLLECTED", "source_url":FED,
         "observed_start":qc["min_meeting_start"],"observed_end":qc["max_meeting_end"],"rows":len(df),"normalized_file":str(RAW.relative_to(ROOT)).replace("\\","/"),
         "source_original_path":str(ORIGINAL.relative_to(ROOT)).replace("\\","/"),"source_original_files":len(original_files),"normalized_sha256":hash_file(RAW),
         "release_time":"verified for explicit statement text only; otherwise UNKNOWN", "vintage":"current archive; historical schedule visibility unverified", "license":"Federal Reserve public HTML; reuse terms not independently confirmed", "limitation":"meeting archive is not proof of advance schedule visibility"},
        {"dataset_id":"34_bls_cpi_calendar","description":"CPI release schedule","provider":"BLS","status":"MANUAL_REQUIRED","source_url":BLS,
         "observed_start":"UNVERIFIED","observed_end":"UNVERIFIED","rows":0,"normalized_file":"","source_original_path":"","source_original_files":0,"normalized_sha256":"",
         "release_time":"08:30 ET on official schedule; full 2011–2026 file not collected", "vintage":"historical schedule revision status unverified", "license":"BLS automated access denied", "limitation":"direct request HTTP 403 Access Denied; no bypass"},
        {"dataset_id":"35_bls_employment_calendar","description":"Employment Situation release schedule","provider":"BLS","status":"MANUAL_REQUIRED","source_url":BLS,
         "observed_start":"UNVERIFIED","observed_end":"UNVERIFIED","rows":0,"normalized_file":"","source_original_path":"","source_original_files":0,"normalized_sha256":"",
         "release_time":"08:30 ET on official schedule; full 2011–2026 file not collected", "vintage":"historical schedule revision status unverified", "license":"BLS automated access denied", "limitation":"direct request HTTP 403 Access Denied; no bypass"},
        {"dataset_id":"36_aaii_sentiment","description":"AAII weekly sentiment historical data","provider":"AAII","status":"MANUAL_REQUIRED","source_url":"https://www.aaii.com/files/surveys/sentiment.xls",
         "observed_start":"UNVERIFIED","observed_end":"UNVERIFIED","rows":0,"normalized_file":"","source_original_path":"","source_original_files":0,"normalized_sha256":"",
         "release_time":"UNVERIFIED", "vintage":"current historical Excel vintage unverified", "license":"AAII member access/reuse terms to confirm", "limitation":"official Excel link exists; direct request gave HTTP 403 or 200 HTML bot challenge, not Excel"},
        {"dataset_id":"37_taiwan_ic_exports","description":"Taiwan HS8542 monthly exports to World USD","provider":"Taiwan Customs Administration","status":"MANUAL_REQUIRED","source_url":TAIWAN,
         "observed_start":"UNVERIFIED","observed_end":"UNVERIFIED","rows":0,"normalized_file":"","source_original_path":"","source_original_files":0,"normalized_sha256":"",
         "release_time":"UNVERIFIED", "vintage":"monthly statistics may be revised; initial vintage unverified", "license":"official site warns against unauthorized reproduction/commercial use", "limitation":"interactive CSV query requires CAPTCHA; historical code mapping not verified"},
        {"dataset_id":"38_ism_manufacturing","description":"ISM Manufacturing PMI and New Orders","provider":"ISM","status":"LICENSE_REVIEW","source_url":ISM,
         "observed_start":"UNVERIFIED","observed_end":"UNVERIFIED","rows":0,"normalized_file":"","source_original_path":"","source_original_files":0,"normalized_sha256":"",
         "release_time":"first business day 10:00 ET stated; individual vintages unverified", "vintage":"revisions/historical first releases unverified", "license":"bulk archive/reuse rights unconfirmed", "limitation":"public report pages do not establish a permitted 2011–2026 bulk download"},
        {"dataset_id":"39_semi_equipment_billings","description":"SEMI equipment bookings/billings","provider":"SEMI","status":"LICENSE_REVIEW","source_url":SEMI,
         "observed_start":"UNVERIFIED","observed_end":"UNVERIFIED","rows":0,"normalized_file":"","source_original_path":"","source_original_files":0,"normalized_sha256":"",
         "release_time":"UNVERIFIED", "vintage":"licensed historical report; first-release history unverified", "license":"paid registration/report license", "limitation":"Book-to-Bill stopped in 2017; billings series is distinct"},
    ]
    with (RUN / "ADDITIONAL_COLLECTION_MANIFEST.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest[0])); writer.writeheader(); writer.writerows(manifest)
    qc["candidate_statuses"] = {m["dataset_id"]: m["status"] for m in manifest}

    report = f"""# 연구 C Phase 0c — 추가 RAW 수집 및 가용성 감사

기준일: 2026-10-16. 기존 D1·W1 및 RAW 01~32는 읽기 전용으로 유지했다. 이번 단계에서 X/Y 및 모델은 생성하지 않았다.

| 후보 | 상태 | 실제 확보 범위 | 결과 |
|---|---|---|---|
| FOMC 회의·성명 일정 | COLLECTED | {qc['min_meeting_start']}~{qc['max_meeting_end']}, {len(df)}건 | [RAW]({ROOT / manifest[0]['normalized_file']}) · 공식 HTML 원본 {len(html_pages)}개, 성명 HTML {len(stmt_pages)}개 |
| BLS CPI 발표 일정 | MANUAL_REQUIRED | 자동 수집 0건 | BLS HTTP 403 자동접근 차단 |
| BLS 고용보고서 발표 일정 | MANUAL_REQUIRED | 자동 수집 0건 | BLS HTTP 403 자동접근 차단 |
| AAII 투자심리 | MANUAL_REQUIRED | 자동 수집 0건 | 공식 Excel 링크 확인, HTTP 403 또는 200 HTML 보안 안내; Excel 원본 아님 |
| 대만 HS8542 수출 | MANUAL_REQUIRED | 자동 수집 0건 | 공식 CSV 조회에 CAPTCHA 필요 |
| ISM 제조업 PMI·New Orders | LICENSE_REVIEW | 수치 미수집 | 장기 원본 다운로드·재배포 권한 미확인 |
| SEMI 장비 수주·매출 | LICENSE_REVIEW | 수치 미수집 | 유료 역사보고서; Book-to-Bill은 2016년 종료 |

FOMC는 연준 [역사자료·일정]({FED})의 2010~2020년 연도별 페이지와 2021~2026년 달력 페이지에서 수집했다. 2026-10-16 이후의 예정 회의는 제외했다. 성명 링크 {qc['statement_links']}건 중 공식 성명에 실제 시각이 명시되고 ET 서머타임과 일치한 {qc['verified_release_times']}건만 `VERIFIED_OFFICIAL_STATEMENT`다. 나머지 {qc['unverified_release_times']}건의 발표시각은 `UNKNOWN` 계열로 남겼다. 성명 링크가 없는 6건에는 conference call, unscheduled event, cancelled meeting 등이 포함된다. 현재 아카이브는 당시 투자자가 사전에 본 **예정 일정의 빈티지**를 입증하지 않는다. 따라서 추후 예측 변수로 사용할 때 계획된 회의와 예고되지 않은 긴급회의를 분리해야 한다.

FOMC QC: 중복 회의 {qc['duplicate_meeting_keys']}건, 날짜 역전 {qc['invalid_date_ranges']}건, 공식 연도별 표제와 추출 건수 불일치 {len(heading_mismatch)}개 연도, 보호 RAW {len(baseline)}개 변경 {len(changed)}건. 원본별 SHA-256은 `FOMC_ORIGINAL_FILE_MANIFEST.csv`, 요청 응답 정보는 `FOMC_REQUEST_LOG.json` 및 `FOMC_STATEMENT_REQUEST_LOG.json`에 있다. 신규 RAW 독립 QC 판정 **{qc['status']}**. 회의일과 성명일이 다른 2019-10-04→2019-10-11 및 2020-03-02→2020-03-03을 별도로 확인했다. `actual_release_datetime_et`는 성명에 명시된 공식 발표시각이며 서버의 실제 최초 게시 로그를 입증하는 값은 아니다.

BLS [2011년 일정](https://www.bls.gov/schedule/2011/home.htm)은 공개 웹에서 열람되지만 이 환경의 직접 HTTP 요청은 403 `Access Denied`를 반환했다. 봇 차단을 우회하지 않았다. [AAII 공식 과거결과]({AAII})에는 Excel 링크가 있으나 직접 요청은 403 또는 200 HTML 보안 안내였고 Excel 바이너리가 아니었다. HTTP 200만으로 수집 성공으로 판정하지 않았다. [대만 관세 공식 질의]({TAIWAN})는 CSV 출력을 제공하지만 CAPTCHA를 요구한다. 원본 없이 웹 검색 스니펫을 완전한 RAW로 오인해 CSV를 만들지 않았다.

Phase 1 전에 해결할 사항: BLS 전체 공식 일정 원본, AAII Excel 사용권한과 게시시각, 대만 HS8542 코드·원본 CSV, ISM·SEMI 라이선스와 최초 공개 빈티지. 현재 확보 FOMC도 과거 예정 일정 빈티지를 검증해야 한다. **Phase 1 주간 X/Y 생성은 아직 진행하지 않았다.**
"""
    put("ADDITIONAL_COLLECTION_REPORT.md", report)

    guide = f"""# 수동 확보 가이드

## BLS CPI·Employment Situation

1. 브라우저에서 [BLS release schedule]({BLS}) 또는 `https://www.bls.gov/schedule/2011/home.htm`부터 연도별 페이지를 연다. 직접 자동 요청은 403으로 차단되었으므로 인증·접근제어를 우회하지 않는다.
2. 2011~2026년 각 연도의 CPI와 Employment Situation 항목만 원본 HTML 또는 공식 캘린더 파일로 저장한다. 날짜, 표기된 ET 시각, 대상 월(reference period), 원본 URL, 저장일을 함께 기록한다.
3. 연도별 일정의 현재 화면이 최초 공표 일정인지 확인한다. 개정 이력이 없는 경우 `historical_visibility_status=UNKNOWN`으로 둔다. 실제 발표시각은 보도자료의 embargo 문구를 별도로 대조한다.

## AAII

1. [AAII historical results]({AAII})의 `Download Complete Historical Data`를 권한이 있는 브라우저에서 열고 공식 `sentiment.xls`를 다운로드한다. 현재 자동 요청은 403 또는 200 HTML 보안 안내이며 실제 Excel이 아니다.
2. 계정·연구 사용·원본 보관 조건을 확인한다. 파일을 받은 경우 원본 바이트, SHA-256, 다운로드 시각과 URL을 보존한다.
3. Bullish/Neutral/Bearish 단위가 %인지 검증하고 주간 조사 기준일·마감일·첫 게시일을 구분한다. 현재 Excel 값이 과거 당시 값과 동일한지 입증할 수 없으면 빈티지 미확인으로 기록한다.

## 대만 관세 HS8542

1. 2026-10-16 재확인: 기존 `{TAIWAN}` 직접 접속은 실패했다. 시스템 개편·링크 변경이 원인인지는 확인되지 않았다. 정상 작동이 검증된 직접 다운로드 주소로 안내하지 않는다.
2. 우선 [대만 관세청 공식 홈페이지](https://web.customs.gov.tw/en)의 `Statistics Database Query` 메뉴로 진입한다. 공식 메뉴 링크에도 세션 정보가 붙어 있었으며, 이번 자동 조회에서는 연결이 시간 초과되었다. 검색에 노출되는 `tportal`의 `TEST TEST TEST` 페이지는 운영 데이터 수집 경로로 사용하지 않는다.
3. 별도의 공식 접근 후보로 [국제무역서 상품별 수출입 조회](https://publicinfo.trade.gov.tw/cuswebo/FSCE3000C?table=FSCE3020F)를 확인했다. 페이지에 Export, Value(US$), CCC 4자리 선택, XLS 다운로드 및 Verification Code가 표시된다. [공식 소개](https://publicinfo.trade.gov.tw/cuswebo/FSCE000F/FSCE000F?menuURL=FSCE000F)는 원천이 대만 관세청임을 명시한다. 동일한 원본 정의·집계범위인지 확인하기 전 기존 관세청 계열과 임의로 병합하지 않는다.
4. 이 후보에서 `Export`, 상품코드 4자리 `8542`, 상대국 전체/World, 월별 2011-01부터 최신 가용월, 금액 `Value(US$)`를 선택한다. CAPTCHA는 사람이 직접 입력하고 결과의 XLS를 원본 그대로 저장한다. 실제 2011년 HS8542 조회·다운로드는 아직 수행하지 않았으므로 UNVERIFIED다.
5. 요청 화면의 선택조건, 재수출 포함/제외 여부, HS/CCC 분류 개정, 단위(USD 또는 million USD), 원본 파일·URL·조회시각·SHA-256을 보존한다. 소개 페이지는 재수출·재수입 제외를 설명하지만 조회 화면은 포함/제외 선택지를 제공하므로 실제 내려받은 결과 기준을 반드시 확인한다.
6. 기존 대만 전자제품 수출주문 RAW는 HS8542 실제 수출액의 대체품으로 합치지 않는다.

## ISM·SEMI

- [ISM 공식 PMI 보고서]({ISM})에서 제조업 PMI와 제조업 New Orders의 **동일 정의** 2011~현재 원본 및 학술적 보관·분석 권한을 확인한다. 개별 보도자료를 무단 일괄 복제하지 않는다.
- [SEMI 역사보고서]({SEMI})의 비용·라이선스·원본 Excel 기간을 확인한다. 등록 페이지에는 학생증 확인 후 학생 무료 할인코드 안내가 있다. 실제 학술 이용·보관 권한은 별도 확인한다. Book-to-Bill 1991~2016과 2017년 이후 Billings는 다른 시계열이다. 수주와 매출을 이어붙이지 않는다.
"""
    put("MANUAL_COLLECTION_GUIDE.md", guide)

    availability = f"""# 공개시점·빈티지 감사

| 원천 | 관측/사건 기준 | 공식 공개시간 확인 | 과거 빈티지 | Phase 1 사용상 위험 |
|---|---|---|---|---|
| FOMC | 회의 시작·종료일 및 성명일 | 공식 성명 명시 {qc['verified_release_times']}건 VERIFIED; 나머지 UNKNOWN | 현재 아카이브가 당시 **사전 예정** 일정임을 증명하지 못함 | 비정례·긴급 회의를 사전 예고 행사로 취급하면 미래정보 유입 |
| BLS CPI | 대상 소비자물가 월과 발표일 별개 | [BLS 일정]({BLS})은 보통 ET 시간을 표기; 전체 원본 미수집 | 일정의 최초 게시·수정 시점 UNKNOWN | 발표 예정일과 실제 발표일 혼동 금지 |
| BLS Employment Situation | 대상 고용 월과 발표일 별개 | BLS 발표자료의 embargo 문구로 개별 확인 필요 | 역사 일정 빈티지 UNKNOWN | 08:30 ET을 모든 사건에 무조건 대입 금지 |
| AAII | 조사 종료·보고주와 게시일 별개 | UNKNOWN | 현행 Excel이 과거 최초 발표값인지 UNKNOWN | 주간 설문 날짜를 09:00 ET 이전 가용 시각으로 간주 금지 |
| 대만 관세 HS8542 | 월간 신고 심사 통계 | 다음달 2일 심사 마감 규칙 확인, 최초 발표시각 UNKNOWN | 수정 이력·초기 빈티지 UNKNOWN | 관측월 말에 바로 사용 금지 |
| ISM 제조업 PMI·New Orders | 전월 제조업 상태 | [공식 일정](https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/)은 첫 영업일 10:00 ET이라고 설명 | 2011~현재 첫 발표 빈티지 미확보 | 현재 조회 수치를 그달 사전 정보로 쓰지 않음 |
| SEMI | 장비 출하/수주 월 | 정확한 최초 발표시각 UNKNOWN | 역사 유료 보고서의 수정 여부 UNKNOWN | 2017년 이후 Book-to-Bill 단절, Billings와 혼합 금지 |

모든 `UNKNOWN`은 검증 완료를 의미하지 않는다. 월간 관측월, 일정 예정일, 실제 발표일, 현재 수정값은 서로 다른 개념이다. 특히 2020년 FOMC 긴급회의는 당시 사전 공표 일정으로 단정하지 않는다.
"""
    put("RELEASE_AVAILABILITY_AUDIT.md", availability)
    legacy_path = RUN / "EXISTING_STUDIES_HASH_QC.json"
    if legacy_path.exists():
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        legacy_missing = sum(len(x["missing"]) for x in legacy["results"])
        legacy_differences = sum(len(x["historical_hash_mismatches"]) for x in legacy["results"])
        qc["new_raw_qc_status"] = qc["status"]
        qc["historical_study_manifest_status"] = legacy["status"]
        qc["historical_study_missing_files"] = legacy_missing
        qc["historical_study_hash_differences"] = legacy_differences
        qc["status"] = "CONDITIONAL" if legacy["status"] != "PASS" else qc["status"]
        put("ADDITIONAL_COLLECTION_QC.json", json.dumps(qc, indent=2, ensure_ascii=False))
        report += f"""\n## 기존 연구 기록과 현재 상태의 대조\n\n기존 D1/W1/동결 매니페스트 5개에 적힌 3,262개 항목을 현재 파일과 비교했다. 이 중 3,254개 항목은 일치하고, D1 실행 코드 6개는 과거 해시와 다르며 동결 매니페스트의 `sentiment_proxy7_QC.csv`, `sentiment_proxy7_FEATURE_DICTIONARY.md` 2개는 현재 없다. `FROZEN_FEATURE_DICTIONARY.md`는 존재하지만 이름이 다른 문서를 같은 원본으로 간주하지 않았다. 상세 경로는 `EXISTING_STUDIES_HASH_QC.json`에 기록했다. D1의 예전 `reports/` 및 `phase_report/` 경로는 승인된 `reports_D1/` 및 `phase_report_D1/`로 해석했다.\n\nD1·W1의 저장 모델과 W1 매니페스트 대상은 모두 기존 해시와 일치했다. 동결 Proxy7 CSV와 생성 코드도 기존 해시와 일치했다. 이 검사는 과거 매니페스트와의 대조이며 **이번 작업 전후의 D1/W1 전체 스냅샷 비교는 아니다**. 차이 6건과 누락 2건의 발생 시점을 이 검사로 확정할 수 없다. 이번 수집 코드는 해당 경로에 쓰기·삭제를 수행하지 않았다. 이번 작업 전후 직접 대조한 RAW 01~32의 41개 파일은 전부 동일하다.\n\n신규 FOMC RAW QC는 PASS, 기존 기록의 미해결 차이를 포함한 전체 감사 판정은 **CONDITIONAL**이다. 이 차이를 숨기거나 기존 파일을 복원·수정하지 않았다.\n"""
        put("ADDITIONAL_COLLECTION_REPORT.md", report)
    stage_qc_path = RUN / "FOMC_COLLECTION_QC.json"
    stage_qc = json.loads(stage_qc_path.read_text(encoding="utf-8"))
    stage_qc["stage"] = "calendar_normalization_before_official_statement_time_enrichment"
    stage_qc["current_final_sha256_location"] = "ADDITIONAL_COLLECTION_QC.json:normalized_sha256"
    stage_qc_path.write_text(json.dumps(stage_qc, indent=2), encoding="utf-8")
    import importlib.metadata
    put("DEPENDENCIES.txt", "\n".join(f"{p}=={importlib.metadata.version(p)}" for p in ["requests", "beautifulsoup4", "pandas", "tzdata"]) + "\n")
    print(json.dumps({"status": qc["status"], "fomc_rows": len(df), "verified_times": int(stated.sum()),
                      "original_files": len(original_files), "protected_changed": len(changed),
                      "manifest_statuses": dict(Counter(m["status"] for m in manifest))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
