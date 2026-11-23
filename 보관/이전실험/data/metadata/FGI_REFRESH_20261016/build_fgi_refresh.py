"""Append only new GitHub/CNN FGI dates to the protected local history."""

import csv
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AUDIT_DIR = Path(__file__).resolve().parent
ORIGINAL = ROOT / "data/raw/11_cnn_fgi/CNN_FGI_FGI_2020_GAP_20110103_20261006 (1).csv"
GITHUB = AUDIT_DIR / "fear-greed_github_d31dc52e.csv"
OUTPUT = ROOT / "data/raw/11_cnn_fgi/11_cnn_fgi_RAW_20110101_20261015.csv"
COMMIT = "d31dc52e62a4b8e2033f3d0fe726665565f395ac"
URL = f"https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/{COMMIT}/fear-greed.csv"
FIELDS = ["Date", "Fear Greed", "Rating"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise ValueError(f"Unexpected columns: {path}: {reader.fieldnames}")
        rows = list(reader)
    dates = [row["Date"] for row in rows]
    if dates != sorted(set(dates)):
        raise ValueError(f"Unsorted or duplicate dates: {path}")
    for row in rows:
        datetime.strptime(row["Date"], "%Y-%m-%d")
        number = Decimal(row["Fear Greed"])
        if not number.is_finite() or not 0 <= number <= 100 or not row["Rating"]:
            raise ValueError(f"Invalid score or rating: {path}: {row}")
    return {row["Date"]: row for row in rows}


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    before = {str(path.relative_to(ROOT)): digest(path) for path in (ORIGINAL, GITHUB)}
    old = read(ORIGINAL)
    upstream = read(GITHUB)
    old_only = sorted(set(old) - set(upstream))
    new_only = sorted(set(upstream) - set(old))
    conflicts = [
        {"date": day, "local": old[day], "github": upstream[day]}
        for day in sorted(set(old) & set(upstream))
        if old[day]["Fear Greed"] != upstream[day]["Fear Greed"]
        or old[day]["Rating"] != upstream[day]["Rating"]
    ]
    if len(old) != 3962 or len(upstream) != 3947 or len(old_only) != 22:
        raise ValueError("Source coverage changed; review before refreshing")
    if len(new_only) != 7 or min(new_only) <= max(old) or max(new_only) != "2026-10-15":
        raise ValueError(f"Unexpected new dates: {new_only}")
    if len(conflicts) != 1 or conflicts[0]["date"] != "2026-10-06":
        raise ValueError(f"Unexpected overlapping revisions: {conflicts[:5]}")
    combined = {**old, **{day: upstream[day] for day in new_only}}
    retrieved = datetime.now(timezone.utc).isoformat()
    metadata = (
        "# SOURCE | dataset_id=11_cnn_fgi"
        " | provider=local verified history + whit3rabbit/fear-greed-data"
        " | administrator=CNN Fear & Greed Index (2021-02 onward historical scores via GitHub)"
        f" | source_url={URL}"
        f" | source_file={ORIGINAL.name};fear-greed_github_d31dc52e.csv"
        " | start_date=2011-01-01 | end_date=2026-10-15"
        f" | retrieved_at_utc={retrieved}"
        " | transformation=retain local rows through 2026-10-06 unchanged; append GitHub dates 2026-10-07 through 2026-10-15 only; no interpolation"
        " | overlap_discrepancy=2026-10-06 local score retained"
    )
    with OUTPUT.open("x", encoding="utf-8", newline="") as handle:
        handle.write(metadata + "\n")
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(combined[day] for day in sorted(combined))
    with OUTPUT.open("r", encoding="utf-8", newline="") as handle:
        assert handle.readline() == metadata + "\n"
        reader = csv.DictReader(handle)
        written = {row["Date"]: row for row in reader}
    if written != combined:
        raise AssertionError("Read-back values differ from planned rows")
    if any(digest(ROOT / relpath) != value for relpath, value in before.items()):
        raise AssertionError("Protected input changed")
    audit = {
        "status": "PASS_APPEND_ONLY_WITH_DOCUMENTED_CONFLICT",
        "github_commit": COMMIT,
        "github_commit_time_utc": "2026-10-16T00:58:29Z",
        "github_source_url": URL,
        "protected_input_sha256": before,
        "output": str(OUTPUT.relative_to(ROOT)),
        "output_sha256": digest(OUTPUT),
        "existing_rows": len(old), "github_rows": len(upstream),
        "output_rows": len(written),
        "min_date": min(written), "max_date": max(written),
        "new_dates": new_only,
        "local_only_2020_gap_dates": old_only,
        "overlap_conflicts": conflicts,
        "duplicate_dates": 0,
        "missing_cells": 0,
        "score_outside_0_100": 0,
        "note": "GitHub is a third-party historical copy. CNN publication times and historical vintages are not independently verified. Existing user CSV and JSON are unchanged.",
    }
    (AUDIT_DIR / "FGI_REFRESH_QC.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
