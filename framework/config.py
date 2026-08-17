from functools import lru_cache
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
    api_key_pepper: str = "development-only-change-me"
    model_config = SettingsConfigDict(env_file=(".env", ".env.development"), extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
