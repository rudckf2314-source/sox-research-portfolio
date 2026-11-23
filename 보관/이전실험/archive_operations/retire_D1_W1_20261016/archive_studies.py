"""Archive retired D1/W1 byte-for-byte before a separate, verified deletion.

This script never deletes source files. ZIP creation is followed by streaming
SHA-256 and CRC checks of every member, then a native PowerShell transfer and
explicit source-deletion step. Research C and shared sources remain active.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
DELETE_DIRS = ["reports_D1", "phase_report_D1", "data/processed_D1", "reports_W1", "phase_report_W1", "data/processed_W1"]
UNBACKED_ENV_DIRS = [".venv", ".venv_W1"]  # User explicitly excluded environment binaries from compression.
DELETE_FILES = ["D1_LIGHT_ARCHIVE_PACKAGING.json", "D1_LIGHT_ARCHIVE_README.md", "D1_MIGRATION_GUIDE.md", "D1_MIGRATION_MAP.csv", "D1_MIGRATION_QC.json", "FGI_RESEARCH_MASTER_PLAN_FINAL.md", "folder_structure.txt"]
SHARED_DIRS = ["data/raw", "data/metadata", "freeze", "stockcharts", "config", "scripts"]
SHARED_FILES = ["KODEX_반도체_20261013.xls", "RESEARCH_PROJECT_INDEX.md"]
PROTECTED_DIRS = SHARED_DIRS + ["research_C", "reports_KFGI", "방금수집"]
PROTECTED_FILES = ["KODEX_반도체_20261013.xls", ".env"]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def write_json(name, data):
    (RUN / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def safe(path):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(ROOT.resolve()) or resolved == ROOT.resolve():
        raise ValueError(f"Path outside workspace: {path}")
    if path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"Reparse point not allowed: {path}")
    return path


def files_under(relative):
    start = safe(ROOT / relative)
    if start.is_file():
        return [start]
    files = []
    for current, dirs, names in os.walk(start, followlinks=False):
        for entry in dirs + names:
            safe(Path(current) / entry)
        files.extend(Path(current) / name for name in names)
    return sorted(files)


def snapshot(paths):
    return {p.relative_to(ROOT).as_posix(): digest(p) for relative in paths for p in files_under(relative)}


def log(message):
    print(message, flush=True)
    with (RUN / "ARCHIVE_PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(datetime.now(timezone.utc).isoformat() + " " + message + "\n")


def build():
    if (RUN / "ARCHIVE_VERIFIED.json").exists():
        raise FileExistsError("Archive already verified; refusing another run")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"FGI_D1_W1_FULL_BACKUP_{timestamp}.zip"
    archive_path = RUN / name
    if archive_path.exists():
        raise FileExistsError(archive_path)
    log("Inventory and source SHA-256 checks started")
    records = []
    for disposition, roots in [("delete_after_verified_backup", DELETE_DIRS + DELETE_FILES), ("keep_shared_original", SHARED_DIRS + SHARED_FILES)]:
        for relative in roots:
            for p in files_under(relative):
                records.append({"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size,
                                "sha256": digest(p), "disposition": disposition})
            log(f"Inventoried {relative}")
    assert len(records) == len({r["path"] for r in records})
    records.sort(key=lambda r: r["path"])
    environments = []
    for relative in UNBACKED_ENV_DIRS:
        environment = ROOT / relative
        environment_files = files_under(relative)
        packages = []
        for metadata in sorted(environment.glob("Lib/site-packages/*.dist-info/METADATA")):
            name_value, version_value = "", ""
            with metadata.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("Name: "):
                        name_value = line[6:].strip()
                    elif line.startswith("Version: "):
                        version_value = line[9:].strip()
                    elif not line.strip():
                        break
            packages.append({"name": name_value, "version": version_value})
        environments.append({"path": relative, "files": len(environment_files),
                             "bytes": sum(p.stat().st_size for p in environment_files),
                             "pyvenv_cfg": (environment / "pyvenv.cfg").read_text(encoding="utf-8"),
                             "installed_distribution_metadata": packages,
                             "disposition": "delete_without_binary_backup_as_user_requested"})
    write_json("ENVIRONMENTS_REBUILD_INFO.json", environments)
    log("Snapshotting retained Research C/shared inputs")
    protected = snapshot(PROTECTED_DIRS + PROTECTED_FILES)
    write_json("PROTECTED_INPUT_HASHES.json", protected)
    manifest = {"schema": "D1-W1-retirement-archive-v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "original_root": str(ROOT), "archive_root": "fgi_pilot", "delete_directories": DELETE_DIRS,
                "delete_files": DELETE_FILES, "environment_directories_excluded_by_user": UNBACKED_ENV_DIRS,
                "shared_originals_to_keep": SHARED_DIRS + SHARED_FILES,
                "excluded": ["research_C", "reports_KFGI", "방금수집", ".env", *UNBACKED_ENV_DIRS],
                "note": "Current existing files are preserved. Historical manifest differences are not silently repaired. Shared snapshots reflect current RAW; original historical runs may reference older vintages.",
                "files": records}
    write_json("ARCHIVE_FILE_MANIFEST.json", manifest)
    total_bytes = sum(r["bytes"] for r in records)
    log(f"Creating ZIP: {len(records)} files; {total_bytes} source bytes")
    last_notice = time.monotonic()
    done_bytes = 0
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True, strict_timestamps=False) as archive:
        for i, record in enumerate(records, 1):
            archive.write(ROOT / record["path"], "fgi_pilot/" + record["path"])
            done_bytes += record["bytes"]
            if time.monotonic() - last_notice >= 10:
                log(f"ZIP {i}/{len(records)} files; {done_bytes / 1048576:.1f} MiB processed")
                last_notice = time.monotonic()
        archive.writestr("_ARCHIVE_FILE_MANIFEST.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr("ENVIRONMENTS_REBUILD_INFO.json", json.dumps(environments, indent=2, ensure_ascii=False))
        archive.writestr("RESTORE_README.md", """# D1/W1 full retirement backup

