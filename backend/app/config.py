from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./assistant.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_ttl_hours: int = 24 * 7
    # Fernet key (urlsafe base64, 32 bytes). Derived from jwt_secret when empty (dev only).
    token_encryption_key: str = ""

    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    # When true, the plan job runs inside the API process instead of the worker.
    run_jobs_inline: bool = False

    llm_provider: str = ""  # "openai" | "anthropic" | "" (rule-based fallback)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    slack_client_id: str = ""
    slack_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant: str = "common"
    fitbit_client_id: str = ""
    fitbit_client_secret: str = ""
    oura_client_id: str = ""
    oura_client_secret: str = ""

    lookback_hours: int = 48


@lru_cache
def get_settings() -> Settings:
    return Settings()
