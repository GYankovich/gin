from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesDashboardSchemas [1]
#/// Исходный модуль `backend/app/modules/dashboard/schemas.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DashboardSortItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    column_name: str = Field(
        ...,
        alias="columnName",
        description="account_name | value | own_funds | day_over_day_delta | last_account_sync",
    )
    sort_type: str = Field(..., alias="sortType", description="asc | desc")


class DashboardDataRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sort: List[DashboardSortItem] = Field(
        default_factory=lambda: [DashboardSortItem(column_name="account_name", sort_type="asc")],
    )


class DashboardAccountSummaryKpi(BaseModel):
    own_funds: Optional[float] = None
    value: Optional[float] = None
    minus_own_funds: Optional[float] = None
    minus_own_funds_percent: Optional[float] = None
    day_over_day_delta: Optional[float] = None
    day_over_day_delta_percent: Optional[float] = None
    currency: Optional[str] = None


class DashboardAccountItem(BaseModel):
    account_id: int
    external_account_id: str
    account_name: Optional[str]
    account_type: str
    account_status: str
    account_opened: Optional[datetime]
    last_account_sync: Optional[datetime]
    dashboard_hidden: bool = False
    last_token_id: Optional[int] = None
    broker: Optional[str] = None
    summary: DashboardAccountSummaryKpi


class DashboardCurrencyTotals(BaseModel):
    currency: str
    total_own_funds: Optional[float] = None
    total_value: float
    total_minus_own_funds: Optional[float] = None
    total_minus_own_funds_percent: Optional[float] = None
    total_day_over_day_delta: Optional[float] = None
    total_day_over_day_delta_percent: Optional[float] = None


class DashboardAssetItem(BaseModel):
    type: str
    value: float
    percent: float
    currency: str
    day_over_day_delta: Optional[float] = None
    day_over_day_delta_percent: Optional[float] = None


class DashboardDataResponse(BaseModel):
    totals: List[DashboardCurrencyTotals]
    assets: List[DashboardAssetItem]
    accounts: List[DashboardAccountItem]


class DashboardAccountsResponse(BaseModel):
    """Открытые счета для настройки, включая скрытые. Фильтры broker и currency необязательны."""
    accounts: List[DashboardAccountItem]


class DashboardAccountVisibilityItem(BaseModel):
    account_id: int
    hidden: bool


class DashboardVisibilityUpdateRequest(BaseModel):
    accounts: List[DashboardAccountVisibilityItem]


class DashboardVisibilityUpdateResponse(BaseModel):
    updated: int
