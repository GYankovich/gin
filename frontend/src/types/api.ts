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
