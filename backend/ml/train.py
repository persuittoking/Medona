"""Train the LightGBM adverse-outcome model on synthetic data.

- Split BY PREGNANCY (no leakage): 70% train / 15% calibration+threshold selection / 15% test.
- 5-fold GroupKFold CV on the train part (reported), then isotonic calibration.
- ML thresholds chosen on the calibration split so that the COMBINED system
  (rules + trends OR ML) flags >=85% of pregnancies with an adverse outcome as YELLOW/RED
  at least once from 28 weeks (pregnancy-level sensitivity). Per-visit sensitivity is reported too.
- Writes artifacts/model.joblib, artifacts/metrics.json and the ML block in app/risk/thresholds.py.

Usage (from backend/):  .venv\\Scripts\\python ml\\train.py [--n 20000] [--seed 42]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from app.risk.features import FEATURES  # noqa: E402 - after sys.path setup

ART = ROOT / "artifacts"
DATA = ROOT / "data" / "synthetic_pregnancies.csv.gz"
THRESH_PY = ROOT.parent / "app" / "risk" / "thresholds.py"
RECALL_TARGET = 0.85  # pregnancy-level RED+YELLOW sensitivity floor
LATE_WEEKS = 28       # pregnancy-level metric: flagged at least once from this week
YELLOW_RANGE = (0.08, 0.20)
RED_PRECISION = 0.60  # ML alone sets RED only where >= 60% of flagged pregnancies have an adverse outcome
PARAMS = dict(n_estimators=400, learning_rate=0.04, num_leaves=31, min_child_samples=40,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1)


def _sens_spec(y: np.ndarray, flag: np.ndarray) -> dict:
    tp = int((flag & (y == 1)).sum())
    fn = int((~flag & (y == 1)).sum())
    tn = int((~flag & (y == 0)).sum())
    fp = int((flag & (y == 0)).sum())
    return {"sensitivity": round(tp / max(tp + fn, 1), 4), "specificity": round(tn / max(tn + fp, 1), 4),
            "precision": round(tp / max(tp + fp, 1), 4), "flag_rate": round(float(flag.mean()), 4),
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn}}


def pregnancy_sensitivity(y: np.ndarray, flag: np.ndarray, groups: np.ndarray, gw: np.ndarray) -> dict:
    """Share of adverse-outcome pregnancies flagged YELLOW/RED at least once from LATE_WEEKS."""
    import pandas as pd

    late = gw >= LATE_WEEKS
    d = pd.DataFrame({"g": groups[late], "y": y[late], "f": flag[late]}).groupby("g").agg(y=("y", "first"), f=("f", "max"))
    return {"sensitivity": round(float(d.f[d.y == 1].mean()), 4), "flag_rate": round(float(d.f.mean()), 4),
            "n_pregnancies": len(d), "from_weeks": LATE_WEEKS}


def choose_thresholds(y: np.ndarray, p: np.ndarray, rule_flag: np.ndarray, groups: np.ndarray,
                      gw: np.ndarray) -> tuple[float, float]:
    grid = np.round(np.arange(0.02, 0.951, 0.005), 3)
    yellow = 0.02
    for t in grid:  # highest t that keeps pregnancy-level combined recall >= target
        if pregnancy_sensitivity(y, rule_flag | (p >= t), groups, gw)["sensitivity"] >= RECALL_TARGET:
            yellow = float(t)
    yellow = float(np.clip(yellow, *YELLOW_RANGE))
    red = None
    for t in grid:  # lowest t > yellow where ML precision reaches RED_PRECISION
        if t > yellow + 0.05 and (p >= t).sum() >= 20 and y[p >= t].mean() >= RED_PRECISION:
            red = float(t)
            break
    return yellow, float(red if red is not None else min(0.9, yellow + 0.35))


def write_thresholds(yellow: float, red: float, note: str) -> None:
    src = THRESH_PY.read_text(encoding="utf-8")
    block = (f"# BEGIN ML THRESHOLDS (auto-written by backend/ml/train.py — do not edit by hand)\n"
             f"ML_YELLOW = {yellow}\nML_RED = {red}\nML_THRESHOLDS_NOTE = {note!r}\n# END ML THRESHOLDS")
    src = re.sub(r"# BEGIN ML THRESHOLDS.*?# END ML THRESHOLDS", block, src, flags=re.DOTALL)
    THRESH_PY.write_text(src, encoding="utf-8")


def main() -> None:
    import joblib
    import pandas as pd
    import shap
    from lightgbm import LGBMClassifier
    from sklearn.calibration import calibration_curve
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    from sklearn.model_selection import GroupKFold, GroupShuffleSplit

    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--regen", action="store_true", help="regenerate the synthetic data")
    a = ap.parse_args()

    if a.regen or not DATA.exists():
        from ml.generate_synthetic import generate_training

        print(f"Generating synthetic data (n={a.n}, seed={a.seed}) ...")
        df = generate_training(a.n, a.seed)
        DATA.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(DATA, index=False)
    else:
        df = pd.read_csv(DATA)
    X, y, g = df[FEATURES].astype(float), df["adverse_outcome"].to_numpy(), df["pregnancy_id"].to_numpy()
    rule_flag = (df["rule_zone"] != "green").to_numpy()

    gss = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=a.seed)
    tr, rest = next(gss.split(X, y, g))
    gss2 = GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=a.seed + 1)
    cal_i, te_i = next(gss2.split(X.iloc[rest], y[rest], g[rest]))
    cal, te = rest[cal_i], rest[te_i]
    assert not set(g[tr]) & set(g[te]) and not set(g[cal]) & set(g[te]), "pregnancy leakage"

    cv_auc = []
    for f_tr, f_va in GroupKFold(n_splits=5).split(X.iloc[tr], y[tr], g[tr]):
        m = LGBMClassifier(**PARAMS, random_state=a.seed).fit(X.iloc[tr[f_tr]], y[tr[f_tr]])
        cv_auc.append(roc_auc_score(y[tr[f_va]], m.predict_proba(X.iloc[tr[f_va]])[:, 1]))

    model = LGBMClassifier(**PARAMS, random_state=a.seed).fit(X.iloc[tr], y[tr])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
    iso.fit(model.predict_proba(X.iloc[cal])[:, 1], y[cal])
    def predict(idx):
        return iso.predict(model.predict_proba(X.iloc[idx])[:, 1])

    p_cal, p_te = predict(cal), predict(te)
    gw_all = X["gest_weeks"].to_numpy()
    yellow, red = choose_thresholds(y[cal], p_cal, rule_flag[cal], g[cal], gw_all[cal])
    yt, rf = y[te], rule_flag[te]

    prob_true, prob_pred = calibration_curve(yt, p_te, n_bins=10, strategy="quantile")
    per_region = {}
    for reg in sorted(df["region"].unique()):
        mask = (df["region"].to_numpy()[te] == reg)
        if len(set(yt[mask])) == 2:
            per_region[reg] = {"n_rows": int(mask.sum()), "roc_auc": round(roc_auc_score(yt[mask], p_te[mask]), 4),
                               "pr_auc": round(average_precision_score(yt[mask], p_te[mask]), 4),
                               "outcome_rate": round(float(yt[mask].mean()), 4),
                               "system_sensitivity": _sens_spec(yt[mask], rf[mask] | (p_te[mask] >= yellow))["sensitivity"]}

    by_tri = {}
    gw_te = X.iloc[te]["gest_weeks"].to_numpy()
    for name, lo_w, hi_w in [("1-trimestr", 0, 14), ("2-trimestr", 14, 28), ("3-trimestr", 28, 99)]:
        m_ = (gw_te >= lo_w) & (gw_te < hi_w)
        if m_.sum() > 50 and len(set(yt[m_])) == 2:
            by_tri[name] = {"n_rows": int(m_.sum()), "roc_auc": round(roc_auc_score(yt[m_], p_te[m_]), 4),
                            "pr_auc": round(average_precision_score(yt[m_], p_te[m_]), 4)}

    sample = X.iloc[te].sample(min(3000, len(te)), random_state=a.seed)
    sv = shap.TreeExplainer(model).shap_values(sample)
    sv = sv[1] if isinstance(sv, list) else sv
    imp = sorted(zip(FEATURES, np.abs(sv).mean(axis=0), strict=True), key=lambda t: -t[1])[:15]

    version = hashlib.sha1(json.dumps([FEATURES, PARAMS, a.seed, len(df)], sort_keys=True).encode()).hexdigest()[:10]
    from app.risk.ml import FEATURE_LABELS

    metrics = {
        "model_version": version, "trained_on": str(date.today()), "data": "SYNTHETIC (demo) — retrain on real DMED data",
        "n_pregnancies": int(df["pregnancy_id"].nunique()), "n_rows": len(df),
        "outcome_rate": round(float(df.groupby("pregnancy_id")["adverse_outcome"].first().mean()), 4),
        "split": {"train_rows": len(tr), "calibration_rows": len(cal), "test_rows": len(te), "by": "pregnancy"},
        "cv_roc_auc": {"folds": [round(x, 4) for x in cv_auc], "mean": round(float(np.mean(cv_auc)), 4)},
        "test": {"roc_auc": round(roc_auc_score(yt, p_te), 4), "pr_auc": round(average_precision_score(yt, p_te), 4),
                 "brier": round(brier_score_loss(yt, p_te), 4), "base_rate": round(float(yt.mean()), 4)},
        "thresholds": {"ml_yellow": yellow, "ml_red": red, "recall_target": RECALL_TARGET, "recall_level": f"pregnancy, flagged from {LATE_WEEKS} w"},
        "at_thresholds": {
            "ml_only_yellow_or_red": _sens_spec(yt, p_te >= yellow),
            "ml_only_red": _sens_spec(yt, p_te >= red),
            "rules_only_yellow_or_red": _sens_spec(yt, rf),
            "system_yellow_or_red": _sens_spec(yt, rf | (p_te >= yellow)),
            "system_pregnancy_level": pregnancy_sensitivity(yt, rf | (p_te >= yellow), g[te], gw_all[te]),
        },
        "calibration_curve": {"predicted": [round(float(v), 4) for v in prob_pred], "observed": [round(float(v), 4) for v in prob_true]},
        "per_region": per_region,
        "by_trimester": by_tri,
        "top_features": [{"feature": f, "uz_label": FEATURE_LABELS.get(f, f).split("{")[0].strip(), "mean_abs_shap": round(float(v), 4)} for f, v in imp],
    }
    ART.mkdir(exist_ok=True)
    joblib.dump({"model": model, "isotonic": iso, "features": FEATURES, "version": version}, ART / "model.joblib")
    (ART / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    try:  # keep MODEL_CARD.md / README.md in sync with the new metrics (never hand-copied)
        from ml.metrics_docs import write_docs

        write_docs(ART / "metrics.json")
    except Exception as e:  # noqa: BLE001 - docs are secondary to a finished training run
        print(f"[train] could not update metric docs: {e}")
    sys_sens = metrics["at_thresholds"]["system_yellow_or_red"]["sensitivity"]
    preg_sens = metrics["at_thresholds"]["system_pregnancy_level"]["sensitivity"]
    write_thresholds(yellow, red, f"chosen {date.today()} on calibration split: pregnancy-level recall target "
                                  f"{RECALL_TARGET:.0%} (flagged from {LATE_WEEKS} w); test pregnancy-level "
                                  f"sensitivity {preg_sens:.1%}, per-visit {sys_sens:.1%}; model {version}")

    t = metrics["test"]
    print(f"Model {version}  |  rows {len(df):,}  pregnancies {metrics['n_pregnancies']:,}")
    print(f"CV ROC-AUC (5-fold, by pregnancy): {metrics['cv_roc_auc']['mean']:.3f}")
    print(f"TEST  ROC-AUC: {t['roc_auc']:.3f}   PR-AUC: {t['pr_auc']:.3f}   Brier: {t['brier']:.4f}   base rate: {t['base_rate']:.1%}")
    print(f"Thresholds: ML yellow >= {yellow}, ML red >= {red}")
    for k, v in metrics["at_thresholds"].items():
        if k == "system_pregnancy_level":
            print(f"  {k:26s} sens {v['sensitivity']:.1%}  flagged {v['flag_rate']:.1%}  (>= {LATE_WEEKS} w, n={v['n_pregnancies']})")
            continue
        print(f"  {k:26s} sens {v['sensitivity']:.1%}  spec {v['specificity']:.1%}  prec {v['precision']:.1%}  flagged {v['flag_rate']:.1%}")
    print("By trimester ROC-AUC:", {k: v["roc_auc"] for k, v in by_tri.items()})
    print("Per region ROC-AUC:", {k: v["roc_auc"] for k, v in per_region.items()})
    print(f"Artifacts -> {ART}")


if __name__ == "__main__":
    main()
