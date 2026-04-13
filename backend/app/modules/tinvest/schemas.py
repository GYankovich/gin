from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# --- Существующие схемы (MoneyValue, Quotation и т.д.) ---
class MoneyValue(BaseModel):
    currency: str
    units: int
    nano: int
    decimal: float


class Quotation(BaseModel):
    units: int
    nano: int
    decimal: float


class AccountInfo(BaseModel):
    id: str
    type: str
    name: Optional[str] = None
    status: str


class PortfolioPosition(BaseModel):
    figi: Optional[str] = None
    instrument_type: str
    quantity: Quotation
    current_price: Optional[MoneyValue] = None
    expected_yield: Optional[Quotation] = None
    blocked: bool = False
    ticker: Optional[str] = None


class PortfolioData(BaseModel):
    total_amount_portfolio: MoneyValue
    total_amount_shares: Optional[MoneyValue] = None
    total_amount_bonds: Optional[MoneyValue] = None
    total_amount_etf: Optional[MoneyValue] = None
    total_amount_currencies: Optional[MoneyValue] = None
    expected_yield: Optional[Quotation] = None
    positions: List[PortfolioPosition]


class PortfolioResponse(BaseModel):
    account: AccountInfo
    portfolio: PortfolioData


# --- НОВЫЕ СХЕМЫ ДЛЯ ТОКЕНОВ ---
class TokenBase(BaseModel):
    """Базовая схема токена"""
    token_type: str = "tinvest"
    token: str = Field(..., min_length=10, description="Токен доступа T-Invest")
    token_name: Optional[str] = Field(None, max_length=255, description="Название токена (например 'Основной', 'Тестовый')")


class TokenCreate(TokenBase):
    """Создание нового токена"""
    pass


class TokenUpdate(BaseModel):
    """Обновление токена"""
    token_name: Optional[str] = None
    is_active: Optional[bool] = None


class TokenInDB(TokenBase):
    """Токен из БД"""
    id: int
    user_id: int
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Ответ с токеном (без самого токена для безопасности)"""
    id: int
    token_type: str
    token_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    token_preview: str = Field(..., description="Первые и последние символы токена для отображения")

    @classmethod
    def from_db(cls, db_token, preview_length: int = 8):
        """Создает ответ из модели БД с маскировкой токена"""
        token = db_token.token
        if len(token) > preview_length * 2:
            token_preview = f"{token[:preview_length]}...{token[-preview_length:]}"
        else:
            token_preview = "***"

        return cls(
            id=db_token.id,
            token_type=db_token.token_type,
            token_name=db_token.token_name,
            is_active=db_token.is_active,
            created_at=db_token.created_at,
            last_used_at=db_token.last_used_at,
            expires_at=db_token.expires_at,
            token_preview=token_preview
        )


class TokenListResponse(BaseModel):
    """Список токенов"""
    total: int
    items: List[TokenResponse]


class TokenTestRequest(BaseModel):
    """Запрос на тестирование токена"""
    token: str


class TokenTestResponse(BaseModel):
    """Результат тестирования токена"""
    is_valid: bool
    message: str
    accounts_count: Optional[int] = None
    first_account: Optional[str] = None
    expires_at: Optional[datetime] = None


class OperationsSyncRequest(BaseModel):
    account_id: str = Field(..., description="Внешний account_id счета (portfolio_accounts.account_id)")
    from_date: datetime
    to_date: datetime
    state: str = Field(default="OPERATION_STATE_UNSPECIFIED")


class AccountOperationItem(BaseModel):
    operation_id: str
    operation_date: datetime
    operation_type: str
    figi: Optional[str] = None
    instrument_type: Optional[str] = None
    quantity: float
    price: float
    payment: float
    currency: Optional[str] = None
    status: str
    type_text: Optional[str] = None


class AccountOperationsResponse(BaseModel):
    account_id: int
    from_date: datetime
    to_date: datetime
    total: int
    items: List[AccountOperationItem]