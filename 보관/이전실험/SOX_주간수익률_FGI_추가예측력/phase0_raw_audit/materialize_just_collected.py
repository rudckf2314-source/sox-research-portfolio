"""Materialize user-supplied source files into versioned research-C RAW folders.

Each source is copied byte-for-byte into its dataset's source_original folder.
Canonical CSVs add a SOURCE preamble and preserve reported values without
interpolation, aggregation, or feature construction. Existing RAW is untouched.
"""

import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "방금수집"
RAW = ROOT / "data/raw"
AUDIT = ROOT / "research_C/phase0_raw_audit/local_import_20261016"
SOURCES = (
    ("26_nasdaqsox_fred", "NASDAQSOX.csv", "FRED", "Nasdaq, Inc.", "https://fred.stlouisfed.org/series/NASDAQSOX", "NASDAQSOX"),
    ("27_vxncls", "VXNCLS.csv", "FRED", "Chicago Board Options Exchange", "https://fred.stlouisfed.org/series/VXNCLS", "VXNCLS"),
)
STOCKCHARTS = (
    ("28_stockcharts_cpce", "_CPCE.csv", "$CPCE", "Equity Put/Call Ratio"),
    ("29_stockcharts_cpci", "_CPCI.csv", "$CPCI", "Index Put/Call Ratio"),
    ("30_stockcharts_bpspx", "_BPSPX.csv", "$BPSPX", "S&P 500 Bullish Percent Index"),
    ("31_stockcharts_ndxa200r", "_NDXA200R.csv", "$NDXA200R", "Nasdaq 100 Percent Above 200-day Moving Average"),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def month_date(year, month):
    datetime(int(year), int(month), 1)
    return f"{int(year):04d}-{int(month):02d}-01"


def date_iso(value):
    datetime.strptime(value, "%Y-%m-%d")
    return value


def numeric(value, allow_blank=False):
    value = str(value).strip()
    if not value and allow_blank:
        return value
    try:
        if not Decimal(value).is_finite():
            raise ValueError(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid number: {value}") from exc
    return value


def read_fred(source, series):
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["observation_date", series]:
            raise ValueError(f"Unexpected FRED header: {source.name}")
        rows = [[date_iso(row["observation_date"]), numeric(row[series], allow_blank=True)] for row in reader]
    return ["Date", series], rows, "observation_date renamed Date; blank holiday observations retained"


def read_stockcharts(source, symbol):
    with source.open(encoding="utf-8-sig", newline="") as handle:
        marker = handle.readline().strip()
        if marker != f"{symbol}, Daily":
            raise ValueError(f"Unexpected marker in {source.name}: {marker}")
        reader = csv.DictReader(handle, skipinitialspace=True)
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        if reader.fieldnames != ["Date", "Open", "High", "Low", "Close", "Volume"]:
            raise ValueError(f"Unexpected StockCharts fields in {source.name}")
        rows = []
        for row in reader:
            date = datetime.strptime(row["Date"].strip(), "%m/%d/%Y").date().isoformat()
            values = [numeric(row[key]) for key in ("Open", "High", "Low", "Close", "Volume")]
            rows.append([date, *values])
    return ["Date", "Open", "High", "Low", "Close", "Volume"], rows, "StockCharts Date normalized to ISO; source OHLCV values retained, no rescaling"


def read_tsmc(source):
    book = load_workbook(source, read_only=True, data_only=True)
    sheet = book["Consolidated"]
    rows = []
    for row in sheet.values:
        year = row[0]
        if not isinstance(year, int) or year < 2000:
            continue
        for month, value in enumerate(row[1:13], 1):
            if value is None:
                continue
            rows.append([month_date(year, month), numeric(value)])
    return ["Date", "Consolidated_Revenue_Million_NTD"], rows, "Consolidated sheet year/month cells unpivoted; no currency conversion or smoothing"


def read_moea(source):
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = ["統計項目", "貨品別", "資料期(民國年)", "統計值(金額)", "計量單位"]
        if reader.fieldnames != expected:
            raise ValueError(f"Unexpected Taiwan MOEA fields: {reader.fieldnames}")
        rows = []
        for row in reader:
            roc = row["資料期(民國年)"].strip()
            if not re.fullmatch(r"\d{5}", roc):
                raise ValueError(f"Invalid ROC period {roc}")
            date = month_date(int(roc[:3]) + 1911, roc[3:])
            if row["計量單位"] != "百萬美元" or row["貨品別"] != "電子產品":
                raise ValueError(f"Unexpected product/unit: {roc}")
            rows.append([date, roc, row["統計項目"], row["貨品別"],
                         numeric(row["統計值(金額)"]), row["計量單位"]])
    return ["Date", "ROC_Month", "Statistic", "Product", "Export_Orders_Million_USD", "Original_Unit"], rows, "ROC month converted to Gregorian first-of-month label; original category/unit retained"


def validate(dataset, header, rows):
    if not rows:
        raise ValueError(f"Empty source: {dataset}")
    dates = [row[0] for row in rows]
    if dates != sorted(dates):
        raise ValueError(f"Dates not ascending: {dataset}")
    if len(rows) != len(set(dates)):
        raise ValueError(f"Duplicate dates: {dataset}")
    if any(len(row) != len(header) or any(value is None for value in row) for row in rows):
        raise ValueError(f"Invalid row shape: {dataset}")
    if dataset.startswith(("25_", "32_")):
        expected = {(year, month) for year in range(int(dates[0][:4]), int(dates[-1][:4])+1)
                    for month in range(1, 13) if dates[0] <= f"{year:04d}-{month:02d}-01" <= dates[-1]}
        if {(int(date[:4]), int(date[5:7])) for date in dates} != expected:
            raise ValueError(f"Missing source month: {dataset}")
    if dataset.startswith(("28_", "29_", "30_", "31_")):
        if any(Decimal(row[4]) < 0 for row in rows):
            raise ValueError(f"Negative indicator Close: {dataset}")
    if dataset.startswith(("30_", "31_")) and any(Decimal(row[4]) > 100 for row in rows):
        raise ValueError(f"Percent indicator above 100: {dataset}")
    return dates[0], dates[-1]


def build():
    if AUDIT.exists():
        raise FileExistsError(AUDIT)
    work = []
    for dataset, filename, provider, administrator, url, series in SOURCES:
        source = INPUT / filename
        header, rows, transformation = read_fred(source, series)
        work.append((dataset, source, header, rows, provider, administrator, url, series, transformation))
    for dataset, filename, symbol, definition in STOCKCHARTS:
        source = INPUT / filename
        header, rows, transformation = read_stockcharts(source, symbol)
        url = f"https://stockcharts.com/h-sc/ui?s=%24{symbol[1:]}"
        work.append((dataset, source, header, rows, "StockCharts", "StockCharts.com", url, symbol,
                     transformation + f"; indicator={definition}"))
    tsmc = INPUT / "Historical_Monthly_Revenue September.xlsx"
    header, rows, transformation = read_tsmc(tsmc)
    work.append(("25_tsmc_monthly_revenue", tsmc, header, rows, "TSMC", "TSMC",
                 "https://investor.tsmc.com/english/monthly-revenue/2026", "Consolidated Monthly Revenue",
                 transformation))
    moea = next(path for path in INPUT.iterdir() if path.name.startswith("經濟部統計處_") and path.suffix == ".csv")
    header, rows, transformation = read_moea(moea)
    work.append(("32_taiwan_electronics_export_orders", moea, header, rows, "Taiwan MOEA Department of Statistics",
                 "Taiwan Ministry of Economic Affairs", "https://data.gov.tw/dataset/16362",
                 "Export Orders - Electronic Products", transformation))

    manifest = []
    for dataset, source, header, rows, provider, administrator, url, series, transformation in work:
        first, last = validate(dataset, header, rows)
        folder = RAW / dataset
        target = folder / f"{dataset}_RAW_{first.replace('-', '')}_{last.replace('-', '')}.csv"
        if folder.exists() or target.exists():
            raise FileExistsError(folder)
        manifest.append({"dataset": dataset, "source": source, "header": header, "rows_data": rows,
                         "provider": provider, "administrator": administrator, "url": url,
                         "series": series, "transformation": transformation, "min_date": first,
                         "max_date": last, "target": target, "source_sha256": sha(source),
                         "missing_cells": sum(value == "" for row in rows for value in row),
                         "rows": len(rows)})
    # WSTS was already materialized in dataset 22 from the identical original.
    wsts = INPUT / "WSTS-Historical-Billings-Report-Aug_2026.xlsx"
    existing_wsts = ROOT / "research_C/phase0_raw_audit/run_20261016_final/new_raw/WSTS_Historical_Billings_Aug_2026_original.xlsx"
    if sha(wsts) != sha(existing_wsts):
        raise ValueError("WSTS upload differs from existing official workbook")
    wsts_copy = RAW / "22_wsts_worldwide_billings/source_original" / wsts.name
    if wsts_copy.exists():
        raise FileExistsError(wsts_copy)
    run_time = datetime.now(timezone.utc).isoformat()
    AUDIT.mkdir(parents=True)
    for item in manifest:
        folder = item["target"].parent
        folder.mkdir()
        original_copy = folder / "source_original" / item["source"].name
        original_copy.parent.mkdir()
        shutil.copyfile(item["source"], original_copy)
        if sha(original_copy) != item["source_sha256"]:
            raise AssertionError(f"Original copy hash mismatch: {item['dataset']}")
        metadata = (
            f"# SOURCE | dataset_id={item['dataset']} | provider={item['provider']}"
            f" | administrator={item['administrator']} | source_url={item['url']}"
            f" | series_or_symbol={item['series']} | source_file={item['source'].name}"
            f" | source_sha256={item['source_sha256']}"
            f" | start_date={item['min_date']} | end_date={item['max_date']}"
            f" | retrieved_at_utc={run_time} | transformation={item['transformation']}"
        )
        with item["target"].open("x", encoding="utf-8", newline="") as handle:
            handle.write(metadata + "\n")
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(item["header"])
            writer.writerows(item["rows_data"])
        with item["target"].open(encoding="utf-8", newline="") as handle:
            assert handle.readline() == metadata + "\n"
            reader = csv.reader(handle)
            assert next(reader) == item["header"]
            assert list(reader) == [[str(value) for value in row] for row in item["rows_data"]]
        item["output_sha256"] = sha(item["target"])
        item["original_copy_sha256"] = sha(original_copy)
        item["original_copy"] = str(original_copy.relative_to(ROOT))
        item["target"] = str(item["target"].relative_to(ROOT))
        item["source"] = str(item["source"].relative_to(ROOT))
        del item["rows_data"]
        del item["header"]
        print(item["dataset"], item["rows"], item["min_date"], item["max_date"], flush=True)
    wsts_copy.parent.mkdir(exist_ok=True)
    shutil.copyfile(wsts, wsts_copy)
    if sha(wsts_copy) != sha(wsts):
        raise AssertionError("WSTS original copy hash mismatch")
    result = {"run_time_utc": run_time, "datasets": manifest,
              "already_present": {"dataset": "22_wsts_worldwide_billings", "source": str(wsts.relative_to(ROOT)),
                                  "identical_existing_source": str(existing_wsts.relative_to(ROOT)),
                                  "sha256": sha(wsts), "source_copy": str(wsts_copy.relative_to(ROOT)),
                                  "action": "existing canonical RAW retained; identical workbook copied into source_original"}}
    (AUDIT / "LOCAL_IMPORT_QC.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
