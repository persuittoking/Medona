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
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    llm_timeout_s: float = 25.0  # Gemini 3.8 Flash takes ~15 s for this prompt
    telegram_bot_token: str = ""
    demo_mode: bool = True
    sla_red_minutes: int = 120
    sla_yellow_hours: int = 72

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
        """In DEMO_MODE the red SLA is 2 minutes so escalation can be shown live."""
        return 2 if self.demo_mode else self.sla_red_minutes


@lru_cache
def get_settings() -> Settings:
    return Settings()