This ZIP preserves all existing D1/W1 reports, processed data, 100 final models,
checkpoints, code and supporting root documents under fgi_pilot/.
It also includes snapshots of shared RAW, metadata, frozen Proxy7, StockCharts,
source configuration, collection scripts and the original Samsung KODEX file.
Those shared originals are kept in the active Research C project.

Restore to a separate directory, preserving all relative paths. The original
project index and master plan are inside this archive. Compare every file with
_ARCHIVE_FILE_MANIFEST.json. The user excluded virtual-environment binaries
from compression and authorized retirement cleanup. Recreate environments from
archived package locks and ENVIRONMENTS_REBUILD_INFO.json when necessary.
The former root .venv already referenced a missing Python312.

This is a current-state backup, not a new reproduction of any research result.
Older D1 code hashes may differ following approved path migration. Missing
historical files have not been invented. Current shared RAW may have been
updated after D1/W1 execution; historical source hashes remain in old reports.

Research C, independent KFGI audit, and current credentials (.env) are excluded.
No model was retrained and no prediction was recalculated for this backup.
""")
    log("ZIP written; verifying each member SHA-256 and CRC")
    with zipfile.ZipFile(archive_path, "r") as archive:
        expected_names = {"fgi_pilot/" + r["path"] for r in records} | {"_ARCHIVE_FILE_MANIFEST.json", "RESTORE_README.md", "ENVIRONMENTS_REBUILD_INFO.json"}
        assert set(archive.namelist()) == expected_names and len(archive.namelist()) == len(expected_names)
        archived_manifest = json.loads(archive.read("_ARCHIVE_FILE_MANIFEST.json"))
        assert archived_manifest == manifest
        assert json.loads(archive.read("ENVIRONMENTS_REBUILD_INFO.json")) == environments
        last_notice = time.monotonic()
        for i, record in enumerate(records, 1):
            h = hashlib.sha256()
            with archive.open("fgi_pilot/" + record["path"]) as member:
                for block in iter(lambda: member.read(1048576), b""):
                    h.update(block)
            assert h.hexdigest() == record["sha256"], record["path"]
            if time.monotonic() - last_notice >= 10:
                log(f"Verified {i}/{len(records)} member hashes and CRCs")
                last_notice = time.monotonic()
    changes = [p for p, h in protected.items() if not (ROOT / p).is_file() or digest(ROOT / p) != h]
    assert not changes, changes
    backed_delete_bytes = sum(r["bytes"] for r in records if r["disposition"] == "delete_after_verified_backup")
    env_delete_bytes = sum(e["bytes"] for e in environments)
    delete_bytes = backed_delete_bytes + env_delete_bytes
    result = {"status": "ARCHIVE_VERIFIED_NOT_DELETED", "archive_path": str(archive_path),
              "download_path": str(Path(os.environ["USERPROFILE"]) / "Downloads" / name),
              "archive_sha256": digest(archive_path), "archive_bytes": archive_path.stat().st_size,
              "source_file_count": len(records), "source_bytes": total_bytes,
              "deletion_file_count": sum(r["disposition"] == "delete_after_verified_backup" for r in records) + sum(e["files"] for e in environments),
              "backed_up_deletion_bytes": backed_delete_bytes, "excluded_environment_bytes": env_delete_bytes,
              "deletion_bytes": delete_bytes, "shared_snapshot_bytes": total_bytes - backed_delete_bytes,
              "verified_member_count": len(records), "crc_and_sha256_pass": True,
              "protected_file_count": len(protected), "protected_changes": changes,
              "expected_net_disk_bytes_reclaimed": delete_bytes - archive_path.stat().st_size,
              "deleted": False}
    write_json("ARCHIVE_VERIFIED.json", result)
    log(json.dumps(result))


def predelete():
    result = json.loads((RUN / "ARCHIVE_VERIFIED.json").read_text(encoding="utf-8"))
    destination = Path(result["download_path"])
    assert destination.is_file() and destination.stat().st_size == result["archive_bytes"]
    assert digest(destination) == result["archive_sha256"], "Downloads archive hash mismatch"
    manifest = json.loads((RUN / "ARCHIVE_FILE_MANIFEST.json").read_text(encoding="utf-8"))
    listed = {r["path"]: r for r in manifest["files"] if r["disposition"] == "delete_after_verified_backup"}
    actual = {p.relative_to(ROOT).as_posix() for relative in DELETE_DIRS + DELETE_FILES for p in files_under(relative)}
    assert actual == set(listed), "Deletion target file set changed since backup"
    for relative, record in listed.items():
        assert digest(ROOT / relative) == record["sha256"], f"Source changed since backup: {relative}"
    protected = json.loads((RUN / "PROTECTED_INPUT_HASHES.json").read_text(encoding="utf-8"))
    assert all((ROOT / p).is_file() and digest(ROOT / p) == h for p, h in protected.items()), "Protected input changed"
    result["status"] = "DOWNLOADS_ARCHIVE_VERIFIED_SOURCE_DELETION_APPROVED"
    result["download_archive_sha256_verified"] = True
    result["source_file_set_and_hashes_reverified"] = True
    write_json("PREDELETE_QC.json", result)
    print(json.dumps({k: result[k] for k in ["status", "download_path", "archive_bytes", "deletion_file_count", "deletion_bytes"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["build", "predelete"])
    arguments = parser.parse_args()
    build() if arguments.mode == "build" else predelete()
