"""Build seven deterministic US-market sentiment proxies from immutable RAW CSVs."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "sentiment_features"
FILES = {
    "04": RAW / "04_sp500" / "04_sp500_RAW_20110101_20261007.csv",
    "05": RAW / "05_nyse_high_low" / "05_nyse_high_low_RAW_20110101_20261007.csv",
    "06": RAW / "06_nyse_breadth" / "06_nyse_breadth_RAW_20110101_20261007.csv",
    "07": RAW / "07_cboe_put_call" / "07_cboe_put_call_RAW_20110101_20261006.csv",
    "08": RAW / "08_vix" / "08_vix_RAW_20110101_20261007.csv",
    "09": RAW / "09_ief" / "09_ief_RAW_20110101_20261007.csv",
    "10": RAW / "10_hyg" / "10_hyg_RAW_20110101_20261007.csv",
}
FEATURES = [
    "x1_momentum", "x2_price_strength", "x3_breadth", "x4_put_call",
    "x5_volatility", "x6_safe_haven", "x7_junk_bond",
]


def load(key: str, columns: list[str]) -> pd.DataFrame:
    path = FILES[key]
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig") as handle:
        if not handle.readline().startswith("# SOURCE |"):
            raise ValueError(f"Missing SOURCE metadata: {path}")
    frame = pd.read_csv(path, comment="#")
    if not {"Date", *columns}.issubset(frame.columns):
        raise ValueError(f"Required columns missing in {path}: {frame.columns.tolist()}")
    frame = frame[["Date", *columns]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="raise")
    if frame.Date.isna().any() or frame.Date.duplicated().any():
        raise ValueError(f"Missing or duplicate Date in {path}")
    for name in columns:
        frame[name] = pd.to_numeric(frame[name], errors="raise")
        if np.isinf(frame[name]).any():
            raise ValueError(f"Infinite input in {path}: {name}")
    return frame.sort_values("Date", kind="stable").reset_index(drop=True)


def adjusted_column(key: str) -> str:
    path = FILES[key]
    columns = pd.read_csv(path, comment="#", nrows=2).columns.tolist()
    print(f"{key} price columns: {columns}")
    print(pd.read_csv(path, comment="#", nrows=2).to_string(index=False))
    if "Adj Close" not in columns:
        raise ValueError(f"Adjusted price unavailable or ambiguous in {path}; columns={columns}")
    return "Adj Close"


def assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-11):
        raise AssertionError(f"{label}: {actual} != {expected}")


def sample_positions(count: int) -> list[int]:
    if count < 5:
        raise AssertionError("Fewer than five valid observations for sample QC")
    return np.linspace(0, count - 1, 5, dtype=int).tolist()


def main() -> None:
    # Verify adjusted columns before generating any deliverable.
    adjusted_column("09")
    adjusted_column("10")
    sp = load("04", ["Close"])
    high_low = load("05", ["New_Highs_52W", "New_Lows_52W"])
    breadth = load("06", ["Advancing_Volume", "Declining_Volume"])
    cpc = load("07", ["Total_Put_Call_Ratio"])
    vix_raw = load("08", ["VIXCLS"])
    ief = load("09", ["Adj Close"])
    hyg = load("10", ["Adj Close"])

    sp["x1_momentum"] = sp.Close / sp.Close.rolling(125, min_periods=125).mean() - 1
    denom = high_low.New_Highs_52W + high_low.New_Lows_52W
    high_low["x2_price_strength"] = (
        (high_low.New_Highs_52W - high_low.New_Lows_52W) / denom.where(denom.ne(0))
    )
    breadth_denom = breadth.Advancing_Volume + breadth.Declining_Volume
    breadth["breadth_ratio"] = (
        (breadth.Advancing_Volume - breadth.Declining_Volume)
        / breadth_denom.where(breadth_denom.ne(0))
    )
    ratio = breadth.breadth_ratio
    oscillator = (ratio.ewm(span=19, adjust=False, min_periods=19).mean()
                  - ratio.ewm(span=39, adjust=False, min_periods=39).mean())
    oscillator = oscillator.where(ratio.notna())
    first_osc = oscillator.first_valid_index()
    if first_osc is None:
        raise ValueError("No valid breadth oscillator")
    # First valid cumulative value is exactly zero, with one forward pass.
    breadth["x3_breadth"] = oscillator.cumsum() - oscillator.iloc[first_osc]
    breadth.loc[:first_osc - 1, "x3_breadth"] = np.nan
    breadth.loc[first_osc, "x3_breadth"] = 0.0

    cpc["x4_put_call"] = -cpc.Total_Put_Call_Ratio.rolling(5, min_periods=5).mean()
    # FRED includes both blank holidays and 33 nonblank closed-market dates.
    # SP500's actual US equity sessions distinguish those from trading observations.
    vix_nonmissing = vix_raw.dropna(subset=["VIXCLS"])
    vix_closed_days = vix_nonmissing.loc[~vix_nonmissing.Date.isin(sp.Date)]
    vix = vix_nonmissing.loc[vix_nonmissing.Date.isin(sp.Date)].reset_index(drop=True).copy()
    vix["vix_ma50"] = vix.VIXCLS.rolling(50, min_periods=50).mean()
    vix["x5_volatility"] = -(vix.VIXCLS / vix.vix_ma50 - 1)
    sp["sp500_ret20"] = sp.Close / sp.Close.shift(20) - 1
    ief["ief_ret20"] = ief["Adj Close"] / ief["Adj Close"].shift(20) - 1
    hyg["hyg_ret20"] = hyg["Adj Close"] / hyg["Adj Close"].shift(20) - 1
    safe = sp[["Date", "sp500_ret20"]].merge(
        ief[["Date", "ief_ret20"]], on="Date", how="outer", validate="one_to_one"
    ).sort_values("Date")
    safe["x6_safe_haven"] = safe.sp500_ret20 - safe.ief_ret20
    junk = hyg[["Date", "hyg_ret20"]].merge(
        ief[["Date", "ief_ret20"]], on="Date", how="outer", validate="one_to_one"
    ).sort_values("Date")
    junk["x7_junk_bond"] = junk.hyg_ret20 - junk.ief_ret20

    individual = {
        "x1_momentum": sp[["Date", "x1_momentum"]],
        "x2_price_strength": high_low[["Date", "x2_price_strength"]],
        "x3_breadth": breadth[["Date", "x3_breadth"]],
        "x4_put_call": cpc[["Date", "x4_put_call"]],
        "x5_volatility": vix[["Date", "x5_volatility"]],
        "x6_safe_haven": safe[["Date", "x6_safe_haven"]],
        "x7_junk_bond": junk[["Date", "x7_junk_bond"]],
    }
    result = individual[FEATURES[0]].copy()
    for feature in FEATURES[1:]:
        result = result.merge(individual[feature], on="Date", how="outer", validate="one_to_one")
    result = result.sort_values("Date").reset_index(drop=True)

    checks: list[tuple[str, bool, str]] = []
    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append((name, bool(passed), detail))

    check("Date ascending and unique", result.Date.is_monotonic_increasing and not result.Date.duplicated().any())
    check("x1 first valid at session 125", sp.loc[sp.x1_momentum.first_valid_index(), "Date"] == sp.loc[124, "Date"])
    check("x3 first valid at session 39, baseline zero", first_osc == 38 and breadth.loc[first_osc, "x3_breadth"] == 0)
    check("x4 first valid at session 5", cpc.loc[cpc.x4_put_call.first_valid_index(), "Date"] == cpc.loc[4, "Date"])
    check("x5 first valid at valid VIX session 50", vix.loc[vix.x5_volatility.first_valid_index(), "Date"] == vix.loc[49, "Date"])
    for name, frame in [("x6", safe), ("x7", junk)]:
        feature = "x6_safe_haven" if name == "x6" else "x7_junk_bond"
        check(f"{name} first valid follows both 20-session returns",
              frame.loc[frame[feature].first_valid_index(), "Date"] ==
              frame.loc[frame.iloc[:, 1:3].notna().all(axis=1).idxmax(), "Date"])
    check("x2 within [-1,1]", high_low.x2_price_strength.dropna().between(-1, 1).all())
    check("breadth ratio within [-1,1]", breadth.breadth_ratio.dropna().between(-1, 1).all())
    check("VIX uses observed US equity sessions only",
          vix.Date.isin(sp.Date).all(),
          f"{len(vix_closed_days)} nonblank FRED dates outside SP500 sessions excluded")
    check("No infinite output", not np.isinf(result[FEATURES].to_numpy(dtype=float)).any())
    check("No NaN to zero replacement", all(
        individual[feature][feature].isna().sum() == result[feature].isna().sum()
        - (len(result) - len(individual[feature])) for feature in FEATURES
    ))

    for i in sample_positions(len(cpc) - 4):
        j = i + 4
        expected = -float(cpc.Total_Put_Call_Ratio.iloc[j - 4:j + 1].sum() / 5)
        assert_close(float(cpc.x4_put_call.iloc[j]), expected, f"x4 {cpc.Date.iloc[j].date()}")
    check("x4 five independent SMA5 samples", True)
    for i in sample_positions(len(vix) - 49):
        j = i + 49
        expected = -(float(vix.VIXCLS.iloc[j]) /
                     float(vix.VIXCLS.iloc[j - 49:j + 1].sum() / 50) - 1)
        assert_close(float(vix.x5_volatility.iloc[j]), expected, f"x5 {vix.Date.iloc[j].date()}")
    check("x5 five independent VIX/MA50 samples", True)
    for name, frame, left, right, left_col, right_col in [
        ("x6", safe, sp, ief, "Close", "Adj Close"),
        ("x7", junk, hyg, ief, "Adj Close", "Adj Close"),
    ]:
        valid = frame.loc[frame[f"{name}_safe_haven" if name == "x6" else "x7_junk_bond"].notna(), "Date"]
        left_index = left.set_index("Date")
        right_index = right.set_index("Date")
        for pos in sample_positions(len(valid)):
            date = valid.iloc[pos]
            li = left_index.index.get_loc(date)
            ri = right_index.index.get_loc(date)
            expected = (left_index[left_col].iloc[li] / left_index[left_col].iloc[li - 20] - 1
                        - (right_index[right_col].iloc[ri] / right_index[right_col].iloc[ri - 20] - 1))
            actual = frame.set_index("Date").loc[date, "x6_safe_haven" if name == "x6" else "x7_junk_bond"]
            assert_close(float(actual), float(expected), f"{name} {date.date()}")
        check(f"{name} five independent 20-session return samples", True)

    specs = {
        "x1_momentum": ("04", "Close", "Close / SMA125(Close) - 1"),
        "x2_price_strength": ("05", "New_Highs_52W;New_Lows_52W", "(highs-lows)/(highs+lows)"),
        "x3_breadth": ("06", "Advancing_Volume;Declining_Volume", "cumsum(EMA19(breadth_ratio)-EMA39(breadth_ratio)) - first oscillator"),
        "x4_put_call": ("07", "Total_Put_Call_Ratio", "-SMA5(Total_Put_Call_Ratio)"),
        "x5_volatility": ("08", "VIXCLS", "-(VIXCLS/SMA50(VIXCLS)-1)"),
        "x6_safe_haven": ("04;09", "Close;Adj Close", "SP500 Close return20 - IEF Adj Close return20"),
        "x7_junk_bond": ("10;09", "Adj Close;Adj Close", "HYG Adj Close return20 - IEF Adj Close return20"),
    }
    qc_rows = []
    for feature in FEATURES:
        key, cols, formula = specs[feature]
        series = result[feature]
        valid = result.loc[series.notna(), "Date"]
        source_files = ";".join(FILES[k].name for k in key.split(";"))
        qc_rows.append({
            "record_type": "feature", "name": feature, "status": "PASS",
            "source_file": source_files, "source_columns": cols, "formula": formula,
            "total_rows": len(result), "valid_rows": int(series.notna().sum()),
            "missing_rows": int(series.isna().sum()),
            "first_valid_date": valid.min().date().isoformat(),
            "last_valid_date": valid.max().date().isoformat(),
            "min": series.min(), "max": series.max(), "mean": series.mean(),
            "median": series.median(), "duplicate_dates": int(result.Date.duplicated().sum()),
            "positive_inf": int(np.isposinf(series).sum()),
            "negative_inf": int(np.isneginf(series).sum()), "detail": "",
        })
    for name, passed, detail in checks:
        qc_rows.append({"record_type": "check", "name": name,
                        "status": "PASS" if passed else "FAIL", "detail": detail})
    if not all(passed for _, passed, _ in checks):
        raise AssertionError("QC failed: " + ", ".join(name for name, passed, _ in checks if not passed))
    if result.Date.min() != pd.Timestamp("2011-01-03") or result.Date.max() != pd.Timestamp("2026-10-07"):
        raise AssertionError("Unexpected output date range")

    dictionary = """# Seven US market sentiment proxies

