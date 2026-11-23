"""Convert eight user-provided official trade workbooks to monthly RAW CSV.

No source changes, filling, unit scaling, feature calculation or model use.
Full annual-summary/header content remains in the original XLSX files.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
RAW = ROOT / "data/raw"
INPUT = ROOT / "방금수집"
DEST = RAW / "37_taiwan_ic_exports"
COLS = ["Date", "Total_Trade_USD", "Total_Trade_Growth_Rate_Pct", "Exports_USD", "Exports_Growth_Rate_Pct",
        "Imports_USD", "Imports_Growth_Rate_Pct", "Trade_Balance_USD", "Trade_Balance_Growth_Rate_Pct"]
AMOUNTS = [1, 3, 5, 7]
URL = "https://publicinfo.trade.gov.tw/cuswebo/FSCE3000C?table=FSCE3020F"


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def decimal(value):
    if pd.isna(value) or str(value).strip() in {"", "---", "--"}:
        return None
    return Decimal(str(value).replace(",", "").strip())


def parse(p):
    book = pd.ExcelFile(p)
    assert book.sheet_names == ["VALUE OF EXPORTS & IMPORTS"], p.name
    table = pd.read_excel(book, sheet_name=0, header=None)
    assert table.shape[1] == 9, p.name
    assert str(table.iloc[1, 0]).strip() == "REPORT_ID : FSC3030R"
    assert str(table.iloc[3, 0]).strip() == "CCC_CODE: 8542-Electronic integrated circuits"
    assert str(table.iloc[3, 5]).strip() == "UNIT:US($)"
    assert "re-imports & re-exports included" in str(table.iloc[5, 0])
    assert str(table.iloc[2, 0]).strip() == "COUNTRY(REGION): Global-Continental"
    assert "special trade system" in str(table.iloc[0, 0]).lower()
    assert "general trade system" in str(table.iloc[0, 0]).lower()
    assert [str(table.iloc[6, k]).strip() for k in [0, 1, 3, 5, 7]] == ["YEAR/MONTH", "TOTAL TRADE", "EXPORT", "IMPORT", "SURPLUS/DEFICIT"]
    rows, origins, annual = [], [], []
    for i, r in table.iterrows():
        label = str(r.iloc[0]).strip()
        if re.fullmatch(r"20\d{4}", label):
            dt = datetime.strptime(label, "%Y%m")
            values = [decimal(v) for v in r.iloc[1:9]]
            for column in AMOUNTS:
                v = values[column - 1]
                assert v is None or v == v.to_integral_value(), (p.name, label, column)
            rows.append([dt.strftime("%Y-%m-01"), *values])
            origins.append({"Date": dt.strftime("%Y-%m-01"), "source_file": p.name,
                            "source_sheet": book.sheet_names[0], "excel_row": int(i) + 1})
        elif re.fullmatch(r"20\d{2}(?:\(01~\d{2}\))?", label):
            annual.append({"year": int(label[:4]), "label": label,
                           "values": {COLS[k]: decimal(r.iloc[k]) for k in AMOUNTS}})
    assert rows, p.name
    metadata = {"source_file": p.name, "sha256": sha(p), "rows": len(rows),
                "min_date": rows[0][0], "max_date": rows[-1][0],
                "country_label": str(table.iloc[2, 0]), "product_label": str(table.iloc[3, 0]),
                "unit_label": str(table.iloc[3, 5]), "time_period_label": str(table.iloc[5, 0]),
                "print_time_as_written": str(table.iloc[2, 5]),
                "print_time_timezone": "UNVERIFIED", "methodology_note": str(table.iloc[0, 0])}
    return rows, origins, annual, metadata


def save_csv(path, rows, sources, imported_at):
    metadata = ("# SOURCE | dataset_id=37_taiwan_ic_exports | provider=International Trade Administration, MOEA, Taiwan"
                " | administrator=Customs Administration, Ministry of Finance, R.O.C."
                f" | source_url={URL} | series_or_symbol=CCC 8542 Electronic integrated circuits"
                " | country_label=Global-Continental | coverage=re-imports and re-exports included"
                " | unit=USD; growth rates in percent as supplied"
                f" | source_files={';'.join(sources)} | start_date={rows[0][0][:7]} | end_date={rows[-1][0][:7]}"
                f" | retrieved_at_utc=UNKNOWN | imported_at_utc={imported_at}"
                " | date_semantics=observation-month label on first day; not release date"
                " | transformation=monthly rows only; comma grouping removed; sorted; no rescaling or filling"
                " | methodology_break=2016-01 special trade system to general trade system\n")
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write(metadata)
        writer = csv.writer(f)
        writer.writerow(COLS)
        writer.writerows(rows)


def main():
    if DEST.exists():
        raise FileExistsError(f"Refusing to overwrite {DEST}")
    files = sorted(INPUT.glob("FSC3030R*.xlsx"))
    assert len(files) == 8, f"Expected 8 source files; found {len(files)}"
    before = {str(p.relative_to(ROOT)): sha(p) for p in RAW.rglob("*") if p.is_file()}
    all_rows, lineage, source_records, parts = [], [], [], []
    for p in files:
        rows, origins, annual, metadata = parse(p)
        all_rows += rows
        lineage += origins
        source_records.append(metadata)
        parts.append((p, rows, annual))
    all_rows.sort(key=lambda r: r[0])
    dates = [r[0] for r in all_rows]
    assert len(dates) == len(set(dates)), "Duplicate months; no merge saved"
    expected = pd.date_range(dates[0], dates[-1], freq="MS").strftime("%Y-%m-%d").tolist()
    missing_months = sorted(set(expected) - set(dates))
    assert not missing_months, f"Missing months; no merge saved: {missing_months}"
    assert dates[0] == "2011-01-01" and dates[-1] == "2026-09-01" and len(dates) == 189
    missing_values = sum(v is None for row in all_rows for v in row[1:])
    assert missing_values == 0, f"Source numeric missing values: {missing_values}"
    monthly_identity_failures = [row[0] for row in all_rows if row[1] != row[3] + row[5] or row[7] != row[3] - row[5]]
    assert not monthly_identity_failures, monthly_identity_failures
    annual_audit = []
    for p, rows, annual in parts:
        for total in annual:
            subset = [r for r in rows if int(r[0][:4]) == total["year"]]
            for k in AMOUNTS:
                observed = sum(r[k] for r in subset)
                difference = observed - total["values"][COLS[k]]
                annual_audit.append({"source_file": p.name, "year": total["year"], "annual_label": total["label"],
                                     "column": COLS[k], "months": len(subset), "source_annual_amount": str(total["values"][COLS[k]]),
                                     "sum_of_months": str(observed), "difference": str(difference)})
    mismatched_annual = [r for r in annual_audit if Decimal(r["difference"]) != 0]
    assert not mismatched_annual, f"Monthly/annual sums disagree: {mismatched_annual}"
    assert not any(row[k] < 0 for row in all_rows for k in [1, 3, 5])
    imported_at = datetime.now(timezone.utc).isoformat()
    (DEST / "source_original").mkdir(parents=True)
    (DEST / "converted_parts").mkdir()
    for p, rows, _ in parts:
        copied = DEST / "source_original" / p.name
        shutil.copy2(p, copied)
        assert sha(p) == sha(copied)
        save_csv(DEST / "converted_parts" / f"{p.stem}_MONTHLY.csv", rows, [p.name], imported_at)
    output = DEST / "37_taiwan_ic_exports_RAW_201101_202609.csv"
    save_csv(output, all_rows, [p.name for p in files], imported_at)
    with output.open(encoding="utf-8", newline="") as f:
        assert f.readline().startswith("# SOURCE")
        stored = list(csv.reader(f))
    assert stored[0] == COLS and len(stored) - 1 == len(all_rows)
    for row, original in zip(stored[1:], all_rows):
        assert row[0] == original[0]
        assert all(Decimal(value) == expected for value, expected in zip(row[1:], original[1:]))
    changed = [p for p, h in before.items() if not (ROOT / p).is_file() or sha(ROOT / p) != h]
    assert not changed, changed
    assert all(sha(p) == record["sha256"] for p, record in zip(files, source_records))
    source_metadata = {"dataset_id": "37_taiwan_ic_exports", "source_url": URL,
                       "source_files": source_records, "imported_at_utc": imported_at,
                       "observation_period": "2011-01 to 2026-09", "release_timestamp_status": "UNVERIFIED",
                       "historical_vintage_status": "current user-downloaded historical table; initial vintages unverified",
                       "source_definition_break": "special trade system until 2015; general trade system from January 2016",
                       "source_values_changed": False, "monthly_rows_only": True,
                       "future_months_not_generated": ["2026-10", "2026-11", "2026-12"]}
    (DEST / "SOURCE_METADATA.json").write_text(json.dumps(source_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, rows in [("SOURCE_ROW_LINEAGE.csv", sorted(lineage, key=lambda r: r["Date"])), ("ANNUAL_TOTAL_RECONCILIATION.csv", annual_audit)]:
        with (RUN / name).open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    qc = {"status": "PASS_WITH_DOCUMENTED_METHODOLOGY_BREAK", "source_file_count": len(files),
          "converted_part_count": len(parts), "rows": len(all_rows), "min_month": dates[0][:7], "max_month": dates[-1][:7],
          "duplicate_months": len(dates) - len(set(dates)), "missing_months_within_source_range": missing_months,
          "missing_cells": missing_values, "monthly_amount_identity_failures": monthly_identity_failures,
          "annual_total_comparisons": len(annual_audit), "annual_total_mismatches": mismatched_annual,
          "csv_source_decimal_values_identical": True, "original_copy_hashes_match": True,
          "original_input_hashes_unchanged": True, "protected_existing_raw_files": len(before), "protected_changed": changed,
          "methodology_break": "2016-01", "release_times": "UNVERIFIED", "output_file": str(output.relative_to(ROOT)),
          "output_sha256": sha(output), "source_file_metadata": source_records}
    (RUN / "TAIWAN_IC_IMPORT_QC.json").write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    (RUN / "PROTECTED_RAW_HASHES.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    report = f"""# 대만 관세 HS/CCC 8542 월별 RAW 병합

