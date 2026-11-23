"""Reconstruct canonical rows from saved Customs XML, independently of collector."""

import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[2]
audit = json.loads((RUN / "COLLECTION_QC.json").read_text(encoding="utf-8"))
csv_file = ROOT / audit["csv_path"]
assert hashlib.sha256(csv_file.read_bytes()).hexdigest() == audit["csv_sha256"]
with csv_file.open(encoding="utf-8", newline="") as handle:
    assert handle.readline().startswith("# SOURCE | dataset_id=24_customs_semiconductor_trade")
    reader = csv.DictReader(handle)
    actual = list(reader)
assert len(actual) == 10035
assert len(audit["requests"]) == 32

expected = []
for request in audit["requests"]:
    raw = (RUN / request["response"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == request["response_sha256"]
    tree = ET.fromstring(raw)
    assert tree.findtext(".//resultCode") == "00"
    items = tree.findall(".//item")
    assert len(items) == request["item_count"]
    for item in items:
        values = {node.tag: (node.text or "").strip() for node in item}
        if values.get("year") in ("총계", "합계"):
            continue
        expected.append({
            "Date": values["year"].replace(".", "-") + "-01",
            "HS_Code": values["hsCode"],
            "Item_Name_Korean": values["statKor"],
            "Export_Weight_kg": values["expWgt"],
            "Export_Value_USD": values["expDlr"],
            "Import_Weight_kg": values["impWgt"],
            "Import_Value_USD": values["impDlr"],
            "Trade_Balance_USD": values["balPayments"],
        })
expected.sort(key=lambda row: (row["Date"], row["HS_Code"]))
assert actual == expected
assert len({(row["Date"], row["HS_Code"]) for row in actual}) == len(actual)
assert len({row["Date"] for row in actual}) == 189
for hs in ("8541", "8542"):
    assert len({row["Date"] for row in actual if row["HS_Code"].startswith(hs)}) == 189
for row in actual:
    assert int(row["Export_Weight_kg"]) >= 0
    assert int(row["Export_Value_USD"]) >= 0
    assert int(row["Import_Weight_kg"]) >= 0
    assert int(row["Import_Value_USD"]) >= 0
    assert int(row["Trade_Balance_USD"]) == int(row["Export_Value_USD"]) - int(row["Import_Value_USD"])
print(json.dumps({"status": "PASS", "rows": len(actual), "months": 189,
                  "xml_responses": 32, "duplicate_month_hs": 0,
                  "first_month": actual[0]["Date"], "last_month": actual[-1]["Date"],
                  "csv_sha256": audit["csv_sha256"]}, ensure_ascii=False))
