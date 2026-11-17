"""AI clinical summary ("AI xulosa"): de-identified input -> Claude -> validated JSON, with a template fallback.

Privacy: the LLM never receives name, PINFL, phone, address/mahalla or free-text notes —
only the pseudonymous patient code and clinical features (see build_llm_input + its test).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm.actions import ACTIONS, RULE_ACTIONS, validate_codes
from app.risk.engine import ZONE_UZ
from app.risk.features import age_years, gest_weeks

log = logging.getLogger("onaradar.llm")

DISCLAIMER_UZ = "Bu tavsiya qaror qabul qilishda yordam uchun. Yakuniy qarorni shifokor qabul qiladi."

# Only these keys may ever appear in the LLM input (allow-list, not a deny-list).
VISIT_KEYS = ["gestational_weeks", "systolic", "diastolic", "proteinuria", "hemoglobin_g_l",
              "fasting_glucose_mmol", "weight_kg", "temperature_c", "fetal_heart_rate", "fundal_height_cm", "symptoms"]
HISTORY_FLAGS = ["previous_cs", "hist_stillbirth", "hist_preterm", "hist_preeclampsia", "hist_pph", "diabetes",
                 "chronic_htn", "heart", "kidney", "thyroid", "epilepsy", "multiple_pregnancy", "rh_negative"]

SYSTEM_PROMPT = f"""Siz O'zbekistondagi patronaj hamshiralari va OvaBMU mutaxassislari uchun akusherlik bo'yicha \
qaror qabul qilishni qo'llab-quvvatlovchi yordamchisiz.

Sizga homilador ayolning taxallusli kodi va klinik ko'rsatkichlari, risk-tizim natijasi (zona, qoida kodlari, \
dinamika kodlari, model omillari) beriladi. Shaxsni aniqlovchi ma'lumot berilmaydi va so'ralmaydi.

Qoidalar:
- Faqat o'zbek tilida, lotin yozuvida, sodda va hurmatli tilda yozing.
- Tashxis qo'ymang. "xavf belgisi", "shubha" so'zlarini ishlating. Dori nomi va dozasini yozmang.
- summary_uz: 3-4 gap — hozirgi holat, nima o'zgargan, nega bu zona.
- key_concerns: har biri berilgan qoida/dinamika kodi yoki model omili nomiga bog'langan bo'lsin (code maydoni).
- recommended_action_codes: FAQAT quyidagi katalogdagi kodlarni tanlang (3-5 ta, eng muhimi birinchi). \
Katalogda yo'q harakatni taklif qilmang.
- questions_to_ask_patient_uz: bemordan so'rash uchun 2-4 qisqa savol.
- Berilmagan ma'lumotni o'ylab topmang.

