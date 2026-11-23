from pathlib import Path
import hashlib
import ast
import json
import shutil

workspace = Path(__file__).resolve().parents[1]
paper = Path(r"C:\Users\rudck\Desktop\SOX_논문_연구")
root = Path(r"C:\SOX_RESEARCH\SOX_DIRECTION_REPRODUCTION")
root.mkdir(exist_ok=False)
data = paper / "06_RAW와변수"
outputs = workspace / "outputs"
crossed = outputs / "crossed_feature_algorithm_v1_20261023"
records = []


def add(source, relative):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    with source.open("rb") as before, target.open("rb") as after:
        expected = hashlib.file_digest(before, "sha256").hexdigest()
        if hashlib.file_digest(after, "sha256").hexdigest() != expected:
            raise RuntimeError(relative)
    records.append({"path": relative, "source": str(source), "sha256": expected})


for path in (paper / "01_논문").glob("*.pdf"):
    add(path, "paper/SOX_final.pdf")
for directory in ["01_RAW", "02_변수데이터", "04_설명_조합", "06_보조원천_시점근거"]:
    for path in (data / directory).rglob("*"):
        if path.is_file() and path.suffix.lower() in {
            ".csv", ".json", ".txt", ".zip", ".xls", ".xlsx", ".md", ".docx", ".html", ".pdf"
        } and not path.name.startswith("."):
            add(path, "data/source/" + path.relative_to(data).as_posix())
add(next((data / "03_Y").glob("*.csv")), "data/labels.csv")
monthly = data / "05_실제모델입력_월별"
add(monthly / "월별학습평가기간.csv", "data/monthly_schedule.csv")
for folder in sorted(monthly.iterdir()):
    if folder.is_dir():
        add(next(folder.glob("*.npz")), f"data/monthly/{folder.name}/arrays.npz")
        add(folder / "FEATURES_16개조합.json", f"data/monthly/{folder.name}/features.json")
for name in ["BANK16.json", "MASKS.json", "screen_METRICS.csv", "confirm_METRICS.csv",
             "DECISION_PRE2024.json", "FROZEN_PLAN.json", "ENVIRONMENT.json"]:
    add(crossed / name, "reference/" + name)
final = outputs / "frozen_extension_all_tasks_20261023_v1_20261024"
add(final / "FULL706_CLASSIFICATION_DAILY.csv", "reference/forecasts.csv")
add(final / "FULL706_REGRESSION_DAILY.csv", "reference/regression.csv")
add(paper / "04_핵심근거/06_동일알고리즘_변수추가효과90.csv", "reference/contrasts90.csv")
add(outputs / "holm30_binary_20261029/이진분류30개_Holm보정_90개대비.csv", "reference/holm30.csv")
add(outputs / "importance706_20261025/ALL_CLASSIFICATION_IMPORTANCE_706.csv", "reference/importance.csv")
add(outputs / "manuscript_v4_feature_comparison_20261026/RISK_COMPARISON.csv", "reference/risk.csv")
add(outputs / "soxq_informal_simulation_20261026/SOXQ_daily_with_existing_signal.csv", "data/soxq.csv")
for name in ["staged_multi_algorithm_search_v2_20261023.py",
             "crossed_feature_algorithm_search_20261023.py",
             "run_french_lag_scenarios_20261023.py",
             "reconcile_extension_original_rules_20261024.py",
             "run_frozen_extension_20261023.py",
             "regression16_monthly_20261024.py",
             "verify_crossed_feature_search_20261023.py",
             "importance_classification_20261024.py",
             "recompute_importance706_20261025.py",
             "refresh_paper_evidence_20261023.py",
             "recalculate_binary_holm30_20261029.py",
             "analyze_v4_evidence_20261026.py"]:
    add(workspace / "work" / name, "provenance/" + name)
for name in ["run.py", "README.md", "requirements.txt"]:
    add(Path(__file__).parent / "sox_repro" / name, name)


def original_function(filename, name):
    script = (workspace / "work" / filename).read_text(encoding="utf-8-sig")
    node = next(node for node in ast.parse(script).body
                if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(script, node)


class_factory = original_function("staged_multi_algorithm_search_v2_20261023.py", "model")
cross_factory = original_function("crossed_feature_algorithm_search_20261023.py", "estimator")
reg_factory = original_function("regression16_monthly_20261024.py", "estimator")
(root / "estimators.py").write_text(
    '"""Original model factories with explicit task seeds and crossed fit budgets."""\n'
    'from sklearn.linear_model import LogisticRegression, Ridge\n'
    'from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier\n'
    'from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor, HistGradientBoostingRegressor\n\n'
    + class_factory.replace('def model(algo,task):', 'def model(algo,task):\n    SEED = 20261023') + '\n\n'
    + cross_factory.replace('def estimator(', 'def classifier(').replace('parent.model(', 'model(') + '\n\n'
    + reg_factory.replace('def estimator(algo):', 'def regressor(algo):\n    SEED = 20261024') + '\n',
    encoding="utf-8")
(root / "simulation.py").write_text(
    '"""SOXQ simulation extracted from analyze_v4_evidence_20261026.py."""\n'
    'import numpy as np\nimport pandas as pd\n\n'
    + original_function("analyze_v4_evidence_20261026.py", "simulate") + '\n', encoding="utf-8")
add(Path(__file__), "provenance/build_sox_reproduction.py")
(root / "SOURCE_MANIFEST.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Verified {len(records)} copied files in {root}")
