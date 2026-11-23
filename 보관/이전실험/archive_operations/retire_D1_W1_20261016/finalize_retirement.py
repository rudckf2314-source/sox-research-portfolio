"""Post-deletion protected-file and Research C runtime checks; no research execution."""
import hashlib
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


predelete = json.loads((RUN / "PREDELETE_QC.json").read_text(encoding="utf-8-sig"))
log = json.loads((RUN / "DELETION_LOG.json").read_text(encoding="utf-8-sig"))
protected = json.loads((RUN / "PROTECTED_INPUT_HASHES.json").read_text(encoding="utf-8"))
changes = [p for p, sha in protected.items() if not (ROOT / p).is_file() or digest(ROOT / p) != sha]
assert not changes, changes
assert log["DeletedTargetCount"] == log["ExpectedTargetCount"] == 11
assert all(not Path(p).exists() for p in log["DeletedTargets"])
archive = Path(predelete["download_path"])
assert archive.is_file() and digest(archive) == predelete["archive_sha256"]
# Import in the retained C interpreter without executing any research.
import numpy
import pandas
import requests
import openpyxl
import xlrd
assert Path(sys.prefix).resolve() == (ROOT / "research_C/phase0_raw_audit/.venv").resolve()
assert not any(str(ROOT / ".venv_W1").lower() in p.lower() for p in sys.path)
manifest = json.loads((RUN / "ARCHIVE_FILE_MANIFEST.json").read_text(encoding="utf-8"))
deleted_roots = [Path(p).relative_to(ROOT).as_posix() for p in log["DeletedTargets"]]
deleted_records = [r for r in manifest["files"] if any(r["path"] == p or r["path"].startswith(p + "/") for p in deleted_roots)]
actual_deleted_bytes = sum(r["bytes"] for r in deleted_records)
for relative in ["FGI_RESEARCH_MASTER_PLAN_FINAL.md", "folder_structure.txt"]:
    expected = next(r["sha256"] for r in manifest["files"] if r["path"] == relative)
    assert (ROOT / relative).is_file() and digest(ROOT / relative) == expected
retained_envs = [p for p in [".venv", ".venv_W1"] if (ROOT / p).is_dir()]
assert len(retained_envs) == 2
result = {**predelete, "status": "PASS_D1_W1_OUTPUT_CLEANUP_ENVIRONMENTS_RETAINED", "deleted": True,
          "deletion_bytes": actual_deleted_bytes, "deletion_file_count": len(deleted_records),
          "expected_net_disk_bytes_reclaimed": actual_deleted_bytes - predelete["archive_bytes"],
          "retained_environment_directories": retained_envs,
          "retained_master_plan_and_structure": True,
          "pending_explicit_approval": "Deletion of .venv and .venv_W1 without binary backup; automatic review rejected the broader scope as not clearly authorized",
          "deleted_target_count": log["DeletedTargetCount"], "retained_protected_files_verified": len(protected),
          "retained_protected_file_changes": changes, "research_C_environment_imports_pass": True,
          "research_C_python": sys.executable, "disk_free_bytes_after": shutil.disk_usage(ROOT).free,
          "remaining_raw_dataset_count": len([p for p in (ROOT / "data/raw").iterdir() if p.is_dir()]),
          "remaining_raw_csv_count": len(list((ROOT / "data/raw").glob("*/*RAW*.csv"))),
          "environment_versions": {p: importlib.metadata.version(p) for p in ["numpy", "pandas", "requests", "openpyxl", "xlrd"]}}
