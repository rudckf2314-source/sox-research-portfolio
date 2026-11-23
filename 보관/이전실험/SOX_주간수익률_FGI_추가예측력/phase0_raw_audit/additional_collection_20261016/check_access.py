"""Record only public HTTP access checks; do not bypass denial or authentication."""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

targets = {
    "BLS_calendar_2011": "https://www.bls.gov/schedule/2011/home.htm",
    "BLS_robots": "https://www.bls.gov/robots.txt",
    "AAII_history_page": "https://www.aaii.com/sentimentsurvey/sent_results",
    "AAII_history_excel": "https://www.aaii.com/files/surveys/sentiment.xls",
    "Federal_Reserve_calendar": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
}
results = []
for name, url in targets.items():
    result = {"name": name, "url": url, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "research-data-audit/1.0 (noncommercial academic source audit)"})
        head = r.content[:2000].decode("utf-8", errors="ignore").lower()
        result.update({"http_status": r.status_code, "content_type": r.headers.get("content-type", ""),
                       "bytes": len(r.content), "access_denied_text": "access denied" in head,
                       "bot_challenge_text": "pardon our interruption" in head,
                       "valid_excel": name == "AAII_history_excel" and r.content[:8] == bytes.fromhex("d0cf11e0a1b11ae1")})
    except requests.RequestException as exc:
        result.update({"error": type(exc).__name__ + ": " + str(exc)[:200]})
    results.append(result)
    print(name, result.get("http_status", result.get("error", "ERROR")), flush=True)
Path(__file__).with_name("ACCESS_TEST_LOG.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
