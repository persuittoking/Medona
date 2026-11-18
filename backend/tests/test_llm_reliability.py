"""Task 06: Gemini attempt chain (primary -> fallback model -> plain retry -> template), time budget,
background generation + cache, demo pre-warm. All clients are mocked: no network."""
import pytest

from app.llm import summary as S
from tests.test_llm import GOOD, _fake_client, _FakeResp, payload


class _ApiError(Exception):
    """Stand-in for google.genai.errors.APIError (it carries an HTTP `code`)."""

    def __init__(self, code: int):
        super().__init__(f"{code} UNAVAILABLE. This model is currently experiencing high demand.")
        self.code = code


def _good():
    return _FakeResp(GOOD, S.LlmOutput.model_validate_json(GOOD))


@pytest.fixture(autouse=True)
def _fresh_status(monkeypatch):
    monkeypatch.setattr(S, "_STATUS", dict(S._STATUS))


def test_primary_503_then_fallback_model_succeeds(monkeypatch):
    models = _fake_client(monkeypatch, [_ApiError(503), _good()], gemini_fallback_model="gemini-fallback")
    res, _, _ = S.generate_summary(payload())
    assert res["source"] == "ai"
    assert [c["model"] for c in models.calls] == ["gemini-test", "gemini-fallback"]
    assert all(c["config"].response_schema is S.LlmOutput for c in models.calls)  # both structured
    att = S.llm_status()["last_attempts"]
    assert [(a["model"], a["mode"], a["ok"]) for a in att] == [("gemini-test", "structured", False),
                                                               ("gemini-fallback", "structured", True)]
    assert "503" in att[0]["error"]


@pytest.mark.parametrize("err", [_ApiError(504), TimeoutError("read timed out"), _ApiError(429)])
def test_transient_errors_use_fallback(monkeypatch, err):
    models = _fake_client(monkeypatch, [err, _good()], gemini_fallback_model="gemini-fallback")
    res, _, _ = S.call_gemini(payload())
    assert res["source"] == "ai" and models.calls[1]["model"] == "gemini-fallback"


def test_both_models_fail_then_plain_retry(monkeypatch):
    plain = _FakeResp("```json\n" + GOOD + "\n```")
    models = _fake_client(monkeypatch, [_ApiError(503), _ApiError(503), plain], gemini_fallback_model="gemini-fallback")
    res, _, _ = S.call_gemini(payload())
    assert res["source"] == "ai" and len(models.calls) == 3
    assert models.calls[2]["config"].response_schema is None  # plain JSON-only prompt


def test_everything_fails_gives_shablon(monkeypatch):
    models = _fake_client(monkeypatch, [_ApiError(503)] * 3, gemini_fallback_model="gemini-fallback")
    res, _, _ = S.generate_summary(payload())
    assert res["source"] == "template" and len(models.calls) == 3
    st = S.llm_status()
    assert st["last_call_ok"] is False and len(st["last_attempts"]) == 3
    assert not any(a["ok"] for a in st["last_attempts"])


def test_non_transient_error_skips_fallback(monkeypatch):
    models = _fake_client(monkeypatch, [ValueError("bad json"), _good()], gemini_fallback_model="gemini-fallback")
    S.call_gemini(payload())
    assert [c["model"] for c in models.calls] == ["gemini-test", "gemini-test"]  # straight to the plain retry


def test_no_fallback_configured_goes_to_plain_retry(monkeypatch):
    models = _fake_client(monkeypatch, [_ApiError(503), _good()])
    S.call_gemini(payload())
    assert [c["model"] for c in models.calls] == ["gemini-test", "gemini-test"]


def test_total_time_budget_is_respected(monkeypatch):
    """After a 30 s first attempt the 25 s budget is gone: no further attempt is started (-> template)."""
    ticks = iter([0.0, 0.0, 30.0, 30.0])
    monkeypatch.setattr(S.time, "monotonic", lambda: next(ticks, 30.0))
    models = _fake_client(monkeypatch, [_ApiError(503), _good()], gemini_fallback_model="gemini-fallback",
                          llm_timeout_s=25)
    res, _, _ = S.generate_summary(payload())
    assert res["source"] == "template" and len(models.calls) == 1
    assert "budget" in S.llm_status()["last_attempts"][-1]["error"]


def test_each_call_gets_remaining_budget_as_timeout(monkeypatch):
    models = _fake_client(monkeypatch, [_good()], llm_timeout_s=12, llm_attempt_timeout_s=30)
    S.call_gemini(payload())
    assert 10_000 <= models.calls[0]["config"].http_options.timeout <= 12_000  # Gemini minimum is 10 s


def test_plain_retry_skipped_when_less_than_10s_left(monkeypatch):
    """25 s budget: primary 10 s timeout + fallback 10 s timeout leave 5 s -> no plain retry, template."""
    ticks = iter([0.0, 0.0, 0.0, 10.0, 10.0, 10.0, 20.0, 20.0])
    monkeypatch.setattr(S.time, "monotonic", lambda: next(ticks, 20.0))
    models = _fake_client(monkeypatch, [TimeoutError("t"), TimeoutError("t"), _good()],
                          gemini_fallback_model="gemini-fallback", llm_timeout_s=25)
    res, _, _ = S.generate_summary(payload())
    assert res["source"] == "template" and len(models.calls) == 2


