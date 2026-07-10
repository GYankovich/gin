from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any, ClassVar, Annotated, Union, Literal
from datetime import datetime, time, date, timezone

from app.modules.robots.config.profiles.type1_bybit import Type1BybitConfig
from app.modules.robots.config.profiles.type1_tinvest import Type1TinvestConfig
from app.modules.robots.config.profiles.type2_bybit import Type2BybitConfig
from app.modules.robots.config.profiles.type2_tinvest import Type2TinvestConfig
from app.modules.robots.config.v2_schema import (
    CONFIG_VERSION_V2,
    HistoricalScreeningConfig,
    PaperSelectionConfig,
    SignalGenerationConfig,
)

#///EPIC Backtesting.ITEM RobotsAPI.TOPIC Request Response Schemas [1]
#/// Централизованные Pydantic-схемы robots-модуля: управление роботом, расписание,
#/// запуск/история/детализация бэктеста и сравнение прогонов.

RobotConfigProfile = Annotated[
    Union[Type1TinvestConfig, Type1BybitConfig, Type2TinvestConfig, Type2BybitConfig],
    Field(discriminator="schema_profile"),
]

class RobotCreate(BaseModel):
    """Создание робота.

    Для type=2 можно передать полный config (как в history-backtest) и расписание —
    робот сразу готов к бэктесту и live после включения (DMS инициализирует universe).
    """
    name: str = Field(..., min_length=1, max_length=255, description="Название робота")
    type: int = Field(default=2, description="Тип робота (1 - Portfolio updater, 2 - Trading)")
    token_id: int = Field(..., description="ID токена доступа")
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Полный конфиг торгового робота (strategy, pipeline, risk, costs, strategy_params)",
    )
    poll_interval_hours: Optional[float] = Field(default=None, ge=(1 / 60), le=12)
    trading_hours_start: Optional[str] = Field(default=None, description="HH:MM или HH:MM MSK")
    trading_hours_end: Optional[str] = Field(default=None, description="HH:MM или HH:MM MSK")
    allowed_weekdays: Optional[int] = Field(default=None, ge=0, le=127)

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def allowed_robot_types(self):
        if int(self.type) not in (1, 2):
            raise ValueError("Поддерживаются только типы: 1 (опросник), 2 (торговый)")
        if int(self.type) == 2 and self.config is not None:
            cfg = self.config if isinstance(self.config, dict) else {}
            if not cfg.get("risk"):
                raise ValueError("config.risk is required for trading robot when config is provided")
        return self

class RobotUpdate(BaseModel):
    """Обновление робота"""
    name: Optional[str] = None
    token_id: Optional[int] = None
    type: Optional[int] = None
    status: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    poll_interval_hours: Optional[float] = Field(default=None, ge=(1 / 60), le=12)
    trading_hours_start: Optional[str] = None
    trading_hours_end: Optional[str] = None
    allowed_weekdays: Optional[int] = Field(default=None, ge=0, le=127)


class RobotUpdateRequest(BaseModel):
    """Patch-style update payload for robot base fields."""
    robotId: int = Field(..., description="ID робота")
    patch: RobotUpdate = Field(..., description="Изменяемые поля робота")


class RobotDuplicateRequest(BaseModel):
    """Дублирование робота (§7.8): копия config с выборочным reset universe."""
    source_robot_id: int = Field(..., ge=1, description="ID исходного робота")
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    broker_type: Optional[str] = Field(
        default=None,
        description="Новый брокер (смена контура §15); по умолчанию как у source",
    )
    token_id: Optional[int] = Field(
        default=None,
        description="Токен копии; null — использовать токен source",
    )
    copy_sections: Optional[List[str]] = Field(
        default=None,
        description="Ветки config для переноса: signal_generation, risk, costs, schedule",
    )
    reset_sections: Optional[List[str]] = Field(
        default=None,
        description="Ветки для сброса: universe, allowed_figis, allowed_symbols, candidate_pool",
    )


