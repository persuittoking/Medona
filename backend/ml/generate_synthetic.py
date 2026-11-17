"""Synthetic perinatal data generator (deterministic with --seed).

ALL DATA IS SYNTHETIC. Assumptions (also in MODEL_CARD.md):
- Maternal age: mostly 20-34; ~6% under 20 (<18 or 18-19); ~8% aged 35+.
- Antenatal schedule: booking (mostly 8-12 weeks, ~6% late at 13-24 weeks), then about every
  4 weeks to 28 weeks, every 2 weeks to 36, then weekly; ~6% of planned visits are missed;
  at most 9 visits are kept per pregnancy.
- Hemoglobin: mean ~120 g/L, SD ~11, physiological fall in pregnancy; regional shift
  (lower in Qoraqalpog'iston, see app/geo.py).
- A subset of pregnancies DETERIORATE: preeclampsia path (rising BP + proteinuria, ~7%),
  anaemia path (falling Hb, ~5-8%), fetal growth restriction path (lagging fundal height, ~5%),
  gestational diabetes path (~3-5%).
- Label `adverse_outcome` (composite) comes from a HIDDEN logistic model over risk factors +
  deterioration + noise, with the intercept tuned so the base rate is ~10%. The latent variables
  are never used as features.
- History / comorbidity prevalences (previous CS ~7% of parous women, chronic disease flags 0.4-3%)
  are demo assumptions tuned so a mahalla register lands near the target zone mix
  (~65-75% green / 20-28% yellow / 3-7% red); they are NOT national statistics.
- Names, PINFL (14 digits) and phone numbers are random and do not belong to real people.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.geo import REGIONS, haversine_km  # noqa: E402

FIRST_NAMES = [
    "Dilnoza", "Malika", "Gulnora", "Shahnoza", "Nilufar", "Madina", "Zarina", "Sevara", "Feruza",
    "Mohira", "Nodira", "Dildora", "Gulbahor", "Kamola", "Laylo", "Munisa", "Sarvinoz", "Ozoda",
    "Barno", "Iroda", "Yulduz", "Zuhra", "Aziza", "Nargiza", "Umida", "Durdona", "Hilola", "Saida",
    "Mavluda", "Rayhona", "Gulchehra", "Aygul", "Gulshan", "Shoira", "Muxlisa", "Charos", "Sabina",
]
SURNAMES = [
    "Karimova", "Rahimova", "Toshmatova", "Yusupova", "Abdullayeva", "Qodirova", "Ergasheva",
    "Nazarova", "Saidova", "Mirzayeva", "Xolmatova", "Sultonova", "Ismoilova", "Jo'rayeva",
    "Bekmuratova", "Allayarova", "Nurmatova", "Hamroyeva", "Usmonova", "Tursunova", "Aminova",
    "Ollaberganova", "Qurbonova", "Rustamova", "Fayzullayeva",
]
MAHALLAS = [
    "Navbahor", "Do'stlik", "Guliston", "Bog'ishamol", "Istiqlol", "Mustaqillik", "Yangi hayot",
    "Obod", "Navro'z", "Tinchlik", "Bunyodkor", "Ma'rifat", "Paxtakor", "Sharq", "Oydin",
]


@dataclass
class Latent:
    pe_onset: float | None = None      # week preeclampsia path starts
    pe_rate: float = 0.0               # systolic mmHg per week after onset
    anemia_onset: float | None = None
    anemia_rate: float = 0.0           # g/L per week
    fgr_onset: float | None = None
    fgr_rate: float = 0.0              # cm lag per week
    gdm: bool = False
    infection_week: float | None = None
    base_sys: float = 112.0
    base_dia: float = 72.0
    base_hb: float = 120.0
    base_glu: float = 4.5
    delivery_week: float = 39.5
    extras: dict = field(default_factory=dict)


def _pinfl(rng: np.random.Generator, birth: date) -> str:
    first = "4" if birth.year < 2000 else "6"
    tail = "".join(str(d) for d in rng.integers(0, 10, 7))
    return f"{first}{birth:%d%m%y}{tail}"


def _age(rng: np.random.Generator) -> float:
    u = rng.random()
    if u < 0.025:
        return rng.uniform(15.5, 18.0)
    if u < 0.06:
        return rng.uniform(18.0, 20.0)
    if u < 0.92:
        return rng.uniform(20.0, 35.0)
    return rng.uniform(35.0, 44.0)


def make_pregnancy(rng: np.random.Generator, region: dict, district: dict, seq: int,
                   lmp: date) -> tuple[dict, dict, Latent]:
    """Patient + pregnancy dicts (DB-shaped) and the hidden latent state."""
    age = _age(rng)
    birth = lmp - timedelta(days=int(age * 365.25))
    gravidity = int(1 + rng.poisson(1.6 if age > 22 else 0.5))
    miscarriages = int(rng.binomial(gravidity - 1, 0.05)) if gravidity > 1 else 0
    parity = max(0, gravidity - 1 - miscarriages)
    p = {
        "previous_cs": parity >= 1 and rng.random() < 0.07,
        "hist_stillbirth": parity >= 1 and rng.random() < 0.008,
        "hist_preterm": parity >= 1 and rng.random() < 0.02,
        "hist_preeclampsia": parity >= 1 and rng.random() < 0.015,
        "hist_pph": parity >= 1 and rng.random() < 0.015,
        "diabetes": rng.random() < 0.01,
        "chronic_htn": rng.random() < (0.03 if age >= 35 else 0.008),
        "heart": rng.random() < 0.006,
        "kidney": rng.random() < 0.008,
        "thyroid": rng.random() < 0.006,
        "epilepsy": rng.random() < 0.004,
        "multiple_pregnancy": rng.random() < 0.015,
        "rh_negative": rng.random() < 0.06,
    }
    height = float(np.clip(rng.normal(160, 6), 142, 185))
    bmi = float(np.clip(rng.normal(24.0, 3.0), 16, 45))
    booking_w = float(rng.uniform(13, 24)) if rng.random() < 0.06 else float(rng.uniform(7, 12))
    dist_centre = haversine_km(district["lat"], district["lon"], region["perinatal"]["lat"], region["perinatal"]["lon"])
    patient = {
        "code": f"{region['code']}-{district['code']}-{seq:05d}",
        "full_name": f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}",
        "pinfl": _pinfl(rng, birth),
        "phone": "+99890" + "".join(str(d) for d in rng.integers(0, 10, 7)),
        "birth_date": birth,
        "mahalla": f"{rng.choice(MAHALLAS)} MFY",
        "distance_to_perinatal_km": round(dist_centre + float(rng.uniform(0.2, 25)), 1),  # homes can be next to the centre
    }
    preg = {
        "lmp_date": lmp,
        "booking_date": lmp + timedelta(days=int(booking_w * 7)),
        "gravidity": gravidity, "parity": parity, "miscarriages_count": miscarriages,
        **{k: bool(v) for k, v in p.items()},
        "interpregnancy_months": int(np.clip(rng.gamma(3.5, 16.0), 4, 160)) if parity >= 1 else None,
        "height_cm": round(height, 1),
        "booking_weight_kg": round(bmi * (height / 100) ** 2, 1),
        "birth_date": birth,
        "distance_to_perinatal_km": patient["distance_to_perinatal_km"],
    }

    lat = Latent()
    lat.base_sys = rng.normal(112, 9) + (16 if p["chronic_htn"] else 0) + max(0, bmi - 28) * 0.8
    lat.base_dia = 0.62 * lat.base_sys + rng.normal(2, 5)
    lat.base_hb = rng.normal(128, 10) + region["hb_shift"]
    lat.base_glu = rng.normal(4.4, 0.22)
    pe_risk = -3.4 + 1.5 * p["hist_preeclampsia"] + 1.2 * p["chronic_htn"] + 0.6 * (age >= 35) \
        + 0.5 * (parity == 0) + 0.8 * p["multiple_pregnancy"] + 0.6 * (bmi >= 30) + 0.5 * p["kidney"]
    if rng.random() < 1 / (1 + np.exp(-pe_risk)):
        lat.pe_onset = float(rng.uniform(22, 35))
        lat.pe_rate = float(rng.uniform(1.5, 6.0))
    if rng.random() < 0.05 + (0.03 if region["hb_shift"] < -5 else 0) + 0.02 * (gravidity >= 4):
        lat.anemia_onset = float(rng.uniform(14, 30))
        lat.anemia_rate = float(rng.uniform(0.6, 2.0))
    if rng.random() < 0.05 + 0.04 * (lat.pe_onset is not None) + 0.03 * (age < 18):
        lat.fgr_onset = float(rng.uniform(24, 32))
        lat.fgr_rate = float(rng.uniform(0.25, 0.7))
    lat.gdm = bool(rng.random() < 0.02 + 0.05 * (bmi >= 30) + 0.03 * (age >= 35)) or p["diabetes"]
    if rng.random() < 0.03:
        lat.infection_week = float(rng.uniform(10, 38))
    preterm = rng.random() < 0.06 + 0.08 * p["hist_preterm"] + 0.15 * p["multiple_pregnancy"]
    lat.delivery_week = float(rng.uniform(30, 36.9) if preterm else rng.uniform(37, 41.5))
    return patient, preg, lat


def schedule(rng: np.random.Generator, booking_w: float, upto_w: float, max_visits: int = 9) -> list[float]:
    weeks, w = [booking_w], booking_w
    while True:
        step = 4.0 if w < 28 else (2.0 if w < 36 else 1.0)
        w = w + step + float(rng.uniform(-0.6, 0.6))
        if w > upto_w:
            break
        if rng.random() < 0.06:  # missed visit
            continue
        weeks.append(round(w, 1))
    if len(weeks) > max_visits:
        weeks = [weeks[0]] + weeks[-(max_visits - 1):]
    return weeks


def make_visit(rng: np.random.Generator, preg: dict, lat: Latent, w: float, prev_weight: float | None) -> dict:
    after = lambda onset: max(0.0, w - onset) if onset is not None else 0.0  # noqa: E731
    pe = after(lat.pe_onset)
    sys_ = lat.base_sys + 0.12 * max(0, w - 24) + lat.pe_rate * pe + rng.normal(0, 5)
    dia = lat.base_dia + 0.08 * max(0, w - 24) + 0.65 * lat.pe_rate * pe + rng.normal(0, 4)
    prot_level = 0
    if pe > 1.5:
        prot_level = int(np.clip(round(pe * lat.pe_rate / 8 + rng.normal(0, 0.5)), 0, 4))
    elif rng.random() < 0.05:
        prot_level = 1
    hb = lat.base_hb - 0.25 * max(0, w - 12) - lat.anemia_rate * after(lat.anemia_onset) + rng.normal(0, 3.5)
    glu = lat.base_glu + rng.normal(0, 0.2)
    if lat.gdm and w >= 22:
        glu += rng.uniform(0.7, 2.2) + (1.3 if preg["diabetes"] else 0)
    # weight is a smooth trajectory + small measurement noise (no spurious jumps)
    base_gain = 0.0 if w < 13 else 0.42 * (w - 13)
    edema = 1.1 * min(pe, 4) * (lat.pe_rate > 3.5)
    weight = preg["booking_weight_kg"] + lat.extras.setdefault("gain_k", rng.uniform(0.75, 1.25)) * base_gain         + edema + rng.normal(0, 0.25)
    temp = rng.normal(36.65, 0.22)
    if lat.infection_week is not None and abs(w - lat.infection_week) < 1.0:
        temp = rng.uniform(38.0, 39.2)
    fhr = fundal = None
    if w >= 20:
        fhr = int(np.clip(rng.normal(141, 7), 115, 165))
        if lat.fgr_onset is not None and w > lat.fgr_onset + 4 and rng.random() < 0.15:
            fhr = int(rng.uniform(100, 112))
        fundal = round(w + rng.normal(0, 1.1) - lat.fgr_rate * after(lat.fgr_onset)
                       + (3 if preg["multiple_pregnancy"] else 0), 1)
    symptoms: list[str] = []
    severe_pe = pe * lat.pe_rate > 25
    for sym, p_base, p_pe in [("severe_headache", 0.03, 0.45), ("visual_disturbance", 0.01, 0.25),
                              ("epigastric_pain", 0.01, 0.15), ("edema", 0.08, 0.6)]:
        if rng.random() < (p_pe if severe_pe else p_base):
            symptoms.append(sym)
    if w >= 28 and rng.random() < (0.15 if lat.fgr_onset and w > lat.fgr_onset else 0.015):
        symptoms.append("reduced_fetal_movement")
    if w >= 20 and rng.random() < 0.008:
        symptoms.append("bleeding")
    if w < 37 and lat.delivery_week < 37 and w > lat.delivery_week - 2 and rng.random() < 0.4:
        symptoms.append("contractions")
    if rng.random() < 0.004:
        symptoms.append("dyspnea")
    prot_names = ["neg", "trace", "+1", "+2", "+3"]
    return {
        "visit_date": preg["lmp_date"] + timedelta(days=int(round(w * 7))),
        "gestational_weeks": w,
        "systolic": int(round(sys_)), "diastolic": int(round(dia)),
        "proteinuria": prot_names[prot_level],
        "hemoglobin_g_l": round(float(np.clip(hb, 45, 160))),
        "fasting_glucose_mmol": round(float(np.clip(glu, 3.2, 14)), 1),
        "weight_kg": round(float(weight), 1),
        "temperature_c": round(float(temp), 1),
        "fetal_heart_rate": fhr,
        "fundal_height_cm": fundal,
        "symptoms": symptoms,
    }


def make_visits(rng: np.random.Generator, preg: dict, lat: Latent, upto_w: float) -> list[dict]:
    booking_w = (preg["booking_date"] - preg["lmp_date"]).days / 7
    visits, prev_w = [], None
    for w in schedule(rng, round(booking_w, 1), upto_w):
        v = make_visit(rng, preg, lat, w, prev_w)
        prev_w = v["weight_kg"]
        visits.append(v)
    return visits


def outcome_logit(preg: dict, lat: Latent, age: float) -> float:
    """Hidden composite-outcome model. NOT available to the ML model."""
    d = lat.delivery_week
    pe_sev = lat.pe_rate * max(0.0, d - lat.pe_onset) if lat.pe_onset is not None else 0.0
    an_sev = lat.anemia_rate * max(0.0, d - lat.anemia_onset) if lat.anemia_onset is not None else 0.0
    fgr_sev = lat.fgr_rate * max(0.0, d - lat.fgr_onset) if lat.fgr_onset is not None else 0.0
    return (0.075 * pe_sev + 0.05 * an_sev + 0.45 * fgr_sev + 2.0 * (d < 34)
            + 0.5 * (age >= 35) + 0.6 * (age < 18)
            + 0.7 * (preg["hist_stillbirth"] or preg["hist_preterm"] or preg["hist_preeclampsia"] or preg["hist_pph"])
            + 0.35 * preg["previous_cs"] + 0.8 * preg["multiple_pregnancy"]
            + 0.5 * (preg["chronic_htn"] or preg["diabetes"] or preg["heart"] or preg["kidney"])
            + 0.5 * lat.gdm + 0.3 * (preg["distance_to_perinatal_km"] > 50)
            + 0.3 * ((preg["booking_date"] - preg["lmp_date"]).days > 84))


def all_districts() -> list[tuple[dict, dict]]:
    return [(r, d) for r in REGIONS for d in r["districts"]]


def generate_training(n: int = 20000, seed: int = 42, target_rate: float = 0.10):
    """One row per visit: features + deltas + label + rule_zone. Returns a DataFrame."""
    import pandas as pd

    from app.risk.engine import rule_zone
    from app.risk.features import build_features
    from app.risk.rules import combine_factors, max_zone, red_rules, yellow_rules
    from app.risk.trends import trend_hits, trend_zone

    rng = np.random.default_rng(seed)
    dists = all_districts()
    base_day = date(2024, 1, 1)
    records, logits = [], []
    for i in range(n):
        region, district = dists[int(rng.integers(len(dists)))]
        lmp = base_day + timedelta(days=int(rng.integers(0, 600)))
        patient, preg, lat = make_pregnancy(rng, region, district, i, lmp)
        age = (lmp - patient["birth_date"]).days / 365.25
        logits.append(outcome_logit(preg, lat, age) + rng.normal(0, 0.6))
        visits = make_visits(rng, preg, lat, upto_w=lat.delivery_week)
        records.append((i, region["code"], preg, visits))
    logits_a = np.array(logits)
    lo, hi = -15.0, 5.0  # tune the intercept so the base rate hits the target
    for _ in range(60):
        mid = (lo + hi) / 2
        rate = (1 / (1 + np.exp(-(logits_a + mid)))).mean()
        lo, hi = (mid, hi) if rate < target_rate else (lo, mid)
    labels = rng.random(n) < 1 / (1 + np.exp(-(logits_a + lo)))

    rows = []
    for (pid, rcode, preg, visits), y in zip(records, labels):
        for k in range(len(visits)):
            hist = visits[: k + 1]
            prev = visits[k - 1] if k else None
            feats = build_features(preg, hist)
            th = trend_hits(preg, hist)
            rz = rule_zone(combine_factors(red_rules(preg, hist[-1]) + yellow_rules(preg, hist[-1], prev), th))
            tz = trend_zone(th)
            rows.append({"pregnancy_id": pid, "region": rcode, "visit_index": k, **feats,
                         "rule_zone": max_zone(rz, tz), "adverse_outcome": int(y)})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(Path(__file__).parent / "data" / "synthetic_pregnancies.csv.gz"))
    a = ap.parse_args()
    df = generate_training(a.n, a.seed)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    preg = df.groupby("pregnancy_id").first()
    last = df.groupby("pregnancy_id").last()
    print(f"Pregnancies: {len(preg):,}  visit rows: {len(df):,}  -> {a.out}")
    print(f"Adverse outcome rate: {preg['adverse_outcome'].mean():.1%}")
    print("Zone share at last visit (rules + trends):")
    print(last["rule_zone"].value_counts(normalize=True).round(3).to_string())
    print("Mean hemoglobin by region (g/L):")
    print(df.groupby("region")["hemoglobin"].mean().round(1).to_string())


if __name__ == "__main__":
    main()
