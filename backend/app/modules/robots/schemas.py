from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# === СХЕМА ДЛЯ ЗАПРОСА СПИСКА РОБОТОВ ===

class RobotListRequest(BaseModel):
    """Запрос на получение списка роботов"""
    include_inactive: bool = Field(False, description="Включать неактивных роботов")
    robot_type: Optional[int] = Field(None, description="Фильтр по типу робота (num_value из dictionary)")


# === БАЗОВЫЕ СХЕМЫ ===

class RobotBase(BaseModel):
    """Базовая схема робота"""
    name: Optional[str] = Field(None, min_length=3, max_length=255)
    token_id: Optional[int] = Field(None, description="ID токена")
    type: int = Field(..., description="Тип робота (ID из dictionary)")
    config: Dict[str, Any] = Field(default_factory=dict)


class RobotCreate(RobotBase):
    """Создание робота"""
    name: Optional[str] = None  # Теперь может быть null
    status: Optional[int] = Field(0, description="Статус робота (ID из dictionary)")


class RobotUpdate(BaseModel):
    """Обновление робота"""
    name: Optional[str] = None
    token_id: Optional[int] = None
    type: Optional[int] = None
    status: Optional[int] = None
    config: Optional[Dict[str, Any]] = None


# === СХЕМЫ ДЛЯ ОТВЕТОВ ===

class DictionaryItem(BaseModel):
    """Элемент справочника"""
    id: int
    name: str
    value: Optional[int] = None


class RobotInDB(RobotBase):
    """Робот из БД"""
    id: int
    user_id: int
    type: DictionaryItem
    status: DictionaryItem
    last_started: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    usercre: Optional[int] = None
    date_creation: datetime
    usermod: Optional[int] = None
    date_modification: Optional[datetime] = None

    class Config:
        from_attributes = True


class RobotListResponse(BaseModel):
    """Список роботов"""
    total: int
    items: List[RobotInDB]


# === СХЕМЫ ДЛЯ СДЕЛОК ===

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