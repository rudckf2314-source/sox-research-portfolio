"""Create versioned 2011-01-01..2026-10-09 RAW files for existing US series.

The older files are retained byte-for-byte so D1/W1 can reproduce their results.
No StockCharts, CNN, KODEX or downstream dataset is modified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RUN = ROOT / "data" / "metadata" / "RAW_REFRESH_20261009"
START = "2011-01-01"
END_EXCLUSIVE = "2026-10-10"
CUTOFF = "2026-10-09"
YAHOO = {
    "02_sox": ("^SOX", "Nasdaq", "PHLX Semiconductor Sector Index"),
    "04_sp500": ("^GSPC", "S&P Dow Jones Indices", "S&P 500 Price Index"),
    "09_ief": ("IEF", "BlackRock / iShares", "iShares 7-10 Year Treasury Bond ETF"),
    "10_hyg": ("HYG", "BlackRock / iShares", "iShares iBoxx High Yield Corporate Bond ETF"),
}
FRED = {
    "03_usdkrw": ("DEXKOUS", "Federal Reserve Board", "South Korean Won to One U.S. Dollar Spot Exchange Rate"),
    "08_vix": ("VIXCLS", "Cboe Global Markets", "CBOE Volatility Index"),
}
PRICE_COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def old_files() -> dict[str, Path]:
    result = {}
    for dataset_id in list(YAHOO) + list(FRED):
        paths = list((RAW / dataset_id).glob(f"{dataset_id}_RAW_20110101_20261007.csv"))
        if len(paths) != 1:
            raise FileNotFoundError(f"Expected one original RAW: {dataset_id}")
        result[dataset_id] = paths[0]
    return result


def read_and_check(frame: pd.DataFrame, date_column: str, values: list[str], series: str) -> dict:
    if date_column not in frame or not set(values).issubset(frame.columns):
        raise ValueError(f"Missing required columns for {series}: {frame.columns.tolist()}")
    dates = pd.to_datetime(frame[date_column], errors="raise")
    if frame.empty or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError(f"Empty, duplicate or nonascending dates: {series}")
    if dates.min().strftime("%Y-%m-%d") != "2011-01-03" or dates.max().strftime("%Y-%m-%d") != CUTOFF:
        raise ValueError(f"Unexpected range: {series}: {dates.min()}..{dates.max()}")
    if not {"2026-10-07", "2026-10-08", "2026-10-09"}.issubset(set(dates.dt.strftime("%Y-%m-%d"))):
        raise ValueError(f"Missing 7/8/9 October observations: {series}")
    numeric = frame[values].apply(pd.to_numeric, errors="coerce")
    return {"rows": len(frame), "min_date": str(dates.min().date()),
            "max_date": str(dates.max().date()), "missing_cells": int(numeric.isna().sum().sum()),
            "duplicate_dates": int(dates.duplicated().sum()), "columns": list(frame.columns)}


def fetch_yahoo(dataset_id: str, series: str) -> tuple[pd.DataFrame, dict]:
    history = yf.Ticker(series).history(start=START, end=END_EXCLUSIVE, interval="1d",
                                        auto_adjust=False, actions=False, repair=False)
    if history.empty or not set(PRICE_COLS).issubset(history.columns):
        raise ValueError(f"Yahoo response empty/incomplete: {series}")
    frame = history.reset_index()
    frame["Date"] = pd.to_datetime(frame["Date"]).dt.strftime("%Y-%m-%d")
    frame = frame[["Date"] + PRICE_COLS]
    qc = read_and_check(frame, "Date", PRICE_COLS, series)
    if qc["missing_cells"]:
        raise ValueError(f"Unexpected Yahoo missing values: {series}: {qc['missing_cells']}")
    if (frame[["Open", "High", "Low", "Close", "Adj Close"]] <= 0).any().any():
        raise ValueError(f"Nonpositive price in {series}")
    source = RUN / "source_downloads" / f"{dataset_id}_{series.lstrip('^')}_20110101_20261009_yfinance.csv"
    if source.exists():
        raise FileExistsError(source)
    frame.to_csv(source, index=False)
    return frame, {**qc, "source_file": source.relative_to(ROOT).as_posix(),
                   "source_sha256": sha(source), "source_url": f"https://finance.yahoo.com/quote/{series}/history/",
                   "retrieved_at_utc": now(), "source_format": "yfinance serialized response; original HTTP bytes unavailable"}


def fetch_fred(dataset_id: str, series: str) -> tuple[pd.DataFrame, dict]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={START}&coed={CUTOFF}"
    source = RUN / "source_downloads" / f"{dataset_id}_{series}_20110101_20261009_FRED_original.csv"
    headers = RUN / "source_downloads" / f"{dataset_id}_{series}_response_headers.txt"
    if source.exists() or headers.exists():
        raise FileExistsError(f"FRED download target exists: {source}")
    result = subprocess.run(["curl.exe", "--location", "--fail", "--max-time", "45",
                             "--retry", "3", "--retry-delay", "2", "--silent", "--show-error",
                             "--dump-header", str(headers), "--output", str(source), url],
                            capture_output=True, text=True)
    if result.returncode:
        source.unlink(missing_ok=True)
        raise RuntimeError(f"FRED curl exit {result.returncode}: {result.stderr.strip()}")
    frame = pd.read_csv(source)
    if frame.columns[0] not in ("observation_date", "DATE") or series not in frame:
        raise ValueError(f"Unexpected FRED columns: {frame.columns.tolist()}")
    frame = frame.rename(columns={frame.columns[0]: "Date"})
    qc = read_and_check(frame, "Date", [series], series)
    return frame, {**qc, "source_file": source.relative_to(ROOT).as_posix(),
                   "source_sha256": sha(source), "source_url": f"https://fred.stlouisfed.org/series/{series}",
                   "retrieval_url": url, "response_headers_file": headers.relative_to(ROOT).as_posix(),
                   "retrieved_at_utc": now(), "source_format": "official FRED CSV original bytes"}


def compare_old(old_path: Path, fresh: pd.DataFrame, series: str) -> dict:
    old = pd.read_csv(old_path, comment="#")
    joined = old.merge(fresh, on="Date", suffixes=("_old", "_new"))
    old_cols = [c for c in old.columns if c != "Date"]
    differences = {}
    for column in old_cols:
        left = pd.to_numeric(joined[f"{column}_old"], errors="coerce")
        right = pd.to_numeric(joined[f"{column}_new"], errors="coerce")
        same = (left.eq(right) | (left.isna() & right.isna()))
        differences[column] = int((~same).sum())
    oct7_old = old.loc[old.Date == "2026-10-07"].to_dict("records")
    oct7_new = fresh.loc[fresh.Date == "2026-10-07"].to_dict("records")
    return {"overlap_rows": len(joined), "original_rows": len(old),
            "original_min_date": old.Date.min(), "original_max_date": old.Date.max(),
            "column_value_difference_count": differences,
            "old_2026_10_07": oct7_old, "new_2026_10_07": oct7_new}


def make_raw(dataset_id: str, series: str, administrator: str, description: str,
             fresh: pd.DataFrame, info: dict, old_path: Path) -> tuple[Path, dict]:
    path = RAW / dataset_id / f"{dataset_id}_RAW_20110101_20261009.csv"
    if path.exists():
        raise FileExistsError(path)
    provider = "Yahoo Finance" if dataset_id in YAHOO else "FRED"
    notes = "full-period re-download; auto_adjust=False; old 2026-10-07 intraday row replaced by later vendor observation" if dataset_id in YAHOO else "full-period official CSV; observation date is not H.10 release time" if series == "DEXKOUS" else "full-period official CSV; market-holiday missing cells retained"
    source_line = (f"# SOURCE | dataset_id={dataset_id} | provider={provider} | administrator={administrator} "
                   f"| source_url={info['source_url']} | series_or_symbol={series} | start_date={START} "
                   f"| end_date={CUTOFF} | retrieved_at_utc={info['retrieved_at_utc']} "
                   f"| dataset_name={description} | frequency=daily | source_file={info['source_file']} "
                   f"| source_sha256={info['source_sha256']} | previous_file={old_path.relative_to(ROOT).as_posix()} "
                   f"| notes={notes}\n")
    if dataset_id in YAHOO:
        # Exactly preserve the newly serialized vendor columns/values after the metadata line.
        body = (ROOT / info["source_file"]).read_bytes()
    else:
        original = (ROOT / info["source_file"]).read_bytes()
        expected = f"observation_date,{series}".encode()
        if original.startswith(expected):
            body = b"Date," + series.encode() + original[len(expected):]
        elif original.startswith(f"DATE,{series}".encode()):
            body = b"Date," + series.encode() + original[len(f"DATE,{series}"):]
        else:
            raise ValueError(f"FRED source header unexpected for {series}")
    return path, {"payload": source_line.encode("utf-8") + body,
                  "source_line": source_line.rstrip("\n")}


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--collect", action="store_true")
    args = ap.parse_args()
    old = old_files()
    if RUN.exists() and args.dry_run:
        raise FileExistsError(f"Audit run already exists: {RUN}")
    if args.dry_run:
        plan = {"target_cutoff": CUTOFF, "old_files": {k: v.relative_to(ROOT).as_posix() for k,v in old.items()},
                "old_hashes": {k: sha(v) for k,v in old.items()},
                "new_files": [f"data/raw/{k}/{k}_RAW_20110101_20261009.csv" for k in old],
                "source_symbols": {k:v[0] for k,v in {**YAHOO, **FRED}.items()},
                "stockcharts_05_06_07": "not collected; originals lack 2026-10-08/09"}
        RUN.mkdir(parents=True)
        (RUN / "DRY_RUN.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({"mode":"dry-run","old":len(old),"new_planned":len(old),"run":str(RUN)},ensure_ascii=False))
        return
    plan_path = RUN / "DRY_RUN.json"
    if not plan_path.exists():
        raise RuntimeError("Run --dry-run first")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for dataset_id, path in old.items():
        if sha(path) != plan["old_hashes"][dataset_id]:
            raise AssertionError(f"Original changed since dry-run: {path}")
    (RUN / "source_downloads").mkdir(exist_ok=True)
    yf.cache.set_cache_location(str(RUN / "yfinance_cache"))
    collected = []
    failures = []
    for dataset_id, (series, administrator, description) in {**YAHOO, **FRED}.items():
        try:
            frame, info = fetch_yahoo(dataset_id, series) if dataset_id in YAHOO else fetch_fred(dataset_id, series)
            comparison = compare_old(old[dataset_id], frame, series)
            output, payload = make_raw(dataset_id, series, administrator, description, frame, info, old[dataset_id])
            collected.append({"dataset_id":dataset_id,"series_id":series,"frame":frame,"info":info,
                              "comparison":comparison,"output":output,"payload":payload["payload"]})
        except Exception as exc:
            failures.append({"dataset_id":dataset_id,"series_id":series,"error":repr(exc)})
    if failures:
        (RUN / "COLLECTION_FAILURES.json").write_text(json.dumps(failures,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"status":"FAILED","failures":failures},ensure_ascii=False))
        return
    # All six sources must pass before any new canonical RAW is written.
    for item in collected:
        output = item["output"]
        with output.open("xb") as f:
            f.write(item["payload"])
    records = []
    for item in collected:
        output = item["output"]
        frame = pd.read_csv(output, comment="#")
        if len(frame) != item["info"]["rows"] or frame.Date.iloc[-1] != CUTOFF:
            raise AssertionError(f"Output validation failed: {output}")
        if sha(old[item["dataset_id"]]) != plan["old_hashes"][item["dataset_id"]]:
            raise AssertionError(f"Original changed: {old[item['dataset_id']]}")
        records.append({"dataset_id":item["dataset_id"],"series_id":item["series_id"],
                        "output_file":output.relative_to(ROOT).as_posix(), "output_sha256":sha(output),
                        "source_file":item["info"]["source_file"],"source_sha256":item["info"]["source_sha256"],
                        "source_url":item["info"]["source_url"],"rows":len(frame),
                        "min_date":frame.Date.iloc[0],"max_date":frame.Date.iloc[-1],
                        "missing_cells":int(frame.isna().sum().sum()),"duplicate_dates":int(frame.Date.duplicated().sum()),
                        "old_comparison":item["comparison"]})
    audit = {"status":"PASS","retrieved_at_utc":now(),"target_cutoff":CUTOFF,
             "original_6_hashes_unchanged":True,"new_files":records,
             "stockcharts_status":"05/06 source files stop 2026-10-07, 07 stops 2026-10-06; no 10/08–10/09 original; unchanged",
             "cnn_status":"existing CNN files unchanged; no verified 2026-10-09 observation"}
    (RUN / "RAW_REFRESH_QC.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","new_raw":len(records),"old_hashes_unchanged":True,
                      "run_dir":RUN.relative_to(ROOT).as_posix()},ensure_ascii=False))


if __name__ == "__main__":
    main()
