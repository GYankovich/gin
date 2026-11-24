#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesTinvestSchemas [1]
#/// Исходный модуль `backend/app/modules/tinvest/schemas.py` — автоматическая разметка для Obsidian Source Scanner.

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