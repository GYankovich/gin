"""
Настройки приложения.
Все переменные окружения загружаются из .env файла и валидируются здесь.
"""
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import quote_plus


class RobotsSettings(BaseModel):
    """Параметры издержек для торговых роботов (доля, не проценты: 0.0005 = 0.05%)."""
    broker_commission_rate: float = Field(default=0.0005, description="Комиссия брокера, доля от оборота")
    ndfl_rate: float = Field(default=0.15, description="НДФЛ с прибыли, доля")


class Settings(BaseSettings):
    """
    Все настройки приложения в одном месте.
    Значения загружаются из .env файла автоматически.
    """

    # ---- База данных ----
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_SCHEMA: str = "ganaly"
    DB_SSL_MODE: str = "require"

    # ---- Безопасность ----
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ---- CORS (кто может обращаться к API) ----
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",  # Vite frontend
        "http://localhost:8000",  # Local backend
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]

    # ---- Режим работы ----
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # ---- Роботы (переопределение через ROBOTS__BROKER_COMMISSION_RATE, ROBOTS__NDFL_RATE) ----
    robots: RobotsSettings = Field(default_factory=RobotsSettings)

    TINVEST_API_URL: str = "https://invest-public-api.tinkoff.ru/rest"
    # Опционально: токен только для загрузки рыночных данных в общую БД (бэктест). Иначе используется токен пользователя.
    TINVEST_MARKET_DATA_TOKEN: Optional[str] = None

    @property
    def DATABASE_URL(self) -> str:
        """URL для SQLAlchemy с правильным SSL режимом"""
        password_encoded = quote_plus(self.DB_PASSWORD)
        base_url = f"postgresql://{self.DB_USER}:{password_encoded}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        return f"{base_url}?sslmode={self.DB_SSL_MODE}&client_encoding=utf8"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_nested_delimiter="__",
    )


@lru_cache
def get_settings() -> Settings:
    """Создает и кеширует настройки"""
    return Settings()


# Создаем глобальный объект для удобного импорта
settings = get_settings()