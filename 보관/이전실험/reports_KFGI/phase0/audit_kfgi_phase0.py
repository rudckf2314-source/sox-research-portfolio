"""Audit preserved official KOSPI FGI JSON without altering study inputs."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIELDS = ["date", "fgi_score", "kospi_close", "regime"]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            if "href" in d:
                self.links.append(d["href"])


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def main():
    history = json.loads((OUT / "KFGI_HISTORY_RAW.json").read_bytes())
    latest = json.loads((OUT / "KFGI_LATEST_RAW.json").read_bytes())
    charts = json.loads((OUT / "KFGI_COMPONENT_CHARTS_RAW.json").read_bytes())
    assert isinstance(history, list) and all(isinstance(x, dict) for x in history)
    with (OUT / "KFGI_HISTORY_DAILY.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in history:
            w.writerow({k: row.get(k) for k in FIELDS})
    dates = [datetime.strptime(x["date"], "%Y-%m-%d").date() for x in history]
    scores = [x.get("fgi_score") for x in history]
    closes = [x.get("kospi_close") for x in history]
    missing = {k: sum(x.get(k) is None or x.get(k) == "" for x in history) for k in FIELDS}
    type_counts = {k: dict(Counter(type(x.get(k)).__name__ for x in history)) for k in FIELDS}
    dup = len(dates) - len(set(dates))
    invalid_score = sum(not isinstance(x, (int, float)) or isinstance(x, bool) or not 0 <= x <= 100 for x in scores)
    invalid_close = sum(not isinstance(x, (int, float)) or isinstance(x, bool) or x <= 0 for x in closes)
    def expected_regime(score):
        if score < 25: return "extreme_fear"
        if score <= 44: return "fear"
        if score <= 55: return "neutral"
        if score <= 75: return "greed"
        return "extreme_greed"
    regime_mismatches = [x["date"] for x in history if expected_regime(x["fgi_score"]) != x.get("regime")]
    krx_path = ROOT / "data/raw/01_kodex_091160/01_kodex_091160_RAW_20110101_20261007.csv"
    krx_dates = set(pd.read_csv(krx_path, comment="#", usecols=["Date"])["Date"])
    ref_max = max(krx_dates)
    comparable = [x for x in dates if x.isoformat() <= ref_max]
    missing_from_krx_ref = [x.isoformat() for x in comparable if x.isoformat() not in krx_dates]
    krx_in_span = [x for x in krx_dates if dates[0].isoformat() <= x <= min(dates[-1].isoformat(), ref_max)]
    missing_fgi_on_krx = sorted(set(krx_in_span) - {x.isoformat() for x in comparable})
    charts_list = charts.get("charts", [])
    factor_info = []
    for chart in charts_list:
        points = chart.get("points", [])
        point_dates = [x.get("date") for x in points if x.get("date")]
        factor_info.append({"key": chart.get("key"), "points": len(points), "min_date": min(point_dates) if point_dates else None,
                            "max_date": max(point_dates) if point_dates else None, "latest_score": chart.get("latest_score")})
    links = Links()
    links.feed((OUT / "KFGI_HOME_RAW.html").read_text(encoding="utf-8"))
    log = json.loads((OUT / "KFGI_API_REQUEST_LOG.json").read_text(encoding="utf-8"))
    variants = {}
    for r in log:
        if r.get("name", "").startswith("history"):
            obj = json.loads((ROOT / r["saved_file"]).read_bytes())
            variants[r["name"]] = {"rows": len(obj), "min_date": min((x["date"] for x in obj), default=None),
                                     "max_date": max((x["date"] for x in obj), default=None),
                                     "same_as_daily": obj == history}
    gaps = [(dates[i-1].isoformat(), dates[i].isoformat(), (dates[i]-dates[i-1]).days) for i in range(1,len(dates))]
    qc = {
        "status": "CONDITIONAL", "source": "https://www.kospifgi.com/", "history_rows": len(history),
        "history_min_date": min(dates).isoformat(), "history_max_date": max(dates).isoformat(),
        "history_ascending": dates == sorted(dates), "duplicate_dates": dup,
        "missing_cells_by_field": missing, "types_by_field": type_counts,
        "score_min": min(scores), "score_max": max(scores), "score_outside_0_100_or_nonnumeric": invalid_score,
        "kospi_close_min": min(closes), "kospi_close_max": max(closes), "nonpositive_or_nonnumeric_kospi_close": invalid_close,
        "regimes": dict(Counter(x.get("regime") for x in history)),
        "regime_vs_published_bands_mismatch_dates": regime_mismatches,
        "weekend_dates": [x.isoformat() for x in dates if x.weekday() >= 5],
        "max_calendar_gap_days": max(gaps, key=lambda x:x[2]),
        "krx_reference_file": krx_path.relative_to(ROOT).as_posix(), "krx_reference_max_date": ref_max,
        "fgi_dates_within_reference_period": len(comparable),
        "fgi_dates_absent_from_kodex_trading_dates": missing_from_krx_ref,
        "kodex_trading_dates_without_fgi_within_overlap": missing_fgi_on_krx,
        "fgi_dates_after_reference_max_unchecked": [x.isoformat() for x in dates if x.isoformat() > ref_max],
        "latest_matches_history_last_score": latest.get("date") == history[-1]["date"] and latest.get("fgi_score") == history[-1]["fgi_score"],
        "latest_json": latest, "history_query_variants": variants, "component_charts": factor_info,
        "home_links": sorted(set(links.links)),
        "source_hashes": {r["name"]:r.get("sha256") for r in log},
        "first_publication_timestamp": "UNVERIFIED", "past_0850_KST_availability": "UNVERIFIED",
        "weights_normalization_full_formula": "UNVERIFIED", "research_storage_use_terms": "UNVERIFIED",
        "external_kospi_full_series_match": "UNVERIFIED; only two historical media spot checks recorded in provenance",
    }
    (OUT / "KFGI_DATA_QC.json").write_text(json.dumps(qc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:qc[k] for k in ["history_rows","history_min_date","history_max_date","duplicate_dates","missing_cells_by_field","score_outside_0_100_or_nonnumeric","fgi_dates_within_reference_period","fgi_dates_absent_from_kodex_trading_dates","kodex_trading_dates_without_fgi_within_overlap","fgi_dates_after_reference_max_unchecked","history_query_variants"]},ensure_ascii=False))


if __name__ == "__main__": main()