class GrainSeedStrategyParams(BaseModel):
    gap_filter_pct: float = 2.5
    spread_limit_pct: float = 0.15
    spread_proxy_multiplier: float = 8.0
    atr_period: int = 14
    atr_min_pct: float = 1.5
    adx_period: int = 14
    adx_threshold: float = 22.0
    ma_fast_period: int = 5
    ma_slow_period: int = 20
    bb_period: int = 20
    bb_stddev: float = 2.0
    commission_pct: float = 0.05
    min_profit_target_pct: float = 0.35
    day_loss_streak_limit: int = 3
    free_funds_reserve_pct: float = 50.0
    risk_per_trade_pct: float = 2.0
    max_position_size_pct: float = 20.0
    force_close_time_msk: str = "18:45"
    force_market_flatten: bool = True
    interval: str = Field(
        default="CANDLE_INTERVAL_5_MIN",
        description="Интервал свечей для сигналов и live (T-Invest)",
    )
    moex_analysis_interval: Optional[str] = Field(
        default=None,
        description="MOEX ISS для преданализа/pipeline (по умолчанию 10m). Не подменяет interval.",
    )
    candle_days: int = Field(default=14, ge=1, le=3650, description="Глубина исторических свечей для bootstrap/live")
    allow_entry_all_day: bool = Field(default=False, description="Для momentum_breakout: разрешить вход не только в окно открытия")
    sell_only_if_has_asset: bool = Field(default=True, description="Не генерировать SELL без позиции в бумаге")
    signal_profile: str = Field(
        default="legacy",
        description="legacy — текущая логика; tz_signals_v1 — §6.5 docs/backtest_review (BUY только, выход в движке)",
    )


class GrainSeedRisk(BaseModel):
    """Legacy-имя для общего риск-профиля.

    BRD-ARCH-03 §7: новый источник правды — `app.modules.robots.trading.risk.RiskParams`.
    Этот класс остаётся в API без изменений ради обратной совместимости — клиенты
    и БД продолжают видеть `risk: { stop_loss_percent, ... }`, а сервис при
    необходимости конвертирует это в `RiskParams` через `RiskParams.from_legacy_dict`.
    """

    stop_loss_percent: float = 2.0
    take_profit_percent: float = 3.0
    max_position_percent: float = 10.0
    max_position_rub: float = 50000.0
    max_daily_loss: float = 10000.0
    min_trade_amount_rub: float = 500.0
    risk_per_trade_pct: float = 2.0
    trading_hours_start: str = "10:00 MSK"
    trading_hours_end: str = "18:45 MSK"
    allowed_weekdays: int = 31


RobotRisk = GrainSeedRisk  # стратегия-агностичное имя; см. BRD-ARCH-03 §7


class GrainSeedCosts(BaseModel):
    broker_commission_rate: float = 0.0005
    ndfl_rate: float = 0.15


class GrainSeedConfig(BaseModel):
    config_version: int = Field(
        default=CONFIG_VERSION_V2,
        ge=1,
        le=2,
        description="2 — конфиг П1/П2/П3 (historical_screening, paper_selection, signal_generation)",
    )
    historical_screening: Optional[HistoricalScreeningConfig] = None
    paper_selection: Optional[PaperSelectionConfig] = None
    signal_generation: Optional[SignalGenerationConfig] = None
    broker_type: str = Field(
        default="tinvest",
        description="LIVE-брокер: tinvest (MOEX); bybit — crypto (план)",
    )
    strategy: str = "grain_seed"
    strategy_params: GrainSeedStrategyParams = Field(default_factory=GrainSeedStrategyParams)
    allowed_figis: List[str] = Field(default_factory=list)
    universe_mode: str = Field(
        default="dms_pipeline",
        description="fixed | dms_pipeline | tqbr_scan — способ формирования universe",
    )
    fixed_tickers: List[str] = Field(
        default_factory=list,
        description="Тикеры TQBR при universe_mode=fixed",
    )
    universe_refresh_minutes: int = Field(
        default=0,
        ge=0,
        le=24 * 60,
        description="0 = без авто-пересборки; иначе интервал пересчёта universe по pipeline в торговые часы",
    )
    update_interval_seconds: int = 10
    indicator_update_schedule: Dict[str, str] = Field(
        default_factory=lambda: {
            "CANDLE_INTERVAL_DAY": "10:00 MSK",
            "CANDLE_INTERVAL_HOUR": "every hour at :05",
        }
    )
    risk: GrainSeedRisk = Field(default_factory=GrainSeedRisk)
    costs: GrainSeedCosts = Field(default_factory=GrainSeedCosts)

    SUPPORTED_STRATEGIES: ClassVar[tuple[str, ...]] = ("grain_seed", "momentum_breakout", "reversion_to_ma")

    @model_validator(mode="before")
    @classmethod
    def _normalize_config_v2(cls, data: Any) -> Any:
        if isinstance(data, dict):
            from app.modules.robots.config.migration import ensure_config_v2

            return ensure_config_v2(data)
        return data

    @model_validator(mode="after")
    def validate_strategy(self):
        strat = self.strategy
        if self.signal_generation is not None:
            strat = str(self.signal_generation.strategy or strat)
        if strat not in self.SUPPORTED_STRATEGIES:
            raise ValueError(
                f"Поддерживаются только стратегии {', '.join(self.SUPPORTED_STRATEGIES)}; "
                f"получено: {strat!r}"
            )
        mode = str(self.universe_mode or "dms_pipeline").strip().lower()
        if mode not in ("fixed", "dms_pipeline", "tqbr_scan"):
            raise ValueError("universe_mode must be fixed, dms_pipeline or tqbr_scan")
        if mode == "fixed" and not list(self.fixed_tickers or []):
            # figis могут быть только в strategy_params — не блокируем pydantic здесь
            pass
        if self.strategy == "grain_seed" and self.strategy_params.ma_fast_period >= self.strategy_params.ma_slow_period:
            raise ValueError("ma_fast_period должен быть меньше ma_slow_period")
        return self


