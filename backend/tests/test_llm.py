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


def _settings(key: str, **kw):
    from app.config import Settings

    return Settings(_env_file=None, gemini_api_key=key, llm_provider="gemini", gemini_model="gemini-test", **kw)


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
    monkeypatch.setattr(S, "get_settings", lambda: _settings(""))
    res, tin, tout = S.generate_summary(payload())
    assert res["source"] == "template" and tin is None
    assert "QIZIL" in res["summary_uz"]
    assert {a["code"] for a in res["recommended_actions"]} >= {"A01", "A03"}
    assert all(a["code"] in ACTIONS for a in res["recommended_actions"])


@pytest.mark.parametrize("exc", [TimeoutError("t"), ValueError("invalid json"), RuntimeError("refusal")])
def test_fallback_on_llm_failure(monkeypatch, exc):
    monkeypatch.setattr(S, "get_settings", lambda: _settings("fake-test-key"))

    def boom(*_):
        raise exc

    monkeypatch.setattr(S, "call_gemini", boom)
    res, _, _ = S.generate_summary(payload())
    assert res["source"] == "template"


# ---------- GET /api/llm/health ----------
def test_status_records_failure_then_success(monkeypatch):
    monkeypatch.setattr(S, "get_settings", lambda: _settings("fake-test-key"))
    monkeypatch.setattr(S, "_STATUS", dict(S._STATUS))

    def boom(*_):
        raise TimeoutError("read timed out " + "x" * 1000)

    monkeypatch.setattr(S, "call_gemini", boom)
    S.generate_summary(payload())
    st = S.llm_status()
    assert st["last_call_ok"] is False and st["last_error"].startswith("TimeoutError: read timed out")
    assert len(st["last_error"]) <= 300 and st["last_call_at"] is not None

    monkeypatch.setattr(S, "call_gemini", lambda p, *_: (S.template_summary(p) | {"source": "ai", "model": "m-1"}, 10, 5))
    S.generate_summary(payload())
    st = S.llm_status()
    assert st["last_call_ok"] is True and st["last_error"] is None and st["last_model"] == "m-1"


def test_status_untouched_without_key(monkeypatch):
    monkeypatch.setattr(S, "get_settings", lambda: _settings(""))
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

    secret = "test-only-fake-gemini-key-123"
    real = llm_api.get_settings()
    monkeypatch.setattr(llm_api, "get_settings", lambda: real.model_copy(update={"gemini_api_key": secret}))
    r = client.get("/api/llm/health", headers=login(client, None, "region.admin"))
    assert r.json()["key_present"] is True and secret not in r.text


def test_health_reports_provider(client):
    from tests.conftest import login

    body = client.get("/api/llm/health", headers=login(client, None, "region.admin")).json()
    assert body["provider"] == "gemini" and body["configured_model"]


def test_settings_strip_crlf_and_spaces():
    from app.config import Settings

    s = Settings(_env_file=None, gemini_api_key=" abc123\r", gemini_model="gemini-x\r\n", llm_provider="Gemini\r")
    assert s.gemini_api_key == "abc123" and s.gemini_model == "gemini-x" and s.llm_enabled


def test_settings_strip_crlf_from_env_file(tmp_path, monkeypatch):
    from app.config import Settings

    for k in ("GEMINI_API_KEY", "GEMINI_MODEL", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)

    f = tmp_path / ".env"
    f.write_bytes(b"LLM_PROVIDER=gemini\r\nGEMINI_API_KEY=k-123 \r\nGEMINI_MODEL=gemini-y\r\n")
    s = Settings(_env_file=f)
    assert s.gemini_api_key == "k-123" and s.gemini_model == "gemini-y"


def test_error_redacts_key(monkeypatch):
    monkeypatch.setattr(S, "get_settings", lambda: _settings("secret-key-xyz"))
    monkeypatch.setattr(S, "_STATUS", dict(S._STATUS))

    def boom(*_):
        raise RuntimeError("bad request for key=secret-key-xyz")

    monkeypatch.setattr(S, "call_gemini", boom)
    S.generate_summary(payload())
    assert "secret-key-xyz" not in S.llm_status()["last_error"]


class _FakeResp:
    def __init__(self, text, parsed=None):
        self.text, self.parsed, self.model_version = text, parsed, "gemini-test-001"
        self.usage_metadata = type("U", (), {"prompt_token_count": 11, "candidates_token_count": 7})()


class _FakeModels:
    def __init__(self, responses):
        self.calls, self._responses = [], list(responses)

    def generate_content(self, **kw):
        self.calls.append(kw)
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _fake_client(monkeypatch, responses, **settings_kw):
    models = _FakeModels(responses)
    monkeypatch.setattr(S, "get_settings", lambda: _settings("fake-test-key", **settings_kw))
    monkeypatch.setattr(S, "_gemini_client", lambda: type("C", (), {"models": models})())
    return models


GOOD = json.dumps({"summary_uz": "Preeklampsiya xavf belgisi.", "key_concerns": [{"code": "R02", "text_uz": "AB"}],
                   "recommended_action_codes": ["A01", "X9"], "questions_to_ask_patient_uz": ["Bosh og'riyaptimi?"]})


def test_gemini_structured_success(monkeypatch):
    models = _fake_client(monkeypatch, [_FakeResp(GOOD, S.LlmOutput.model_validate_json(GOOD))])
    res, tin, tout = S.call_gemini(payload())
    assert res["source"] == "ai" and res["model"] == "gemini-test-001" and (tin, tout) == (11, 7)
    assert [a["code"] for a in res["recommended_actions"]] == ["A01"]
    cfg = models.calls[0]["config"]
    assert cfg.response_mime_type == "application/json" and cfg.response_schema is S.LlmOutput
    # only the de-identified payload is sent
    assert "QQR-NUK-DEMO1" in models.calls[0]["contents"]
    for value in PII.values():
        assert value not in models.calls[0]["contents"]


def test_gemini_retries_once_without_schema(monkeypatch):
    models = _fake_client(monkeypatch, [RuntimeError("schema error"), _FakeResp("```json\n" + GOOD + "\n```")])
    res, _, _ = S.call_gemini(payload())
    assert res["source"] == "ai" and len(models.calls) == 2
    assert models.calls[1]["config"].response_schema is None


def test_gemini_two_failures_fall_back_to_template(monkeypatch):
    models = _fake_client(monkeypatch, [RuntimeError("a"), _FakeResp("not json")])
    monkeypatch.setattr(S, "_STATUS", dict(S._STATUS))
    res, _, _ = S.generate_summary(payload())
    assert res["source"] == "template" and len(models.calls) == 2
