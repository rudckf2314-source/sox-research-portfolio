"""Independently compare each new RAW to the preserved uploaded source."""

import csv
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[3]
AUDIT_DIR = Path(__file__).resolve().parent
manifest = json.loads((AUDIT_DIR / "LOCAL_IMPORT_QC.json").read_text(encoding="utf-8"))
results = []
for item in manifest["datasets"]:
    dataset = item["dataset"]
    source = ROOT / item["source"]
    source_copy = ROOT / item["original_copy"]
    target = ROOT / item["target"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == item["source_sha256"]
    assert hashlib.sha256(source_copy.read_bytes()).hexdigest() == item["source_sha256"]
    assert hashlib.sha256(target.read_bytes()).hexdigest() == item["output_sha256"]
    with target.open(encoding="utf-8", newline="") as handle:
        assert handle.readline().startswith(f"# SOURCE | dataset_id={dataset} |")
        rows = list(csv.DictReader(handle))
    assert len(rows) == item["rows"]
    dates = [row["Date"] for row in rows]
    assert dates == sorted(set(dates))
    assert dates[0] == item["min_date"] and dates[-1] == item["max_date"]
    assert sum(value == "" for row in rows for value in row.values()) == item["missing_cells"]
    if dataset in ("26_nasdaqsox_fred", "27_vxncls"):
        with source.open(encoding="utf-8-sig", newline="") as handle:
            source_rows = list(csv.DictReader(handle))
        series = "NASDAQSOX" if dataset.startswith("26_") else "VXNCLS"
        assert [(row["Date"], row[series]) for row in rows] == [
            (row["observation_date"], row[series]) for row in source_rows]
    elif dataset.startswith(("28_", "29_", "30_", "31_")):
        with source.open(encoding="utf-8-sig", newline="") as handle:
            assert handle.readline().strip().endswith(", Daily")
            reader = csv.DictReader(handle, skipinitialspace=True)
            reader.fieldnames = [column.strip() for column in reader.fieldnames]
            source_rows = list(reader)
        assert len(source_rows) == len(rows)
        for raw_row, output_row in zip(source_rows, rows):
            assert datetime.strptime(raw_row["Date"].strip(), "%m/%d/%Y").date().isoformat() == output_row["Date"]
            for field in ("Open", "High", "Low", "Close", "Volume"):
                assert Decimal(raw_row[field].strip()) == Decimal(output_row[field])
    elif dataset.startswith("25_"):
        sheet = load_workbook(source, read_only=True, data_only=True)["Consolidated"]
        expected = []
        for row in sheet.values:
            if isinstance(row[0], int) and row[0] >= 2000:
                for month, value in enumerate(row[1:13], 1):
                    if value is not None:
                        expected.append((f"{row[0]:04d}-{month:02d}-01", Decimal(str(value))))
        assert [(row["Date"], Decimal(row["Consolidated_Revenue_Million_NTD"])) for row in rows] == expected
        assert rows[-1]["Consolidated_Revenue_Million_NTD"] == "511857"
    elif dataset.startswith("32_"):
        with source.open(encoding="utf-8-sig", newline="") as handle:
            source_rows = list(csv.DictReader(handle))
        assert len(source_rows) == len(rows)
        for raw_row, output_row in zip(source_rows, rows):
            roc = raw_row["資料期(民國年)"]
            assert output_row["Date"] == f"{int(roc[:3])+1911:04d}-{int(roc[3:]):02d}-01"
            assert output_row["ROC_Month"] == roc
            assert output_row["Statistic"] == raw_row["統計項目"]
            assert output_row["Product"] == raw_row["貨品別"]
            assert Decimal(output_row["Export_Orders_Million_USD"]) == Decimal(raw_row["統計值(金額)"])
            assert output_row["Original_Unit"] == raw_row["計量單位"]
    results.append({"dataset": dataset, "rows": len(rows), "min_date": dates[0],
                    "max_date": dates[-1], "missing_cells": item["missing_cells"],
                    "source_sha256_match": True, "full_value_match": True})

wsts = manifest["already_present"]
assert hashlib.sha256((ROOT / wsts["source_copy"]).read_bytes()).hexdigest() == wsts["sha256"]
assert hashlib.sha256((ROOT / wsts["identical_existing_source"]).read_bytes()).hexdigest() == wsts["sha256"]
report = {"status": "PASS", "new_raw_datasets": len(results), "datasets": results,
          "wsts_duplicate_original_verified": True}
(AUDIT_DIR / "INDEPENDENT_QC.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=True))