class RobotSyncUniverseRequest(BaseModel):
    """Внутридневной пересбор universe по DMS pipeline → allowed_figis."""
    robotId: int = Field(..., description="ID торгового робота")
    force_refresh_snapshot: bool = Field(
        default=True,
        description="Создать/взять свежий market_snapshot",
    )
    force_recompute_universe: bool = Field(
        default=True,
        description="Пересчитать daily_universe за сегодня",
    )


class RobotSyncUniverseResponse(BaseModel):
    robot_id: int
    allowed_figis: List[str] = Field(default_factory=list)
    accepted_tickers: List[str] = Field(default_factory=list)
    snapshot_id: Optional[int] = None
    analyzer_written_rows: int = 0
    recomputed: bool = False
    universe_mode: Optional[str] = None
    message: Optional[str] = None


class RobotJobRequest(BaseModel):
    robotId: int = Field(..., description="ID торгового робота")
    force_refresh_snapshot: bool = Field(default=True)
    force_recompute_universe: bool = Field(default=True)


class RobotHistoricalScreeningResponse(BaseModel):
    robot_id: int
    tickers: List[str] = Field(default_factory=list)
    passed: int = 0
    scanned: int = 0
    as_of: Optional[str] = None
    message: Optional[str] = None
    skipped: bool = False


class RobotPaperSelectionResponse(RobotSyncUniverseResponse):
    candidate_pool_size: int = 0


class RobotCryptoScreeningResponse(BaseModel):
    robot_id: int
    symbols: List[str] = Field(default_factory=list)
    accepted: int = 0
    scanned: int = 0
    rejected: int = 0
    message: Optional[str] = None
    skipped: bool = False
    reused: bool = False


class RobotUniverseActiveCountsResponse(BaseModel):
    robot_id: int
    today: str
    today_active: int = 0
    yesterday: str
    yesterday_active: int = 0
    source: str = Field(description="daily_universe | crypto_universe_daily | fixed")


class RobotUniverseDailyItem(BaseModel):
    id: int
    robot_id: int
    trade_date: date
    ticker: str
    source: str
    filter_result: Optional[str] = None
    reject_reason: Optional[str] = None
    snapshot_id: Optional[int] = None
    price_at_filter: Optional[float] = None
    volume_at_filter: Optional[int] = None
    atr_value: Optional[float] = None
    gap_percent: Optional[float] = None
    applied_filters: Optional[Any] = None
    created_at: datetime


class RobotUniverseDailyResponse(BaseModel):
    total: int
    items: List[RobotUniverseDailyItem] = Field(default_factory=list)
    source: str = Field(description="daily_universe | crypto_universe_daily")

class RobotMigrateConfigV2Request(BaseModel):
    """Миграция config роботов type=2 в схему П1/П2/П3."""
    robotId: Optional[int] = Field(
        default=None,
        description="Один робот; без robotId — все торговые роботы пользователя",
    )


class RobotMigrateConfigV2Item(BaseModel):
    robot_id: int
    config_version: int = 0
    universe_mode: Optional[str] = None
    historical_enabled: Optional[bool] = None
    paper_input: Optional[str] = None
    updated: bool = False


