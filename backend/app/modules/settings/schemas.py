from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class ApiKeyCreate(BaseModel):
    """Схема для создания API ключа"""
    token: str = Field(..., min_length=10, description="API токен")
    key_type: str = Field(..., description="Тип ключа (tinvest, telegram и т.д.)")
    name: Optional[str] = Field(None, max_length=100, description="Название ключа")


class ApiKeyUpdate(BaseModel):
    """Схема для обновления ключа"""
    name: Optional[str] = Field(None, max_length=100, description="Новое название")
    is_active: Optional[bool] = Field(None, description="Статус активности")


class ApiKeyResponse(BaseModel):
    """Базовая схема для ответа с данными ключа"""
    id: int
    name: Optional[str] = None
    key_type: str
    is_active: bool
    created_at: datetime
    masked_token: str
    message: Optional[str] = None  # Для сообщений типа "ключ уже существует"

    class Config:
        from_attributes = True


class ApiKeyDetailResponse(ApiKeyResponse):
    """Детальная информация о ключе"""
    updated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class ApiKeyListResponse(BaseModel):
    """Список ключей с пагинацией"""
    keys: List[ApiKeyResponse]
    total: int
    limit: int
    offset: int


# Для обратной совместимости
class TInvestTokenIn(BaseModel):
    """Схема для входящего запроса T-Invest токена"""
    api_token: str = Field(..., min_length=10, description="Токен API T-Invest")


class TInvestTokenOut(BaseModel):
    """Схема для ответа T-Invest (упрощенная)"""
    has_token: bool
    key_id: Optional[int] = None
    key_name: Optional[str] = None
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class ErrorResponse(BaseModel):
    """Схема для ответа с ошибкой"""
    code: str
    description: str
