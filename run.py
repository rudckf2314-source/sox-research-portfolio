"""Reproduce SOX results from the frozen, monthly model inputs."""
import argparse
import itertools
import json
import os
from pathlib import Path
import warnings

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, r2_score

from estimators import classifier, regressor
from simulation import simulate

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "데이터"
REF = ROOT / "기준자료"
ALGORITHMS = ("LR", "RF", "ET", "HGB", "XGB", "LGBM")
REGRESSORS = ("RIDGE", "RF", "ET", "HGB", "XGB", "LGBM")
REFERENCE = ("G110000_NONE", "BINARY", "LR")
SELECTED = ("G001000_MONTH2_FIRST", "BINARY", "LR")
BEST = ("G001100_MONTH2_FIRST", "BINARY", "LGBM")
FOUR = ("G001100_MONTH2_FIRST", "FOUR", "LR")
REGRESSION = ("G000000_NONE", "REGRESSION", "XGB")
IMPORTANCE_CASES = dict(zip((BEST, REFERENCE, FOUR),
    ("BINARY_BEST_OBSERVED", "BINARY_REFERENCE", "FOUR_BEST_OBSERVED")))
TARGETS = {"BINARY": "Y", "FOUR": "class4", "REGRESSION": "return_pct"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def selection():
    masks = {row["mask"]: row["kind"] for row in load(REF / "후보_변수조합.json")}
    rows = pd.read_csv(REF / "조합탐색_성능.csv")
    bank, ranks = [], {mask: [] for mask in masks}
    for task, algo in itertools.product(("BINARY", "FOUR"), ALGORITHMS):
        group = rows[(rows.task == task) & (rows.algo == algo)].copy()
        if task == "BINARY":
            base = group[group["mask"] == REFERENCE[0]].iloc[0]
            group["qualified"] = (group.accuracy >= base.accuracy) & (group.BA >= base.BA)
            fields, order = ["qualified", "BA", "accuracy", "candidate"], [False, False, False, True]
        else:
            fields, order = ["macro_F1", "accuracy", "candidate"], [False, False, True]
        ranked = group.sort_values(fields, ascending=order)["mask"].tolist()
        if ranked[0] not in bank:
            bank.append(ranked[0])
        for index, mask in enumerate(ranked):
            ranks[mask].append(index / 255)
    if REFERENCE[0] not in bank:
        bank.append(REFERENCE[0])
    pooled = sorted(ranks, key=lambda mask: (np.mean(ranks[mask]), mask))
    while sum(masks[mask] == "INDIVIDUAL" for mask in bank) < 3:
        bank.append(next(mask for mask in pooled if masks[mask] == "INDIVIDUAL" and mask not in bank))
    bank.extend([mask for mask in pooled if mask not in bank][:16-len(bank)])
    assert bank == load(REF / "최종_변수조합16개.json")
    confirm = pd.read_csv(REF / "사전검증_성능.csv")
    decisions = {}
    for task in ("BINARY", "FOUR"):
        group = confirm[confirm.task == task].copy()
        base = group[(group["mask"] == REFERENCE[0]) & (group.algo == "LR")].iloc[0]
        eligible = group[(group.accuracy > base.accuracy) &
                         ((group.TN >= base.TN) if task == "BINARY" else (group.macro_F1 > base.macro_F1))].copy()
        eligible["tie"] = eligible["mask"] + "__" + eligible.algo
        if task == "BINARY":
            eligible["qualified"] = eligible.BA >= base.BA
            fields, order = ["qualified", "BA", "accuracy", "tie"], [False, False, False, True]
        else:
            fields, order = ["macro_F1", "accuracy", "tie"], [False, False, True]
        chosen = base if eligible.empty else eligible.sort_values(fields, ascending=order).iloc[0]
        decisions[task] = {"mask": chosen["mask"], "algo": chosen.algo}
    assert decisions == load(REF / "사전선정_기록.json")["selected"]
    return bank, decisions


def load_forecasts():
    classification = pd.read_csv(REF / "분류_예측.csv", float_precision="round_trip")
    regression = pd.read_csv(REF / "회귀_예측.csv", float_precision="round_trip")
    regression["task"] = "REGRESSION"
    daily = pd.concat([classification, regression], ignore_index=True)
    return {key: group.set_index("date").sort_index() for key, group in daily.groupby(["mask", "task", "algo"])}


def fit_models(forecasts, labels, bank, mode, out):
    rng = np.random.default_rng(20261024)
    importance = {}
    predictions = []
    max_error = 0.0
    for row in pd.read_csv(DATA / "월별학습일정.csv").itertuples():
        folder = DATA / "월별입력" / row.month
        with np.load(folder / "학습평가_배열.npz") as arrays:
            train, evaluate = arrays["X_train"], arrays["X_eval"]
            train_dates, dates = arrays["train_dates"], arrays["eval_dates"]
            names = arrays["feature_names"].tolist()
        assert len(train_dates) == row.train_rows and len(dates) == row.eval_rows
        assert train_dates[-1] < row.month + "-01" <= dates[0]
        features = load(folder / "모형별_입력변수.json")
        ordered = list(IMPORTANCE_CASES) + [SELECTED, REGRESSION]
        if mode == "full":
            ordered.extend(key for key in forecasts if key[0] in bank and key not in ordered)
        for key in ordered:
            mask, task, algo = key
            columns = features[mask]
            indices = [names.index(name) for name in columns]
            a, b = train[:, indices], evaluate[:, indices]
            model = regressor(algo) if task == "REGRESSION" else classifier(algo, task)
            model.fit(a, labels.loc[train_dates, TARGETS[task]].to_numpy())
            saved = forecasts[key].loc[dates]
            if task == "REGRESSION":
                estimate = model.predict(b)
                expected = saved.prediction.to_numpy()
                new = pd.DataFrame({"prediction": estimate}, index=dates)
            else:
                estimate = model.predict_proba(b)
                probability_columns = [f"p{i}" for i in range(estimate.shape[1])]
                expected = saved[probability_columns].to_numpy()
                new = pd.DataFrame(estimate, columns=probability_columns, index=dates)
                new["prediction"] = (estimate[:, 1] >= .5).astype(int) if task == "BINARY" else estimate.argmax(1)
                np.testing.assert_array_equal(new.prediction, saved.prediction)
            np.testing.assert_allclose(estimate, expected, atol=1e-8, rtol=1e-8, err_msg=str((row.month, key)))
            max_error = max(max_error, float(np.max(np.abs(estimate - expected))))
            predictions.append(new.assign(date=dates, mask=mask, task=task, algo=algo))
            if key in IMPORTANCE_CASES:
                y = labels.loc[dates, TARGETS[task]].to_numpy(int)
                base = -np.log(np.clip(estimate[np.arange(len(y)), y], 1e-15, 1))
                for column, name in enumerate(columns):
                    total = importance.setdefault((IMPORTANCE_CASES[key], name), 0.0)
                    varies = np.ptp(b[:, column]) > 1e-10
                    for _ in range(5):
                        if varies:
                            modified = b.copy()
                            modified[:, column] = modified[rng.permutation(len(b)), column]
                            probability = model.predict_proba(modified)
                            loss = -np.log(np.clip(probability[np.arange(len(y)), y], 1e-15, 1))
                            total += float((loss - base).sum())
                        rng.integers(max(0, len(a) - 252), len(a), size=len(b))
                    importance[IMPORTANCE_CASES[key], name] = total
        print(f"{row.month} verified {len(ordered)} fits", flush=True)
    exact = pd.Series({key: value / (5 * 706) for key, value in importance.items()})
    expected = pd.read_csv(REF / "변수중요도.csv").set_index(["case", "feature"])
    np.testing.assert_allclose(exact, expected.loc[exact.index, "within_month_delta_logloss"], atol=1e-8, rtol=1e-7)
    exact.rename("within_month_delta_logloss").rename_axis(["case", "feature"]).to_csv(out / "변수중요도.csv")
    table = pd.concat(predictions, ignore_index=True)
    table.to_csv(out / "재학습_예측.csv", index=False)
    return {"fits": len(pd.read_csv(DATA / "월별학습일정.csv")) * len(ordered),
            "max_forecast_error": max_error, "importance_rows_verified": len(exact)}


def holm(p):
    order = np.argsort(p)
    result = np.empty(len(p))
    result[order] = np.minimum(1, np.maximum.accumulate((len(p) - np.arange(len(p))) * p[order]))
    return result


def evaluate(forecasts, labels, out):
    dates = forecasts[REFERENCE].index
    assert len(dates) == 706 and dates[0] == "2024-01-02" and dates[-1] == "2026-10-23"
    y = labels.loc[dates, "Y"].to_numpy()
    rows, yearly = [], []
    for key, group in forecasts.items():
        mask, task, algo = key
        assert group.index.equals(dates)
        target = labels.loc[dates, TARGETS[task]].to_numpy()
        np.testing.assert_allclose(group.Y, target, atol=1e-12, rtol=1e-12)
        prediction = group.prediction.to_numpy()
        for year, take in [("ALL", np.ones(len(dates), bool))] + [
            (str(year), dates.str.startswith(str(year))) for year in (2024, 2025, 2026)
        ]:
            actual, pred = target[take], prediction[take]
            row = dict(mask=mask, task=task, algo=algo, year=year, n=len(actual))
            if task == "REGRESSION":
                error = pred - actual
                row.update(MAE=np.abs(error).mean(), RMSE=np.sqrt(np.mean(error ** 2)),
                           R2=r2_score(actual, pred), direction_accuracy=np.mean((pred > 0) == (actual > 0)))
            else:
                row.update(correct=int(np.sum(actual == pred)), accuracy=accuracy_score(actual, pred),
                           balanced_accuracy=balanced_accuracy_score(actual, pred),
                           macro_F1=f1_score(actual, pred, average="macro", zero_division=0))
                if task == "BINARY":
                    row["nonup_recall"] = float(np.mean(pred[actual == 0] == 0))
            (rows if year == "ALL" else yearly).append(row)
    for year in ("ALL", "2024", "2025", "2026"):
        actual = y if year == "ALL" else y[dates.str.startswith(year)]
        pred = np.ones_like(actual)
        row = dict(mask="BASELINE", task="BINARY", algo="ALWAYS_UP", year=year, n=len(actual),
                   correct=int(actual.sum()), accuracy=float(actual.mean()), nonup_recall=0.0,
                   macro_F1=f1_score(actual, pred, average="macro", zero_division=0),
                   balanced_accuracy=balanced_accuracy_score(actual, pred))
        (rows if year == "ALL" else yearly).append(row)
    pd.DataFrame(rows).to_csv(out / "전체_조합의_주요_예측_성과.csv", index=False)
    pd.DataFrame(yearly).to_csv(out / "연도별_안정성.csv", index=False)
    keys = [REFERENCE, SELECTED, BEST]
    correct = {key: int(np.sum(forecasts[key].prediction == y)) for key in keys}
    assert [correct[key] for key in keys] == [434, 426, 442] and int(y.sum()) == 400

    starts = np.random.default_rng(20261044).integers(0, len(y), size=(5000, int(np.ceil(len(y)/20))))
    indices = ((starts[:, :, None] + np.arange(20)) % len(y)).reshape(5000, -1)[:, :len(y)]
    verify_model_intervals(forecasts, labels.loc[dates], indices, out)
    contrasts = pd.read_csv(REF / "변수군_추가효과90개.csv")
    for index, row in contrasts.iterrows():
        actual = labels.loc[dates, TARGETS[row.task]].to_numpy()
        a = forecasts[row.candidate, row.task, row.algo].prediction.to_numpy()
        b = forecasts[row.base, row.task, row.algo].prediction.to_numpy()
        if row.task == "REGRESSION":
            diff, scale = (actual - b)**2 - (actual - a)**2, 1
        else:
            diff, scale = (a == actual).astype(float) - (b == actual).astype(float), 100
        samples, effect = diff[indices].mean(1), float(diff.mean())
        probability = (1 + np.sum(np.abs(samples-effect) >= abs(effect))) / 5001
        lo, hi = np.quantile(samples, [.025, .975])
        np.testing.assert_allclose([effect * scale, lo * scale, hi * scale, probability],
                                   [row.effect, row.lo95, row.hi95, row.p_centered_block_bootstrap_approx],
                                   atol=1e-10, rtol=1e-10)
        contrasts.loc[index, ["effect", "lo95", "hi95", "p_centered_block_bootstrap_approx"]] = [
            effect * scale, lo * scale, hi * scale, probability]
    np.testing.assert_allclose(holm(contrasts.p_centered_block_bootstrap_approx.to_numpy()), contrasts.p_Holm90)
    binary = contrasts[contrasts.task == "BINARY"].copy()
    binary["p_Holm30"] = holm(binary.p_centered_block_bootstrap_approx.to_numpy())
    np.testing.assert_allclose(binary.p_Holm30, pd.read_csv(REF / "이진_Holm30_보정.csv").p_Holm30)
    contrasts.to_csv(out / "동일_알고리즘의_변수군_추가_전체90개.csv", index=False)
    binary.to_csv(out / "동일_알고리즘의_변수군_추가_이진분류30개_Holm보정.csv", index=False)

    q = pd.read_csv(DATA / "SOXQ_가격.csv").set_index("date").sort_index()
    np.testing.assert_array_equal(q.signal, forecasts[BEST].loc[q.index, "prediction"])
    pred, _ = simulate(q, "prediction")
    hold, _ = simulate(q, "buyhold")
    lo, hi = 0.0, 1.0
    for _ in range(35):
        weight = (lo + hi) / 2
        result, _ = simulate(q, "fixed_weight", weight)
        if result["mean_close_exposure_pct"] < pred["mean_close_exposure_pct"]:
            lo = weight
        else:
            hi = weight
    matched, _ = simulate(q, "fixed_weight", (lo + hi) / 2)
    risk = pd.DataFrame([hold, matched, pred])
    for column in ["ending", "total_return_pct", "MDD_pct"]:
        np.testing.assert_allclose(risk[column], pd.read_csv(REF / "SOXQ_모의투자_성과.csv")[column], atol=1e-7)
    risk.to_csv(out / "SOXQ_모의투자_성과.csv", index=False)
    pd.read_csv(REF / "회귀_변수중요도.csv").to_csv(out / "회귀_변수중요도_보존결과.csv", index=False)
    return {"sessions": len(dates), "classification_and_regression_series": len(forecasts),
            "baseline_correct": 400, "reference_correct": 434, "preselected_correct": 426,
            "observed_best_correct": 442, "contrasts_verified": 90, "holm30_verified": True,
            "soxq_strategies_verified": 3}


def verify_model_intervals(forecasts, labels, indices, out):
    reference = pd.read_csv(REF / "모형별_성능차이_블록신뢰구간.csv")
    rows = reference[(reference.block == 20) & reference.task.isin(["BINARY", "REGRESSION"])].copy()
    binary = {"분류사전선정": forecasts[SELECTED].prediction.to_numpy(),
              "분류비교기준": forecasts[REFERENCE].prediction.to_numpy(),
              "분류관측최고": forecasts[BEST].prediction.to_numpy(),
              "항상상승": np.ones(len(labels))}
    baselines = {"항상0%": "ZERO", "과거학습평균": "TRAIN_MEAN", "과거학습중앙값": "TRAIN_MEDIAN"}
    actual = labels.return_pct.to_numpy()
    best_error = actual - forecasts[REGRESSION].prediction.to_numpy()
    for row in rows.itertuples():
        if row.task == "BINARY":
            y = labels.Y.to_numpy()
            delta = (binary[row.candidate] == y).astype(float) - (binary[row.baseline] == y)
            point, samples = delta.mean() * 100, delta[indices].mean(1) * 100
        else:
            error = actual - forecasts["BASELINE", "REGRESSION", baselines[row.baseline]].prediction.to_numpy()
            if row.metric == "MAE_improvement":
                point = np.abs(error).mean() - np.abs(best_error).mean()
                samples = np.abs(error[indices]).mean(1) - np.abs(best_error[indices]).mean(1)
            else:
                point = np.sqrt((error ** 2).mean()) - np.sqrt((best_error ** 2).mean())
                samples = np.sqrt((error[indices] ** 2).mean(1)) - np.sqrt((best_error[indices] ** 2).mean(1))
        values = [point, *np.quantile(samples, [.025, .975])]
        np.testing.assert_allclose(values, [row.difference, row.lo95, row.hi95], atol=1e-10)
        rows.loc[row.Index, ["difference", "lo95", "hi95"]] = values
    rows.to_csv(out / "모형별_성능차이_20일_블록신뢰구간.csv", index=False)


def render_figures(binary, yearly, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/malgun.ttf"
    if font.is_file():
        font_manager.fontManager.addfont(font)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    folder = out / "그림"
    folder.mkdir(exist_ok=True)

    ranges = binary.groupby("comparison", sort=False).effect.agg(["min", "max"])
    lr = binary[binary.algo == "LR"].set_index("comparison").effect.reindex(ranges.index)
    fig, ax = plt.subplots(figsize=(7, 3.4), layout="constrained")
    positions = np.arange(len(ranges))
    ax.hlines(positions, ranges["min"], ranges["max"], color="#a6bac5", lw=5)
    ax.scatter(lr, positions, color="#14688d", zorder=3)
    ax.set_yticks(positions, ranges.index)
    ax.invert_yaxis()
    ax.axvline(0, color="gray", ls="--")
    ax.set_xlabel("정확도 변화 (%p)")
    fig.savefig(folder / "그림1_추가효과의_알고리즘별_범위와_LR.png", dpi=180)
    plt.close(fig)

    imp_path = out / "변수중요도.csv"
    importance = pd.read_csv(imp_path if imp_path.exists() else REF / "변수중요도.csv")
    names = {"s23_delta1": "대만 반도체 업종지수 1일 변화량",
             "s01_body_open": "한국 반도체 ETF 장중 변화",
             "s01_ret1": "한국 반도체 ETF 1일 수익률",
             "s09_ret1": "IEF 1일 수익률", "s12_ret5": "NASDAQ-100 5일 수익률"}
    top = importance[importance.case == "BINARY_BEST_OBSERVED"].nlargest(5, "within_month_delta_logloss")
    fig, ax = plt.subplots(figsize=(7, 3.2), layout="constrained")
    ax.barh(top.feature.map(names).fillna(top.feature), top.within_month_delta_logloss, color="#216789")
    ax.invert_yaxis()
    ax.set_xlabel("월내 순열 로그손실 증가량")
    fig.savefig(folder / "그림2_최고_LightGBM의_주요_변수_의존도.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(6, 6), sharex=True, layout="constrained")
    for key, label in [(("BASELINE", "BINARY", "ALWAYS_UP"), "항상 상승"),
                       (REFERENCE, "비교기준 LR"), (SELECTED, "과거 선정 LR"), (BEST, "최고 LightGBM")]:
        mask, task, algo = key
        group = yearly[(yearly["mask"] == mask) & (yearly.task == task) & (yearly.algo == algo)]
        for ax, field in zip(axes, ("accuracy", "nonup_recall")):
            ax.plot(group.year, group[field] * 100, marker="o", label=label)
    axes[0].set_ylabel("방향 정확도 (%)")
    axes[1].set_ylabel("비상승 재현율 (%)")
    axes[0].legend()
    axes[1].set_xlabel("2026년은 10월 23일까지")
    fig.savefig(folder / "그림3_연도별_정확도와_비상승_재현율.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("replay", "key", "full"), default="key")
    parser.add_argument("--out", type=Path, default=ROOT / "재현결과")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    bank, decisions = selection()
    forecasts = load_forecasts()
    labels = pd.read_csv(DATA / "예측정답.csv", index_col="date", float_precision="round_trip")
    np.testing.assert_array_equal(labels.Y, (labels.return_pct > 0).astype(int))
    report = {"mode": args.mode, "selected_masks": len(bank), "pre2024_selection": decisions}
    report.update(evaluate(forecasts, labels, args.out))
    if args.mode != "replay":
        report.update(fit_models(forecasts, labels, bank, args.mode, args.out))
    render_figures(
        pd.read_csv(args.out / "동일_알고리즘의_변수군_추가_이진분류30개_Holm보정.csv"),
        pd.read_csv(args.out / "연도별_안정성.csv", dtype={"year": str}), args.out)
    (args.out / "재현_검증.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
