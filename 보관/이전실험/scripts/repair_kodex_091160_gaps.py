"""Add only verified Samsung KODEX trading dates absent from the Yahoo RAW CSV.

Requires xlrd >= 2.0.2 to read the supplied legacy XLS workbook. The original
Yahoo rows are retained verbatim. Adj Close is deliberately blank on new rows.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import sys
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import xlrd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/01_kodex_091160/01_kodex_091160_RAW_20110101_20261007.csv"
AUDIT = ROOT / "data/metadata/KODEX_091160_GAP_FILL_AUDIT_20261014.json"
XLS_FILES = list(ROOT.glob("KODEX*.xls"))
BACKUP = Path.home() / "Downloads/selected_fgi_raw_proxy7_m0_m3_20261014.zip"
MANIFEST = ROOT / "PACKAGE_CONTENTS.json"
EXPECTED_BEFORE_SHA256 = "25f3c539f91f5af65760f7e0947847d5e84d1291b1817c208282d28a5aa871dd"
HEADER = "Date,Open,High,Low,Close,Adj Close,Volume"
LOWER = date(2011, 1, 1)
UPPER = date(2026, 10, 7)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_raw(data: bytes) -> tuple[str, str, dict[str, str], dict[str, dict[str, str]]]:
    lines = data.decode("utf-8-sig").splitlines()
    if len(lines) < 3 or not lines[0].startswith("# SOURCE |") or lines[1] != HEADER:
        raise ValueError("Unexpected RAW metadata or columns")
    original_lines: dict[str, str] = {}
    original_values: dict[str, dict[str, str]] = {}
    for line in lines[2:]:
        fields = next(csv.reader([line]))
        if len(fields) != 7:
            raise ValueError(f"Unexpected RAW row: {line}")
        day = date.fromisoformat(fields[0])
        if not LOWER <= day <= UPPER or fields[0] in original_lines:
            raise ValueError(f"Out-of-range or duplicated RAW date: {fields[0]}")
        original_lines[fields[0]] = line
        original_values[fields[0]] = dict(zip(HEADER.split(","), fields))
    if len(original_lines) != 3842:
        raise ValueError(f"Expected 3842 original rows; found {len(original_lines)}")
    return lines[0], lines[1], original_lines, original_values


def parse_xls(path: Path) -> dict[str, dict[str, object]]:
    workbook = xlrd.open_workbook(path, on_demand=True)
    if workbook.sheet_names() != ["www.kodex.com"]:
        raise ValueError("Unexpected XLS sheet")
    sheet = workbook.sheet_by_index(0)
    if sheet.ncols != 9 or sheet.cell_value(3, 1) != "종가" or sheet.cell_value(3, 4) != "거래량":
        raise ValueError("Unexpected XLS Close/Volume column layout")
    result: dict[str, dict[str, object]] = {}
    for index in range(4, sheet.nrows):
        value = str(sheet.cell_value(index, 0)).strip()
        if len(value) != 8 or not value.isdigit():
            raise ValueError(f"Invalid XLS date at row {index + 1}: {value}")
        day = datetime.strptime(value, "%Y%m%d").date()
        if not LOWER <= day <= UPPER:
            continue
        key = day.isoformat()
        if key in result:
            raise ValueError(f"Duplicated XLS date: {key}")
        close = sheet.cell_value(index, 1)
        volume = sheet.cell_value(index, 4)
        if not isinstance(close, (int, float)) or not math.isfinite(close) or close <= 0:
            raise ValueError(f"Invalid XLS Close: {key}")
        if not isinstance(volume, (int, float)) or not math.isfinite(volume) or volume < 0 or int(volume) != volume:
            raise ValueError(f"Invalid XLS Volume: {key}")
        result[key] = {"Close": float(close), "Volume": int(volume), "xls_row": index + 1}
    return result


def main() -> None:
    if len(XLS_FILES) != 1 or AUDIT.exists():
        raise ValueError("Expected exactly one KODEX XLS and no prior audit output")
    xls = XLS_FILES[0]
    before = RAW.read_bytes()
    before_hash = sha256(before)
    if before_hash != EXPECTED_BEFORE_SHA256:
        raise ValueError("RAW SHA-256 differs from the audited pre-change version")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw_relpath = RAW.relative_to(ROOT).as_posix()
    saved = next(record for record in manifest["files"] if record["path"] == raw_relpath)
    with zipfile.ZipFile(BACKUP) as archive:
        backup_hash = sha256(archive.read(raw_relpath))
    if not before_hash == saved["sha256"] == backup_hash:
        raise ValueError("Pre-change ZIP backup or manifest hash does not match RAW")

    original_source, header, original_lines, original_values = parse_raw(before)
    official = parse_xls(xls)
    if len(official) != 3874 or set(original_lines) - set(official):
        raise ValueError("Unexpected date coverage in official XLS")
    missing = sorted(set(official) - set(original_lines))
    if len(missing) != 32:
        raise ValueError(f"Expected 32 missing dates; found {len(missing)}")

    close_mismatches = [key for key in original_lines if float(original_values[key]["Close"]) != official[key]["Close"]]
    volume_mismatches = [key for key in original_lines if int(original_values[key]["Volume"]) != official[key]["Volume"]]
    if close_mismatches:
        raise ValueError(f"Yahoo/Samsung overlapping Close mismatch: {close_mismatches[:5]}")

    new_lines: dict[str, str] = {}
    for key in missing:
        close = repr(official[key]["Close"])
        volume = str(official[key]["Volume"])
        new_lines[key] = f"{key},,,,{close},,{volume}"
    xls_hash = sha256(xls.read_bytes())
    metadata = (
        original_source
        + " | supplemental_provider=Samsung Asset Management (KODEX)"
        + " | supplemental_source_url=https://www.kodex.com/"
        + f" | supplemental_source_file={xls.name}"
        + f" | supplemental_source_sha256={xls_hash}"
        + " | supplemental_rows=32"
        + " | supplemental_fields=Close;Volume"
        + " | supplemental_missing_fields=Open;High;Low;Adj Close"
        + " | supplemental_method=insert_missing_trading_dates_only;original_3842_rows_unchanged"
    )
    merged = {**original_lines, **new_lines}
    output = ("\n".join([metadata, header, *[merged[key] for key in sorted(merged)]]) + "\n").encode("utf-8")
    # Independent pre-write checks on the constructed bytes.
    candidate_lines = output.decode("utf-8").splitlines()
    candidate_values = list(csv.DictReader(io.StringIO("\n".join(candidate_lines[1:]))))
    candidate_dates = [row["Date"] for row in candidate_values]
    if len(candidate_values) != 3874 or candidate_dates != sorted(official) or len(set(candidate_dates)) != 3874:
        raise ValueError("Candidate row count, order, or date coverage failed")
    candidate_by_date = {row["Date"]: row for row in candidate_values}
    for key, previous in original_values.items():
        if candidate_by_date[key] != previous or merged[key] != original_lines[key]:
            raise ValueError(f"Original Yahoo row changed: {key}")
    for key in missing:
        row = candidate_by_date[key]
        if any(row[field] for field in ("Open", "High", "Low", "Adj Close")):
            raise ValueError(f"Unknown new value was filled: {key}")
        if float(row["Close"]) != official[key]["Close"] or int(row["Volume"]) != official[key]["Volume"]:
            raise ValueError(f"Supplemental value mismatch: {key}")

    audit = {
        "dataset_id": "01_kodex_091160",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_file": str(RAW),
        "raw_sha256_before": before_hash,
        "raw_sha256_after": sha256(output),
        "backup_zip": str(BACKUP),
        "backup_raw_sha256": backup_hash,
        "official_source_file": str(xls),
        "official_source_sheet": "www.kodex.com",
        "official_source_url": "https://www.kodex.com/",
        "official_source_sha256": xls_hash,
        "original_rows_unchanged": len(original_lines),
        "supplemented_rows": len(missing),
        "final_rows": len(candidate_values),
        "min_date": candidate_dates[0],
        "max_date": candidate_dates[-1],
        "duplicate_dates": 0,
        "overlap_close_mismatches": len(close_mismatches),
        "overlap_volume_mismatches_original_values_preserved": len(volume_mismatches),
        "adjusted_close_decision": "Missing on all 32 inserted rows: local Yahoo adjustment ratios and the XLS do not establish date-specific dividend history or Yahoo Adj Close factors; fund NAV is not Adj Close.",
        "new_rows": [
            {"Date": key, "Close": official[key]["Close"], "Volume": official[key]["Volume"], "xls_row": official[key]["xls_row"], "Open": None, "High": None, "Low": None, "Adj Close": None}
            for key in missing
        ],
    }
    audit_bytes = (json.dumps(audit, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if "--check-only" in sys.argv:
        print(json.dumps({"status": "prewrite_qc_pass", "missing_dates": missing, "supplemented_rows": len(missing), "final_rows": len(candidate_values), "overlap_close_mismatches": len(close_mismatches), "original_volume_mismatches_preserved": len(volume_mismatches), "adjusted_close": "missing_on_new_rows"}, indent=2))
        return
    raw_temp = RAW.with_name(RAW.name + ".supplement.tmp")
    audit_temp = AUDIT.with_name(AUDIT.name + ".tmp")
    try:
        with raw_temp.open("xb") as handle:
            handle.write(output)
        with audit_temp.open("xb") as handle:
            handle.write(audit_bytes)
        if sha256(raw_temp.read_bytes()) != audit["raw_sha256_after"]:
            raise ValueError("Temporary RAW hash check failed")
        os.replace(raw_temp, RAW)
        os.replace(audit_temp, AUDIT)
        if sha256(RAW.read_bytes()) != audit["raw_sha256_after"]:
            raise ValueError("Final RAW hash check failed")
    finally:
        raw_temp.unlink(missing_ok=True)
        audit_temp.unlink(missing_ok=True)
    print(json.dumps({"supplemented_rows": 32, "final_rows": 3874, "duplicate_dates": 0, "adj_close_missing_new_rows": 32, "original_rows_unchanged": 3842, "raw_sha256_after": audit["raw_sha256_after"]}, indent=2))


if __name__ == "__main__":
    main()
