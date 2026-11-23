"""Build versioned StockCharts RAW files from the user's refreshed exports.

Only the five local files under 갱신/ are read. Existing RAW files are never
overwritten. The script fails on duplicate dates, missing closes, pairwise date
mismatches, or unexpected changes before the previous terminal date.
"""

import csv
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "갱신"
OUTPUT = ROOT / "data" / "metadata" / "RAW_REFRESH_STOCKCHARTS_20261015"
START = "2011-01-01"
MAX_END = "2026-10-15"
CONFIG = (
    ("05_nyse_high_low", "20261007", ("_NYHGH.csv", "_NYLOW.csv"),
     ("New_Highs_52W", "New_Lows_52W"), "$NYHGH;$NYLOW",
     "NYSE 52-week new highs and new lows, StockCharts market indicators"),
    ("06_nyse_breadth", "20261007", ("_NYUPV.csv", "_NYDNV.csv"),
     ("Advancing_Volume", "Declining_Volume"), "$NYUPV;$NYDNV",
     "NYSE advancing volume and declining volume, StockCharts market indicators"),
    ("07_cboe_put_call", "20261006", ("_CPC.csv",),
     ("Total_Put_Call_Ratio",), "$CPC",
     "Cboe Total Put/Call Ratio as represented by StockCharts $CPC Close"),
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_source(name):
    path = SOURCE / name
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        marker = handle.readline().strip()
        if marker != f"${name[1:-4]}, Daily":
            raise ValueError(f"Unexpected StockCharts marker: {name}: {marker}")
        reader = csv.DictReader(handle, skipinitialspace=True)
        reader.fieldnames = [field.strip() for field in reader.fieldnames]
        if reader.fieldnames != ["Date", "Open", "High", "Low", "Close", "Volume"]:
            raise ValueError(f"Unexpected source header: {name}: {reader.fieldnames}")
        values = {}
        for row in reader:
            date = datetime.strptime(row["Date"].strip(), "%m/%d/%Y").date().isoformat()
            if date < START:
                continue
            close = row["Close"].strip()
            try:
                number = Decimal(close)
            except InvalidOperation as exc:
                raise ValueError(f"Nonnumeric Close: {name} {date}") from exc
            if not number.is_finite() or number < 0 or (name == "_CPC.csv" and number <= 0):
                raise ValueError(f"Invalid Close: {name} {date} {close}")
            if date in values:
                raise ValueError(f"Duplicate source date: {name} {date}")
            values[date] = close
    if not values or min(values) != "2011-01-03" or max(values) != MAX_END:
        raise ValueError(f"Unexpected date coverage: {name} {min(values)}..{max(values)}")
    return values, sha256(path)


def read_old(path, columns):
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        if not handle.readline().startswith("# SOURCE |"):
            raise ValueError(f"Missing source metadata in {path}")
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["Date", *columns]:
            raise ValueError(f"Unexpected old header: {path}")
        rows = {}
        for row in reader:
            date = row["Date"]
            if date in rows:
                raise ValueError(f"Duplicate old date {path}: {date}")
            rows[date] = [row[column] for column in columns]
    return rows


def main():
    staged = []
    audit = {"source_directory": str(SOURCE), "datasets": {}, "created_at_utc": datetime.now(timezone.utc).isoformat()}
    protected = {}
    for dataset, old_end, files, columns, symbols, definition in CONFIG:
        source_values, source_hashes = [], {}
        for name in files:
            values, digest = read_source(name)
            source_values.append(values)
            source_hashes[name] = digest
            protected[SOURCE / name] = digest
        dates = set(source_values[0])
        for value in source_values[1:]:
            if set(value) != dates:
                raise ValueError(f"Paired source date mismatch: {dataset}: {sorted(dates ^ set(value))[:20]}")
        sorted_dates = sorted(dates)
        if len(sorted_dates) != 3970 or sorted_dates[-1] != MAX_END:
            raise ValueError(f"Unexpected rows/end: {dataset}: {len(sorted_dates)} {sorted_dates[-1]}")
        old = ROOT / "data" / "raw" / dataset / f"{dataset}_RAW_20110101_{old_end}.csv"
        old_rows = read_old(old, columns)
        protected[old] = sha256(old)
        if set(old_rows) - dates:
            raise ValueError(f"Old dates missing from refresh: {dataset}")
        changes = []
        for date, previous in old_rows.items():
            refreshed = [source_values[i][date] for i in range(len(columns))]
            if [Decimal(value) for value in previous] != [Decimal(value) for value in refreshed]:
                changes.append({"date": date, "old": previous, "new": refreshed})
        if any(change["date"] != "2026-10-07" for change in changes):
            raise ValueError(f"Unexpected historical revisions: {dataset}: {changes[:5]}")
        if dataset == "07_cboe_put_call" and changes:
            raise ValueError("Unexpected historical CPC revision")
        target = old.parent / f"{dataset}_RAW_20110101_20261015.csv"
        if target.exists():
            raise FileExistsError(target)
        transformation = "Close columns merged by exact Date; no rescaling or filling" if len(files) == 2 else "Close column only; no smoothing or filling"
        metadata = (
            f"# SOURCE | dataset_id={dataset} | provider=StockCharts"
            f" | source_url=https://stockcharts.com/ | source_symbols={symbols}"
            f" | source_files={';'.join('갱신/' + name for name in files)}"
            f" | definition={definition} | start_date={START} | end_date={MAX_END}"
            f" | retrieved_at_utc={audit['created_at_utc']}"
            f" | transformation={transformation}"
        )
        rows = [[date, *[source_values[i][date] for i in range(len(columns))]] for date in sorted_dates]
        staged.append((target, metadata, ["Date", *columns], rows))
        audit["datasets"][dataset] = {
            "old_file": str(old.relative_to(ROOT)), "old_sha256": protected[old],
            "new_file": str(target.relative_to(ROOT)), "source_sha256": source_hashes,
            "rows": len(rows), "min_date": sorted_dates[0], "max_date": sorted_dates[-1],
            "duplicate_dates": 0, "missing_cells": 0, "negative_values": 0,
            "new_dates": sorted(dates - set(old_rows)), "overlap_changes": changes,
        }
    # All three datasets have passed source, pairing and historical-overlap checks.
    for target, metadata, header, rows in staged:
        with target.open("x", newline="", encoding="utf-8") as handle:
            handle.write(metadata + "\n")
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        with target.open("r", newline="", encoding="utf-8") as handle:
            assert handle.readline().startswith("# SOURCE |")
            reread = list(csv.reader(handle))
        if reread[0] != header or reread[1:] != rows:
            raise AssertionError(f"Read-back mismatch: {target}")
        audit["datasets"][target.parent.name]["new_sha256"] = sha256(target)
    if any(sha256(path) != digest for path, digest in protected.items()):
        raise AssertionError("Protected source or old RAW changed")
    OUTPUT.mkdir(exist_ok=False)
    (OUTPUT / "RAW_REFRESH_QC.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
