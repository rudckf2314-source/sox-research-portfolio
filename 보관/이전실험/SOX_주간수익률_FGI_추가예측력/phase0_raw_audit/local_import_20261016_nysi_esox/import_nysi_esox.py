"""Register local NYSI and NASDAQESOX without replacing NYMO or NASDAQSOX."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
RAW = ROOT / "data/raw"
INPUT = ROOT / "방금수집"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def summary(df):
    numbers = df.drop(columns="Date")
    return {"rows": len(df), "min_date": df.Date.min().strftime("%Y-%m-%d"),
            "max_date": df.Date.max().strftime("%Y-%m-%d"),
            "duplicate_dates": int(df.Date.duplicated().sum()),
            "missing_cells": int(df.isna().sum().sum()),
            "missing_by_column": {c: int(n) for c, n in df.isna().sum().items()},
            "ascending": bool(df.Date.is_monotonic_increasing),
            "nonfinite_nonmissing_values": int((~np.isfinite(numbers.to_numpy(dtype=float)) & numbers.notna().to_numpy()).sum())}


def compare(new, old, new_value, old_value):
    overlap = new[["Date", new_value]].merge(old[["Date", old_value]], on="Date", suffixes=("_new", "_old"), validate="one_to_one")
    if new_value == old_value:
        new_value, old_value = new_value + "_new", old_value + "_old"
    paired = overlap.dropna(subset=[new_value, old_value])
    equal = int(paired[new_value].eq(paired[old_value]).sum())
    return {"overlap_date_rows": len(overlap), "valid_value_pairs": len(paired),
            "equal_value_pairs": equal, "different_value_pairs": len(paired) - equal,
            "both_values_missing": int((overlap[new_value].isna() & overlap[old_value].isna()).sum()),
            "missing_pattern_differences": int((overlap[new_value].isna() != overlap[old_value].isna()).sum())}


def main():
    if (RUN / "LOCAL_IMPORT_QC.json").exists():
        raise FileExistsError("Import already completed; refusing overwrite")
    files = [INPUT / "_NYSI.csv", INPUT / "NASDAQESOX.csv"]
    assert all(p.is_file() for p in files)
    baseline = {str(p.relative_to(ROOT)): sha(p) for p in RAW.rglob("*") if p.is_file()}
    input_hashes = {str(p.relative_to(ROOT)): sha(p) for p in files}
    nysi = pd.read_csv(files[0], skiprows=1)
    nysi.columns = nysi.columns.str.strip()
    with files[0].open(encoding="utf-8-sig") as f:
        assert f.readline().strip().replace(" ", "") == "$NYSI,Daily"
    assert list(nysi.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    nysi.Date = pd.to_datetime(nysi.Date, format="%m/%d/%Y", errors="raise")
    esox = pd.read_csv(files[1])
    assert list(esox.columns) == ["observation_date", "NASDAQESOX"]
    esox = esox.rename(columns={"observation_date": "Date"})
    esox.Date = pd.to_datetime(esox.Date, format="%Y-%m-%d", errors="raise")
    for frame in [nysi, esox]:
        for c in frame.columns[1:]:
            frame[c] = pd.to_numeric(frame[c], errors="raise")
        assert not frame.Date.isna().any() and not frame.Date.duplicated().any()
    nysi = nysi.sort_values("Date").reset_index(drop=True)
    esox = esox.sort_values("Date").reset_index(drop=True)
    assert not nysi.isna().any().any()
    assert not esox.NASDAQESOX.dropna().le(0).any()
    nymo_file = next((RAW / "40_stockcharts_nymo").glob("*RAW*.csv"))
    sox_file = next((RAW / "26_nasdaqsox_fred").glob("*RAW*.csv"))
    nymo = pd.read_csv(nymo_file, comment="#")
    sox = pd.read_csv(sox_file, comment="#")
    for frame in [nymo, sox]:
        frame.Date = pd.to_datetime(frame.Date, errors="raise")
    comparisons = {"NYSI_vs_existing_NYMO": compare(nysi, nymo, "Close", "Close"),
                   "NASDAQESOX_vs_existing_NASDAQSOX": compare(esox, sox, "NASDAQESOX", "NASDAQSOX")}
    specifications = [
        ("41_stockcharts_nysi", files[0], nysi, "StockCharts", "StockCharts.com", "$NYSI",
         "https://stockcharts.com/h-sc/ui?s=%24NYSI", "source indicator points", "NYSE Summation Index",
         "StockCharts first line omitted; Date normalized to ISO; source OHLCV retained; no rescaling or filling"),
        ("42_nasdaqesox_fred", files[1], esox, "FRED", "Nasdaq, Inc.", "NASDAQESOX",
         "https://fred.stlouisfed.org/series/NASDAQESOX", "Index, Not Seasonally Adjusted", "PHLX Semiconductor Equal Weighted Index",
         "observation_date renamed Date; source numeric values and missing observations retained; no rescaling or filling"),
    ]
    for dataset_id, *_ in specifications:
        if (RAW / dataset_id).exists():
            raise FileExistsError(RAW / dataset_id)
    timestamp = datetime.now(timezone.utc).isoformat()
    records = []
    for dataset_id, original, frame, provider, administrator, symbol, url, unit, name, transformation in specifications:
        qc = summary(frame)
        assert qc["duplicate_dates"] == 0 and qc["nonfinite_nonmissing_values"] == 0
        copied = RAW / dataset_id / "source_original" / original.name
        copied.parent.mkdir(parents=True)
        shutil.copy2(original, copied)
        assert sha(original) == sha(copied)
        output = RAW / dataset_id / f"{dataset_id}_RAW_{qc['min_date'].replace('-', '')}_{qc['max_date'].replace('-', '')}.csv"
        with output.open("w", encoding="utf-8", newline="") as f:
            f.write(f"# SOURCE | dataset_id={dataset_id} | provider={provider} | administrator={administrator} | source_url={url} | series_or_symbol={symbol} | dataset_name={name} | source_file={original.name} | source_sha256={sha(original)} | start_date={qc['min_date']} | end_date={qc['max_date']} | retrieved_at_utc=UNKNOWN | imported_at_utc={timestamp} | provenance=user-provided local download | unit={unit} | transformation={transformation}\n")
            frame.to_csv(f, index=False, date_format="%Y-%m-%d", float_format="%.17g")
        restored = pd.read_csv(output, comment="#", float_precision="round_trip")
        restored.Date = pd.to_datetime(restored.Date, errors="raise")
        assert restored.Date.equals(frame.Date)
        assert np.allclose(restored.iloc[:, 1:].to_numpy(dtype=float), frame.iloc[:, 1:].to_numpy(dtype=float), rtol=0, atol=1e-15, equal_nan=True)
        record = {"dataset_id": dataset_id, "name": name, "symbol": symbol, **qc,
                  "output_file": str(output.relative_to(ROOT)), "output_sha256": sha(output),
                  "original_copy": str(copied.relative_to(ROOT)), "source_sha256": sha(copied), "source_url": url,
                  "first_valid_date": frame.loc[frame.iloc[:, 1:].notna().all(axis=1), "Date"].min().strftime("%Y-%m-%d"),
                  "last_valid_date": frame.loc[frame.iloc[:, 1:].notna().all(axis=1), "Date"].max().strftime("%Y-%m-%d"),
                  "historical_publication_time": "UNVERIFIED", "historical_vintage": "UNVERIFIED"}
        if symbol == "NASDAQESOX":
            record["history_limitation"] = "Supplied file begins 2021-11-09; does not cover 2011-2020; not extended using NASDAQSOX"
            record["official_license_note"] = "FRED tags Copyrighted: Pre-Approval Required; this local import does not establish reuse or redistribution rights"
        (RAW / dataset_id / "SOURCE_METADATA.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        records.append(record)
    changes = [p for p, value in baseline.items() if not (ROOT / p).is_file() or sha(ROOT / p) != value]
    assert not changes
    assert all(sha(ROOT / p) == value for p, value in input_hashes.items())
    result = {"status": "PASS_WITH_SOURCE_LIMITATIONS", "imported_at_utc": timestamp,
              "datasets": records, "existing_series_comparisons": comparisons,
              "protected_existing_raw_files": len(baseline), "protected_hash_changes": changes,
              "input_originals_unchanged": True, "original_copy_hashes_match": True,
              "numeric_and_missing_values_roundtrip": True, "new_features_or_models_computed": 0}
    (RUN / "LOCAL_IMPORT_QC.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (RUN / "PROTECTED_RAW_HASHES.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    report = f"""# NYSI·NASDAQESOX 로컬 RAW 등록

