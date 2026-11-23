"""Phase 0d public-source fetch only. No X/Y, alignment, returns or model work.

Run --dry-run before --collect. Original HTTP bodies are kept in download_cache
until a separate parser validates and publishes new RAW directories.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
CACHE = RUN / "download_cache"
FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
SPECS = [
    {"dataset_id": "43_ff49_industry_daily", "kind": "french", "symbol": "49_Industry_Portfolios_daily", "filename": "49_Industry_Portfolios_daily_CSV.zip", "url": FRENCH + "ftp/49_Industry_Portfolios_daily_CSV.zip"},
    {"dataset_id": "44_ff5_daily", "kind": "french", "symbol": "F-F_Research_Data_5_Factors_2x3_daily", "filename": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip", "url": FRENCH + "ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"},
    {"dataset_id": "45_ff_momentum_daily", "kind": "french", "symbol": "F-F_Momentum_Factor_daily", "filename": "F-F_Momentum_Factor_daily_CSV.zip", "url": FRENCH + "ftp/F-F_Momentum_Factor_daily_CSV.zip"},
    {"dataset_id": "46_soxx", "kind": "yahoo", "symbol": "SOXX", "url": "https://finance.yahoo.com/quote/SOXX/history/"},
    {"dataset_id": "47_smh", "kind": "yahoo", "symbol": "SMH", "url": "https://finance.yahoo.com/quote/SMH/history/"},
    *[{"dataset_id": f"{number}_{symbol.lower()}", "kind": "fred", "symbol": symbol, "filename": symbol + ".csv",
       "url": f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={symbol}&cosd=2010-01-01&coed=2026-10-16"}
      for number, symbol in enumerate(["ICSA", "CPIAUCSL", "CPILFESL", "PAYEMS", "UNRATE"], 48)],
]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def save(name, data):
    (RUN / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def prepare():
    RUN.mkdir(parents=True, exist_ok=True)
    if (RUN / "PROTECTED_INPUT_HASHES.json").exists():
        raise FileExistsError("Phase 0d inventory already exists; refusing overwrite")
    roots = ["data/raw", "freeze", "data/metadata", "stockcharts", "config", "scripts"]
    protected = {p.relative_to(ROOT).as_posix(): sha(p) for relative in roots for p in (ROOT / relative).rglob("*") if p.is_file()}
    inventory = []
    for p in sorted((ROOT / "data/raw").glob("*/*RAW*.csv")):
        with p.open(encoding="utf-8-sig") as f:
            first = f.readline().strip()
        meta = dict(t.strip().split("=", 1) for t in first.split("|")[1:] if "=" in t)
        inventory.append({"dataset_id": p.parent.name, "file": p.relative_to(ROOT).as_posix(), "sha256": sha(p),
                          "provider": meta.get("provider"), "symbol": meta.get("series_or_symbol", meta.get("source_symbols", ""))})
    maximum = max(int(p.name.split("_", 1)[0]) for p in (ROOT / "data/raw").iterdir() if p.is_dir())
    assert maximum == 42, f"RAW numbering changed: max={maximum}; review before collection"
    for spec in SPECS:
        assert not (ROOT / "data/raw" / spec["dataset_id"]).exists()
        if spec["kind"] in {"fred", "yahoo"}:
            existing = [r for r in inventory if r["symbol"] == spec["symbol"]]
            if existing:
                raise ValueError(f"Existing identical source must be reused: {spec['symbol']}: {existing}")
    versions = {p: importlib.metadata.version(p) for p in ["pandas", "numpy", "requests", "yfinance", "curl_cffi"]}
    save("ENVIRONMENT.json", {"python": platform.python_version(), "executable": os.sys.executable, "packages": versions})
    save("PROTECTED_INPUT_HASHES.json", protected)
    save("EXISTING_RAW_INVENTORY.json", inventory)
    save("COLLECTION_PLAN.json", {"existing_raw_datasets": len(inventory), "max_number": maximum,
                                   "requested_start_date": "2010-01-01", "candidate_count": len(SPECS), "sources": SPECS})
    print(json.dumps({"mode": "dry-run", "existing_raw_datasets": len(inventory), "protected_files": len(protected), "new_sources": [s["dataset_id"] for s in SPECS]}), flush=True)


def fetch_http(spec):
    folder = CACHE / spec["dataset_id"]
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / spec["filename"]
    if dest.exists():
        return {"status": "CACHED", "file": str(dest.relative_to(ROOT)), "sha256": sha(dest)}
    errors = []
    for attempt in range(1, 4):
        try:
            response = requests.get(spec["url"], timeout=(12, 60), headers={"User-Agent": "Research-C-Phase0d/1.0 (academic data availability audit)"})
            record = {"attempt": attempt, "http_status": response.status_code, "request_url": spec["url"], "response_url": response.url,
                      "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "headers": dict(response.headers), "bytes": len(response.content)}
            if response.status_code in {401, 403}:
                return {"status": "ACCESS_DENIED", "request": record, "errors": errors}
            response.raise_for_status()
            if spec["kind"] == "french":
                if not response.content.startswith(b"PK"):
                    raise ValueError("HTTP response is not a ZIP; may be HTML challenge")
            elif not response.content.lstrip().startswith((b"observation_date,", b"DATE,")):
                raise ValueError("FRED response is not expected CSV; refusing HTML or unsupported format")
            dest.write_bytes(response.content)
            record.update(file=str(dest.relative_to(ROOT)), sha256=sha(dest))
            (folder / "HTTP_RESPONSE_METADATA.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            return {"status": "FETCHED", **record, "errors": errors}
        except Exception as exc:
            errors.append({"attempt": attempt, "type": type(exc).__name__, "message": str(exc)[:300]})
            if attempt < 3:
                time.sleep([2, 5][attempt - 1])
    return {"status": "ERROR", "errors": errors}


def fetch_yahoo(spec):
    import yfinance as yf
    from curl_cffi.requests import Session
    from zoneinfo import ZoneInfo

    folder = CACHE / spec["dataset_id"]
    folder.mkdir(parents=True, exist_ok=True)
    end = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    raw_responses = []

    class RecordingSession(Session):
        def request(self, method, url, *args, **kwargs):
            response = super().request(method, url, *args, **kwargs)
            if "/v8/finance/chart/" in str(url):
                body = response.content
                number = len(raw_responses) + 1
                path = folder / f"{spec['symbol']}_CHART_HTTP_{number:03d}.json"
                path.write_bytes(body)
                params = kwargs.get("params", {})
                params = {k: v for k, v in params.items() if str(k).lower() not in {"crumb", "token"}} if isinstance(params, dict) else "not recorded"
                raw_responses.append({"method": method, "url": str(url).split("?", 1)[0], "params_without_tokens": params,
                                      "http_status": response.status_code, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                                      "content_type": response.headers.get("content-type"), "file": str(path.relative_to(ROOT)), "sha256": sha(path)})
            return response

    errors = []
    yf.cache.set_cache_location(str(RUN / "yfinance_cache"))
    for attempt in range(1, 4):
        try:
            with RecordingSession(impersonate="chrome") as session:
                history = yf.Ticker(spec["symbol"], session=session).history(start="2010-01-01", end=end, interval="1d",
                    auto_adjust=False, actions=True, repair=False, back_adjust=False, keepna=True)
            required = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
            if history.empty or not all(c in history.columns for c in required):
                raise ValueError(f"Empty or unsupported yfinance history: columns={list(history.columns)}")
            snapshot_path = folder / f"{spec['symbol']}_YFINANCE_RETURN.csv"
            history.to_csv(snapshot_path, float_format="%.17g")
            metadata = {"symbol": spec["symbol"], "requested_start": "2010-01-01", "end_exclusive_et_date": end,
                        "current_et_date_excluded": True, "auto_adjust": False, "actions": True, "repair": False,
                        "fetched_at_utc": datetime.now(timezone.utc).isoformat(), "rows": len(history),
                        "index_timezone": str(history.index.tz), "client_snapshot": str(snapshot_path.relative_to(ROOT)),
                        "client_snapshot_sha256": sha(snapshot_path), "chart_http_responses": raw_responses}
            (folder / "YFINANCE_FETCH_METADATA.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
            return {"status": "FETCHED", **metadata, "errors": errors}
        except Exception as exc:
            errors.append({"attempt": attempt, "type": type(exc).__name__, "message": str(exc)[:300]})
            if attempt < 3:
                time.sleep([2, 5][attempt - 1])
    (folder / "YFINANCE_FETCH_ERRORS.json").write_text(json.dumps({"errors": errors, "chart_http_responses": raw_responses}, indent=2, default=str), encoding="utf-8")
    return {"status": "ERROR", "errors": errors, "chart_http_responses": raw_responses}


def collect():
    if not (RUN / "COLLECTION_PLAN.json").exists():
        raise RuntimeError("Run --dry-run before collecting")
    CACHE.mkdir(exist_ok=True)
    results = {}
    if (RUN / "FETCH_RESULTS.json").exists():
        results = json.loads((RUN / "FETCH_RESULTS.json").read_text(encoding="utf-8"))
    for spec in SPECS:
        if results.get(spec["dataset_id"], {}).get("status") in {"FETCHED", "CACHED"}:
            print(spec["dataset_id"], "already fetched", flush=True)
            continue
        print(spec["dataset_id"], "fetching", flush=True)
        result = fetch_yahoo(spec) if spec["kind"] == "yahoo" else fetch_http(spec)
        results[spec["dataset_id"]] = {"specification": spec, **result}
        save("FETCH_RESULTS.json", results)
        print(spec["dataset_id"], result["status"], flush=True)
    print(json.dumps({k: r["status"] for k, r in results.items()}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--collect", action="store_true")
    a = p.parse_args()
    if a.dry_run == a.collect:
        p.error("Choose exactly one of --dry-run and --collect")
    prepare() if a.dry_run else collect()
