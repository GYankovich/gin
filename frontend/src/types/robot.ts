export interface TokenInfo {
    id: number
    name: string
    status: number
    type: number
    typeName: string
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
    config: Record<string, any> | null
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