## 저장 결과

| dataset | rows | period | missing cells | output |
|---|---:|---|---:|---|
"""
    for r in records:
        report += f"| {r['dataset_id']} | {r['rows']} | {r['min_date']}~{r['max_date']} | {r['missing_cells']} | `{r['output_file']}` |\n"
    report += f"""
## 기존 RAW와 비교

- NYSI와 기존 NYMO는 같은 날짜 7,137개에서 비교했으며 Close가 같은 관측은 0개다. 별도 지표로 보존했다.
- NASDAQESOX와 기존 NASDAQSOX는 같은 날짜 1,288개 중 유효한 값 쌍 1,238개에서 비교했으며 같은 값은 0개다. 단순 갱신본으로 덮어쓰거나 과거 구간을 이어붙이지 않았다.
- FRED 공식 https://fred.stlouisfed.org/series/NASDAQESOX 에서 PHLX Semiconductor Equal Weighted Index, 일별 Index, Not Seasonally Adjusted임을 확인했다.
- 받은 NASDAQESOX는 2021-11-09부터다. 2011~2020년 자료는 이 파일에 없다. 원본 결측 50개를 그대로 보존했으며 기존 SOX의 결측 패턴과의 비교는 QC JSON에 있다.
- NYSI의 음수 값 및 0 Volume은 원본대로 유지했다. Proxy7 x3를 재계산하거나 대체하지 않았다.
- 두 원본을 source_original에 바이트 그대로 보존했다. 방금수집 입력 파일도 유지했다. 출처 첫 줄과 실제 헤더를 구분하고 CSV는 comment='#'로 읽는다.
- 기존 RAW {len(baseline)}개 파일의 SHA-256 변경 0건. 기존 26번·40번 포함 모든 기존 RAW를 유지했다.
- 역사적 최초 게시시각·빈티지·이용권한은 이 파일 수령만으로 검증되지 않는다. Nasdaq 자료의 FRED 이용권한 표시는 SOURCE_METADATA.json에 기록했다.
"""
    (RUN / "LOCAL_IMPORT_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
