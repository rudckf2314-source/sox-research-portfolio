"""Check official linked FOMC statements for explicit release times.

This enriches only dataset 33 created by this run. It never infers a time from
normal FOMC practice or from the date on a calendar page.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
DATASET = ROOT / "data" / "raw" / "33_fomc_calendar"
CSV = DATASET / "33_fomc_calendar_RAW_20100101_20261016.csv"
DEST = DATASET / "source_original" / "statements"
UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")
HEADERS = {"User-Agent": "research-data-audit/1.0 (noncommercial academic source audit)"}


def main() -> None:
    with CSV.open(encoding="utf-8") as f:
        metadata = f.readline()
    rows = pd.read_csv(CSV, comment="#", dtype=str, keep_default_na=False).to_dict("records")
    DEST.mkdir(parents=True, exist_ok=True)
    log = []
    for i, row in enumerate(rows, 1):
        url = row["statement_url"]
        if not url:
            continue
        filename = Path(urlparse(url).path).name
        path = DEST / filename
        cache_hit = path.exists()
        if not path.exists():
            try:
                response = requests.get(url, headers=HEADERS, timeout=30)
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", "").lower() or "Access Denied" in response.text[:2000]:
                    raise ValueError("Expected public statement HTML")
                path.write_bytes(response.content)
                time.sleep(0.5)
            except Exception as e:
                log.append({"url": url, "status": "ERROR", "error": str(e)[:200]})
                print(i, "ERROR", flush=True)
                continue
        html = path.read_bytes()
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        m = re.search(r"For release at\s+(\d{1,2}):(\d{2})\s*([ap])\.?m\.?\s*(EDT|EST)", text, re.I)
        if m:
            hour = int(m[1]) % 12 + (12 if m[3].lower() == "p" else 0)
            dt = datetime.fromisoformat(row["statement_date"]).replace(hour=hour, minute=int(m[2]), tzinfo=ET)
            if dt.strftime("%Z") != m[4].upper():
                log.append({"url": url, "status": "TIMEZONE_MISMATCH", "source_text": m.group(0)})
                row["release_time_status"] = "UNKNOWN_TIMEZONE_MISMATCH"
            else:
                row["actual_release_datetime_et"] = dt.isoformat()
                row["release_time_status"] = "VERIFIED_OFFICIAL_STATEMENT"
        else:
            row["release_time_status"] = "UNKNOWN_IMMEDIATE_OR_UNSTATED"
        log.append({"url": url, "status": row["release_time_status"], "original_path": str(path),
                    "sha256": hashlib.sha256(html).hexdigest(),
                    "first_saved_at_utc": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                    "checked_at_utc": datetime.now(UTC).isoformat(), "cache_hit": cache_hit})
        if i % 20 == 0:
            print(i, "processed", flush=True)
    tmp = CSV.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        f.write(metadata)
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    tmp.replace(CSV)
    (RUN / "FOMC_STATEMENT_REQUEST_LOG.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(json.dumps({"statement_links": sum(bool(r["statement_url"]) for r in rows),
                      "verified_times": sum(r["release_time_status"] == "VERIFIED_OFFICIAL_STATEMENT" for r in rows),
                      "unverified_times": sum(r["release_time_status"] != "VERIFIED_OFFICIAL_STATEMENT" for r in rows),
                      "errors": sum(r["status"] == "ERROR" for r in log)}, indent=2))


if __name__ == "__main__":
    main()
