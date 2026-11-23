"""Archive TWSE public monthly Semiconductor Industry Index CSVs, without changing legacy data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = "https://www.twse.com.tw/indicesReport/EFTRI_HIST?response=csv&date={year:04d}{month:02d}15"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def months(first: tuple[int, int], last: tuple[int, int]):
    year, month = first
    while (year, month) <= last:
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def parse_original(path: Path, year: int, month: int) -> dict:
    # TWSE's public CSV is Big5/CP950 and uses ROC-calendar dates.
    text = path.read_bytes().decode("cp950")
    rows = list(csv.reader(text.splitlines()))
    observations = []
    for row in rows:
        if len(row) < 3:
            continue
        parts = row[0].strip().split("/")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            continue
        roc_year, mm, dd = map(int, parts)
        when = date(roc_year + 1911, mm, dd)
        if (when.year, when.month) != (year, month):
            raise ValueError(f"TWSE response month mismatch: {when} vs {year}-{month:02d}")
        value = float(row[2].replace(",", ""))
        if value <= 0:
            raise ValueError(f"nonpositive index {when}: {value}")
        observations.append((when.isoformat(), value))
    if not observations:
        raise ValueError("No dated semiconductor-index rows found")
    dates = [x[0] for x in observations]
    if len(set(dates)) != len(dates):
        raise ValueError("duplicate TWSE dates")
    return {"rows": len(dates), "min_date": min(dates), "max_date": max(dates),
            "duplicate_dates": 0, "missing_values": 0,
            "semiconductor_header": rows[1][2] if len(rows) > 1 and len(rows[1]) > 2 else ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--collect", action="store_true")
    args = ap.parse_args()
    run = args.run_dir.resolve()
    if BASE not in run.parents or run == BASE:
        raise ValueError("run-dir must be within research_C/phase0_raw_audit")
    run.mkdir(parents=True, exist_ok=True)
    last = (datetime.now().year, datetime.now().month)
    planned = list(months((2011, 1), last))
    plan_path = run / "TWSE_DRY_RUN.json"
    if args.dry_run:
        if plan_path.exists():
            raise FileExistsError(plan_path)
        plan_path.write_text(json.dumps({"source": SOURCE, "first": "2011-01", "last": f"{last[0]}-{last[1]:02d}",
                                         "months": len(planned), "original_format": "CP950 CSV with ROC dates",
                                         "script_sha256": digest(Path(__file__))}, indent=2) + "\n", encoding="utf-8")
        print(f"TWSE dry-run: {len(planned)} months")
        return
    if not plan_path.exists():
        raise RuntimeError("dry-run required")
    out = run / "twse_original_monthly"
    out.mkdir(exist_ok=True)
    records = []
    for idx, (year, month) in enumerate(planned, 1):
        url = SOURCE.format(year=year, month=month)
        target = out / f"TWSE_EFTRI_HIST_{year:04d}{month:02d}_original.csv"
        headers = out / f"TWSE_EFTRI_HIST_{year:04d}{month:02d}_headers.txt"
        rec = {"year_month": f"{year:04d}-{month:02d}", "source_url": url,
               "file": target.relative_to(BASE).as_posix(), "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            if target.exists():
                raise FileExistsError(target)
            result = subprocess.run(["curl.exe", "--location", "--fail", "--max-time", "30",
                                     "--retry", "2", "--retry-delay", "2", "--silent", "--show-error",
                                     "--dump-header", str(headers), "--output", str(target), url],
                                    capture_output=True, text=True)
            if result.returncode:
                target.unlink(missing_ok=True)
                raise RuntimeError(f"curl exit {result.returncode}: {result.stderr.strip()}")
            rec.update(parse_original(target, year, month))
            rec.update(status="COLLECTED", sha256=digest(target), bytes=target.stat().st_size,
                       http_status=200, unit="TWSE index points", frequency="daily trading session",
                       vintage_status="current archive; original daily publication vintage unverified")
        except Exception as exc:
            rec.update(status="FAILED", error=repr(exc))
        records.append(rec)
        if idx % 25 == 0 or idx == len(planned):
            print(f"TWSE {idx}/{len(planned)}; success={sum(r['status']=='COLLECTED' for r in records)}", flush=True)
        time.sleep(0.25)
    fields = ["year_month", "status", "source_url", "file", "rows", "min_date", "max_date",
              "duplicate_dates", "missing_values", "sha256", "bytes", "http_status",
              "unit", "frequency", "vintage_status", "retrieved_at_utc", "semiconductor_header", "error"]
    with (run / "TWSE_monthly_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows({k: rec.get(k, "") for k in fields} for rec in records)
    print(json.dumps({"months": len(records), "collected": sum(r["status"] == "COLLECTED" for r in records),
                      "failed": [r["year_month"] for r in records if r["status"] != "COLLECTED"]}))


if __name__ == "__main__":
    main()
