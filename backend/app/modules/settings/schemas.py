#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesSettingsSchemas [1]
#/// Исходный модуль `backend/app/modules/settings/schemas.py` — автоматическая разметка для Obsidian Source Scanner.

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Any, Dict

class TokenTypeInfo(BaseModel):
    """Информация о типе токена"""
    type: int
    typeName: str
    typeDesc: str


class ApiKeyCreate(BaseModel):
    """Схема для создания API ключа"""
    token: str = Field(..., min_length=6, description="API токен / API key")
    key_type: str = Field(..., description="Тип ключа (tinvest, telegram и т.д.)")
    name: Optional[str] = Field(None, max_length=100, description="Название ключа")
    refresh_interval_minutes: Optional[int] = Field(60, ge=5, le=1440, description="Частота обновления в минутах (минимум 5)")
    token_secret: Optional[str] = Field(None, description="Секрет ключа (например ByBit API secret)")
    testnet: Optional[bool] = Field(None, description="Использовать testnet окружение")
    account_type: Optional[str] = Field(None, description="Тип аккаунта брокера (например UNIFIED)")


class ApiKeyUpdate(BaseModel):
    """Схема для обновления ключа"""
    name: Optional[str] = Field(None, max_length=100, description="Новое название")
    status: Optional[int] = Field(None, description="Статус токена (1 active, 0 inactive, 3 expired)")
    refresh_interval_minutes: Optional[int] = Field(None, ge=5, le=1440, description="Частота обновления в минутах")


class ApiKeyResponse(BaseModel):
    """Базовая схема для ответа с данными ключа"""
    id: int
    name: Optional[str] = None
    token_type: TokenTypeInfo
    # Словарный перевод TOKEN.TYPE (dictionary.name по num_value = token_type).
    broker_type: Optional[str] = None
    status: int
    status_name: Optional[str] = None
    status_description: Optional[str] = None
    created_at: datetime
    masked_token: str
    last_used_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    masked_secret: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ApiKeyDetailResponse(ApiKeyResponse):
    """Детальная информация о ключе"""
    updated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    masked_secret: Optional[str] = None


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


class ApiKeyTestRequest(BaseModel):
    token: str = Field(..., min_length=6, description="Тестируемый API key / token")
    key_type: str = Field(..., description="Тип ключа")
    token_secret: Optional[str] = Field(None, description="Секрет API key для private endpoints")
    testnet: bool = Field(default=False, description="Флаг testnet (устарело, всегда mainnet)")
    account_type: str = Field(default="UNIFIED", description="ByBit account type")


class ApiKeyRevealResponse(BaseModel):
    token: str
    masked_token: str
    token_secret: Optional[str] = None
    masked_secret: Optional[str] = None


class ApiKeyTestResponse(BaseModel):
    is_valid: bool
    message: str
    accounts_count: Optional[int] = None
    first_account: Optional[str] = None
    testnet: Optional[bool] = None
