export interface TokenInfo {
    id: number
    name: string
    status: number
    type: number
    typeName: string
}

export interface GrainSeedStrategyParams {
    gap_filter_pct: number
    spread_limit_pct: number
    spread_proxy_multiplier: number
    atr_period: number
    atr_min_pct: number
    adx_period: number
    adx_threshold: number
    ma_fast_period: number
    ma_slow_period: number
    bb_period: number
    bb_stddev: number
    commission_pct: number
    min_profit_target_pct: number
    day_loss_streak_limit: number
    free_funds_reserve_pct: number
    risk_per_trade_pct: number
    max_position_size_pct: number
    force_close_time_msk: string
    force_market_flatten: boolean
    interval: string
}

export interface GrainSeedRiskConfig {
    stop_loss_percent: number
    take_profit_percent: number
    max_position_percent: number
    max_position_rub: number
    max_daily_loss: number
    trading_hours_start: string
    trading_hours_end: string
    allowed_weekdays: number
}

export interface GrainSeedCostsConfig {
    broker_commission_rate: number
    ndfl_rate: number
}

export interface GrainSeedConfig {
    broker_type: string
    strategy: 'grain_seed'
    strategy_params: GrainSeedStrategyParams
    allowed_figis: string[]
    update_interval_seconds: number
    indicator_update_schedule: Record<string, string>
    risk: GrainSeedRiskConfig
    costs: GrainSeedCostsConfig
}

export interface PortfolioUpdaterConfig {
    [key: string]: any
}

export interface Robot {
    id: number
    user_id: number
    token: TokenInfo
    name: string
    type: number
    typeName: string
    status: number
    statusName: string
    config: GrainSeedConfig | PortfolioUpdaterConfig | null
    schedule?: {
        id: number
        schedule_type?: number | null
        interval_seconds?: number | null
        start_time?: string | null
        end_time?: string | null
        weekdays?: number | null
        is_active?: number | null
        priority?: number | null
        description?: string | null
    } | null
    last_started: string | null
    last_error: string | null
    last_error_at: string | null
    last_stopped: string | null
    usercre: number
    date_creation: string
    usermod: number | null
    date_modification: string | null
}

export interface RobotListResponse {
    total: number
    items: Robot[]
    limit: number
    offset: number
}

export interface StrategyParam {
    name: string
    title: string
    description: string
    params_schema: Record<string, any>
}

export interface StrategyListResponse {
    items: StrategyParam[]
}

export interface RobotMetrics {
    robot_id: number
    total_trades: number
    open_trades: number
    closed_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: number
    total_pnl: number
    avg_profit: number
    avg_loss: number
    best_trade: number
    worst_trade: number
    max_drawdown: number
    profit_factor: number
    avg_trade_duration_hours: number
    sharpe_ratio?: number | null
    sortino_ratio?: number | null
    calmar_ratio?: number | null
    fill_rate?: number | null
    reject_rate?: number | null
    partial_fills?: number
    rejected_orders?: number
    total_commission?: number
}

export interface UserRobotsTradingOverview {
    robots_with_closed_trades: number
    total_trades: number
    open_trades: number
    closed_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: number | null
    total_pnl: number
    total_commission: number
    profit_factor: number | null
    max_drawdown: number | null
    sharpe_ratio: number | null
    sortino_ratio: number | null
    calmar_ratio: number | null
}

export interface RobotTradeItem {
    id: number
    figi: string
    side: string
    quantity: number
    entry_price: number
    exit_price: number | null
    profit: number | null
    profit_percent: number | null
    status: string
    created_at: string
    closed_at: string | null
}

export interface RobotMetricsResponse {
    metrics: RobotMetrics
    recent_trades: RobotTradeItem[]
}

export interface RobotTradingDefaults {
    broker_commission_rate: number
    ndfl_rate: number
}

export interface RobotHistoryBacktestTrade {
    id: number
    figi: string
    side: string
    bar_time?: string | null
    price: number
    quantity: number
    commission: number
    pnl_net?: number | null
}

export interface RobotHistoryBacktestResult {
    initial_capital: number
    final_equity: number
    total_return_percent: number
    max_drawdown_percent: number | null
    trades: RobotHistoryBacktestTrade[]
    equity_curve: { time: string; equity: number }[]
    stages?: string[]
}

export interface RobotBacktestHistoryItem {
    id: number
    robot_id: number
    requested_from: string
    requested_to: string
    initial_capital: number
    final_equity: number
    total_return_percent: number
    max_drawdown_percent: number | null
    created_at: string
    result_payload: RobotHistoryBacktestResult
}

export interface RobotBacktestHistoryResponse {
    total: number
    items: RobotBacktestHistoryItem[]
}