Source datasets: 04_sp500, 05_nyse_high_low, 06_nyse_breadth, 07_cboe_put_call, 08_vix, 09_ief, 10_hyg. Source paths and source columns are recorded in the QC CSV. No CNN FGI data are used.

All windows count each source's observed US-market sessions. Calculations move forward in Date order and use only current and past observations. The feature series are outer-merged on Date after calculation. Missing values stay missing; no forward-fill, backfill, interpolation, clipping, or winsorization is applied. Date is not aligned to KRX at this stage. For VIX only, nonblank FRED values on dates absent from the S&P 500 trading-session calendar are excluded from the 50-session calculation: those dates are closed US equity sessions, not additional observations. The number excluded is recorded in QC; the VIX RAW file remains intact.

| Feature | Definition | Direction / initial missing period |
| --- | --- | --- |
| x1_momentum | S&P 500 canonical Close / 125-session simple mean of Close − 1 | Higher = greed; first 124 S&P observations missing. |
| x2_price_strength | (NYSE 52-week new highs − new lows) / (new highs + new lows) | Higher = greed; zero denominator gives NaN. |
| x3_breadth | breadth_ratio = (NYSE advancing volume − declining volume)/(advancing + declining); oscillator = EMA19(breadth_ratio) − EMA39(breadth_ratio), pandas adjust=False; x3 = cumulative oscillator minus its first valid value | Higher = greed; min_periods 19/39, first 38 observations missing; first valid cumulative value exactly 0. One forward cumulative sequence over all dates, never reset by validation fold. Zero denominator gives NaN. |
| x4_put_call | Negative of 5-session simple mean of Cboe Total Put/Call Ratio | Higher = greed; first 4 CPC observations missing; no inverse/log. |
| x5_volatility | Negative of (VIX / 50-observation simple mean of VIX − 1) | Higher = greed; first 49 observed US equity-session VIX values missing. FRED holiday rows without VIX and nonblank values on closed equity sessions are excluded from the window, not filled. |
| x6_safe_haven | S&P 500 Close 20-observation return minus IEF Adj Close 20-observation return | Higher = greed; each return calculated on its own source dates before Date matching. |
| x7_junk_bond | HYG Adj Close 20-observation return minus IEF Adj Close 20-observation return | Higher = greed; public price-based risk-bond preference proxy, **not** a reconstruction of CNN's original yield-spread indicator. |

