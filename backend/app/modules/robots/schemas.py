from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class RobotCreate(BaseModel):
    """Создание робота"""
    name: str = Field(..., min_length=1, max_length=255, description="Название робота")
    type: int = Field(..., description="Тип робота (num_value из dictionary: 1 - Portfolio, 2 - Trading)")
    token_id: int = Field(..., description="ID токена доступа")

    class Config:
        from_attributes = True

class RobotUpdate(BaseModel):
    """Обновление робота"""
    name: Optional[str] = None
    token_id: Optional[int] = None
    type: Optional[int] = None
    status: Optional[int] = None
    config: Optional[Dict[str, Any]] = None


class RobotConfigUpdateRequest(BaseModel):
    """Запрос обновления конфигурации робота."""
    robotId: int = Field(..., description="ID робота")
    config: Dict[str, Any] = Field(default_factory=dict, description="Новая конфигурация робота")


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