class RobotMigrateConfigV2Response(BaseModel):
    total: int = 0
    updated: int = 0
    items: List[RobotMigrateConfigV2Item] = Field(default_factory=list)


class RobotMigrateConfigV3Request(BaseModel):
    """Миграция config роботов в схему v3 (schema_profile + config_version=3)."""
    robotId: Optional[int] = Field(
        default=None,
        description="Один робот; без robotId — все торговые роботы пользователя",
    )


class RobotMigrateConfigV3Item(BaseModel):
    robot_id: int
    config_version: int = 0
    schema_profile: Optional[str] = None
    broker_type: Optional[str] = None
    updated: bool = False


class RobotMigrateConfigV3Response(BaseModel):
    total: int = 0
    updated: int = 0
    items: List[RobotMigrateConfigV3Item] = Field(default_factory=list)


class RobotConfigUpdateRequest(BaseModel):
    """Запрос обновления конфигурации робота."""
    robotId: int = Field(..., description="ID робота")
    config: Dict[str, Any] = Field(default_factory=dict, description="Config payload (validated per schema_profile)")


class RobotValidateConfigRequest(BaseModel):
    """Запрос валидации/нормализации конфига без сохранения."""
    robot_type: int = Field(default=2, ge=1, le=2, description="Тип робота (по умолчанию trading=2)")
    broker_type: Optional[str] = Field(default=None, description="Опциональный broker_type для выбора schema profile")
    config: Dict[str, Any] = Field(default_factory=dict, description="Сырой config payload")


class RobotValidateConfigResponse(BaseModel):
    """Нормализованный config после profile-based validation."""
    schema_profile: str
    normalized_config: RobotConfigProfile


class RobotConfigSchemaResponse(BaseModel):
    """JSON Schema профиля конфигурации робота."""
    schema_profile: str
    json_schema: Dict[str, Any] = Field(default_factory=dict)


class RobotScheduleUpdateRequest(BaseModel):
    """Запрос обновления расписания робота."""
    robotId: int = Field(..., description="ID робота")
    poll_interval_hours: float = Field(default=1, ge=(1 / 60), le=12)
    trading_hours_start: str = Field(default="10:00")
    trading_hours_end: str = Field(default="18:45")
    allowed_weekdays: int = Field(default=31, ge=0, le=127)


class StrategyInfoResponse(BaseModel):
    """Описание торговой стратегии для UI."""
    name: str
    title: str
    description: str
    params_schema: Dict[str, Any] = Field(default_factory=dict)


class StrategyListResponse(BaseModel):
    """Список доступных стратегий."""
    items: List[StrategyInfoResponse] = Field(default_factory=list)


class RobotTradingDefaultsResponse(BaseModel):
    """Глобальные значения издержек (settings.robots) для подсказок в UI."""
    broker_commission_rate: float
    ndfl_rate: float


class RobotHistoryBacktestRequest(BaseModel):
    """Запуск исторического бэктеста: с роботом или полным телом без robot_id (BRD-ARCH-02 §3.2).

    BRD-ARCH-03 §6: поле `strategy` принимает grain_seed | momentum_breakout |
    reversion_to_ma. Старые клиенты с `strategy="grain_seed"` продолжают работать
    без изменений.
    """
    robot_id: Optional[int] = Field(default=None, description="Если null — все параметры из config/strategy")
    strategy: Optional[str] = Field(
        default=None,
        description="Без robot_id обязательно. grain_seed | momentum_breakout | reversion_to_ma",
    )
    from_date: datetime = Field(..., description="Начало периода (UTC)")
    to_date: datetime = Field(..., description="Конец периода (UTC)")
    initial_capital: float = Field(default=1_000_000.0, ge=10, description="Начальный капитал, ₽")
    token_id: Optional[int] = None
    type: Optional[int] = None
    poll_interval_hours: Optional[float] = Field(default=None, ge=(1 / 60), le=12)
    trading_hours_start: Optional[str] = None
    trading_hours_end: Optional[str] = None
    allowed_weekdays: Optional[int] = Field(default=None, ge=0, le=127)
    config: Optional[Dict[str, Any]] = None
    async_execution: bool = Field(
        default=True,
        description="Если true — HTTP 202 и прогон в фоне (BackgroundTasks); статус через GET .../runs/{run_id}",
    )
    skip_crypto_prefetch: bool = Field(
        default=False,
        description="Внутренний флаг: crypto D1/funding prefetch уже выполнен фоновой задачей",
    )
    crypto_screening_symbols: Optional[List[str]] = Field(
        default=None,
        description="Снимок тикеров с ByBit на момент prefetch (для scoring после фоновой догрузки)",
    )

    @model_validator(mode="after")
    def check_range(self):
        if self.from_date.tzinfo is None:
            self.from_date = self.from_date.replace(tzinfo=timezone.utc)
        else:
            self.from_date = self.from_date.astimezone(timezone.utc)
        if self.to_date.tzinfo is None:
            self.to_date = self.to_date.replace(tzinfo=timezone.utc)
        else:
            self.to_date = self.to_date.astimezone(timezone.utc)
        if self.to_date <= self.from_date:
            raise ValueError("to_date must be after from_date")
        if self.robot_id is None:
            if not (self.strategy or "").strip():
                raise ValueError("strategy is required when robot_id is omitted")
            cfg = self.config if isinstance(self.config, dict) else {}
            if not cfg.get("risk"):
                raise ValueError("config.risk is required when robot_id is omitted")
        return self


