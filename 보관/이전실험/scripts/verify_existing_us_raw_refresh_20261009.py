"""Independent read-only QC for the October 9 versioned US RAW refresh."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data/metadata/RAW_REFRESH_20261009"
RAW = ROOT / "data/raw"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    run = json.loads((RUN / "RAW_REFRESH_QC.json").read_text(encoding="utf-8"))
    dry = json.loads((RUN / "DRY_RUN.json").read_text(encoding="utf-8"))
    if len(run["new_files"]) != 6:
        raise AssertionError("Expected six refreshed series")
    details = []
    for rec in run["new_files"]:
        dataset_id = rec["dataset_id"]
        old = ROOT / dry["old_files"][dataset_id]
        new = ROOT / rec["output_file"]
        vendor = ROOT / rec["source_file"]
        if sha(old) != dry["old_hashes"][dataset_id]:
            raise AssertionError(f"Old file changed: {old}")
        if sha(new) != rec["output_sha256"] or sha(vendor) != rec["source_sha256"]:
            raise AssertionError(f"Hash mismatch: {dataset_id}")
        payload = new.read_bytes()
        metadata, split, body = payload.partition(b"\n")
        if not split or not metadata.startswith(f"# SOURCE | dataset_id={dataset_id}".encode()):
            raise AssertionError(f"SOURCE metadata missing: {dataset_id}")
        if dataset_id in ("02_sox", "04_sp500", "09_ief", "10_hyg"):
            if body != vendor.read_bytes():
                raise AssertionError(f"Vendor observation bytes differ: {dataset_id}")
        else:
            symbol = rec["series_id"]
            raw = vendor.read_bytes()
            expected = raw.replace(f"observation_date,{symbol}".encode(), f"Date,{symbol}".encode(), 1)
            if expected == raw:
                expected = raw.replace(f"DATE,{symbol}".encode(), f"Date,{symbol}".encode(), 1)
            if body != expected:
                raise AssertionError(f"FRED observation bytes differ: {dataset_id}")
        fresh = pd.read_csv(io.BytesIO(payload), comment="#")
        previous = pd.read_csv(old, comment="#")
        dates = pd.to_datetime(fresh["Date"], format="%Y-%m-%d", errors="raise")
        if fresh.Date.iloc[0] != "2011-01-03" or fresh.Date.iloc[-1] != "2026-10-09":
            raise AssertionError(f"Wrong coverage: {dataset_id}")
        if dates.duplicated().any() or not dates.is_monotonic_increasing:
            raise AssertionError(f"Date QC failed: {dataset_id}")
        if len(fresh) != rec["rows"] or int(fresh.isna().sum().sum()) != rec["missing_cells"]:
            raise AssertionError(f"Row/missing QC failed: {dataset_id}")
        if not {"2026-10-07", "2026-10-08", "2026-10-09"}.issubset(set(fresh.Date)):
            raise AssertionError(f"Missing target dates: {dataset_id}")
        left = previous.set_index("Date")
        right = fresh.set_index("Date")
        common = left.index.intersection(right.index)
        before_intraday = common[common < "2026-10-07"]
        material_differences = {}
        for col in left.columns:
            a = pd.to_numeric(left.loc[before_intraday, col], errors="coerce")
            b = pd.to_numeric(right.loc[before_intraday, col], errors="coerce")
            diff = (a - b).abs()
            material_differences[col] = {
                "count_gt_0_0001": int((diff > 0.0001).sum()),
                "count_gt_0_01": int((diff > 0.01).sum()),
                "max_abs": float(diff.max()) if len(diff) else 0.0,
            }
        details.append({"dataset_id": dataset_id, "series_id": rec["series_id"],
                        "rows": len(fresh), "min_date": fresh.Date.iloc[0], "max_date": fresh.Date.iloc[-1],
                        "missing_cells": int(fresh.isna().sum().sum()), "duplicate_dates": 0,
                        "old_2026_10_07": left.loc["2026-10-07"].to_dict() if "2026-10-07" in left.index else None,
                        "new_2026_10_07": right.loc["2026-10-07"].to_dict(),
                        "pre_2026_10_07_differences": material_differences,
                        "output_file": rec["output_file"], "output_sha256": sha(new)})
    result = {"status": "PASS", "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "old_files_unchanged": 6, "new_files_verified": 6, "details": details}
    dest = RUN / "INDEPENDENT_QC.json"
    if dest.exists():
        raise FileExistsError(dest)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"old_files_unchanged":6,"new_files_verified":6,
                      "important_historical_changes":{x["dataset_id"]:{k:v["count_gt_0_01"] for k,v in x["pre_2026_10_07_differences"].items()} for x in details}},ensure_ascii=False))


if __name__ == "__main__":
    main()
