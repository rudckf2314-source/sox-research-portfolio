"""Copy Research C Phase 0 observations into new canonical data/raw CSVs.

Existing RAW files and archived vendor originals are read-only.  No financial
features, weekly observations, labels, or model inputs are calculated here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
RAW = ROOT / "data" / "raw"
RUN = BASE / "run_20261016_final"
MANIFEST = RUN / "collection_manifest.csv"
TWSE_MANIFEST = RUN / "TWSE_monthly_manifest_corrected.csv"

SPEC = [
    ("12_ndx", "^NDX", "Yahoo Finance via yfinance", "Nasdaq", "2010-01-01"),
    ("13_twii", "^TWII", "Yahoo Finance via yfinance", "Taiwan Stock Exchange", "2010-01-01"),
    ("14_tsm", "TSM", "Yahoo Finance via yfinance", "TSMC / NYSE", "2010-01-01"),
    ("15_dgs10", "DGS10", "FRED", "Federal Reserve Board", "2010-01-01"),
    ("16_dgs2", "DGS2", "FRED", "Federal Reserve Board", "2010-01-01"),
    ("17_dfii10", "DFII10", "FRED", "Federal Reserve Board", "2010-01-01"),
    ("18_dtwexbgs", "DTWEXBGS", "FRED", "Federal Reserve Board", "2010-01-01"),
    ("19_nfci", "NFCI", "FRED", "Federal Reserve Bank of Chicago", "2010-01-01"),
    ("20_ipg3344s", "IPG3344S", "FRED", "Federal Reserve Board", "2010-01-01"),
    ("21_a34sno", "A34SNO", "FRED", "U.S. Census Bureau", "2010-01-01"),
    ("22_wsts_worldwide_billings", "historical_billings", "WSTS", "World Semiconductor Trade Statistics", "2011-01-01"),
    ("23_twse_semiconductor_index", "TWSE semiconductor industry index", "TWSE", "Taiwan Stock Exchange", "2011-01-01"),
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rows_of(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def csv_body(header: list[str], rows: list[list[str]]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def wsts_worldwide(source: Path) -> tuple[bytes, dict]:
    sheet = load_workbook(source, read_only=True, data_only=True)["Monthly Data"]
    year = None
    data = []
    for row in sheet.values:
        if isinstance(row[0], int) and 1980 < row[0] <= 2030:
            year = row[0]
        elif row[0] == "Worldwide" and year is not None and year >= 2011:
            for month, value in enumerate(row[1:13], 1):
                if isinstance(value, (int, float)):
                    data.append([f"{year:04d}-{month:02d}-01", str(int(value)) if int(value) == value else str(value)])
    if len(data) != 188 or data[0][0] != "2011-01-01" or data[-1][0] != "2026-08-01":
        raise AssertionError("WSTS coverage differs from Phase 0 audit")
    return csv_body(["Date", "Worldwide_Billings_1000USD"], data), {
        "definition": "Worldwide monthly semiconductor billings; source workbook Monthly Data sheet, Worldwide row; unit 1000 USD",
        "transformation": "Worldwide row selected; month represented by first calendar day; values not scaled or smoothed",
    }


def twse_semiconductor() -> tuple[bytes, dict]:
    data = []
    sources = rows_of(TWSE_MANIFEST)
    for item in sources:
        path = BASE / item["file"]
        if sha(path) != item["sha256"]:
            raise AssertionError(f"TWSE source hash mismatch: {path}")
        text = path.read_bytes().decode("cp950")
        for row in csv.reader(text.splitlines()):
            if len(row) < 3:
                continue
            parts = row[0].strip().split("/")
            if len(parts) != 3 or not all(part.isdigit() for part in parts):
                continue
            roc_year, month, day = map(int, parts)
            iso = date(roc_year + 1911, month, day).isoformat()
            value = row[2].replace(",", "").strip()
            if not value or float(value) <= 0:
                raise AssertionError(f"TWSE missing/nonpositive value on {iso}")
            data.append([iso, value])
    if len(data) != 3862 or len({x[0] for x in data}) != len(data):
        raise AssertionError("TWSE Phase 0 row or duplicate count changed")
    if [x[0] for x in data] != sorted(x[0] for x in data):
        raise AssertionError("TWSE dates not ascending")
    return csv_body(["Date", "Semiconductor_Industry_Index"], data), {
        "definition": "TWSE Semiconductor Industry Index, EFTRI_HIST source CSV third column; index points",
        "transformation": "190 official monthly CSV files concatenated by trading date; ROC date converted to ISO; commas removed from number formatting; no rescaling",
        "source_manifest": TWSE_MANIFEST.relative_to(ROOT).as_posix(),
    }


def source_body(item: dict) -> tuple[bytes, dict]:
    series = item["series_id"]
    if series == "TWSE semiconductor industry index":
        return twse_semiconductor()
    source = ROOT / item["file"]
    if sha(source) != item["sha256"]:
        raise AssertionError(f"Original source hash mismatch: {source}")
    if series == "historical_billings":
        body, extra = wsts_worldwide(source)
        extra["source_sha256"] = item["sha256"]
        return body, extra
    if item["provider"].startswith("Yahoo"):
        original = source.read_bytes()
        if not original.startswith(b"Date,Open,High,Low,Close,Adj Close,Volume"):
            raise AssertionError(f"Yahoo source columns changed: {source}")
        return original, {"definition": f"{series} daily OHLC, Adj Close and Volume",
                          "transformation": "yfinance output columns preserved; auto_adjust=False; no adjustment, filling or resampling",
                          "source_sha256": item["sha256"]}
    if item["provider"] == "FRED":
        original = source.read_bytes()
        expected = f"observation_date,{series}".encode()
        if not original.startswith(expected):
            raise AssertionError(f"FRED source header changed: {source}")
        # Existing project RAW conventions use Date as the first column.
        body = b"Date," + series.encode() + original[len(expected):]
        return body, {"definition": f"FRED {series} observations; {item['unit']}; {item['frequency']}",
                      "transformation": "observation_date header renamed to Date only; observation rows and missing blanks preserved byte-for-byte",
                      "source_sha256": item["sha256"]}
    raise ValueError(f"Unsupported collected series {series}")


def validate_body(body: bytes, item: dict, series: str) -> dict:
    frame = pd.read_csv(io.BytesIO(body))
    if "Date" not in frame or frame.empty:
        raise AssertionError(f"Bad canonical body: {series}")
    dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="raise")
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise AssertionError(f"Duplicate or unsorted dates: {series}")
    if frame.drop(columns="Date").empty:
        raise AssertionError(f"No value columns: {series}")
    if item["rows"] and len(frame) != int(item["rows"]):
        raise AssertionError(f"Source row count differs: {series}")
    if item["min_date"] and str(dates.min().date()) != item["min_date"]:
        raise AssertionError(f"Source minimum date differs: {series}")
    if item["max_date"] and str(dates.max().date()) != item["max_date"]:
        raise AssertionError(f"Source maximum date differs: {series}")
    missing = int(frame.isna().sum().sum())
    if item["missing_cells"] and missing != int(item["missing_cells"]):
        raise AssertionError(f"Source missing count differs: {series}")
    return {"rows": len(frame), "min_date": str(dates.min().date()),
            "max_date": str(dates.max().date()), "missing_cells": missing,
            "duplicate_dates": 0, "columns": list(frame.columns)}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    source_rows = {r["series_id"]: r for r in rows_of(MANIFEST)}
    twse_rows = rows_of(TWSE_MANIFEST)
    source_rows["TWSE semiconductor industry index"] = {
        "series_id": "TWSE semiconductor industry index", "provider": "TWSE", "status": "COLLECTED",
        "source_url": "https://www.twse.com.tw/indicesReport/EFTRI_HIST?response=csv&date=YYYYMM15",
        "rows": "3862", "min_date": "2011-01-03", "max_date": "2026-10-15", "missing_cells": "0",
        "retrieved_at_utc": max(r["retrieved_at_utc"] for r in twse_rows),
    }
    existing = {p.relative_to(RAW).as_posix(): sha(p) for p in RAW.rglob("*") if p.is_file()}
    plan = []
    payloads = []
    for dataset_id, series, provider, administrator, start in SPEC:
        item = source_rows[series]
        if item["status"] not in ("COLLECTED", "COLLECTED_ORIGINAL_UNPARSED"):
            raise AssertionError(f"Not collected: {series}")
        folder = RAW / dataset_id
        if folder.exists():
            raise FileExistsError(f"Refusing to alter existing folder {folder}")
        body, extra = source_body(item)
        q = validate_body(body, item, series)
        name = f"{dataset_id}_RAW_{start.replace('-', '')}_{q['max_date'].replace('-', '')}.csv"
        destination = folder / name
        source_url = item["source_url"]
        origin = extra.get("source_sha256", "")
        pieces = ["# SOURCE", f"dataset_id={dataset_id}", f"provider={provider}",
                  f"administrator={administrator}", f"source_url={source_url}",
                  f"series_or_symbol={series}", f"definition={extra['definition']}",
                  f"start_date={start}", f"end_date={q['max_date']}",
                  f"retrieved_at_utc={item['retrieved_at_utc']}",
                  f"transformation={extra['transformation']}"]
        if origin:
            pieces.append(f"source_sha256={origin}")
        if extra.get("source_manifest"):
            pieces.append(f"source_manifest={extra['source_manifest']}")
        if series == "^TWII":
            pieces.append("last_observation_status=2026-10-16 intraday/unverified; not a confirmed final close")
        if series in ("NFCI", "DTWEXBGS", "IPG3344S", "A34SNO"):
            pieces.append("release_date_and_historical_vintage=unverified; observation Date is not availability timestamp")
        content = (" | ".join(pieces) + "\n").encode("utf-8") + body
        output = {"dataset_id": dataset_id, "series_id": series,
                  "output_file": destination.relative_to(ROOT).as_posix(), **q,
                  "source_url": source_url, "source_file_sha256": origin or item.get("sha256", ""),
                  "canonical_sha256": hashlib.sha256(content).hexdigest(),
                  "status": "PLANNED" if args.dry_run else "CREATED"}
        plan.append(output)
        payloads.append((folder, destination, content))
    if args.dry_run:
        print(json.dumps({"new_raw_files": len(plan), "existing_files_to_preserve": len(existing),
                          "destinations": [r["output_file"] for r in plan]}, ensure_ascii=False))
        return
    for folder, destination, content in payloads:
        folder.mkdir()
        with destination.open("xb") as f:
            f.write(content)
    for rec in plan:
        path = ROOT / rec["output_file"]
        if sha(path) != rec["canonical_sha256"]:
            raise AssertionError(f"Canonical output hash mismatch: {path}")
        first, second = path.read_text(encoding="utf-8").splitlines()[:2]
        if not first.startswith("# SOURCE | dataset_id=") or not second.startswith("Date,"):
            raise AssertionError(f"Canonical metadata/header mismatch: {path}")
        frame = pd.read_csv(path, comment="#")
        if len(frame) != rec["rows"] or frame.Date.duplicated().sum() != 0:
            raise AssertionError(f"Canonical row/duplicate mismatch: {path}")
    after = {p.relative_to(RAW).as_posix(): sha(p) for p in RAW.rglob("*") if p.is_file()}
    if any(after.get(k) != v for k, v in existing.items()):
        raise AssertionError("Existing RAW altered")
    if len(after) != len(existing) + len(plan):
        raise AssertionError("Unexpected RAW file count")
    qc = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
          "existing_raw_files_preserved": len(existing), "existing_raw_hash_mismatches": 0,
          "new_canonical_files": len(plan), "license_held_NASDAQESOX_created": False,
          "new_files": plan}
    out = BASE / "RESEARCH_C_RAW_MATERIALIZATION_QC.json"
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(qc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"created": len(plan), "old_files_preserved": len(existing),
                      "output_qc": out.relative_to(ROOT).as_posix()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
