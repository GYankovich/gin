from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class AccountSummary(BaseModel):
    """Краткая информация о портфеле"""
    id: int
    account_id: str
    name: Optional[str]
    type: str
    status: str
    last_snapshot_date: Optional[datetime]
    total_value: float
    currency: str
    positions_count: int


class PortfolioSnapshotSummary(BaseModel):
    """Снимок портфеля для истории"""
    snapshot_id: int
    date: datetime
    total_value: float
    daily_yield: Optional[float]
    expected_yield: Optional[float]


class PositionDistribution(BaseModel):
    """Распределение по типам активов"""
    instrument_type: str
    value: float
    percentage: float
    count: int


class AccountDetailResponse(BaseModel):
    """Детальная информация по портфелю"""
    account: dict
    last_snapshot: Optional[dict]
    history: List[PortfolioSnapshotSummary]
    distribution: List[PositionDistribution]


class OverallSummaryResponse(BaseModel):
    """Сводка по всем портфелям пользователя"""
    total_value: float
    total_daily_yield: Optional[float]
    total_expected_yield: Optional[float]
    accounts_count: int
    accounts: List[AccountSummary]