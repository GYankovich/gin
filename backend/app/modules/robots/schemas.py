from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

# === БАЗОВЫЕ СХЕМЫ ===



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








class ChangeStatusRequest(BaseModel):
    """Запрос на изменение статуса робота"""
    robotId: int = Field(..., description="ID робота")
    status: int = Field(..., description="Новый статус: 1 - Включить, 2 - Выключить")

    class Config:
        from_attributes = True


class DictionaryItem(BaseModel):
    """Элемент справочника"""
    id: int
    name: str
    value: Optional[int] = None


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