class RobotHistoryBacktestAsyncAccepted(BaseModel):
    """Ответ 202: прогон поставлен в очередь, исполнение продолжается в фоне."""
    run_id: int
    status: str = "queued"
    message: str = "Опросите GET /api/robots/history-backtest/runs/<run_id>, подставив run_id из ответа."


class RobotHistoryBacktestTrade(BaseModel):
    id: int = 0
    figi: str
    side: str
    bar_time: Optional[str] = None
    price: float
    quantity: int
    commission: float = 0.0
    pnl_net: Optional[float] = None


class RobotHistoryBacktestResponse(BaseModel):
    run_id: Optional[int] = None
    accepted: bool = Field(default=True, description="False если прогон принят в фон (202) — зарезервировано")
    status: Optional[str] = Field(default=None, description="queued и т.д. для async — зарезервировано")
    initial_capital: float
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: Optional[float] = None
    trades: List[RobotHistoryBacktestTrade] = Field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = Field(default_factory=list)
    stages: List[str] = Field(default_factory=list)
    history_stats: Dict[str, int] = Field(default_factory=dict)
    daily_summary: List[Dict[str, Any]] = Field(default_factory=list)


class RobotLiveSnapshotRequest(BaseModel):
    robotId: int = Field(..., description="ID робота")


class RobotLiveSnapshotResponse(BaseModel):
    robot_id: int
    status: int
    broker_type: str
    strategy: str
    account_id: Optional[str] = None
    active_positions: List[Dict[str, Any]] = Field(default_factory=list)
    portfolio_positions: List[Dict[str, Any]] = Field(default_factory=list)
    portfolio_summary: Dict[str, Any] = Field(default_factory=dict)
    portfolio_fetch_error: Optional[str] = None
    portfolio_source: Optional[str] = None
    recent_signals: List[Dict[str, Any]] = Field(default_factory=list)
    recent_orders: List[Dict[str, Any]] = Field(default_factory=list)
    stream_health: Dict[str, Any] = Field(default_factory=dict)


class RobotBacktestHistoryRequest(BaseModel):
    robotId: Optional[int] = Field(default=None, description="Если null — история по user_id (все прогоны пользователя)")
    limit: int = Field(default=30, ge=1, le=200)
    only_active: bool = Field(default=False, description="Только незавершённые (RUNNING/QUEUED)")
    broker_type: Optional[Literal["tinvest", "bybit"]] = Field(
        default=None,
        description="Фильтр по рынку из config_snapshot прогона",
    )


class RobotBacktestHistoryItem(BaseModel):
    id: int
    robot_id: Optional[int] = None
    broker_type: Optional[str] = Field(default=None, description="tinvest | bybit | sandbox")
    market_profile: Optional[str] = Field(default=None, description="moex | crypto")
    strategy: Optional[str] = Field(
        default=None,
        description="Код стратегии из config_snapshot прогона (grain_seed, momentum_breakout, …)",
    )
    strategy_title: Optional[str] = Field(
        default=None,
        description="Отображаемое название стратегии (из реестра стратегий)",
    )
    status: Optional[str] = Field(default=None, description="SUCCESS | FAILED | RUNNING | QUEUED | …")
    run_phase: Optional[str] = None
    error_message: Optional[str] = None
    requested_from: datetime
    requested_to: datetime
    initial_capital: float
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: Optional[float] = None
    created_at: datetime
    result_payload: Dict[str, Any]