def test_each_attempt_is_capped_so_fallback_gets_time(monkeypatch):
    models = _fake_client(monkeypatch, [TimeoutError("read timed out"), _good()],
                          gemini_fallback_model="gemini-fallback", llm_timeout_s=25, llm_attempt_timeout_s=10)
    S.call_gemini(payload())
    assert [c["config"].http_options.timeout for c in models.calls] == [10_000, 10_000]


def test_lowest_thinking_setting():
    assert S.thinking_config("gemini-3.1-flash-lite").thinking_level.value.lower() == "minimal"
    assert S.thinking_config("gemini-3.8-flash").thinking_level.value.lower() == "low"
    assert S.thinking_config("other-model") is None


# ---------- background generation + cache ----------
def _drop_cache(preg_id: int) -> int:
    from app.db import SessionLocal
    from app.services import ai_summary as A
    from app.services.scoring import latest_assessment

    with SessionLocal() as db:
        ra = latest_assessment(db, preg_id)
        old = A.get_cached(db, ra.id)
        if old is not None:
            db.delete(old)
            db.commit()
        return ra.id


def test_background_generation_stores_cached_result(client, monkeypatch):
    from app.db import SessionLocal
    from app.services import ai_summary as A
    from tests.conftest import NUK, demo, login

    fake = {"version": S.SUMMARY_VERSION, "source": "ai", "model": "gemini-mock", "summary_uz": "Mock xulosa.", "key_concerns": [],
            "recommended_actions": [], "questions_to_ask_patient_uz": [], "disclaimer_uz": S.DISCLAIMER_UZ}
    monkeypatch.setattr(A, "generate_summary", lambda p: (fake, 5, 3))
    _, preg = demo("QQR-NUK-DEMO1")
    ra_id = _drop_cache(preg)
    A.generate_cached(ra_id)
    with SessionLocal() as db:
        row = A.get_cached(db, ra_id)
        assert row is not None and row.source == "ai" and row.payload["model"] == "gemini-mock"
        assert row.input_tokens == 5
    assert not A.is_pending(ra_id)
    body = client.get(f"/api/llm/summary/{preg}", headers=login(client, NUK, "specialist")).json()
    assert body["status"] == "ready" and body["summary_uz"] == "Mock xulosa."


def test_visit_save_generates_summary_in_background(client, monkeypatch):
    from app.services import ai_summary as A
    from tests.conftest import NUK, demo, login

    calls = []

    def fake(p):
        calls.append(p["patient_code"])
        return S.template_summary(p) | {"source": "ai", "model": "gemini-mock"}, 1, 1

    monkeypatch.setattr(A, "generate_summary", fake)
    _, preg = demo("QQR-NUK-DEMO2")
    r = client.post("/api/visits", json={"pregnancy_id": preg, "systolic": 120, "diastolic": 78},
                    headers=login(client, NUK, "nurse"))
    assert r.status_code == 201
    assert calls == ["QQR-NUK-DEMO2"]  # TestClient runs BackgroundTasks before returning
    body = client.get(f"/api/llm/summary/{preg}", headers=login(client, NUK, "specialist")).json()
    assert body["status"] == "ready" and body["source"] == "ai" and body["model"] == "gemini-mock"


def test_summary_endpoint_returns_pending_when_llm_enabled(client, monkeypatch):
    from app.api import llm as llm_api
    from tests.conftest import NUK, demo, login

    real = llm_api.get_settings()
    monkeypatch.setattr(llm_api, "get_settings", lambda: real.model_copy(update={"gemini_api_key": "fake"}))
    scheduled = []
    monkeypatch.setattr(llm_api, "generate_cached", lambda ra_id: scheduled.append(ra_id))
    _, preg = demo("QQR-NUK-DEMO3")
    ra_id = _drop_cache(preg)
    r = client.get(f"/api/llm/summary/{preg}", headers=login(client, NUK, "specialist"))
    assert r.status_code == 202 and r.json() == {"status": "pending", "risk_assessment_id": ra_id}
    assert scheduled == [ra_id]


def test_prewarm_generates_demo_summaries(client, monkeypatch):
    from app.db import SessionLocal
    from app.models import LlmSummaryCache
    from app.services import ai_summary as A

    with SessionLocal() as db:
        db.query(LlmSummaryCache).delete()
        db.commit()
    monkeypatch.setattr(A, "generate_summary", lambda p: (S.template_summary(p), None, None))
    assert A.prewarm_demo_patients(gap_s=0) == 4
    assert A.prewarm_demo_patients(gap_s=0) == 0  # already cached


def test_prewarm_not_scheduled_without_key(client):
    from app.scheduler import PREWARM_JOB_ID

    assert client.app.state.scheduler.get_job(PREWARM_JOB_ID) is None


def test_health_lists_attempts(client, monkeypatch):
    from tests.conftest import login

    monkeypatch.setattr(S, "_STATUS", S._STATUS | {"last_call_ok": True, "last_attempts": [
        {"model": "a", "mode": "structured", "ok": False, "seconds": 1.0, "error": "ServerError: 503"},
        {"model": "b", "mode": "structured", "ok": True, "seconds": 2.0, "error": None}]})
    body = client.get("/api/llm/health", headers=login(client, None, "region.admin")).json()
    assert [a["model"] for a in body["last_attempts"]] == ["a", "b"] and "fallback_model" in body
