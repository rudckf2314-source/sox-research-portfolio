"""Read-only comparison against archived D1/W1/Proxy7 manifests.

This is a historical-manifest comparison, not a substitute for a pre-run
snapshot. Former reports/ paths are resolved to the approved reports_D1/ tree.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def resolve(value):
    value = value.replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    prefix = "C:/fgi_pilot/"
    if value.lower().startswith(prefix.lower()):
        value = value[len(prefix):]
    if value.startswith("reports/"):
        value = "reports_D1/" + value[len("reports/"):]
    if value.startswith("phase_report/"):
        value = "phase_report_D1/" + value[len("phase_report/"):]
    return ROOT / value


specs = [
    ("reports_D1/phase4/PHASE4_MANIFEST.json", "output_sha256"),
    ("reports_D1/phase5/PHASE5_MANIFEST.json", "outputs_sha256"),
    ("reports_W1/phase4/W1_PHASE4_FILE_MANIFEST.json", "files"),
    ("reports_W1/phase5/W1_PHASE5_FILE_MANIFEST.json", "files"),
    ("freeze/proxy7_v1/FROZEN_MANIFEST.json", "frozen_files"),
]
results = []
for manifest, key in specs:
    document = json.loads((ROOT / manifest).read_text(encoding="utf-8-sig"))
    entries = document[key]
    entries = [{"path": p, "sha256": h} for p, h in entries.items()] if isinstance(entries, dict) else entries
    mismatches, missing, matched = [], [], 0
    for row in entries:
        path = resolve(row.get("path", row.get("frozen_path", "")))
        if not path.is_file():
            missing.append(str(path))
        elif digest(path) != row["sha256"]:
            mismatches.append(str(path))
        else:
            matched += 1
    results.append({"manifest": manifest, "manifest_sha256": digest(ROOT / manifest),
                    "entries": len(entries), "matched": matched, "missing": missing,
                    "historical_hash_mismatches": mismatches})
output = {"comparison_type": "current files versus historical manifests; no pre-run D1/W1 baseline was taken",
          "results": results, "status": "PASS" if all(not x["missing"] and not x["historical_hash_mismatches"] for x in results) else "CONDITIONAL"}
(RUN / "EXISTING_STUDIES_HASH_QC.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
print(json.dumps({"status": output["status"], "manifests": len(results),
                  "entries": sum(x["entries"] for x in results),
                  "matched": sum(x["matched"] for x in results),
                  "missing": sum(len(x["missing"]) for x in results),
                  "mismatches": sum(len(x["historical_hash_mismatches"]) for x in results)}))
