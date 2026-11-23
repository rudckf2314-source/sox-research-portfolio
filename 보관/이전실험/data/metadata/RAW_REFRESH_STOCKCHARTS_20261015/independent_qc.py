"""Independent read-back checks for the three versioned StockCharts RAW files."""

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
AUDIT = json.loads((Path(__file__).parent / "RAW_REFRESH_QC.json").read_text(encoding="utf-8"))
for dataset, info in AUDIT["datasets"].items():
    path = ROOT / info["new_file"]
    with path.open(encoding="utf-8") as handle:
        assert handle.readline().startswith("# SOURCE |")
    frame = pd.read_csv(path, comment="#")
    dates = pd.to_datetime(frame["Date"], errors="raise")
    assert len(frame) == 3970
    assert dates.min().date().isoformat() == "2011-01-03"
    assert dates.max().date().isoformat() == "2026-10-15"
    assert dates.is_unique and dates.is_monotonic_increasing
    assert not frame.isna().any().any()
    assert (frame.iloc[:, 1:] >= 0).all().all()
    if dataset == "07_cboe_put_call":
        assert (frame["Total_Put_Call_Ratio"] > 0).all()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == info["new_sha256"]
    old = ROOT / info["old_file"]
    assert hashlib.sha256(old.read_bytes()).hexdigest() == info["old_sha256"]
    source_path = ROOT / AUDIT["source_directory"]
    for source_name, expected in info["source_sha256"].items():
        assert hashlib.sha256((source_path / source_name).read_bytes()).hexdigest() == expected
    print(dataset, "PASS", "rows", len(frame), "min", dates.min().date(),
          "max", dates.max().date(), "max_gap_days", dates.diff().dt.days.max(),
          "last", frame.tail(1).to_dict("records"))