Zero denominator produces NaN. 20-observation return is price at t divided by price 20 observations earlier, minus one. The first valid x3 value is an explicit zero baseline, not missing-value imputation. Actual source coverage differs: CPC and VIX end on 2026-10-06; the output reaches 2026-10-07 through other sources.
"""
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "sentiment_proxy7_20110103_20261007.csv"
    metadata = ("# SOURCE | dataset_id=sentiment_proxy7 | source_datasets=04_sp500;05_nyse_high_low;"
                "06_nyse_breadth;07_cboe_put_call;08_vix;09_ief;10_hyg | definition=Seven public US market "
                "sentiment proxy features for FGI representation study | transformation=pre-specified deterministic "
                "feature engineering; no interpolation; no future data; x3 cumulative EMA19-EMA39 oscillator "
                "starts at zero on first valid observation; x7 is a price-based risk-bond proxy, not CNN yield spread")
    with output.open("w", encoding="utf-8", newline="") as handle:
        handle.write(metadata + "\n")
        result.to_csv(handle, index=False, date_format="%Y-%m-%d", float_format="%.15g")
    qc_path = OUT / "sentiment_proxy7_QC.csv"
    pd.DataFrame(qc_rows).to_csv(qc_path, index=False)
    dictionary_path = OUT / "sentiment_proxy7_FEATURE_DICTIONARY.md"
    dictionary_path.write_text(dictionary, encoding="utf-8")
    reread = pd.read_csv(output, comment="#")
    if len(reread) != len(result) or reread.columns.tolist() != ["Date", *FEATURES]:
        raise AssertionError("Saved output structure differs from in-memory output")
    print(f"Output: {output}\nQC: {qc_path}\nDictionary: {dictionary_path}")
    print(f"Date rows: {len(result)}; range: {result.Date.min().date()} to {result.Date.max().date()}")
    print(pd.DataFrame(qc_rows[:7])[["name", "valid_rows", "missing_rows", "first_valid_date", "last_valid_date"]].to_string(index=False))
    print(f"QC: PASS ({len(checks)} checks)")
    print(f"Warning: CPC ends {cpc.Date.max().date()}; VIX ends {vix.Date.max().date()}; no values filled.")
    print(f"Warning: {len(vix_closed_days)} nonblank FRED VIX dates outside SP500 trading sessions excluded from VIX window.")


if __name__ == "__main__":
    main()
