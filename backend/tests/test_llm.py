"""LLM summary: PII never reaches the prompt, catalog validation, fallback path."""
import json
from datetime import date, timedelta

import pytest

from app.llm import summary as S
from app.llm.actions import ACTIONS, validate_codes

PII = {"full_name": "Dilnoza Karimova", "pinfl": "41234567890123", "phone": "+998901234567",
       "mahalla": "Navbahor MFY", "address": "Nukus, Amir Temur ko'chasi 5"}

PREG = {"lmp_date": date.today() - timedelta(weeks=31), "gravidity": 1, "parity": 0, "miscarriages_count": 0,
        "previous_cs": False, "rh_negative": True, "full_name": PII["full_name"], "pinfl": PII["pinfl"]}
VISITS = [
    {"visit_date": date.today() - timedelta(days=14), "gestational_weeks": 29, "systolic": 136, "diastolic": 88,
     "hemoglobin_g_l": 104, "symptoms": [], "notes": f"Telefon {PII['phone']}, manzil {PII['address']}"},
    {"visit_date": date.today(), "gestational_weeks": 31, "systolic": 152, "diastolic": 98, "proteinuria": "+2",
     "hemoglobin_g_l": 103, "symptoms": ["severe_headache"], "notes": PII["full_name"], "mahalla": PII["mahalla"]},
]
ASSESSMENT = {"zone": "red", "ml_probability": 0.82,
              "rule_hits": [{"code": "R02", "zone": "red", "uz_text": "Preeklampsiya shubhasi (AB 152/98, proteinuriya +2)"}],
              "trend_hits": [], "shap_top": [{"feature": "systolic", "uz_label": "Sistolik bosim 152", "direction": "up",
                                              "shap": 0.9, "value": 152}]}


def payload():
    return S.build_llm_input("QQR-NUK-DEMO1", date(2007, 1, 1), PREG, VISITS, ASSESSMENT)


def test_no_pii_reaches_the_prompt():
    text = json.dumps(payload(), ensure_ascii=False, default=str) + S.SYSTEM_PROMPT
    for value in PII.values():
        assert value not in text
    p = payload()
    assert p["patient_code"] == "QQR-NUK-DEMO1"
    assert all("notes" not in v and "mahalla" not in v for v in p["last_visits"])
    assert not {"full_name", "pinfl", "phone", "birth_date"} & set(p)


def test_catalog_validation_drops_invented_codes():
    assert validate_codes(["A01", "a03", "X99", "A01", "A777", "Give 10mg drug"]) == ["A01", "A03"]


def test_finalize_drops_invented_actions_and_untied_concerns():
    out = S.LlmOutput(summary_uz="Holat og'ir.", recommended_action_codes=["A01", "Z42"],
                      key_concerns=[S.Concern(code="R02", text_uz="ok"), S.Concern(code="R99", text_uz="invented")],
                      questions_to_ask_patient_uz=["Bosh og'riyaptimi?"])
    res = S._finalize(out, payload(), "ai", "m")
    assert [a["code"] for a in res["recommended_actions"]] == ["A01"]
    assert [c["code"] for c in res["key_concerns"]] == ["R02"]
    assert res["disclaimer_uz"] == S.DISCLAIMER_UZ


def test_template_fallback_without_key(monkeypatch):
    monkeypatch.setattr(S, "get_settings", lambda: type("S", (), {"anthropic_api_key": ""})())
    res, tin, tout = S.generate_summary(payload())
    assert res["source"] == "template" and tin is None
    assert "QIZIL" in res["summary_uz"]
    assert {a["code"] for a in res["recommended_actions"]} >= {"A01", "A03"}
    assert all(a["code"] in ACTIONS for a in res["recommended_actions"])


@pytest.mark.parametrize("exc", [TimeoutError("t"), ValueError("invalid json"), RuntimeError("refusal")])
def test_fallback_on_llm_failure(monkeypatch, exc):
    monkeypatch.setattr(S, "get_settings", lambda: type("S", (), {"anthropic_api_key": "sk-test"})())

    def boom(_):
        raise exc

    monkeypatch.setattr(S, "call_claude", boom)
    res, _, _ = S.generate_summary(payload())
    assert res["source"] == "template"
