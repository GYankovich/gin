from pydantic import BaseModel, Field
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
    last_token_id: Optional[int] = None


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


# --- Robot trading analytics ---

class RobotTradeItem(BaseModel):
    id: int
    figi: str
    side: str
    quantity: float
    entry_price: Optional[float]
    exit_price: Optional[float]
    profit: Optional[float]
    profit_percent: Optional[float]
    status: str
    created_at: Optional[datetime]
    closed_at: Optional[datetime]


class RobotMetrics(BaseModel):
    """Основные KPI торгового робота"""
    robot_id: int
    total_trades: int
    open_trades: int
    closed_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Optional[float]
    total_pnl: float
    avg_profit: Optional[float]
    avg_loss: Optional[float]
    best_trade: Optional[float]
    worst_trade: Optional[float]
    max_drawdown: Optional[float]
    profit_factor: Optional[float]
    avg_trade_duration_hours: Optional[float]
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    fill_rate: Optional[float] = None
    reject_rate: Optional[float] = None
    partial_fills: int = 0
    rejected_orders: int = 0
    total_commission: float = 0.0


class RobotMetricsResponse(BaseModel):
    metrics: RobotMetrics
    recent_trades: List[RobotTradeItem]


class UserRobotsTradingOverview(BaseModel):
    """Сводка по алготорговле всех роботов пользователя (чистый PnL и издержки)."""
    robots_with_closed_trades: int = 0
    total_trades: int = 0
    open_trades: int = 0
    closed_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: Optional[float] = None
    total_pnl: float = 0.0
    total_commission: float = 0.0
    profit_factor: Optional[float] = None
    max_drawdown: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None


class AnalyticsRangeRequest(BaseModel):
    account_id: int
    from_date: datetime
    to_date: datetime


class AnalyticsOperationsRequest(AnalyticsRangeRequest):
    operation_type: Optional[str] = None


class AnalyticsSyncOperationsRequest(BaseModel):
    account_id: str = Field(..., description="external account_id from portfolio_accounts")
    from_date: datetime
    to_date: datetime
    tokenId: int
    state: str = "OPERATION_STATE_UNSPECIFIED"


class AnalyticsOperationsItem(BaseModel):
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


class AnalyticsOperationsResponse(BaseModel):
    account_id: int
    from_date: datetime
    to_date: datetime
    total: int
    items: List[AnalyticsOperationsItem]


class AccountStatisticsBlock(BaseModel):
    own_funds: float
    current_total_value: float
    roi_percent: Optional[float] = None
    avg_monthly_roi_percent: Optional[float] = None


class AccountPeriodStatisticsBlock(BaseModel):
    from_date: datetime
    to_date: datetime
    period_inflow: float
    max_drawdown_percent: Optional[float] = None
    max_growth_percent: Optional[float] = None
    end_value: Optional[float] = None
    period_roi_percent: Optional[float] = None


class AccountStatisticsResponse(BaseModel):
    account_id: int
    overall: AccountStatisticsBlock
    period: AccountPeriodStatisticsBlock