Harakatlar katalogi:
{json.dumps(ACTIONS, ensure_ascii=False, indent=0)}
"""


class Concern(BaseModel):
    code: str
    text_uz: str


class LlmOutput(BaseModel):
    summary_uz: str
    key_concerns: list[Concern] = Field(default_factory=list)
    recommended_action_codes: list[str] = Field(default_factory=list)
    questions_to_ask_patient_uz: list[str] = Field(default_factory=list)


def build_llm_input(patient_code: str, birth_date: date, preg: dict, visits: list[dict], assessment: dict,
                    today: date | None = None) -> dict:
    """De-identified payload. Built from an allow-list, so new PII columns can never leak in."""
    today = today or date.today()
    last3 = visits[-3:]
    deltas = {}
    if len(last3) >= 2:
        a, b = last3[-2], last3[-1]
        for k in ("systolic", "diastolic", "hemoglobin_g_l", "weight_kg"):
            if a.get(k) is not None and b.get(k) is not None:
                deltas[k] = round(float(b[k]) - float(a[k]), 1)
    return {
        "patient_code": patient_code,
        "age": int(age_years(birth_date, today)),
        "gestational_weeks": gest_weeks(preg["lmp_date"], today),
        "gravidity": preg.get("gravidity"),
        "parity": preg.get("parity"),
        "miscarriages_count": preg.get("miscarriages_count", 0),
        "history_flags": [k for k in HISTORY_FLAGS if preg.get(k)],
        "last_visits": [{k: v.get(k) for k in VISIT_KEYS} for v in last3],
        "deltas_vs_previous_visit": deltas,
        "zone": assessment["zone"],
        "ml_probability": assessment.get("ml_probability"),
        "rule_hits": [{"code": h["code"], "zone": h["zone"], "text": h["uz_text"]} for h in assessment.get("rule_hits", [])],
        "trend_hits": [{"code": h["code"], "text": h["uz_text"]} for h in assessment.get("trend_hits", [])],
        "shap_top": [{"feature": s["feature"], "label": s["uz_label"], "direction": s["direction"]}
                     for s in assessment.get("shap_top", [])],
    }


def _finalize(out: LlmOutput, payload: dict, source: str, model: str | None) -> dict:
    allowed = {h["code"] for h in payload["rule_hits"] + payload["trend_hits"]} | {s["feature"] for s in payload["shap_top"]}
    concerns = [c.model_dump() for c in out.key_concerns if c.code in allowed][:6]
    codes = validate_codes(out.recommended_action_codes)[:6]
    return {
        "source": source, "model": model,
        "summary_uz": out.summary_uz.strip(),
        "key_concerns": concerns,
        "recommended_actions": [{"code": c, "text_uz": ACTIONS[c]} for c in codes],
        "questions_to_ask_patient_uz": [q.strip() for q in out.questions_to_ask_patient_uz if q.strip()][:4],
        "disclaimer_uz": DISCLAIMER_UZ,
    }


def template_summary(payload: dict) -> dict:
    """Deterministic fallback: no network, built from rule/trend hits + SHAP + rule->action table."""
    # Tier B factors ("factor") go last: they are follow-up notes, not the reason for the zone.
    hits = sorted(payload["rule_hits"] + payload["trend_hits"], key=lambda h: h.get("zone") == "factor")
    zone = payload["zone"]
    s = [f"{payload['patient_code']}: {payload['age']} yosh, homiladorlik muddati {payload['gestational_weeks']:g} hafta, "
         f"hozirgi zona — {ZONE_UZ[zone]}."]
    if hits:
        s.append("Asosiy xavf belgilari: " + "; ".join(h["text"] for h in hits[:3]) + ".")
    else:
        s.append("Klinik qoidalar bo'yicha xavf belgilari aniqlanmadi.")
    ups = [x["label"] for x in payload["shap_top"] if x["direction"] == "up"][:2]
    if payload.get("ml_probability") is not None:
        s.append(f"Model bo'yicha xavf ehtimoli {payload['ml_probability']:.0%}" + (f" (omillar: {', '.join(ups)})." if ups else "."))
    s.append("Rejalashtirilgan kuzatuvni davom ettirish tavsiya etiladi." if zone == "green"
             else "Holat mutaxassis tomonidan ko'rib chiqilishi kerak.")
    codes: list[str] = []
    for h in hits:
        codes += RULE_ACTIONS.get(h["code"], [])
    if not codes:
        codes = ["A16", "A11"] if zone == "green" else ["A10", "A07"]
    questions = ["Bosh og'rig'i, ko'z oldi qorong'ilashishi yoki shish bormi?", "Homila harakatini qanday sezyapsiz?"]
    if any(h["code"] in ("R03", "Y06", "T01") for h in hits):
        questions.append("Temir preparatlarini muntazam qabul qilyapsizmi?")
    if any(h["code"] in ("Y13",) for h in hits):
        questions.append("Tashrifga kelishingizga nima xalaqit berdi?")
    out = LlmOutput(summary_uz=" ".join(s),
                    key_concerns=[Concern(code=h["code"], text_uz=h["text"]) for h in hits[:5]],
                    recommended_action_codes=codes, questions_to_ask_patient_uz=questions)
    return _finalize(out, payload, "template", None)


def call_claude(payload: dict) -> tuple[dict, int | None, int | None]:
    """Call Claude with JSON-only structured output. Raises on any failure (caller falls back)."""
    import anthropic

    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.llm_timeout_s, max_retries=0)
    resp = client.beta.messages.parse(
        model=s.llm_model,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # on a policy refusal the API retries on a fallback model in the same call
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "Bemor ma'lumotlari (JSON):\n" + json.dumps(payload, ensure_ascii=False, default=str)}],
        output_format=LlmOutput,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"LLM returned no usable output (stop_reason={resp.stop_reason})")
    usage = resp.usage
    log.info("llm summary tokens: in=%s out=%s model=%s", usage.input_tokens, usage.output_tokens, resp.model)
    return _finalize(resp.parsed_output, payload, "ai", resp.model), usage.input_tokens, usage.output_tokens


# In-process status of the most recent real LLM call (for GET /api/llm/health). Never holds payloads.
_STATUS: dict = {"last_call_at": None, "last_call_ok": None, "last_error": None, "last_model": None}
_ERROR_MAX_CHARS = 300


def llm_status() -> dict:
    return dict(_STATUS)


def _record_call(ok: bool, error: Exception | None = None, model: str | None = None) -> None:
    _STATUS["last_call_at"] = datetime.now(timezone.utc)
    _STATUS["last_call_ok"] = ok
    _STATUS["last_model"] = model
    _STATUS["last_error"] = None if error is None else f"{type(error).__name__}: {error}"[:_ERROR_MAX_CHARS]


def generate_summary(payload: dict) -> tuple[dict, int | None, int | None]:
    if not get_settings().anthropic_api_key:
        return template_summary(payload), None, None
    try:
        result = call_claude(payload)
    except Exception as e:  # noqa: BLE001 - any failure (timeout, invalid JSON, auth) -> template, demo never fails
        log.warning("LLM call failed, using template fallback: %s", type(e).__name__)
        _record_call(False, e)
        return template_summary(payload), None, None
    _record_call(True, model=result[0].get("model"))
    return result
