"""Write the model metrics into MODEL_CARD.md and README.md FROM artifacts/metrics.json (never hand-copied).

Usage: python -m ml.metrics_docs   (train.py calls it after every training run; a test checks the docs match)
The block between the BEGIN/END markers is replaced; everything else in the documents is left alone.
"""
import json
import re
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
REPO = ML_DIR.parent.parent
METRICS = ML_DIR / "artifacts" / "metrics.json"
DOCS = (ML_DIR / "MODEL_CARD.md", REPO / "README.md")
BEGIN = "<!-- BEGIN METRICS (auto-generated from backend/ml/artifacts/metrics.json by ml/metrics_docs.py) -->"
END = "<!-- END METRICS -->"
_BLOCK = re.compile(re.escape(BEGIN) + r"\n(.*?)\n" + re.escape(END), re.S)


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_block(m: dict) -> str:
    t, at = m["test"], m["at_thresholds"]
    tri = m.get("by_trimester", {})
    reg = m.get("per_region", {})
    preg = at["system_pregnancy_level"]
    rows = [
        f"Model `{m['model_version']}`, trained {m['trained_on']} on **{m['data']}** "
        f"({m['n_pregnancies']:,} pregnancies, {m['n_rows']:,} visit rows; split by {m['split']['by']}).",
        "",
        "| Metric (synthetic test set) | Value |",
        "|---|---|",
        f"| ROC-AUC | {t['roc_auc']:.3f} |",
        f"| PR-AUC (base rate {_pct(t['base_rate'])}) | {t['pr_auc']:.3f} |",
        f"| Brier score | {t['brier']:.3f} |",
        f"| CV ROC-AUC (5-fold mean) | {m['cv_roc_auc']['mean']:.3f} |",
    ]
    if tri:
        rows.append("| ROC-AUC by trimester (1 / 2 / 3) | "
                    + " / ".join(f"{v['roc_auc']:.2f}" for _, v in sorted(tri.items())) + " |")
    if reg:
        rows.append(f"| ROC-AUC by region ({' / '.join(sorted(reg))}) | "
                    + " / ".join(f"{reg[k]['roc_auc']:.2f}" for k in sorted(reg)) + " |")
    rows += [
        f"| Combined system sensitivity, pregnancy level (from {preg['from_weeks']} w) | "
        f"{_pct(preg['sensitivity'])} (flags {_pct(preg['flag_rate'])} of pregnancies) |",
        f"| Combined system sensitivity, per visit | {_pct(at['system_yellow_or_red']['sensitivity'])} "
        f"(flags {_pct(at['system_yellow_or_red']['flag_rate'])} of visits) |",
        f"| ML alone at red cut-off {m['thresholds']['ml_red']} | sensitivity {_pct(at['ml_only_red']['sensitivity'])}, "
        f"precision {_pct(at['ml_only_red']['precision'])} |",
        "",
        "Synthetic data only: real-world performance is unknown until the model is retrained and validated on real data.",
    ]
    return "\n".join(rows)


def extract_block(text: str) -> str | None:
    mm = _BLOCK.search(text)
    return mm.group(1) if mm else None


def write_docs(metrics_path: Path = METRICS) -> list[Path]:
    block = render_block(json.loads(metrics_path.read_text(encoding="utf-8")))
    changed = []
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        if _BLOCK.search(text) is None:
            raise ValueError(f"{doc}: metrics markers not found")
        new = _BLOCK.sub(lambda _: f"{BEGIN}\n{block}\n{END}", text)
        if new != text:
            doc.write_text(new, encoding="utf-8", newline="")
            changed.append(doc)
    return changed


if __name__ == "__main__":
    print("updated:", [p.name for p in write_docs()] or "nothing (already up to date)")
