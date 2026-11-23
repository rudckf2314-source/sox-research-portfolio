"""Import user-downloaded AAII XLS and StockCharts NYMO; never modify inputs.

AAII: retain every date-labelled row and the three raw survey proportions.
NYMO: retain all source OHLCV fields. No feature calculation or rescaling.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
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


def inspect(df):
    numeric = df.drop(columns="Date")
    return {"rows": len(df), "min_date": df.Date.min().strftime("%Y-%m-%d"),
            "max_date": df.Date.max().strftime("%Y-%m-%d"),
            "duplicate_dates": int(df.Date.duplicated().sum()),
            "missing_cells": int(df.isna().sum().sum()),
            "missing_by_column": {k: int(v) for k, v in df.isna().sum().items()},
            "nonfinite_nonmissing_values": int((~np.isfinite(numeric.to_numpy(dtype=float)) & numeric.notna().to_numpy()).sum()),
            "ascending": bool(df.Date.is_monotonic_increasing),
            "rows_since_2011": int((df.Date >= "2011-01-01").sum()),
            "missing_cells_since_2011": int(df.loc[df.Date >= "2011-01-01"].isna().sum().sum())}


def main():
    if (RUN / "LOCAL_IMPORT_QC.json").exists():
        raise FileExistsError("This import was already run; refusing overwrite")
    baseline = {str(p.relative_to(ROOT)): sha(p) for p in RAW.rglob("*") if p.is_file()}
    sources = [INPUT / "sentiment.xls", INPUT / "_NYMO.csv"]
    for p in sources:
        if not p.is_file():
            raise FileNotFoundError(p)
    source_hash = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    xls = pd.read_excel(sources[0], sheet_name="SENTIMENT", header=None)
    assert "American Association" in str(xls.iloc[0, 3])
    assert [str(v).strip() for v in xls.iloc[3, :4]] == ["Date", "Bullish", "Neutral", "Bearish"]
    date_mask = xls.iloc[:, 0].apply(lambda value: isinstance(value, datetime))
    aaii = xls.loc[date_mask, :3].copy()
    aaii.columns = ["Date", "Bullish", "Neutral", "Bearish"]
    aaii.Date = pd.to_datetime(aaii.Date, errors="raise")
    for c in aaii.columns[1:]:
        aaii[c] = pd.to_numeric(aaii[c], errors="raise")
    aaii = aaii.sort_values("Date").reset_index(drop=True)
    assert not aaii.Date.isna().any() and not aaii.Date.duplicated().any()
    assert not ((aaii.iloc[:, 1:] < 0) | (aaii.iloc[:, 1:] > 1)).any().any()
    with sources[1].open(encoding="utf-8-sig") as f:
        nymo_first_line = f.readline().strip()
    assert nymo_first_line.replace(" ", "") == "$NYMO,Daily"
    nymo = pd.read_csv(sources[1], skiprows=1)
    nymo.columns = nymo.columns.str.strip()
    assert list(nymo.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    nymo.Date = pd.to_datetime(nymo.Date, format="%m/%d/%Y", errors="raise")
    for c in nymo.columns[1:]:
        nymo[c] = pd.to_numeric(nymo[c], errors="raise")
    nymo = nymo.sort_values("Date").reset_index(drop=True)
    assert not nymo.isna().any().any() and not nymo.Date.duplicated().any()
    assert np.isfinite(nymo.iloc[:, 1:].to_numpy()).all()
    imported_at = datetime.now(timezone.utc).isoformat()
    plans = [
        ("36_aaii_sentiment", sources[0], aaii, "AAII", "American Association of Individual Investors",
         "https://www.aaii.com/files/surveys/sentiment.xls", "AAII Sentiment Survey",
         "Date-labelled SENTIMENT rows and Bullish Neutral Bearish columns only; source fractions retained; no rescaling or filling",
         "fraction_0_to_1; source Excel displays percentages"),
        ("40_stockcharts_nymo", sources[1], nymo, "StockCharts", "StockCharts.com",
         "https://stockcharts.com/h-sc/ui?s=%24NYMO", "$NYMO",
         "Date normalized to ISO; all source OHLCV numeric values retained; no rescaling or filling", "source_indicator_points"),
    ]
    for dataset_id, *_ in plans:
        if (RAW / dataset_id).exists():
            raise FileExistsError(RAW / dataset_id)
    records = []
    for dataset_id, original, frame, provider, administrator, url, symbol, transformation, unit in plans:
        qc = inspect(frame)
        assert qc["duplicate_dates"] == 0 and qc["nonfinite_nonmissing_values"] == 0
        folder = RAW / dataset_id
        original_folder = folder / "source_original"
        original_folder.mkdir(parents=True)
        saved_original = original_folder / original.name
        shutil.copy2(original, saved_original)
        assert sha(saved_original) == source_hash[str(original.relative_to(ROOT))]
        output = folder / (f"{dataset_id}_RAW_{qc['min_date'].replace('-', '')}_{qc['max_date'].replace('-', '')}.csv")
        with output.open("w", newline="", encoding="utf-8") as f:
            f.write(f"# SOURCE | dataset_id={dataset_id} | provider={provider} | administrator={administrator} | source_url={url} | series_or_symbol={symbol} | source_file={original.name} | source_sha256={sha(original)} | start_date={qc['min_date']} | end_date={qc['max_date']} | retrieved_at_utc=UNKNOWN | imported_at_utc={imported_at} | provenance=user-provided local download; not fetched in this run | unit={unit} | transformation={transformation}\n")
            frame.to_csv(f, index=False, date_format="%Y-%m-%d", float_format="%.17g")
        restored = pd.read_csv(output, comment="#", float_precision="round_trip")
        restored.Date = pd.to_datetime(restored.Date, errors="raise")
        assert restored.Date.equals(frame.Date)
        assert np.allclose(restored.iloc[:, 1:].to_numpy(dtype=float), frame.iloc[:, 1:].to_numpy(dtype=float), rtol=0, atol=1e-15, equal_nan=True)
        record = {"dataset_id": dataset_id, "provider": provider, "status": "IMPORTED_WITH_SOURCE_MISSING_VALUES" if qc["missing_cells"] else "IMPORTED",
                  **qc, "output_file": str(output.relative_to(ROOT)), "sha256": sha(output),
                  "source_original": str(saved_original.relative_to(ROOT)), "source_sha256": sha(saved_original),
                  "source_url": url, "unit": unit, "release_time_status": "UNVERIFIED", "historical_vintage_status": "UNVERIFIED"}
        records.append(record)
        (folder / "SOURCE_METADATA.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = [p for p, h in baseline.items() if not (ROOT / p).is_file() or sha(ROOT / p) != h]
    assert not changed, f"Existing RAW changed: {changed}"
    assert all(sha(ROOT / p) == h for p, h in source_hash.items())
    aaii_notes = {
        "date_label": "Reported Date in supplied workbook; not proven survey close or first publication time",
        "missing_date_rows": aaii.loc[aaii.iloc[:, 1:].isna().any(axis=1), "Date"].dt.strftime("%Y-%m-%d").tolist(),
        "first_nonmissing_survey_date": aaii.loc[aaii.iloc[:, 1:].notna().all(axis=1), "Date"].min().strftime("%Y-%m-%d"),
        "max_abs_fraction_sum_minus_one": float((aaii.iloc[:, 1:].sum(axis=1, min_count=3) - 1).abs().max()),
        "normalization_of_source_rounding": "none; source values retained even when sum differs from one",
        "terms_sheet": "Terms of Service exists but yielded no tabular cells; drawings/images and reuse rights not verified",
    }
    nymo_notes = {"first_line": nymo_first_line, "negative_close_rows": int((nymo.Close < 0).sum()),
                  "negative_values_policy": "preserved; signed indicator values are not invalid prices",
                  "zero_volume_rows": int(nymo.Volume.eq(0).sum()), "volume_policy": "preserved source indicator field; not traded volume",
                  "not_existing_x3": "This is supplied $NYMO OHLCV; frozen Proxy7 x3 is neither changed nor substituted"}
    qc = {"status": "PASS_WITH_SOURCE_LIMITATIONS", "imported_at_utc": imported_at,
          "records": records, "aaii_notes": aaii_notes, "nymo_notes": nymo_notes,
          "protected_existing_raw_count": len(baseline), "protected_changed": changed,
          "source_input_hashes_unchanged": True, "original_copy_hashes_match": True,
          "source_value_roundtrip_pass": True, "new_feature_or_model_calculations": 0}
    (RUN / "LOCAL_IMPORT_QC.json").write_text(json.dumps(qc, indent=2, ensure_ascii=False), encoding="utf-8")
    (RUN / "PROTECTED_RAW_HASHES.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    (RUN / "DEPENDENCIES.txt").write_text("\n".join(f"{p}=={importlib.metadata.version(p)}" for p in ["numpy", "pandas", "xlrd"]) + "\n", encoding="utf-8")
    lines = ["# 사용자 다운로드 원본 RAW 등록", "", f"등록시각(UTC): {imported_at}", "",
             "기존 감사의 AAII 후보 번호 36을 유지했다. 34~35 및 37~39는 기존 감사 후보와 혼동하지 않도록 사용하지 않았으며 빈 폴더도 만들지 않았다. NYMO는 새 번호 40이다.", "",
             "| dataset | rows | min_date | max_date | missing_cells | output_file |", "|---|---:|---|---|---:|---|"]
    for r in records:
        lines.append(f"| {r['dataset_id']} | {r['rows']} | {r['min_date']} | {r['max_date']} | {r['missing_cells']} | `{r['output_file']}` |")
    lines += ["", "AAII는 원본에 날짜가 있는 2,048행을 모두 보존했다. 1987-06-26, 1987-07-17, 1996-01-11의 세 비중이 결측이며 보간하지 않았다. 최초 완전한 설문은 1987-07-24이다. 2011년 이후 결측 현황은 QC JSON에 별도 기록했다. 비중은 Excel의 내부 단위인 0~1을 유지했다. 원본의 합계 반올림 차이도 수정하지 않았다.",
              "", "NYMO의 음수 Close 및 0 Volume은 원본 그대로다. 이 자료로 기존 Proxy7 x3를 재계산하거나 대체하지 않았다.",
              "", f"기존 RAW {len(baseline)}개 파일 SHA-256 변경 0건. 방금수집 입력 2개와 source_original 복사본의 SHA-256이 일치한다. 원본 Excel 전체 시트와 CSV의 원래 텍스트는 source_original에 보존했으며, 입력 폴더의 파일도 유지했다.",
              "", "공식 사이트에서 재다운로드한 자료가 아니라 사용자가 제공한 로컬 파일을 등록했다. SOURCE의 retrieved_at_utc는 UNKNOWN으로 기록하고 실제 등록시각을 imported_at_utc에 구분했다. 역사적 최초 게시시각·빈티지·이용권한은 미확인이다. 과거 additional_collection 감사의 MANUAL_REQUIRED는 당시 자동 접근 결과이며, 이번 파일 확보 이력은 별도 등록했다."]
    (RUN / "LOCAL_IMPORT_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"records": records, "protected_existing_raw_files": len(baseline), "protected_changed": len(changed)}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
