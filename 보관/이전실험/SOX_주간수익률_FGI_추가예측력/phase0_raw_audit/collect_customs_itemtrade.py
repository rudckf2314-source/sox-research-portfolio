"""Collect Korea Customs item-trade monthly RAW for semiconductor HS 8541/8542.

The data.go.kr key is read from the project .env and never written to output.
Requests are annual (the API's maximum span), with an optional single-month
probe. Raw XML responses are retained in the run directory after validation.
"""

import argparse
import csv
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import requests


ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
PAGE = "https://www.data.go.kr/data/15101609/openapi.do"
HEADERS = ["Date", "HS_Code", "Item_Name_Korean", "Export_Weight_kg", "Export_Value_USD", "Import_Weight_kg", "Import_Value_USD", "Trade_Balance_USD"]


def key_from_env():
    value = ""
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("CUSTOMS_TRADE_API_KEY="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not value:
        raise RuntimeError("CUSTOMS_TRADE_API_KEY is empty")
    return unquote(value)


def request_one(session, key, start, end, hs):
    parameters = {"serviceKey": key, "strtYymm": start, "endYymm": end, "hsSgn": hs}
    for attempt in range(3):
        try:
            response = session.get(ENDPOINT, params=parameters, timeout=60)
            data = response.content
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            root = ET.fromstring(data)
            code = root.findtext(".//resultCode")
            message = root.findtext(".//resultMsg") or ""
            if code not in ("00", "0"):
                raise RuntimeError(f"API resultCode={code}; resultMsg={message[:120]}")
            items = root.findall(".//item")
            return data, items, code
        except (requests.RequestException, ET.ParseError, RuntimeError) as exc:
            # Exception strings can include the credential-bearing URL: log only
            # the class and HTTP/API status, never the request object or URL.
            if isinstance(exc, RuntimeError):
                safe_error = str(exc)
            else:
                safe_error = type(exc).__name__
            if attempt == 2 or ("resultCode=" in safe_error and not safe_error.startswith("API resultCode=05")):
                raise RuntimeError(safe_error) from None
            time.sleep((2, 5, 10)[attempt])


def parse_items(items, hs):
    rows = []
    for item in items:
        value = {child.tag: (child.text or "").strip() for child in item}
        period = value.get("year", "")
        if period in ("총계", "합계"):
            continue
        if not re.fullmatch(r"\d{4}\.\d{2}", period):
            raise ValueError(f"Invalid period: {period}")
        code = value.get("hsCode", "")
        if not code.startswith(hs):
            raise ValueError(f"Unexpected HS code: {code} for {hs}")
        row = [period.replace(".", "-") + "-01", code, value.get("statKor", ""),
               value.get("expWgt", ""), value.get("expDlr", ""),
               value.get("impWgt", ""), value.get("impDlr", ""),
               value.get("balPayments", "")]
        for field in row[3:]:
            if not re.fullmatch(r"-?\d+", field):
                raise ValueError(f"Nonnumeric field for {code} {period}: {field!r}")
        rows.append(row)
    return rows


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--end-month", default="202609")
    args = parser.parse_args()
    key = key_from_env()
    session = requests.Session()
    if args.probe:
        for hs in ("8541", "8542"):
            data, items, code = request_one(session, key, "202601", "202601", hs)
            rows = parse_items(items, hs)
            print(json.dumps({"hs": hs, "api_code": code, "items": len(items),
                              "parsed_rows": len(rows), "response_bytes": len(data),
                              "xml_declaration": data[:80].decode("ascii", errors="replace"),
                              "sample_item_name_bytes_hex": data[data.find(b"<statKor>"):data.find(b"</statKor>")+10][:100].hex(),
                              "sample_hs_codes": [row[1] for row in rows[:2]]}, ensure_ascii=False))
        return
    if not re.fullmatch(r"20\d{4}", args.end_month) or args.end_month > "202609":
        raise ValueError("Only completed months through 2026-09 are allowed for this run")
    output = ROOT / "data/raw/24_customs_semiconductor_trade"
    if output.exists():
        raise FileExistsError(output)
    run_dir = ROOT / "research_C/phase0_raw_audit/customs_itemtrade_20261016"
    if run_dir.exists():
        raise FileExistsError(run_dir)
    collected = []
    records = []
    for year in range(2011, 2027):
        start = f"{year}01"
        end = min(f"{year}12", args.end_month)
        if start > end:
            break
        for hs in ("8541", "8542"):
            data, items, code = request_one(session, key, start, end, hs)
            rows = parse_items(items, hs)
            if not rows:
                raise RuntimeError(f"Empty response: {start}-{end} HS {hs}")
            if any(not (start <= row[0].replace("-", "")[:6] <= end) for row in rows):
                raise ValueError(f"Period outside request: {start}-{end} HS {hs}")
            collected.extend(rows)
            records.append({"start": start, "end": end, "hs": hs, "item_count": len(items),
                            "rows": len(rows), "response_sha256": sha(data),
                            "response_bytes": len(data), "response": f"responses/{year}_{hs}.xml"})
            print(f"{year} HS {hs}: {len(rows)} rows", flush=True)
            # Preserve only successful responses; no credential-bearing URL.
            records[-1]["data"] = data
            time.sleep(0.25)
    keys = [(row[0], row[1]) for row in collected]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate monthly HS code")
    collected.sort(key=lambda row: (row[0], row[1]))
    if min(row[0] for row in collected) != "2011-01-01":
        raise ValueError("Historical coverage does not start in 2011-01")
    latest = max(row[0] for row in collected)
    if latest != "2026-09-01":
        raise ValueError(f"Unexpected latest month: {latest}")
    expected_months = {f"{year}-{month:02d}-01" for year in range(2011, 2027)
                       for month in range(1, 13) if f"{year}{month:02d}" <= args.end_month}
    for hs in ("8541", "8542"):
        actual_months = {row[0] for row in collected if row[1].startswith(hs)}
        if actual_months != expected_months:
            raise ValueError(f"Missing months for HS {hs}: {sorted(expected_months - actual_months)}")
    retrieved = datetime.now(timezone.utc).isoformat()
    output.mkdir(parents=True)
    (run_dir / "responses").mkdir(parents=True)
    for record in records:
        (run_dir / record["response"]).write_bytes(record.pop("data"))
    target = output / "24_customs_semiconductor_trade_RAW_20110101_20260901.csv"
    metadata = ("# SOURCE | dataset_id=24_customs_semiconductor_trade | provider=Korea Customs Service / data.go.kr"
                " | administrator=Korea Customs Service | source_url=" + PAGE +
                " | api_endpoint=" + ENDPOINT +
                " | hs_codes=8541;8542 | hs_scope=4-digit prefix; API returns 10-digit HS rows"
                " | unit=kg;USD | frequency=monthly | start_date=2011-01-01 | end_date=2026-09-01"
                " | retrieved_at_utc=" + retrieved +
                " | transformation=API item fields retained; no HS aggregation or interpolation")
    with target.open("x", encoding="utf-8", newline="") as handle:
        handle.write(metadata + "\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADERS)
        writer.writerows(collected)
    audit = {"source_page": PAGE, "endpoint_without_key": ENDPOINT,
             "retrieved_at_utc": retrieved, "query_scope": "HS 8541 and 8542, 2011-01 through 2026-09",
             "rows": len(collected), "min_month": collected[0][0], "max_month": latest,
             "unique_months": len(set(row[0] for row in collected)),
             "unique_hs_codes": len(set(row[1] for row in collected)),
             "duplicate_month_hs": 0, "csv_path": str(target.relative_to(ROOT)),
             "csv_sha256": sha(target.read_bytes()), "requests": records,
             "limitations": "Current-revised monthly API data, not historical publication vintages; release timing must be mapped before use as a predictive X."}
    (run_dir / "COLLECTION_QC.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ("rows", "min_month", "max_month", "unique_months", "unique_hs_codes", "duplicate_month_hs", "csv_path", "csv_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