- 원본: 사용자 제공 FSC3030R XLSX 8개. 국가 표기는 원본 그대로 Global-Continental, 품목은 8542 Electronic integrated circuits이다.
- 기간: 2011-01~2026-09, 189개월. 2026년 10~12월은 원본에 없어 만들지 않았다.
- 금액: USD 그대로. 원본의 TOTAL TRADE, EXPORT, IMPORT, SURPLUS/DEFICIT 금액과 각각의 GROWTH RATE(%)를 모두 보존했다. 성장률은 원본 수치이며 새로 계산하지 않았다.
- Date는 해당 관측월의 첫날 표지이며 발표일·게시시각이 아니다. 원본 PRINT TIME은 파일 생성 표기일 뿐 최초 공표시각으로 간주하지 않았다.
- 재수입·재수출 포함. 2015년까지 특별무역체계, 2016-01부터 일반무역체계라는 원본 주석을 보존했다. 같은 보고서 계열의 시간순 병합이며 이 통계기준 변경을 보정하거나 숨기지 않았다.
- 월별 행만 병합했다. 연간 합계 행을 월 자료로 포함하지 않았으며 원본 XLSX에 그대로 보존했다.
- 중복 월 0, 범위 내 누락 월 0, 결측 셀 0. 월별 수출+수입=총교역 및 수출-수입=무역수지를 전부 확인했다. 연간/연중 누계와 월별 합계 64개 비교가 모두 일치했다.
- 원본의 숫자와 저장 CSV를 Decimal로 재대조하여 값 일치를 확인했다. 쉼표 구분만 제거했고 단위 재조정·보간은 하지 않았다.
- 기존 RAW {len(before)}개 파일의 해시 변경 0건. 원본 XLSX 8개도 변경 없이 유지했다.

최종 RAW: `{output.relative_to(ROOT)}`

`source_original/`: XLSX 원본 8개 및 해시 검증. `converted_parts/`: 원본별 월별 CSV 8개. 상세 출처와 인쇄시각은 `SOURCE_METADATA.json`, 월별 원본 파일·행 추적은 `SOURCE_ROW_LINEAGE.csv`에 기록했다.

QC: PASS_WITH_DOCUMENTED_METHODOLOGY_BREAK. 역사적 최초 발표시각·빈티지·2016년 기준 변경은 이후 연구 설계에서 검토해야 한다. X/Y 생성이나 연구 D1·W1·C 모델 계산은 수행하지 않았다.
"""
    (RUN / "TAIWAN_IC_IMPORT_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({k: v for k, v in qc.items() if k != "source_file_metadata"}, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
