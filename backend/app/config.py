"""Application settings, read from environment / backend/.env."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEV_JWT_SECRET = "dev-only-insecure-secret"  # dev fallback: allowed ONLY in DEMO_MODE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./onaradar.db"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_minutes: int = 60 * 12
    fernet_key: str = ""
    pinfl_hash_secret: str = ""  # HMAC-SHA256 key for exact-match JShShIR lookup (DEMO_MODE falls back to jwt_secret)
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
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"  # comma-separated
    login_rate_limit: int = 20  # POST /api/auth/login attempts per client IP per window (0 = off)
    login_rate_window_s: int = 600

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, v: object) -> object:
        """.env files edited on Windows may carry CRLF / stray spaces: strip them so keys stay valid."""
        return v.strip().strip("\r").strip() if isinstance(v, str) else v

    def secret_problems(self) -> list[str]:
        """Weak secrets. Outside DEMO_MODE the backend refuses to start if this is not empty (never prints values)."""
        problems = []
        if not self.jwt_secret or self.jwt_secret == DEV_JWT_SECRET:
            problems.append("JWT_SECRET is empty or the dev default")
        if not self.pinfl_hash_secret:
            problems.append("PINFL_HASH_SECRET is empty")
        elif self.pinfl_hash_secret == self.jwt_secret:
            problems.append("PINFL_HASH_SECRET must differ from JWT_SECRET")
        if not self.fernet_key:
            problems.append("FERNET_KEY is empty")
        return problems

    def check_secrets(self) -> None:
        """Called on startup. DEMO_MODE keeps the dev fallbacks; production refuses to start with weak secrets."""
        problems = self.secret_problems()
        if problems and not self.demo_mode:
            raise RuntimeError("Refusing to start (DEMO_MODE=false): " + "; ".join(problems))

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
