from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, time


class RobotCreate(BaseModel):
    """Создание робота"""
    name: str = Field(..., min_length=1, max_length=255, description="Название робота")
    type: int = Field(default=2, description="Тип робота (1 - Portfolio updater, 2 - Trading)")
    token_id: int = Field(..., description="ID токена доступа")

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def allowed_robot_types(self):
        if int(self.type) not in (1, 2):
            raise ValueError("Поддерживаются только типы: 1 (опросник), 2 (торговый)")
        return self

class RobotUpdate(BaseModel):
    """Обновление робота"""
    name: Optional[str] = None
    token_id: Optional[int] = None
    type: Optional[int] = None
    status: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    poll_interval_hours: Optional[int] = Field(default=None, ge=1, le=12)
    trading_hours_start: Optional[str] = None
    trading_hours_end: Optional[str] = None
    allowed_weekdays: Optional[int] = Field(default=None, ge=0, le=127)


class RobotUpdateRequest(BaseModel):
    """Patch-style update payload for robot base fields."""
    robotId: int = Field(..., description="ID робота")
    patch: RobotUpdate = Field(..., description="Изменяемые поля робота")


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
    interval: str = "CANDLE_INTERVAL_5_MIN"


class GrainSeedRisk(BaseModel):
    stop_loss_percent: float = 2.0
    take_profit_percent: float = 3.0
    max_position_percent: float = 10.0
    max_position_rub: float = 50000.0
    max_daily_loss: float = 10000.0
    trading_hours_start: str = "10:00 MSK"
    trading_hours_end: str = "18:45 MSK"
    allowed_weekdays: int = 31


class GrainSeedCosts(BaseModel):
    broker_commission_rate: float = 0.0005
    ndfl_rate: float = 0.15


class GrainSeedConfig(BaseModel):
    broker_type: str = "tinvest"
    strategy: str = "grain_seed"
    strategy_params: GrainSeedStrategyParams = Field(default_factory=GrainSeedStrategyParams)
    allowed_figis: List[str] = Field(default_factory=list)
    update_interval_seconds: int = 10
    indicator_update_schedule: Dict[str, str] = Field(
        default_factory=lambda: {
            "CANDLE_INTERVAL_DAY": "10:00 MSK",
            "CANDLE_INTERVAL_HOUR": "every hour at :05",
        }
    )
    risk: GrainSeedRisk = Field(default_factory=GrainSeedRisk)
    costs: GrainSeedCosts = Field(default_factory=GrainSeedCosts)

    @model_validator(mode="after")
    def validate_grain_seed_only(self):
        if self.strategy != "grain_seed":
            raise ValueError("Поддерживается только стратегия grain_seed")
        if self.strategy_params.ma_fast_period >= self.strategy_params.ma_slow_period:
            raise ValueError("ma_fast_period должен быть меньше ma_slow_period")
        return self


class RobotConfigUpdateRequest(BaseModel):
    """Запрос обновления конфигурации робота."""
    robotId: int = Field(..., description="ID робота")
    config: GrainSeedConfig = Field(default_factory=GrainSeedConfig, description="Новая конфигурация grain_seed")


class RobotScheduleUpdateRequest(BaseModel):
    """Запрос обновления расписания робота."""
    robotId: int = Field(..., description="ID робота")
    poll_interval_hours: int = Field(default=1, ge=1, le=12)
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
    """Запуск исторического бэктеста по конфигу робота."""
    robot_id: int = Field(..., description="ID робота")
    from_date: datetime = Field(..., description="Начало периода (UTC)")
    to_date: datetime = Field(..., description="Конец периода (UTC)")
    initial_capital: float = Field(default=1_000_000.0, ge=1000, description="Начальный капитал, ₽")

    @model_validator(mode="after")
    def check_range(self):
        if self.to_date <= self.from_date:
            raise ValueError("to_date must be after from_date")
        return self


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
    initial_capital: float
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: Optional[float] = None
    trades: List[RobotHistoryBacktestTrade] = Field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = Field(default_factory=list)
    stages: List[str] = Field(default_factory=list)


class RobotLiveSnapshotRequest(BaseModel):
    robotId: int = Field(..., description="ID робота")


class RobotLiveSnapshotResponse(BaseModel):
    robot_id: int
    status: int
    broker_type: str
    strategy: str
    account_id: Optional[str] = None
    active_positions: List[Dict[str, Any]] = Field(default_factory=list)
    recent_signals: List[Dict[str, Any]] = Field(default_factory=list)
    recent_orders: List[Dict[str, Any]] = Field(default_factory=list)
    stream_health: Dict[str, Any] = Field(default_factory=dict)


class RobotBacktestHistoryRequest(BaseModel):
    robotId: int = Field(..., description="ID робота")
    limit: int = Field(default=30, ge=1, le=200)


class RobotBacktestHistoryItem(BaseModel):
    id: int
    robot_id: int
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
    config: Dict[str, Any] = Field(default_factory=dict)
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
