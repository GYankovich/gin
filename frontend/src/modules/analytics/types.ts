export interface AccountSummary {
    id: number;
    account_id: string;
    name: string | null;
    type: string;
    status: string;
    last_snapshot_date: string | null;
    total_value: number;
    currency: string;
    positions_count: number;
}

export interface OverallSummary {
    total_value: number;
    total_daily_yield: number | null;
    total_expected_yield: number | null;
    accounts_count: number;
    accounts: AccountSummary[];
}

export interface HistoryItem {
    snapshot_id: number;
    date: string;
    total_value: number;
    daily_yield: number | null;
    expected_yield: number | null;
}

export interface DistributionItem {
    instrument_type: string;
    value: number;
    percentage: number;
    count: number;
}

export interface AccountDetail {
    account: {
        id: string;
        name: string | null;
        type: string;
        status: string;
    };
    last_snapshot: {
        id: number;
        date: string;
        total_value: number;
        shares_value: number;
        bonds_value: number;
        etf_value: number;
        currencies_value: number;
        expected_yield: number;
        daily_yield: number;
        daily_yield_relative: number;
    } | null;
    history: HistoryItem[];
    distribution: DistributionItem[];
}

// --- Robot trading analytics ---

export interface RobotTradeItem {
    id: number;
    figi: string;
    side: string;
    quantity: number;
    entry_price: number | null;
    exit_price: number | null;
    profit: number | null;
    profit_percent: number | null;
    status: string;
    created_at: string | null;
    closed_at: string | null;
}

export interface RobotMetrics {
    robot_id: number;
    total_trades: number;
    open_trades: number;
    closed_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number | null;
    total_pnl: number;
    avg_profit: number | null;
    avg_loss: number | null;
    best_trade: number | null;
    worst_trade: number | null;
    max_drawdown: number | null;
    profit_factor: number | null;
    avg_trade_duration_hours: number | null;
}

export interface RobotMetricsResponse {
    metrics: RobotMetrics;
    recent_trades: RobotTradeItem[];
}