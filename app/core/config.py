# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Budget Mini App Backend"
    API_V1_STR: str = "/api/v1"

    # Database
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    
    DATABASE_URL: str | None = None # Будет вычислено

    # Telegram
    TELEGRAM_BOT_TOKEN_HMAC: str # Токен вашего бота для проверки HMAC initData
    TELEGRAM_BOT_ID: Optional[int] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        # SQLAlchemy 2.0+ рекомендует asyncpg для асинхронного драйвера PostgreSQL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:5432/{self.POSTGRES_DB}"
    
    @property
    def SYNC_DATABASE_URL(self) -> str: # Для Alembic
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:5432/{self.POSTGRES_DB}"


@lru_cache() # Кэшируем, чтобы настройки читались один раз
def get_settings() -> Settings:
    return Settings()

settings = get_settings()