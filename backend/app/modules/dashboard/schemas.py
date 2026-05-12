from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesDashboardSchemas [1]
#/// Исходный модуль `backend/app/modules/dashboard/schemas.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DashboardSortItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    column_name: str = Field(..., alias="columnName", description="account_name | total_value | own_funds | day_over_day_delta | last_account_sync")
    sort_type: str = Field(..., alias="sortType", description="asc | desc")


class DashboardDataRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sort: List[DashboardSortItem] = Field(
        default_factory=lambda: [DashboardSortItem(column_name="account_name", sort_type="asc")],
    )


class DashboardAccountSummaryKpi(BaseModel):
    own_funds: float
    total_value: float
    total_minus_own_funds: float
    day_over_day_delta: Optional[float] = None
    day_over_day_delta_percent: Optional[float] = None
    currency: str = "RUB"


class DashboardAccountItem(BaseModel):
    account_id: int
    external_account_id: str
    account_name: Optional[str]
    account_type: str
    account_status: str
    last_account_sync: Optional[datetime]
    summary: DashboardAccountSummaryKpi


class DashboardDataResponse(BaseModel):
    accounts: List[DashboardAccountItem]
