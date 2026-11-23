"""Research C Phase 0: read-only legacy audit and isolated public-source collection.

Usage: python collect_phase0.py --run-dir RUN --dry-run
       python collect_phase0.py --run-dir RUN --collect
No weekly alignment, feature, label, or model operation is performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
YAHOO = {"NDX": "^NDX", "TWII": "^TWII", "TSM": "TSM"}
FRED = {
    "DGS10": ("Percent", "Daily", "Federal Reserve Board / H.15", "public domain; citation requested", "H.15 release, vintage unverified"),
    "DGS2": ("Percent", "Daily", "Federal Reserve Board / H.15", "public domain; citation requested", "H.15 release, vintage unverified"),
    "DFII10": ("Percent", "Daily", "Federal Reserve Board / H.15", "public domain; citation requested", "H.15 release, vintage unverified"),
    "DTWEXBGS": ("Index Jan 2006=100", "Daily", "Federal Reserve Board / H.10", "public domain; citation requested", "H.10 release after observation date; vintage unverified"),
    "NFCI": ("Index", "Weekly ending Friday", "Chicago Fed", "copyrighted; citation required", "normally published after reference Friday; release date must be mapped"),
    "IPG3344S": ("Index 2017=100", "Monthly", "Federal Reserve Board / G.17", "public domain; citation requested", "released after reference month and revisable"),
    "A34SNO": ("Millions of USD SA", "Monthly", "US Census Bureau / M3", "copyrighted; verify redistribution", "released after reference month and revisable; not semiconductor-only"),
}
FRED_HELD = {"NASDAQESOX": "Nasdaq copyrighted: FRED flags Pre-Approval Required; no automatic collection or publication without approval"}
WSTS_URL = "https://www.wsts.org/esraCMS/extension/media/f/WST/7803/WSTS-Historical-Billings-Report-Aug_2026.xlsx"
PROTECTED = ["data/raw", "data/processed", "data/processed_W1", "freeze", "stockcharts", "reports_D1", "reports_W1", "phase_report_D1", "phase_report_W1"]


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def protected_hashes() -> dict[str, str]:
    paths = []
    for rel in PROTECTED:
        p = ROOT / rel
        if p.exists():
            paths.extend(x for x in p.rglob("*") if x.is_file())
    return {p.relative_to(ROOT).as_posix(): sha_file(p) for p in sorted(set(paths))}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def existing_audit(out: Path) -> list[dict]:
    records = []
    for p in sorted((ROOT / "data/raw").rglob("*")) + sorted((ROOT / "stockcharts").glob("*.csv")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        rec = {"dataset_id": p.parent.name if p.parent.name != "stockcharts" else "stockcharts_original",
               "status": "EXISTING_READ_ONLY", "provider": "as_file_metadata", "series_id": p.stem,
               "source_url": "", "file": rel, "sha256": sha_file(p), "bytes": p.stat().st_size,
               "rows": None, "min_date": "", "max_date": "", "missing_cells": None, "duplicate_dates": None,
               "columns": "", "source_header": "", "notes": ""}
        try:
            if p.suffix.lower() == ".csv":
                if p.parent.name == "stockcharts":
                    with p.open(encoding="utf-8-sig") as f: rec["source_header"] = f.readline().strip()
                    frame = pd.read_csv(p, skiprows=1)
                    frame.columns = frame.columns.str.strip()
                    date_col = "Date"
                    frame[date_col] = pd.to_datetime(frame[date_col], format="%m/%d/%Y", errors="coerce")
                else:
                    with p.open(encoding="utf-8-sig") as f: rec["source_header"] = f.readline().strip()
                    frame = pd.read_csv(p, comment="#")
                    date_col = next((x for x in ["Date", "DATE"] if x in frame), None)
                    if date_col: frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
                rec.update(rows=len(frame), columns="|".join(frame.columns), missing_cells=int(frame.isna().sum().sum()))
                if date_col:
                    rec.update(min_date=str(frame[date_col].min().date()), max_date=str(frame[date_col].max().date()),
                               duplicate_dates=int(frame[date_col].duplicated().sum()),
                               invalid_dates=int(frame[date_col].isna().sum()))
            elif p.suffix.lower() == ".json":
                obj = json.loads(p.read_bytes())
                seq = obj.get("fear_and_greed_historical", {}).get("data", []) if isinstance(obj, dict) else []
                rec.update(rows=len(seq), columns="|".join(obj.keys()) if isinstance(obj, dict) else "", notes="CNN JSON historical x is date label; first publication time/vintage unverified")
        except Exception as exc:
            rec["notes"] = f"READ_ERROR {type(exc).__name__}: {exc}"
        records.append(rec)
    with (out / "existing_raw_inventory.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0])); w.writeheader(); w.writerows(records)
    return records


def fetch(url: str, out: Path) -> dict:
    if out.exists(): raise FileExistsError(out)
    start = now_utc()
    headers_file = out.with_suffix(out.suffix + ".headers.txt")
    result = subprocess.run(["curl.exe", "--location", "--fail", "--max-time", "45",
                             "--retry", "3", "--retry-delay", "2", "--silent", "--show-error",
                             "--dump-header", str(headers_file), "--output", str(out), url],
                            capture_output=True, text=True)
    if result.returncode:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"curl exit {result.returncode}: {result.stderr.strip()}")
    if out.stat().st_size == 0: raise ValueError("empty HTTP body")
    header_text = headers_file.read_text(encoding="iso-8859-1", errors="replace")
    last = header_text.replace("\r\n", "\n").strip().split("\n\n")[-1]
    lines = last.splitlines()
    status = int(lines[0].split()[1]) if lines and lines[0].startswith("HTTP/") else 200
    response_headers = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
    meta = {"request_url": url, "effective_url": url, "http_status": status,
            "response_headers": {k.strip():v.strip() for k,v in response_headers.items()},
            "retrieved_at_utc": start, "body_bytes": out.stat().st_size}
    meta["sha256"] = sha_file(out)
    return meta


def evaluate_dates(frame: pd.DataFrame, date_col: str, val_cols: list[str]) -> dict:
    ds = pd.to_datetime(frame[date_col], errors="coerce")
    vals = frame[val_cols].apply(pd.to_numeric, errors="coerce")
    return {"rows": len(frame), "min_date": str(ds.min().date()) if len(frame) else "",
            "max_date": str(ds.max().date()) if len(frame) else "",
            "duplicate_dates": int(ds.duplicated().sum()), "invalid_dates": int(ds.isna().sum()),
            "missing_cells": int(vals.isna().sum().sum()), "missing_by_column": vals.isna().sum().astype(int).to_dict(),
            "columns": "|".join(frame.columns)}


def collect_yahoo(symbol: str, ident: str, out: Path) -> dict:
    import yfinance as yf
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    frame = yf.Ticker(symbol).history(start="2010-01-01", end=str(today + timedelta(days=1)),
                                      interval="1d", auto_adjust=False, actions=False, repair=False)
    if frame.empty: raise ValueError("Yahoo returned no rows")
    expected = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    if not set(expected).issubset(frame.columns): raise ValueError(f"Expected OHLCV + Adj Close, received {list(frame.columns)}")
    frame = frame.reset_index()
    frame["Date"] = pd.to_datetime(frame["Date"]).dt.date.astype(str)
    frame = frame[["Date"] + expected]
    q = evaluate_dates(frame, "Date", expected)
    if q["duplicate_dates"] or q["invalid_dates"] or q["missing_cells"]:
        raise ValueError(f"Yahoo QC failed: {q}")
    nonpositive = int((frame[["Open", "High", "Low", "Close", "Adj Close"]] <= 0).sum().sum())
    if nonpositive: raise ValueError(f"nonpositive prices: {nonpositive}")
    dest = out / f"{ident}_yfinance_20100101_{q['max_date'].replace('-', '')}.csv"
    if dest.exists(): raise FileExistsError(dest)
    frame.to_csv(dest, index=False, float_format="%.10g")
    return {**q, "status": "COLLECTED", "provider": "Yahoo Finance via yfinance", "series_id": symbol,
            "unit": "index points" if symbol.startswith("^") else "USD/share", "frequency": "Daily trading sessions",
            "source_url": f"https://finance.yahoo.com/quote/{symbol}/history/", "file": dest.relative_to(ROOT).as_posix(),
            "sha256": sha_file(dest), "bytes": dest.stat().st_size, "retrieved_at_utc": now_utc(),
            "vintage_status": "UNVERIFIED; historical adjusted close can be revised", "release_timing": "historical Yahoo posting time UNVERIFIED",
            "license": "Yahoo Finance terms apply; redistribution not assumed", "qc_note": "auto_adjust=False; no calendar filling; yfinance DataFrame serialization, not original HTTP bytes"}


def collect_fred(series: str, meta: tuple, out: Path) -> dict:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd=2010-01-01"
    dest = out / f"{series}_FRED_original.csv"
    http = fetch(url, dest)
    if http["http_status"] != 200: raise ValueError(f"HTTP {http['http_status']}")
    frame = pd.read_csv(dest)
    date_column = next((c for c in ("DATE", "observation_date") if c in frame.columns), None)
    if date_column is None or series not in frame.columns:
        raise ValueError(f"unexpected FRED columns {list(frame.columns)}")
    q = evaluate_dates(frame, date_column, [series])
    if q["duplicate_dates"] or q["invalid_dates"] or q["rows"] == 0: raise ValueError(f"FRED QC failed: {q}")
    return {**q, "status": "COLLECTED", "provider": "FRED", "series_id": series, "unit": meta[0],
            "frequency": meta[1], "administrator": meta[2], "source_url": f"https://fred.stlouisfed.org/series/{series}",
            "retrieval_url": url, "file": dest.relative_to(ROOT).as_posix(), "sha256": http["sha256"],
            "bytes": http["body_bytes"], "retrieved_at_utc": http["retrieved_at_utc"],
            "http_status": http["http_status"], "response_headers": http["response_headers"],
            "vintage_status": "CURRENT_REVISED_NOT_POINT_IN_TIME", "release_timing": meta[4], "license": meta[3],
            "qc_note": "'.' holiday/release missing cells retained; no forward fill"}


def collect_wsts(out: Path) -> dict:
    dest = out / "WSTS_Historical_Billings_Aug_2026_original.xlsx"
    http = fetch(WSTS_URL, dest)
    if not dest.read_bytes().startswith(b"PK\x03\x04"):
        raise ValueError("WSTS response is not an XLSX ZIP")
    return {"status": "COLLECTED_ORIGINAL_UNPARSED", "provider": "WSTS", "series_id": "historical_billings",
            "source_url": WSTS_URL, "file": dest.relative_to(ROOT).as_posix(), "sha256": http["sha256"],
            "bytes": http["body_bytes"], "retrieved_at_utc": http["retrieved_at_utc"],
            "http_status": http["http_status"], "response_headers": http["response_headers"],
            "unit": "USD sales; verify workbook units", "frequency": "Monthly", "rows": None,
            "min_date": "", "max_date": "", "missing_cells": None, "duplicate_dates": None,
            "vintage_status": "HISTORICAL_CURRENT_COMPILATION; original monthly publication vintages unverified",
            "release_timing": "monthly, exact first-release timestamps unverified",
            "license": "WSTS copyright; free download, reproduction/redistribution requires written permission",
            "qc_note": "official XLSX kept byte-for-byte; workbook interpretation deferred to manual audit"}


def manifest_row(rec: dict) -> dict:
    fields = ["series_id", "status", "provider", "administrator", "source_url", "retrieval_url", "file", "sha256", "bytes",
              "rows", "min_date", "max_date", "frequency", "unit", "columns", "missing_cells", "duplicate_dates", "invalid_dates",
              "retrieved_at_utc", "http_status", "vintage_status", "release_timing", "license", "qc_note", "error"]
    return {k:rec.get(k, "") for k in fields}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if BASE not in run.parents or run == BASE: raise ValueError("run-dir must be a child of research_C/phase0_raw_audit")
    run.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        legacy = existing_audit(run)
        plan = {"mode":"DRY_RUN", "legacy_files":len(legacy), "yahoo":YAHOO,
                "fred_to_collect":list(FRED), "fred_license_hold":FRED_HELD,
                "wsts_direct_xlsx":WSTS_URL, "start":"2010-01-01", "no_existing_raw_writes":True,
                "script_sha256":sha_file(Path(__file__))}
        (run / "DRY_RUN.json").write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(plan,ensure_ascii=False)); return
    if not (run / "DRY_RUN.json").exists(): raise RuntimeError("dry-run must complete first")
    before = protected_hashes()
    out = run / "new_raw"; out.mkdir(exist_ok=True)
    # Keep yfinance's SQLite timezone/cookie caches inside this isolated run.
    import yfinance as yf
    yf.cache.set_cache_location(str(run / "yfinance_cache"))
    rows = []
    for ident,symbol in YAHOO.items():
        try: rows.append(collect_yahoo(symbol,ident,out))
        except Exception as ex: rows.append({"series_id":symbol,"status":"FAILED","provider":"Yahoo Finance via yfinance",
                                           "source_url":f"https://finance.yahoo.com/quote/{symbol}/history/","error":repr(ex)})
    for ident,meta in FRED.items():
        try: rows.append(collect_fred(ident,meta,out))
        except Exception as ex: rows.append({"series_id":ident,"status":"FAILED","provider":"FRED",
                                           "source_url":f"https://fred.stlouisfed.org/series/{ident}","error":repr(ex)})
    for ident,reason in FRED_HELD.items():
        rows.append({"series_id":ident,"status":"LICENSE_HOLD","provider":"FRED / Nasdaq",
                     "source_url":f"https://fred.stlouisfed.org/series/{ident}","license":reason})
    try: rows.append(collect_wsts(out))
    except Exception as ex: rows.append({"series_id":"WSTS historical billings","status":"FAILED","provider":"WSTS",
                                        "source_url":WSTS_URL,"error":repr(ex)})
    with (run / "collection_manifest.csv").open("w",encoding="utf-8",newline="") as f:
        table=[manifest_row(r) for r in rows]
        w=csv.DictWriter(f,fieldnames=list(table[0])); w.writeheader(); w.writerows(table)
    (run / "collection_details.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    after = protected_hashes()
    mismatches = [p for p,h in before.items() if after.get(p)!=h]
    added=sorted(set(after)-set(before))
    protect={"checked":len(before),"mismatches":mismatches,"added":added,
             "before_digest":hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
             "after_digest":hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest()}
    (run / "protected_inputs_qc.json").write_text(json.dumps(protect,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"statuses":{k:sum(r["status"]==k for r in rows) for k in sorted({r["status"] for r in rows})},
                      "protected_checked":len(before),"protected_mismatches":len(mismatches),"run_dir":str(run)},ensure_ascii=False))
    if mismatches or added: raise AssertionError("protected inputs changed")


if __name__ == "__main__": main()
