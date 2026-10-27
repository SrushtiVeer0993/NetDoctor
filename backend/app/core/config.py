"""
Application configuration, loaded from environment variables / .env.
Nothing here should be hard-coded elsewhere in the app.
"""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "dev-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    DATABASE_URL: str = "postgresql+psycopg2://netdoctor:netdoctor@localhost:5433/netdoctor"

    DEMO_MODE: bool = False
    CORS_ORIGINS: str = "http://localhost:5173"
    HOST_AGENT_URL: str | None = None
    HOST_AGENT_TOKEN: str | None = None
    HOST_AGENT_TIMEOUT_SECONDS: float = 210

    @model_validator(mode="after")
    def require_production_secret(self):
        secret_lower = self.SECRET_KEY.lower()
        is_placeholder = any(marker in secret_lower for marker in ("dev-secret", "replace-with", "change-this"))
        if self.ENVIRONMENT.lower() == "production" and (is_placeholder or len(self.SECRET_KEY) < 32):
            raise ValueError("Production requires a SECRET_KEY of at least 32 characters")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
