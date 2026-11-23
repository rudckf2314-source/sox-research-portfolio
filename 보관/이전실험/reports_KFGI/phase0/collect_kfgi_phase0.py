"""Read only public KOSPI FGI pages and preserve HTTP response bodies verbatim."""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "https://www.kospifgi.com"
URLS = [
    ("history_daily", BASE + "/fgi/history?interval_days=1&from=2011-01-01", "KFGI_HISTORY_RAW.json"),
    ("latest", BASE + "/fgi/latest", "KFGI_LATEST_RAW.json"),
    ("component_charts", BASE + "/fgi/components/charts", "KFGI_COMPONENT_CHARTS_RAW.json"),
    ("history_pre2024_to", BASE + "/fgi/history?interval_days=1&from=2011-01-01&to=2024-04-17", "KFGI_HISTORY_PRE2024_QUERY_RAW.json"),
    ("history_earlier_from", BASE + "/fgi/history?interval_days=1&from=2010-01-01", "KFGI_HISTORY_FROM2010_RAW.json"),
    ("history_default_daily", BASE + "/fgi/history?interval_days=1", "KFGI_HISTORY_DEFAULT_DAILY_RAW.json"),
    ("home", BASE + "/", "KFGI_HOME_RAW.html"),
    ("robots", BASE + "/robots.txt", "KFGI_ROBOTS_RAW.txt"),
    ("sitemap", BASE + "/sitemap.xml", "KFGI_SITEMAP_RAW.xml"),
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def protected_snapshot() -> dict[str, str]:
    targets = []
    for rel in ["data/raw", "freeze", "reports_D1", "reports_W1", "phase_report_D1", "phase_report_W1", "data/processed_W1"]:
        p = ROOT / rel
        if p.exists():
            targets.extend(x for x in p.rglob("*") if x.is_file())
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(targets))}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = protected_snapshot()
    records = []
    for name, url, filename in URLS:
        path = OUT / filename
        if path.exists():
            raise FileExistsError(path)
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research availability audit; read-only)"})
        retrieval = datetime.now(timezone.utc).isoformat()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                status = response.status
                headers = dict(response.headers.items())
                effective_url = response.url
        except urllib.error.HTTPError as ex:
            body = ex.read()
            status = ex.code
            headers = dict(ex.headers.items())
            effective_url = ex.url
        except Exception as ex:
            records.append({"name": name, "request_url": url, "retrieved_at_utc": retrieval, "error": type(ex).__name__ + ": " + str(ex)})
            continue
        path.write_bytes(body)
        records.append({"name": name, "request_url": url, "effective_url": effective_url,
                        "retrieved_at_utc": retrieval, "http_status": status,
                        "response_headers": headers, "body_bytes": len(body),
                        "sha256": sha(path), "saved_file": path.relative_to(ROOT).as_posix()})
    current = protected_snapshot()
    bad = [k for k, v in baseline.items() if current.get(k) != v]
    added = sorted(set(current) - set(baseline))
    audit = {"snapshot_count_before": len(baseline), "snapshot_count_after": len(current),
             "changed_or_missing": bad, "added_protected_files": added,
             "protected_snapshot_sha256": hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest()}
    (OUT / "KFGI_PROTECTED_FILE_AUDIT.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "KFGI_API_REQUEST_LOG.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert not bad and not added, audit
    print(json.dumps({"requests": [{"name": r["name"], "status": r.get("http_status"), "bytes": r.get("body_bytes"), "error": r.get("error")} for r in records],
                      "protected_files_unchanged": len(baseline)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
