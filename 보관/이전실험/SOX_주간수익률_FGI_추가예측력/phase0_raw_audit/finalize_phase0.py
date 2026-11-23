"""Independent Phase 0 file audit; reads protected inputs and collected originals only."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from collect_twse_official import digest, parse_original

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
RUN = BASE / "run_20261016_final"


def csv_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    if path.exists():
        raise FileExistsError(path)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    manifest = csv_rows(RUN / "collection_manifest.csv")
    twse = csv_rows(RUN / "TWSE_monthly_manifest.csv")
    failed = [r for r in twse if r["status"] != "COLLECTED"]
    if len(failed) != 1 or failed[0]["year_month"] != "2011-05":
        raise AssertionError(f"Unexpected TWSE failures: {[r['year_month'] for r in failed]}")
    retry = RUN / "twse_original_monthly" / "TWSE_EFTRI_HIST_201105_retry_original.csv"
    qc_retry = parse_original(retry, 2011, 5)
    failed[0].update(qc_retry)
    failed[0].update(status="COLLECTED_RETRY", source_url="https://www.twse.com.tw/indicesReport/EFTRI_HIST?response=csv&date=20110520",
                     file=retry.relative_to(BASE).as_posix(), sha256=digest(retry), bytes=str(retry.stat().st_size),
                     http_status="200", unit="TWSE index points", frequency="daily trading session",
                     vintage_status="current archive; original daily publication vintage unverified",
                     retrieved_at_utc=datetime.fromtimestamp(retry.stat().st_mtime, timezone.utc).isoformat(),
                     error="")
    twse_fields = list(twse[0])
    write_csv(RUN / "TWSE_monthly_manifest_corrected.csv", twse, twse_fields)

    twse_days = []
    for item in twse:
        if item["status"] not in {"COLLECTED", "COLLECTED_RETRY"}:
            raise AssertionError(f"TWSE unresolved {item['year_month']}")
        path = BASE / item["file"]
        if digest(path) != item["sha256"]:
            raise AssertionError(f"TWSE SHA mismatch {path}")
        parsed = parse_original(path, *map(int, item["year_month"].split("-")))
        if int(item["rows"]) != parsed["rows"]:
            raise AssertionError(f"TWSE row mismatch {path}")
        # Dates, rather than transformed index values, are sufficient for Phase 0 QC.
        text = path.read_bytes().decode("cp950")
        for row in csv.reader(text.splitlines()):
            if len(row) > 2:
                parts = row[0].strip().split("/")
                if len(parts) == 3 and all(x.isdigit() for x in parts):
                    y, m, d = map(int, parts)
                    twse_days.append(date(y + 1911, m, d).isoformat())

    legacy = csv_rows(RUN / "existing_raw_inventory.csv")
    if len(legacy) != 17 or any("READ_ERROR" in r["notes"] for r in legacy):
        raise AssertionError("Legacy inventory incomplete")
    for r in legacy:
        if digest(ROOT / r["file"]) != r["sha256"]:
            raise AssertionError(f"Legacy SHA mismatch {r['file']}")

    cnn_dir = ROOT / "data/raw/11_cnn_fgi"
    cnn_csv = pd.read_csv(next(cnn_dir.glob("*.csv")))
    cnn_csv["Date"] = pd.to_datetime(cnn_csv["Date"]).dt.date
    cnn_json = json.loads(next(cnn_dir.glob("*.json")).read_text(encoding="utf-8"))
    hist = pd.DataFrame(cnn_json["fear_and_greed_historical"]["data"])
    hist["Date"] = pd.to_datetime(hist["x"], unit="ms", utc=True).dt.date
    overlap = hist.merge(cnn_csv, on="Date")
    disagreement = overlap[(overlap["y"] - overlap["Fear Greed"]).abs() > 1e-9]

    workbook_path = RUN / "new_raw" / "WSTS_Historical_Billings_Aug_2026_original.xlsx"
    sheet = load_workbook(workbook_path, read_only=True, data_only=True)["Monthly Data"]
    workbook_rows = list(sheet.values)
    wsts_worldwide = []
    current_year = None
    for row in workbook_rows:
        if isinstance(row[0], int) and 1980 < row[0] <= 2030:
            current_year = row[0]
        if row[0] == "Worldwide" and current_year:
            for month, value in enumerate(row[1:13], 1):
                if isinstance(value, (int, float)):
                    wsts_worldwide.append(f"{current_year:04d}-{month:02d}")

    protected = json.loads((RUN / "protected_inputs_qc.json").read_text(encoding="utf-8"))
    if protected["mismatches"] or protected["added"]:
        raise AssertionError("Protected inputs changed during collection")

    master = []
    for r in legacy:
        master.append({"source_type": "EXISTING_READ_ONLY", "series_id": r["dataset_id"] + "/" + r["series_id"],
                       "status": "EXISTING_READ_ONLY", "provider": r["provider"], "source_url": r["source_url"],
                       "file": r["file"], "sha256": r["sha256"], "rows": r["rows"],
                       "min_date": r["min_date"], "max_date": r["max_date"],
                       "missing_cells": r["missing_cells"], "duplicate_dates": r["duplicate_dates"],
                       "unit": "see original SOURCE/header", "vintage_status": "see Phase 0 report"})
    for r in manifest:
        master.append({"source_type": "NEW_COLLECTION", **r})
    for r in twse:
        master.append({"source_type": "NEW_TWSE_OFFICIAL_MONTHLY", "series_id": "TWSE_semiconductor_index/" + r["year_month"],
                       "status": r["status"], "provider": "TWSE", "source_url": r["source_url"],
                       "file": r["file"], "sha256": r["sha256"], "rows": r["rows"],
                       "min_date": r["min_date"], "max_date": r["max_date"],
                       "missing_cells": r["missing_values"], "duplicate_dates": r["duplicate_dates"],
                       "unit": r["unit"], "vintage_status": r["vintage_status"]})
    fields = ["source_type", "series_id", "status", "provider", "source_url", "file", "sha256", "rows",
              "min_date", "max_date", "missing_cells", "duplicate_dates", "unit", "vintage_status"]
    write_csv(BASE / "collection_manifest.csv", master, fields)

    result = {
        "phase": "Research C Phase 0 only", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "existing_physical_files": len(legacy), "existing_raw_dataset_folders": len(set(r["dataset_id"] for r in legacy if r["dataset_id"] != "stockcharts_original")),
        "new_yahoo_collected": sum(r["provider"].startswith("Yahoo") and r["status"] == "COLLECTED" for r in manifest),
        "new_fred_collected": sum(r["provider"] == "FRED" and r["status"] == "COLLECTED" for r in manifest),
        "wsts_original_collected": any(r["provider"] == "WSTS" and r["status"] == "COLLECTED_ORIGINAL_UNPARSED" for r in manifest),
        "nasdaqesox_license_hold": any(r["series_id"] == "NASDAQESOX" and r["status"] == "LICENSE_HOLD" for r in manifest),
        "twse_monthly_originals": len(twse), "twse_rows_total": len(twse_days),
        "twse_min_date": min(twse_days), "twse_max_date": max(twse_days),
        "twse_duplicate_dates": len(twse_days) - len(set(twse_days)),
        "twse_retry": "2011-05: initial 200 maintenance HTML; retry with date=20110520 returned official CSV",
        "wsts_unit": "1000 US$", "wsts_worldwide_months_2011_onward": sum(x >= "2011-01" for x in wsts_worldwide),
        "wsts_worldwide_last_month": max(wsts_worldwide),
        "cnn_csv_rows": len(cnn_csv), "cnn_csv_min_date": str(cnn_csv["Date"].min()),
        "cnn_csv_max_date": str(cnn_csv["Date"].max()),
        "cnn_csv_2020_rows": sum(d.year == 2020 for d in cnn_csv["Date"]),
        "cnn_json_historical_rows": len(hist), "cnn_json_min_date": str(hist["Date"].min()),
        "cnn_json_max_date": str(hist["Date"].max()),
        "cnn_json_duplicate_calendar_dates": int(hist["Date"].duplicated().sum()),
        "cnn_csv_json_overlap_rows": len(overlap), "cnn_csv_json_score_disagreements_current": len(disagreement),
        "cnn_historical_first_publication_vintage_verified": False,
        "protected_files_checked": protected["checked"], "protected_hash_mismatches": len(protected["mismatches"]),
        "protected_new_files": len(protected["added"]),
        "new_collection_manifest_sha256": digest(RUN / "collection_manifest.csv"),
        "twse_corrected_manifest_sha256": digest(RUN / "TWSE_monthly_manifest_corrected.csv"),
    }
    out = BASE / "PHASE0_COLLECTION_QC.json"
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
