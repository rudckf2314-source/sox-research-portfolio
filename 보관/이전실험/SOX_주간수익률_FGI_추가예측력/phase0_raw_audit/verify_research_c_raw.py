"""Independent read-only verification of Research C canonical RAW against archives."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
RUN = BASE / "run_20261016_final"
QC_FILE = BASE / "RESEARCH_C_RAW_MATERIALIZATION_QC.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    qc = json.loads(QC_FILE.read_text(encoding="utf-8"))
    manifest = {r["series_id"]: r for r in table(RUN / "collection_manifest.csv")}
    old = [r for r in table(RUN / "existing_raw_inventory.csv") if r["file"].startswith("data/raw/")]
    old_bad = [r["file"] for r in old if sha(ROOT / r["file"]) != r["sha256"]]
    checks = []
    for rec in qc["new_files"]:
        path = ROOT / rec["output_file"]
        raw = path.read_bytes()
        meta, sep, body = raw.partition(b"\n")
        assert sep and meta.startswith(b"# SOURCE | dataset_id="), path
        assert sha(path) == rec["canonical_sha256"], path
        frame = pd.read_csv(io.BytesIO(raw), comment="#")
        dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="raise")
        assert len(frame) == rec["rows"] and dates.is_monotonic_increasing and not dates.duplicated().any(), path
        assert str(dates.min().date()) == rec["min_date"] and str(dates.max().date()) == rec["max_date"], path
        assert int(frame.isna().sum().sum()) == rec["missing_cells"], path
        series = rec["series_id"]
        match = "row_and_value_audited"
        if series in manifest and manifest[series]["provider"].startswith("Yahoo"):
            assert body == (ROOT / manifest[series]["file"]).read_bytes(), path
            match = "exact_body_bytes"
        elif series in manifest and manifest[series]["provider"] == "FRED":
            source = (ROOT / manifest[series]["file"]).read_bytes()
            expected = source.replace(f"observation_date,{series}".encode(), f"Date,{series}".encode(), 1)
            assert body == expected, path
            match = "exact_observation_bytes_after_header_rename"
        elif series == "historical_billings":
            workbook = load_workbook(ROOT / manifest[series]["file"], read_only=True, data_only=True)["Monthly Data"]
            year = None
            sample = {}
            for row in workbook.values:
                if isinstance(row[0], int) and 1980 < row[0] <= 2030:
                    year = row[0]
                if row[0] == "Worldwide" and year is not None and year >= 2011:
                    for month, value in enumerate(row[1:13], 1):
                        if isinstance(value, (int, float)):
                            sample[f"{year:04d}-{month:02d}-01"] = value
            assert len(sample) == len(frame)
            assert all(float(value) == sample[day] for day, value in zip(frame["Date"], frame.iloc[:, 1])), path
            match = "all_188_workbook_values"
        elif series == "TWSE semiconductor industry index":
            months = table(RUN / "TWSE_monthly_manifest_corrected.csv")
            sample = {}
            for item in months:
                original = BASE / item["file"]
                assert sha(original) == item["sha256"]
                for row in csv.reader(original.read_bytes().decode("cp950").splitlines()):
                    if len(row) >= 3:
                        pieces = row[0].strip().split("/")
                        if len(pieces) == 3 and all(x.isdigit() for x in pieces):
                            y, m, d = map(int, pieces)
                            sample[date(y + 1911, m, d).isoformat()] = float(row[2].replace(",", ""))
            assert len(sample) == len(frame)
            assert all(float(value) == sample[day] for day, value in zip(frame["Date"], frame.iloc[:, 1])), path
            match = "all_3862_official_csv_values"
        checks.append({"dataset_id": rec["dataset_id"], "source_value_match": match,
                       "rows": len(frame), "min_date": rec["min_date"], "max_date": rec["max_date"],
                       "missing_cells": rec["missing_cells"], "sha256": sha(path)})
    result = {"verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "PASS" if not old_bad and len(checks) == 12 else "FAIL",
              "existing_raw_files_checked": len(old), "existing_raw_hash_mismatches": old_bad,
              "new_files_checked": len(checks), "checks": checks}
    out = BASE / "RESEARCH_C_RAW_INDEPENDENT_QC.json"
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "existing_raw_files_checked", "existing_raw_hash_mismatches", "new_files_checked")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
