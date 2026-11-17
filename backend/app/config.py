"""Application settings, read from environment / backend/.env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "sqlite:///./onaradar.db"
    jwt_secret: str = "dev-only-insecure-secret"
    jwt_expire_minutes: int = 60 * 12
    fernet_key: str = ""
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5-5"
    llm_timeout_s: float = 15.0
    telegram_bot_token: str = ""
    demo_mode: bool = True
    sla_red_minutes: int = 120
    sla_yellow_hours: int = 72

    @property
    def effective_sla_red_minutes(self) -> int:
        """In DEMO_MODE the red SLA is 2 minutes so escalation can be shown live."""
        return 2 if self.demo_mode else self.sla_red_minutes


@lru_cache
def get_settings() -> Settings:
    return Settings()
