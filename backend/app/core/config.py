"""
Настройки приложения.
Все переменные окружения загружаются из .env файла и валидируются здесь.
"""
#///EPIC Platform.ITEM Core.TOPIC BackendAppCoreConfig [1]
#/// Исходный модуль `backend/app/core/config.py` — автоматическая разметка для Obsidian Source Scanner.

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
    DB_CONNECT_TIMEOUT_SECONDS: int = Field(
        default=5,
        ge=1,
        le=60,
        description="libpq connect_timeout для PostgreSQL, секунды",
    )
    DB_POOL_SIZE: int = Field(default=10, ge=2, le=50)
    DB_MAX_OVERFLOW: int = Field(default=15, ge=0, le=50)

    # ---- Безопасность ----
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ---- CORS (кто может обращаться к API) ----
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",  # Vite frontend
        "http://localhost:8000",  # Local backend
        "http://localhost:8001",  # Live WS gateway
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8001",
    ]

    # ---- Режим работы ----
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # ---- Роботы (переопределение через ROBOTS__BROKER_COMMISSION_RATE, ROBOTS__NDFL_RATE) ----
    robots: RobotsSettings = Field(default_factory=RobotsSettings)

    TINVEST_API_URL: str = "https://invest-public-api.tinkoff.ru/rest"
    # Опционально: токен только для загрузки рыночных данных в общую БД (бэктест). Иначе используется токен пользователя.
    TINVEST_MARKET_DATA_TOKEN: Optional[str] = None

    # ---- Corporate actions (MOEX CCI + per-ticker dividends fallback) ----
    # Минимум часов между проходами fallback …/securities/{SECID}/dividends.json (CCI недоступен).
    CORP_ACTIONS_SECURITIES_DIVIDENDS_MIN_INTERVAL_HOURS: float = Field(
        default=24.0,
        ge=1.0,
        le=168.0,
        description="Интервал для MOEX per-ticker dividends fallback",
    )
    # Одноразово: true → проигнорировать интервал и снова дернуть все dividends.json.
    CORP_ACTIONS_FORCE_SECURITIES_DIVIDENDS_SYNC: bool = False

    # ---- market_data_v1: очередь candle_load_jobs (MOEX → shared_market_candles) ----
    # Пауза цикла при пустой очереди (меньше BEGIN/UPDATE/ROLLBACK в логах SQL echo).
    CANDLE_LOAD_SCHEDULER_POLL_SECONDS: float = Field(default=20.0, ge=2.0, le=120.0)
    # Как часто выполнять UPDATE «зависших» running job; claim очереди идёт каждый цикл.
    CANDLE_LOAD_SCHEDULER_STALE_SWEEP_INTERVAL_SECONDS: float = Field(
        default=60.0,
        ge=10.0,
        le=3600.0,
    )

    # Пауза перед первым циклом фоновых планировщиков после старта uvicorn.
    SCHEDULER_STARTUP_DELAY_SECONDS: float = Field(
        default=15.0,
        ge=0.0,
        le=300.0,
        description="Секунды до первого тика portfolio/trading/MOEX/candle schedulers",
    )

    # ---- Background job lanes (portfolio / heavy) ----
    LANE_PORTFOLIO_CONCURRENCY: int = Field(default=1, ge=1, le=16)
    LANE_HEAVY_CONCURRENCY: int = Field(default=1, ge=1, le=8)
    WORKER_EMBEDDED_ENABLED: bool = Field(
        default=False,
        description="Запускать lane workers внутри uvicorn (dev/single-process)",
    )
    WORKER_POLL_INTERVAL_SECONDS: float = Field(default=1.0, ge=0.2, le=30.0)
    BACKGROUND_JOB_STALE_SECONDS: int = Field(default=7200, ge=60, le=86400)
    LIVE_SESSION_HEARTBEAT_SECONDS: float = Field(
        default=30.0,
        ge=5.0,
        le=300.0,
        description="Интервал touch updated_at для live_trading_session (анти-залипание)",
    )
    LIVE_SESSION_STALE_SECONDS: int = Field(
        default=180,
        ge=60,
        le=3600,
        description="Если live_trading_session running без heartbeat дольше — fail и разрешить re-enqueue",
    )
    WORKER_LEASE_STALE_SECONDS: int = Field(
        default=90,
        ge=30,
        le=3600,
        description="Lease lane-worker считается мёртвым, если heartbeat старше N секунд",
    )
    WORKER_LEASE_HEARTBEAT_SECONDS: float = Field(
        default=20.0,
        ge=5.0,
        le=120.0,
        description="Интервал heartbeat в background_worker_leases",
    )
    EMBEDDED_BACKGROUND_MAX_CONCURRENT: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Макс. одновременных фоновых job в embedded-режиме (общий лимит для всех lane)",
    )
    BACKTEST_LOG_DIR: Optional[str] = Field(
        default=None,
        description="Корень файловых логов history-backtest (по умолчанию <repo>/logs/backtest)",
    )
    WORKER_DEFER_WHILE_REST_BUSY: bool = Field(
        default=True,
        description="Не брать новые job из очереди, пока идут REST-запросы (embedded)",
    )

    LIVE_EVENTS_BACKEND: str = Field(
        default="postgres",
        description="postgres: NOTIFY + DB; memory: in-process live_event_hub",
    )
    WS_PORT: int = Field(default=8001, ge=1024, le=65535)
    LIVE_EVENTS_POLL_FALLBACK_MS: int = Field(default=500, ge=100, le=10000)

    @property
    def DATABASE_URL(self) -> str:
        """URL для SQLAlchemy с правильным SSL режимом"""
        password_encoded = quote_plus(self.DB_PASSWORD)
        base_url = f"postgresql://{self.DB_USER}:{password_encoded}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        # connect_timeout (libpq, seconds) — не зависать при недоступном хосте; pool_pre_ping в database.py
        return f"{base_url}?sslmode={self.DB_SSL_MODE}&client_encoding=utf8&connect_timeout={int(self.DB_CONNECT_TIMEOUT_SECONDS)}"

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