class RobotBacktestHistoryResponse(BaseModel):
    total: int
    items: List[RobotBacktestHistoryItem] = Field(default_factory=list)


class RobotBacktestRunRequest(BaseModel):
    runId: int = Field(..., description="ID прогона из backtest_runs")


class RobotBacktestRunStatusResponse(BaseModel):
    """Лёгкий статус прогона (GET …/runs/{id}/status) — для опроса без тяжёлых артефактов."""

    run_id: int
    robot_id: Optional[int] = None
    status: str
    requested_from: datetime
    requested_to: datetime
    started_at: datetime
    finished_at: Optional[datetime] = None
    initial_capital: float = 0.0
    partial_result: Optional[bool] = None
    progress_percent: Optional[float] = Field(default=None, description="0–100, взвешенный по фазам")
    eta_seconds: Optional[int] = Field(default=None, description="Оценка оставшегося времени, сек")
    eta_confidence: Optional[str] = Field(default=None, description="low | medium | high")
    phase_units_done: Optional[int] = None
    phase_units_total: Optional[int] = None
    run_phase: Optional[str] = None
    phase_label: Optional[str] = Field(default=None, description="Человекочитаемая фаза")
    current_trade_date: Optional[date] = None
    trade_dates_total: Optional[int] = None
    trade_dates_remaining: Optional[int] = None
    cancel_requested: Optional[bool] = None
    error_message: Optional[str] = Field(default=None, description="Текст ошибки для FAILED")


class RobotBacktestRunDetailsResponse(RobotBacktestRunStatusResponse):
    total_return_percent: Optional[float] = None
    max_drawdown_percent: Optional[float] = None
    final_equity: Optional[float] = None
    trades_total: int = 0
    result_payload: Dict[str, Any] = Field(default_factory=dict)
    signals: List[Dict[str, Any]] = Field(default_factory=list)
    orders: List[Dict[str, Any]] = Field(default_factory=list)
    portfolio_snapshots: List[Dict[str, Any]] = Field(default_factory=list)
    daily_summary: List[Dict[str, Any]] = Field(default_factory=list)


class RobotBacktestCancelResponse(BaseModel):
    run_id: int
    cancel_requested: bool = True
    status: Optional[str] = Field(
        default=None,
        description="Статус после отмены: CANCELLED если сняли из очереди или «зомби»; RUNNING/FETCHING — отмена в процессе (см. run_phase)",
    )
    run_phase: Optional[str] = Field(default=None, description="cancel_pending — ждём остановки воркера; cancelled — финал")
    stale_reconciled: bool = Field(
        default=False,
        description="True если прогон был RUNNING/FETCHING дольше порога и закрыт как зависший",
    )


class RobotBacktestCompareRequest(BaseModel):
    baseRunId: int = Field(..., description="Базовый run_id")
    compareRunId: int = Field(..., description="Сравниваемый run_id")
    name: Optional[str] = Field(default=None, description="Название сравнения")


class RobotBacktestCompareResponse(BaseModel):
    comparison_id: int
    name: str
    base_run_id: int
    compare_run_id: int
    metrics_base: Dict[str, Any] = Field(default_factory=dict)
    metrics_compare: Dict[str, Any] = Field(default_factory=dict)
    metrics_diff: Dict[str, Any] = Field(default_factory=dict)
    config_diff: Dict[str, Any] = Field(default_factory=dict)


