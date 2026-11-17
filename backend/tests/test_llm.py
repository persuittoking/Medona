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


# ---------- GET /api/llm/health ----------
def test_status_records_failure_then_success(monkeypatch):
    monkeypatch.setattr(S, "get_settings", lambda: type("S", (), {"anthropic_api_key": "sk-test"})())
    monkeypatch.setattr(S, "_STATUS", dict(S._STATUS))

    def boom(_):
        raise TimeoutError("read timed out " + "x" * 1000)

    monkeypatch.setattr(S, "call_claude", boom)
    S.generate_summary(payload())
    st = S.llm_status()
    assert st["last_call_ok"] is False and st["last_error"].startswith("TimeoutError: read timed out")
    assert len(st["last_error"]) <= 300 and st["last_call_at"] is not None

    monkeypatch.setattr(S, "call_claude", lambda p: (S.template_summary(p) | {"source": "ai", "model": "m-1"}, 10, 5))
    S.generate_summary(payload())
    st = S.llm_status()
    assert st["last_call_ok"] is True and st["last_error"] is None and st["last_model"] == "m-1"


def test_status_untouched_without_key(monkeypatch):
    monkeypatch.setattr(S, "get_settings", lambda: type("S", (), {"anthropic_api_key": ""})())
    monkeypatch.setattr(S, "_STATUS", {"last_call_at": None, "last_call_ok": None, "last_error": None, "last_model": None})
    S.generate_summary(payload())
    assert S.llm_status()["last_call_ok"] is None  # template mode is not an LLM call


def test_llm_health_endpoint_admin_only(client, monkeypatch):
    from tests.conftest import NUK, login

    h = login(client, None, "region.admin")
    body = client.get("/api/llm/health", headers=h).json()
    assert body["key_present"] is False and body["mode"] == "template"
    assert set(body) >= {"key_present", "last_call", "last_error", "last_call_at"}
    for role in ("nurse", "doctor", "specialist"):
        assert client.get("/api/llm/health", headers=login(client, NUK, role)).status_code == 403
    assert client.get("/api/llm/health").status_code == 401

    monkeypatch.setattr(S, "_STATUS", {"last_call_at": None, "last_call_ok": False,
                                       "last_error": "AuthenticationError: invalid x-api-key", "last_model": None})
    body = client.get("/api/llm/health", headers=login(client, None, "district.admin")).json()
    assert body["last_call"] == "failed" and "AuthenticationError" in body["last_error"]


def test_llm_health_never_returns_the_key(client, monkeypatch):
    from app.api import llm as llm_api
    from tests.conftest import login

    secret = "sk-ant-very-secret-key"
    real = llm_api.get_settings()
    monkeypatch.setattr(llm_api, "get_settings", lambda: real.model_copy(update={"anthropic_api_key": secret}))
    r = client.get("/api/llm/health", headers=login(client, None, "region.admin"))
    assert r.json()["key_present"] is True and secret not in r.text
