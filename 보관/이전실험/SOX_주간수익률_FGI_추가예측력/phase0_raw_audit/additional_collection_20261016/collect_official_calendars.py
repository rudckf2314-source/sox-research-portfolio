"""Research C Phase 0c: preserve official FOMC calendar pages and normalize meetings.

Usage: python collect_official_calendars.py --dry-run | --collect
Only the Federal Reserve public HTML is downloaded. BLS/AAII access denials
are recorded in the audit; this script does not attempt to evade them.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
DATASET = RAW / "33_fomc_calendar"
ORIGINAL = DATASET / "source_original"
BASE = "https://www.federalreserve.gov"
MAIN = BASE + "/monetarypolicy/fomccalendars.htm"
TODAY = date(2026, 10, 16)
HEADERS = {"User-Agent": "research-data-audit/1.0 (noncommercial academic source audit)"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def protected_files() -> list[Path]:
    return sorted(p for d in RAW.iterdir() if d.is_dir() and re.match(r"^(0[1-9]|[12][0-9]|3[0-2])_", d.name)
                  for p in d.rglob("*") if p.is_file())


def snapshot() -> dict[str, str]:
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in protected_files()}


def download(url: str) -> tuple[bytes, dict]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    if "text/html" not in r.headers.get("content-type", "").lower():
        raise ValueError(f"Expected HTML: {url}")
    if "Access Denied" in r.text[:2000]:
        raise ValueError(f"Access denied: {url}")
    return r.content, {"url": url, "http_status": r.status_code,
                       "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                       "headers": dict(r.headers), "sha256": hashlib.sha256(r.content).hexdigest()}


def parse_date(year: int, month: str, day: int) -> str:
    number = next((i for i in range(1, 13) if date(2000, i, 1).strftime("%B").lower().startswith(month.lower()[:3])), None)
    if number is None:
        raise ValueError(f"Unknown month: {month}")
    return date(year, number, day).isoformat()


def statement_url(panel) -> str:
    for a in panel.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/newsevents/pressreleases/monetary\d{8}[a-z]?\.htm$|/newsevents/press/monetary/\d{8}[a-z]?\.htm$", href, re.I):
            return urljoin(BASE, href)
    return ""


def statement_date_from_url(url: str) -> str:
    m = re.search(r"(?:monetary|/)\s*(20\d{6})[a-z]?\.htm$", url, re.I)
    return datetime.strptime(m[1], "%Y%m%d").date().isoformat() if m else ""


def historical_rows(year: int, html: bytes, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for heading in soup.find_all("h5"):
        label = heading.get_text(" ", strip=True)
        m = re.match(r"([A-Za-z/]+)\s+(\d{1,2})(?:-(\d{1,2}))?\s+(.+?)\s+-\s+" + str(year) + r"$", label)
        cross = re.match(r"([A-Za-z]+)\s+(\d{1,2})-([A-Za-z]+)\s+(\d{1,2})\s+(.+?)\s+-\s+" + str(year) + r"$", label)
        if not m and not cross:
            continue
        panel = heading.find_parent("div", class_="panel")
        if panel is None:
            continue
        if cross:
            month1, day1, month2, day2, kind = cross.groups()
            start, end = parse_date(year, month1, int(day1)), parse_date(year, month2, int(day2))
        else:
            month, day1, day2, kind = m.groups()
            months = month.split("/")
            start = parse_date(year, months[0], int(day1))
            end = parse_date(year, months[-1], int(day2 or day1))
        stmt = statement_url(panel)
        out.append({"meeting_start_date": start, "meeting_end_date": end,
                    "statement_date": statement_date_from_url(stmt), "statement_url": stmt,
                    "meeting_type": kind.lower().replace(" ", "_"),
                    "scheduled_or_unscheduled": "UNSCHEDULED" if "unscheduled" in kind.lower() else "CANCELLED" if "cancelled" in kind.lower() else "UNVERIFIED",
                    "actual_release_datetime_et": "", "release_time_status": "UNKNOWN",
                    "historical_visibility_status": "CURRENT_ARCHIVE_ONLY",
                    "source_url": source_url, "source_heading": label})
    return out


def recent_rows(year: int, html: bytes) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    panel = next((p for p in soup.select("div.panel.panel-default")
                  if p.find(string=re.compile(rf"\b{year} FOMC Meetings\b"))), None)
    if panel is None:
        raise ValueError(f"No panel for {year}")
    out = []
    for row in panel.select("div.fomc-meeting"):
        month_el = row.select_one(".fomc-meeting__month")
        day_el = row.select_one(".fomc-meeting__date")
        if month_el is None or day_el is None:
            continue
        month = month_el.get_text(" ", strip=True)
        days = re.match(r"(\d{1,2})(?:-(\d{1,2}))?", day_el.get_text(" ", strip=True))
        if not days:
            continue
        months = month.split("/")
        start = parse_date(year, months[0], int(days[1]))
        end = parse_date(year, months[-1], int(days[2] or days[1]))
        stmt = statement_url(row)
        out.append({"meeting_start_date": start, "meeting_end_date": end,
                    "statement_date": statement_date_from_url(stmt), "statement_url": stmt,
                    "meeting_type": "meeting", "scheduled_or_unscheduled": "UNVERIFIED",
                    "actual_release_datetime_et": "", "release_time_status": "UNKNOWN",
                    "historical_visibility_status": "CURRENT_ARCHIVE_ONLY",
                    "source_url": MAIN, "source_heading": f"{month} {day_el.get_text(' ', strip=True)} {year}"})
    return out


def main() -> None:
    arg = argparse.ArgumentParser()
    arg.add_argument("--dry-run", action="store_true")
    arg.add_argument("--collect", action="store_true")
    arg.add_argument("--rebuild", action="store_true", help="Rebuild only this run's derived CSV from saved official HTML")
    a = arg.parse_args()
    if sum([a.dry_run, a.collect, a.rebuild]) != 1:
        arg.error("choose exactly one mode")
    RUN.mkdir(parents=True, exist_ok=True)
    before = snapshot()
    (RUN / "PROTECTED_INPUT_HASHES_BEFORE.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    urls = [BASE + f"/monetarypolicy/fomchistorical{year}.htm" for year in range(2010, 2021)] + [MAIN]
    if not a.rebuild and DATASET.exists() and any(DATASET.iterdir()):
        raise FileExistsError(f"Existing dataset; refusing overwrite: {DATASET}")
    plan = {"mode": "dry-run" if a.dry_run else "collect", "urls": urls,
            "dataset": str(DATASET), "protected_file_count": len(before)}
    if a.dry_run:
        (RUN / "DRY_RUN.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        print(json.dumps(plan, indent=2))
        return
    raw_pages, request_log = {}, []
    for year, url in [(y, BASE + f"/monetarypolicy/fomchistorical{y}.htm") for y in range(2010, 2021)] + [(0, MAIN)]:
        if a.rebuild:
            source = ORIGINAL / ("fomccalendars_original.html" if year == 0 else f"fomchistorical{year}_original.html")
            content = source.read_bytes()
            meta = {"url": url, "http_status": 200, "retrieved_at_utc": "preserved_original",
                    "headers": {}, "sha256": sha(source)}
        else:
            content, meta = download(url)
        raw_pages[year] = content
        request_log.append(meta)
        print(year or "main", meta["http_status"], len(content), flush=True)
    rows = []
    for year in range(2010, 2021):
        rows.extend(historical_rows(year, raw_pages[year], BASE + f"/monetarypolicy/fomchistorical{year}.htm"))
    for year in range(2021, 2027):
        rows.extend(recent_rows(year, raw_pages[0]))
    rows = [r for r in rows if r["meeting_start_date"] <= TODAY.isoformat()]
    rows.sort(key=lambda r: (r["meeting_start_date"], r["meeting_end_date"]))
    keys = [(r["meeting_start_date"], r["meeting_end_date"], r["meeting_type"]) for r in rows]
    if not rows or len(keys) != len(set(keys)):
        raise ValueError("Empty/duplicate FOMC rows; no RAW saved")
    if not any(r["meeting_start_date"].startswith("2011") for r in rows):
        raise ValueError("2011 missing; no RAW saved")
    if not a.rebuild:
        ORIGINAL.mkdir(parents=True)
        for year, content in raw_pages.items():
            (ORIGINAL / ("fomccalendars_original.html" if year == 0 else f"fomchistorical{year}_original.html")).write_bytes(content)
    dest = DATASET / "33_fomc_calendar_RAW_20100101_20261016.csv"
    with dest.open("w", newline="", encoding="utf-8") as f:
        f.write("# SOURCE | dataset_id=33_fomc_calendar | provider=Federal Reserve Board | administrator=Federal Open Market Committee | source_url=" + MAIN + " | source_pages=2010-2020 historical;2021-2026 calendar | start_date=2010-01-01 | end_date=2026-10-16 | definition=official meeting calendar and linked statement dates; release time unknown unless separately verified | retrieved_at_utc=" + datetime.now(timezone.utc).isoformat() + "\n")
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    after = snapshot()
    if before != after:
        raise RuntimeError("Protected RAW changed")
    (RUN / "PROTECTED_INPUT_HASHES_AFTER.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
    if not a.rebuild:
        (RUN / "FOMC_REQUEST_LOG.json").write_text(json.dumps(request_log, indent=2), encoding="utf-8")
    qc = {"rows": len(rows), "min_start": rows[0]["meeting_start_date"], "max_start": rows[-1]["meeting_start_date"],
          "statement_links": sum(bool(r["statement_url"]) for r in rows),
          "missing_statement_links": sum(not bool(r["statement_url"]) for r in rows),
          "duplicate_meetings": len(keys)-len(set(keys)), "protected_changed": before != after,
          "output_file": str(dest), "output_sha256": sha(dest),
          "source_original_count": len(raw_pages)}
    (RUN / "FOMC_COLLECTION_QC.json").write_text(json.dumps(qc, indent=2), encoding="utf-8")
    print(json.dumps(qc, indent=2))


if __name__ == "__main__":
    main()
