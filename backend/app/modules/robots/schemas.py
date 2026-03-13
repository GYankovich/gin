from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# --- Базовые схемы ---
class RobotBase(BaseModel):
    """Базовая схема робота"""
    name: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    robot_type: str = Field(..., description="Тип робота: grid, trend, arbitrage")
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


# --- Схемы для ответов ---
class RobotTokenInfo(BaseModel):
    """Информация о токене для робота"""
    id: int
    token_name: Optional[str]
    token_preview: str
    is_active: bool

    class Config:
        from_attributes = True


class RobotInDB(RobotBase):
    """Робот из БД"""
    id: int
    user_id: int
    token_id: Optional[int]
    token: Optional[RobotTokenInfo] = None

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

    class Config:
        from_attributes = True


class RobotListResponse(BaseModel):
    """Список роботов"""
    total: int
    items: List[RobotInDB]


# --- Схемы для сделок ---
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


# --- Схемы для логов ---
class RobotLogBase(BaseModel):
    """Базовая схема лога"""
    level: str
    message: str
    details: Optional[Dict[str, Any]]


class RobotLogInDB(RobotLogBase):
    """Лог из БД"""
    id: int
    robot_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Схемы для сигналов ---
class RobotSignalBase(BaseModel):
    """Базовая схема сигнала"""
    figi: str
    ticker: Optional[str]
    signal_type: str
    signal_strength: Optional[int]
    indicators: Optional[Dict[str, Any]]
    price_at_signal: Optional[float]


class RobotSignalInDB(RobotSignalBase):
    """Сигнал из БД"""
    id: int
    robot_id: int
    was_executed: int
    executed_trade_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Схемы для статистики ---
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

    trades_by_day: Dict[str, int]
    profit_by_day: Dict[str, float]

    active_since: Optional[datetime]
    last_trade_at: Optional[datetime]