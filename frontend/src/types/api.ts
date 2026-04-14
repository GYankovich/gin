/* Shared API types */

export interface AccountSummary {
    id: number
    account_id: string
    name: string
    type: string
    status: string
    last_snapshot_date: string | null
    total_value: number
    currency: string
    positions_count: number
    last_token_id?: number | null
}

export interface OverallSummary {
    total_value: number
    total_daily_yield: number
    total_expected_yield: number
    accounts_count: number
    accounts: AccountSummary[]
}

export interface PortfolioSnapshotSummary {
    snapshot_id?: number
    date: string
    total_value: number
    daily_yield: number
    expected_yield: number
}

export interface PositionDistribution {
    instrument_type: string
    value: number
    percentage: number
    count: number
}

export interface AccountDetail {
    account: Record<string, any>
    last_snapshot: Record<string, any> | null
    history: PortfolioSnapshotSummary[]
    distribution: PositionDistribution[]
}

export interface HistoryResponse {
    account_id: number
    days: number
    interval?: string
    history: PortfolioSnapshotSummary[]
}

export interface AccountStatisticsOverall {
    own_funds: number
    current_total_value: number
    roi_percent: number | null
    avg_monthly_roi_percent: number | null
}

export interface AccountStatisticsPeriod {
    from_date: string
    to_date: string
    period_inflow: number
    max_drawdown_percent: number | null
    max_growth_percent: number | null
    end_value: number | null
    period_roi_percent: number | null
}

export interface AccountStatisticsResponse {
    account_id: number
    overall: AccountStatisticsOverall
    period: AccountStatisticsPeriod
}

export interface CapitalFlowMetrics {
    net_capital_inflow: number
    dividends_received: number
    dividends_share_of_portfolio_percent: number | null
    realized_pnl: number | null
    unrealized_pnl: number | null
}

export interface TradingPerformanceMetrics {
    closed_trades_count: number
    winning_trades_count: number
    losing_trades_count: number
    win_rate_percent: number | null
    win_rate_ratio_text: string | null
    profit_factor: number | null
    max_consecutive_losses: number
    max_consecutive_losses_sum: number | null
    avg_winning_trade: number | null
    avg_losing_trade: number | null
    avg_win_loss_ratio: number | null
}

export interface OperationalMetrics {
    average_hold_time_hours: number | null
    average_hold_time_label: string | null
    total_broker_fees: number
    total_track_fees: number
    total_taxes: number
    track_fees_share_of_avg_portfolio_percent: number | null
}

export interface BenchmarkMetrics {
    portfolio_return_percent: number | null
    imoex_return_percent: number | null
    relative_return_percent: number | null
    benchmark_unavailable: boolean
}

export interface RiskRecoveryMetrics {
    max_drawdown_percent: number | null
    average_recovery_days: number | null
    current_drawdown_percent: number | null
}

export interface DrawdownPoint {
    date: string
    drawdown_percent: number
}

export interface PortfolioStatisticsExtendedResponse {
    account_id: number
    from_date: string
    to_date: string
    overall: AccountStatisticsOverall
    capital_flow: CapitalFlowMetrics
    trading_performance: TradingPerformanceMetrics
    operational_metrics: OperationalMetrics
    benchmark_metrics: BenchmarkMetrics
    risk_recovery: RiskRecoveryMetrics
    drawdown_series: DrawdownPoint[]
}

export interface ChartPoint {
    date: string
    value: number
}

export interface ChartInstrumentSeries {
    figi: string
    ticker: string | null
    points: ChartPoint[]
}

export interface ChartAvailableInstrument {
    figi: string
    ticker: string | null
}

export interface AnalyticsChartSeriesResponse {
    account_id: number
    from_date: string
    to_date: string
    portfolio_series: ChartPoint[]
    drawdown_series: DrawdownPoint[]
    instruments_series: ChartInstrumentSeries[]
    available_instruments: ChartAvailableInstrument[]
}
