"""ML model loading, prediction and SHAP explanations (Uzbek labels).

If the artifact is missing the engine still works (rules + trends only).
"""
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import BACKEND_DIR

ARTIFACT_PATH = BACKEND_DIR / "ml" / "artifacts" / "model.joblib"

# Uzbek label + value formatter per feature. {v} = value.
FEATURE_LABELS: dict[str, str] = {
    "age": "Onaning yoshi {v:.0f}",
    "gest_weeks": "Homiladorlik muddati {v:.0f} hafta",
    "booking_weeks": "Ro'yxatga olingan muddat {v:.0f} hafta",
    "gravidity": "Homiladorliklar soni {v:.0f}",
    "parity": "Tug'ruqlar soni {v:.0f}",
    "previous_cs": "Oldingi kesarcha kesish",
    "hist_stillbirth": "Anamnezda o'lik tug'ilish",
    "hist_preterm": "Anamnezda muddatidan oldin tug'ruq",
    "miscarriages_count": "Homila tushishlari soni {v:.0f}",
    "hist_preeclampsia": "Anamnezda preeklampsiya",
    "hist_pph": "Anamnezda tug'ruqdan keyingi qon ketish",
    "diabetes": "Qandli diabet",
    "chronic_htn": "Surunkali gipertenziya",
    "other_chronic": "Boshqa surunkali kasallik",
    "multiple_pregnancy": "Ko'p homilali homiladorlik",
    "rh_negative": "Rezus-manfiy",
    "interpregnancy_months": "Homiladorliklar orasidagi interval {v:.0f} oy",
    "bmi_booking": "Tana massasi indeksi {v:.1f}",
    "distance_km": "Perinatal markazgacha {v:.0f} km",
    "systolic": "Sistolik bosim {v:.0f}",
    "diastolic": "Diastolik bosim {v:.0f}",
    "proteinuria_level": "Siydikda oqsil ({v_prot})",
    "hemoglobin": "Gemoglobin {v:.0f} g/L",
    "glucose": "Glyukoza {v:.1f} mmol/L",
    "temperature": "Harorat {v:.1f}°C",
    "fetal_heart_rate": "Homila yurak urishi {v:.0f}",
    "fundal_gap": "Bachadon tubi balandligi farqi {v:+.0f} sm",
    "weight_gain_rate": "Vazn ortishi {v:.1f} kg/hafta",
    "d_systolic": "Sistolik bosim o'zgarishi ({v:+.0f})",
    "d_diastolic": "Diastolik bosim o'zgarishi ({v:+.0f})",
    "d_hemoglobin": "Gemoglobin o'zgarishi ({v:+.0f} g/L)",
    "max_systolic": "Eng yuqori sistolik bosim {v:.0f}",
    "min_hemoglobin": "Eng past gemoglobin {v:.0f} g/L",
    "symptom_count": "Shikoyatlar soni {v:.0f}",
    "danger_symptom": "Xavfli shikoyat bor",
    "n_visits": "Tashriflar soni {v:.0f}",
}
_PROT_NAMES = {0: "manfiy", 1: "iz", 2: "+1", 3: "+2", 4: "+3"}


def label_for(feature: str, value: float) -> str:
    tmpl = FEATURE_LABELS.get(feature, feature)
    if value != value:  # NaN
        return tmpl.split("{")[0].strip() + " (o'lchanmagan)"
    if feature == "d_hemoglobin" and value < 0:
        return f"Gemoglobin pasaygan ({value:+.0f} g/L)".replace("-", "−")
    if feature == "d_systolic" and value > 0:
        return f"Sistolik bosim oshgan ({value:+.0f})"
    return tmpl.format(v=value, v_prot=_PROT_NAMES.get(int(value), value))


class Model:
    def __init__(self, bundle: dict):
        self.lgbm = bundle["model"]
        self.iso = bundle["isotonic"]
        self.features: list[str] = bundle["features"]
        self.version: str = bundle["version"]
        import warnings

        import shap

        self.booster = self.lgbm.booster_  # numpy-in, no feature-name warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.explainer = shap.TreeExplainer(self.booster)

    def _row(self, feats: dict[str, float]) -> np.ndarray:
        return np.array([[feats.get(f, np.nan) for f in self.features]], dtype=float)

    def predict(self, feats: dict[str, float]) -> float:
        raw = self.booster.predict(self._row(feats))
        return float(np.clip(self.iso.predict(raw)[0], 0.0, 1.0))

    def explain(self, feats: dict[str, float], k: int = 5) -> list[dict]:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sv = self.explainer.shap_values(self._row(feats))
        sv = sv[1] if isinstance(sv, list) else sv
        vals = np.asarray(sv).reshape(-1)[: len(self.features)]
        order = np.argsort(-np.abs(vals))[:k]
        return [
            {
                "feature": self.features[i],
                "value": None if feats.get(self.features[i]) != feats.get(self.features[i]) else feats.get(self.features[i]),
                "shap": round(float(vals[i]), 4),
                "direction": "up" if vals[i] > 0 else "down",
                "uz_label": label_for(self.features[i], feats.get(self.features[i], np.nan)),
            }
            for i in order
        ]


@lru_cache
def load_model(path: Path = ARTIFACT_PATH) -> Model | None:
    if not path.exists():
        return None
    import joblib

    try:
        return Model(joblib.load(path))
    except Exception:  # noqa: BLE001 - a broken artifact must not break the demo
        return None