class RobotBacktestCompareListRequest(BaseModel):
    limit: int = Field(default=30, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class RobotBacktestCompareListItem(BaseModel):
    id: int
    name: str
    base_run_id: int
    compare_run_id: int
    created_at: datetime
    config_diff: Dict[str, Any] = Field(default_factory=dict)


class RobotBacktestCompareListResponse(BaseModel):
    total: int
    items: List[RobotBacktestCompareListItem] = Field(default_factory=list)


class RobotBacktestCompareIdRequest(BaseModel):
    comparisonId: int = Field(..., description="ID записи сравнения")


class BacktestRequest(BaseModel):
    returns: List[float] = Field(default_factory=list, description="Серия доходностей по шагам в долях (например 0.01)")
    initial_capital: float = Field(100000.0, gt=0)
    fee_bps: float = Field(5.0, ge=0)


class BacktestResultResponse(BaseModel):
    initial_capital: float
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: float
    sharpe_ratio: Optional[float]
    trades_count: int
    equity_curve: List[float] = Field(default_factory=list)


class WalkForwardRequest(BaseModel):
    returns: List[float] = Field(default_factory=list)
    folds: int = Field(3, ge=2, le=20)
    train_ratio: float = Field(0.7, gt=0.3, lt=0.95)
    initial_capital: float = Field(100000.0, gt=0)
    fee_bps: float = Field(5.0, ge=0)


class WalkForwardFoldResult(BaseModel):
    fold: int
    train_points: int
    test_points: int
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: float
    sharpe_ratio: Optional[float]


class WalkForwardResponse(BaseModel):
    folds: List[WalkForwardFoldResult] = Field(default_factory=list)
    avg_total_return_percent: float
    avg_sharpe_ratio: Optional[float]


class PaperModeRequest(BaseModel):
    robotId: int
    enabled: bool = True


class PaperModeResponse(BaseModel):
    robot_id: int
    paper_mode: bool


class ChangeStatusRequest(BaseModel):
    """Запрос на изменение статуса робота"""
    robotId: int = Field(..., description="ID робота")
    status: int = Field(..., description="Новый статус: 1 - Включить, 2 - Выключить")

    class Config:
        from_attributes = True


class RobotIdRequest(BaseModel):
    """Запрос с только ID робота"""
    robotId: int = Field(..., description="ID робота")


class TokenInfo(BaseModel):
    """Информация о токене"""
    id: Optional[int] = None
    name: Optional[str] = None
    status: Optional[int] = None
    type: Optional[int] = None
    typeName: Optional[str] = None


class RobotScheduleInfo(BaseModel):
    id: int
    schedule_type: Optional[int] = None
    interval_seconds: Optional[int] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    weekdays: Optional[int] = None
    is_active: Optional[int] = None
    priority: Optional[int] = None
    description: Optional[str] = None


class RobotInDB(BaseModel):
    """Полная схема робота из БД"""
    id: int
    user_id: int
    token: TokenInfo = Field(default_factory=TokenInfo)
    name: str
    type: int
    typeName: str
    status: int
    statusName: str
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "JSON config робота. v3: discriminated union по полю schema_profile "
            "(type1_tinvest | type1_bybit | type2_tinvest | type2_bybit). "
            "Схемы: GET /api/robots/config-schema/{schema_profile}."
        ),
    )
    schedule: Optional[RobotScheduleInfo] = None
    last_started: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    last_stopped: Optional[datetime] = None
    usercre: Optional[int] = None
    date_creation: datetime
    usermod: Optional[int] = None
    date_modification: Optional[datetime] = None

    class Config:
        from_attributes = True


class RobotListRequest(BaseModel):
    """Запрос на получение списка роботов"""
    robot_status: Optional[List[int]] = Field(None, description="Фильтр по статусам (1 - активен, 2 - остановлен)")
    robot_type: Optional[List[int]] = Field(None, description="Фильтр по типам роботов")
    robot_name: Optional[str] = Field(None, description="Поиск по названию")
    token_type: Optional[List[int]] = Field(None, description="Фильтр по типам токенов")
    limit: int = Field(100, ge=1, le=1000, description="Количество записей")
    offset: int = Field(0, ge=0, description="Смещение")
    sort_by: Optional[str] = Field(None, description="Поле для сортировки (status, name, token_type)")
    sort_order: Optional[str] = Field("asc", description="Направление сортировки (asc, desc)")


class RobotListResponse(BaseModel):
    """Список роботов"""
    total: int
    items: List[RobotInDB]  # ← Используем RobotInDB
    limit: int
    offset: int








# === СХЕМЫ ДЛЯ ЛОГОВ ===

class RobotLogBase(BaseModel):
    """Базовая схема лога"""
    robot_name: str
    robot_version: Optional[str]
    token_id: Optional[int]
    user_id: Optional[int]
    endpoint: str
    started_at: datetime
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    success: bool
    error_message: Optional[str]


class RobotLogInDB(RobotLogBase):
    """Лог из БД"""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class RobotLogListResponse(BaseModel):
    """Список логов"""
    total: int
    logs: List[RobotLogInDB]
    limit: int
    offset: int
