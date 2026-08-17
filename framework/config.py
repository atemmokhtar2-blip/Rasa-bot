from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "ai-developer-framework"
    app_env: str = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    database_url: str = "memory://"
    redis_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    rasa_endpoint: str | None = None
    worker_max_retries: int = 3
    nlu_timeout: float = 10.0
    intent_high_threshold: float = 0.80
    intent_low_threshold: float = 0.55
    session_timeout_minutes: int = 30
    action_timeout: float = 10.0
    plugin_timeout: float = 10.0
    rate_limit: int = 60
    api_key_pepper: str = "development-only-change-me"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    secret_manager_url: str | None = None
    secret_manager_token: str | None = None
    otel_exporter_endpoint: str | None = None
    audit_retention_days: int = 365
    model_config = SettingsConfigDict(env_file=(".env", ".env.development"), extra="ignore")

    @model_validator(mode="after")
    def validate_runtime_security(self):
        if self.app_env in {"production", "staging"} and self.api_key_pepper == "development-only-change-me":
            raise ValueError("API_KEY_PEPPER must be replaced outside development")
        if self.app_env == "production" and not self.database_url.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://")):
            raise ValueError("Production requires PostgreSQL DATABASE_URL")
        if not 0 <= self.intent_low_threshold <= self.intent_high_threshold <= 1: raise ValueError("Invalid intent confidence thresholds")
        if self.nlu_timeout <= 0 or self.action_timeout <= 0 or self.plugin_timeout <= 0 or self.session_timeout_minutes <= 0 or self.rate_limit <= 0: raise ValueError("Timeouts, session timeout, and rate limit must be positive")
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
