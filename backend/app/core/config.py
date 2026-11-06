from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    DATABASE_URL: str = "postgresql://ueba:ueba_pass@localhost:5432/ueba_db"
    SECRET_KEY: str = "change-this-to-a-random-64-char-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    FIRST_SUPERUSER_EMAIL: str = "admin@ueba.local"
    FIRST_SUPERUSER_PASSWORD: str = "Admin1234!"
    ENVIRONMENT: str = "development"
    DEV_AUTH_BYPASS: bool = True

    # CORS — allow the Vite dev server
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
    ]
    UPLOAD_DIR: str = "data/uploads"

    @model_validator(mode="after")
    def require_production_secret(self):
        if self.ENVIRONMENT.lower() == "production":
            if self.DEV_AUTH_BYPASS:
                raise ValueError("DEV_AUTH_BYPASS cannot be enabled in production environment.")
            if (
                self.SECRET_KEY.startswith("change-this")
                or self.SECRET_KEY.startswith("generate-a-unique")
                or len(self.SECRET_KEY) < 32
            ):
                raise ValueError("Set a unique SECRET_KEY of at least 32 characters in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