(RUN / "RETIREMENT_QC.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
gib = 1024 ** 3
report = f"""# D1·W1 연구 종료 보관 및 용량 정리

상태: PASS_D1_W1_OUTPUT_CLEANUP_ENVIRONMENTS_RETAINED

- 압축본: `{archive}`
- 압축본 SHA-256: `{result['archive_sha256']}`
- 압축 파일 크기: {result['archive_bytes']:,} bytes ({result['archive_bytes'] / 1048576:.1f} MiB)
- ZIP 원본 파일 수: {result['source_file_count']:,}. 모든 파일의 압축 내 CRC 및 SHA-256 일치.
- D1/W1 전용 삭제 파일 수(환경 포함): {result['deletion_file_count']:,}.
- 삭제 대상 원래 크기: {result['deletion_bytes'] / gib:.3f} GiB.
- 같은 C 드라이브에 남는 압축본을 차감한 파일 크기 기준 순 확보량: 약 {result['expected_net_disk_bytes_reclaimed'] / gib:.3f} GiB.

D1/W1 Phase 0~5 보고서·모델·전처리기·체크포인트·예측값·검증 코드, 전용 가공 데이터, 과거 마스터 플랜과 이관 문서를 보관했다. 재현용 공통 RAW·출처 기록·동결 Proxy7·StockCharts 원본·수집 코드·삼성 자료의 현재 스냅샷도 ZIP에 포함했다. 원본 위치는 ZIP의 `fgi_pilot/` 아래에 보존했다.

사용자 지시에 따라 `.venv`, `.venv_W1` 바이너리는 압축하지 않았다. 패키지 목록과 pyvenv.cfg만 `ENVIRONMENTS_REBUILD_INFO.json`에 기록했다. 자동 승인 검토가 공용 문서 및 비백업 환경의 삭제 승인 범위가 불명확하다는 이유로 넓은 삭제 요청을 거절했다. 따라서 두 환경(합계 1,088,878,996 bytes)과 공용 `FGI_RESEARCH_MASTER_PLAN_FINAL.md`, `folder_structure.txt`는 실제 삭제하지 않았다. 전용 데이터·모델·보고서·D1 이관 문서만 검증된 백업 후 삭제했다. 환경을 백업 없이 삭제하려면 명시적인 사용자 승인이 필요하다. 기존 root .venv는 이미 없는 Python312를 참조하던 상태였다.

연구 C 폴더와 가상환경, 공통 RAW {result['remaining_raw_dataset_count']}종, freeze, stockcharts, 공통 metadata·scripts·config, 삼성 KODEX 원본, KFGI 감사, 방금수집, .env는 유지했다. 보호 대상 {len(protected):,}개 기존 파일의 해시 변경은 0건이다. 연구 C 환경에서 NumPy/pandas/requests/openpyxl/xlrd import가 성공했다.

과거 보고서 및 매니페스트의 현재 폴더에 대한 참조는 이제 보관본을 가리키는 역사적 기록이다. 연구 C의 과거 보호해시 확인 스크립트는 삭제된 D1/W1 경로를 현 위치에서 다시 검사하면 누락을 보고할 수 있다. 이를 새 변조나 자료 손상으로 오인하지 않아야 한다. 원본 연구 결과를 재학습·재계산하지 않았다.

복원 시 별도 디렉터리에 ZIP을 풀고 `_ARCHIVE_FILE_MANIFEST.json`으로 바이트를 대조한다. 가상환경은 기록된 패키지 버전으로 재구성한다. 현재 RAW 스냅샷과 과거 연구 최초 실행 당시 빈티지의 동일성은 별개이며 기존 보고서의 해시 및 한계 기록을 참조한다.
"""
(RUN / "RETIREMENT_REPORT.md").write_text(report, encoding="utf-8")
index = f"""# 연구 프로젝트 인덱스

현재 진행 연구: 연구 C — SOX 비중첩 주간 부호수익률 예측 연구 준비.

- 작업 및 수집 감사: `research_C/phase0_raw_audit/`
- 공통 RAW: `data/raw/` ({result['remaining_raw_dataset_count']}종)
- 보존된 Proxy7 및 생성 코드: `freeze/proxy7_v1/`
- 원천 출처·갱신 이력: `data/metadata/`, `stockcharts/`, `scripts/`, `config/`
- 연구 C 실행환경: `research_C/phase0_raw_audit/.venv/`

D1·W1은 사용자 지시에 따라 추가 연구를 중단하고 전용 데이터·모델·보고서를 압축 보관한 뒤 작업 폴더에서 삭제했다. 두 예전 가상환경은 ZIP에서 제외했고, 백업 없는 삭제 승인이 불명확하다는 자동 검토 결과에 따라 현재 유지했다. 공용 마스터 플랜과 구조 문서도 유지했다.

- 보관본: `{archive}`
- 정리·무결성 보고서: `archive_operations/retire_D1_W1_20261016/RETIREMENT_REPORT.md`
- 파일 목록·해시: `archive_operations/retire_D1_W1_20261016/ARCHIVE_FILE_MANIFEST.json`
- 이전 D1/W1 마스터 플랜과 프로젝트 인덱스도 압축본에 보존되어 있다.

이 정리는 연구 C의 X/Y 생성이나 모델 학습을 시작하는 작업이 아니다.
"""
(ROOT / "RESEARCH_PROJECT_INDEX.md").write_text(index, encoding="utf-8")
print(json.dumps({k: result[k] for k in ["status", "download_path", "archive_bytes", "deletion_bytes", "expected_net_disk_bytes_reclaimed", "retained_protected_files_verified", "remaining_raw_dataset_count", "research_C_environment_imports_pass"]}, ensure_ascii=True, indent=2))
