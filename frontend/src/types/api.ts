///@EPIC Frontend.ITEM Types.TOPIC FrontendSrcTypesApi [1]
///@ Исходный модуль `frontend/src/types/api.ts` — автоматическая разметка для Obsidian Source Scanner.

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

/** Paginated snapshots: omit both dates for all-time. */
export interface AnalyticsSnapshotsRequest {
    account_id: number
    from_date?: string | null
    to_date?: string | null
    limit?: number
    offset?: number
}

export interface AnalyticsSnapshotsResponse {
    account_id: number
    from_date: string | null
    to_date: string | null
    count: number
    limit: number
    offset: number
    history: PortfolioSnapshotSummary[]
}

export interface AnalyticsOperationItem {
    operation_id: string
    operation_date: string
    operation_type?: string | null
    operation_type_name?: string | null
    type_text?: string | null
    ticker?: string | null
    ticker_name?: string | null
    short_name?: string | null
    figi?: string | null
    quantity?: number | null
    price?: number | null
    payment?: number | null
    currency?: string | null
    status?: string | null
    status_name?: string | null
    [key: string]: unknown
}

/** Paginated operations: omit both dates for all-time. Uses `count` (not `total`). */
export interface AnalyticsOperationsRequest {
    account_id: number
    from_date?: string | null
    to_date?: string | null
    operation_type?: string | null
    limit?: number
    offset?: number
}

export interface AnalyticsOperationsResponse {
    account_id: number
    from_date: string | null
    to_date: string | null
    count: number
    limit: number
    offset: number
    items: AnalyticsOperationItem[]
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
    imoex_series?: ImoexBenchmarkPoint[]
}

export interface ImoexBenchmarkPoint {
    date: string
    close: number
    return_percent: number
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

export interface DashboardAccountSummaryKpi {
    own_funds: number
    value: number
    minus_own_funds: number
    minus_own_funds_percent: number | null
    day_over_day_delta: number | null
    day_over_day_delta_percent: number | null
    currency: string
}

export interface DashboardAccountItem {
    account_id: number
    external_account_id: string
    account_name: string | null
    account_type: string
    account_status: string
    account_opened: string | null
    last_account_sync: string | null
    dashboard_hidden: boolean
    summary: DashboardAccountSummaryKpi
}

export interface DashboardCurrencyTotals {
    currency: string
    total_own_funds: number
    total_value: number
    total_minus_own_funds: number
    total_minus_own_funds_percent: number | null
    total_day_over_day_delta: number | null
    total_day_over_day_delta_percent: number | null
}

export interface DashboardAssetItem {
    type: string
    value: number
    percent: number
    currency: string
    day_over_day_delta: number | null
    day_over_day_delta_percent: number | null
}

export interface DashboardDataResponse {
    totals: DashboardCurrencyTotals[]
    assets: DashboardAssetItem[]
    accounts: DashboardAccountItem[]
}

export interface ChartPoint {
    date: string
    value: number
}

export interface ChartInstrumentSeries {
    figi: string
    ticker: string | null
    name?: string | null
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
