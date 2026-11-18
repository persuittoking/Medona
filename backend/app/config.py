"""Application settings, read from environment / backend/.env."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./onaradar.db"
    jwt_secret: str = "dev-only-insecure-secret"
    jwt_expire_minutes: int = 60 * 12
    fernet_key: str = ""
    pinfl_hash_secret: str = ""  # HMAC-SHA256 key for exact-match JShShIR lookup (defaults to jwt_secret)
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_fallback_model: str = ""  # tried when the primary model returns 503/504 or times out
    llm_timeout_s: float = 25.0  # total budget for all LLM attempts of one summary
    llm_attempt_timeout_s: float = 10.0  # cap per attempt (Gemini minimum is 10 s): a hung primary leaves time for the fallback
    llm_prewarm: bool = True  # on startup, pre-generate AI summaries for the DEMO1-DEMO4 patients
    telegram_bot_token: str = ""
    demo_mode: bool = True
    sla_red_minutes: int = 120
    demo_sla_red_minutes: int = 10  # red SLA in DEMO_MODE; long enough not to escalate mid-pitch
    sla_yellow_hours: int = 72
    light_visit_max_weeks: float = 36.0  # from this week all remaining scheduled visits stay "To'liq"
    minutes_saved_per_light_visit: int = 10  # estimated doctor minutes saved per confirmed light visit (demo)
    propose_fewer_visits: bool = False  # OFF by default; docs-only "Vazirlikka taklif", 12 visits are never reduced

    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, v: object) -> object:
        """.env files edited on Windows may carry CRLF / stray spaces: strip them so keys stay valid."""
        return v.strip().strip("\r").strip() if isinstance(v, str) else v

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider.lower() == "gemini" and bool(self.gemini_api_key)

    @property
    def effective_sla_red_minutes(self) -> int:
        """In DEMO_MODE the red SLA is DEMO_SLA_RED_MINUTES (escalation is then shown via the demo button)."""
        return self.demo_sla_red_minutes if self.demo_mode else self.sla_red_minutes


@lru_cache
def get_settings() -> Settings:
    return Settings()
