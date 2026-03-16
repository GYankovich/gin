from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# === БАЗОВЫЕ СХЕМЫ (существующие) ===

class RobotBase(BaseModel):
    """Базовая схема робота"""
    name: str = Field(..., min_length=3, max_length=255)
    display_name: Optional[str] = Field(None, description="Отображаемое имя для логов")
    description: Optional[str] = None
    robot_type: str = Field(..., description="Тип робота: portfolio_updater, trading")
    strategy_params: Dict[str, Any] = Field(default_factory=dict)

    # Риск-менеджмент
    max_daily_loss: Optional[float] = Field(None, ge=0, le=100)
    max_position_size: Optional[float] = Field(None, ge=0)
    allowed_instruments: Optional[List[str]] = None


class RobotCreate(RobotBase):
    """Создание робота"""
    token_id: Optional[int] = Field(None, description="ID токена для торговли")


class RobotUpdate(BaseModel):
    """Обновление робота"""
    name: Optional[str] = Field(None, min_length=3, max_length=255)
    display_name: Optional[str] = None
    description: Optional[str] = None
    token_id: Optional[int] = None
    strategy_params: Optional[Dict[str, Any]] = None
    max_daily_loss: Optional[float] = Field(None, ge=0, le=100)
    max_position_size: Optional[float] = Field(None, ge=0)
    allowed_instruments: Optional[List[str]] = None
    status: Optional[str] = Field(None, pattern="^(active|stopped|error)$")


class RobotAction(BaseModel):
    """Действие с роботом"""
    action: str = Field(..., pattern="^(start|stop|pause|restart)$")


# === СХЕМЫ ДЛЯ ОТВЕТОВ ===

class RobotInDB(RobotBase):
    """Робот из БД"""
    id: int
    user_id: int
    token_id: Optional[int]
    status: str
    is_active: int
    total_trades: int
    successful_trades: int
    total_profit: float
    total_profit_percent: float
    created_at: datetime
    updated_at: Optional[datetime]
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    last_error: Optional[str]
    last_error_at: Optional[datetime]
    last_heartbeat_at: Optional[datetime]

    class Config:
        from_attributes = True


class RobotListResponse(BaseModel):
    """Список роботов"""
    total: int
    items: List[RobotInDB]


# === НОВЫЕ СХЕМЫ ДЛЯ ЛОГОВ ===

class RobotLogBase(BaseModel):
    """Базовая схема лога"""
    robot_name: str
    robot_version: Optional[str]
    token_id: Optional[int]
    user_id: Optional[int]
    endpoint: str
    level: str
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


class RobotLogStats(BaseModel):
    """Статистика по логам"""
    robot_name: str
    total_runs: int
    successful: int
    failed: int
    avg_duration_ms: float
    last_run: Optional[datetime]


# === СХЕМЫ ДЛЯ СДЕЛОК (без изменений) ===

class RobotTradeBase(BaseModel):
    """Базовая схема сделки"""
    figi: str
    ticker: Optional[str]
    instrument_type: str
    side: str
    quantity: float
    price: float
    order_id: Optional[str]


class RobotTradeCreate(RobotTradeBase):
    """Создание сделки"""
    robot_id: int


class RobotTradeInDB(RobotTradeBase):
    """Сделка из БД"""
    id: int
    robot_id: int
    total_amount: float
    commission: Optional[float]
    profit: Optional[float]
    profit_percent: Optional[float]
    status: str
    created_at: datetime
    closed_at: Optional[datetime]

    class Config:
        from_attributes = True


# === СХЕМЫ ДЛЯ СТАТИСТИКИ ===

class RobotStats(BaseModel):
    """Статистика робота"""
    total_trades: int
    successful_trades: int
    failed_trades: int
    success_rate: float
    total_profit: float
    total_profit_percent: float
    average_profit_per_trade: float
    biggest_win: float
    biggest_loss: float
    trades_by_day: List[Dict[str, Any]]
    profit_by_day: Dict[str, float]
    active_since: Optional[datetime]
    last_trade_at: Optional[datetime]