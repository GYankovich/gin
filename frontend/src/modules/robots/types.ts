// frontend/src/modules/robots/types.ts

export interface StrategyParam {
    type: 'integer' | 'float' | 'string' | 'boolean' | 'array';
    default?: any;
    min?: number;
    max?: number;
    enum?: string[];
    label: string;
    description?: string;
}

export interface StrategyInfo {
    name: string;
    title: string;
    description: string;
    params_schema: Record<string, StrategyParam>;
}

export interface RobotBase {
    name: string;
    display_name?: string;
    description?: string;
    robot_type: 'portfolio_updater' | 'trading';
    strategy_name?: string;
    strategy_params: Record<string, any>;
    max_daily_loss?: number;
    max_position_size?: number;
    allowed_instruments?: string[];
}

export interface RobotCreate extends RobotBase {
    token_id?: number;
}

export interface RobotUpdate {
    name?: string;
    display_name?: string;
    description?: string;
    token_id?: number | null;
    strategy_params?: Record<string, any>;
    max_daily_loss?: number | null;
    max_position_size?: number | null;
    allowed_instruments?: string[] | null;
    status?: 'active' | 'stopped' | 'error';
}

export interface Robot extends RobotBase {
    id: number;
    user_id: number;
    token_id: number | null;
    status: 'active' | 'stopped' | 'error';
    is_active: number;
    total_trades: number;
    successful_trades: number;
    total_profit: number;
    total_profit_percent: number;
    created_at: string;
    updated_at: string | null;
    started_at: string | null;
    stopped_at: string | null;
    last_error: string | null;
    last_error_at: string | null;
    last_heartbeat_at: string | null;
}

export interface RobotListResponse {
    total: number;
    items: Robot[];
}

export interface RobotTrade {
    id: number;
    robot_id: number;
    figi: string;
    ticker: string | null;
    instrument_type: string;
    side: 'buy' | 'sell';
    quantity: number;
    price: number;
    total_amount: number;
    commission: number | null;
    profit: number | null;
    profit_percent: number | null;
    status: 'open' | 'closed' | 'cancelled';
    created_at: string;
    closed_at: string | null;
}

export interface RobotLog {
    id: number;
    robot_name: string;
    robot_version: string | null;
    token_id: number | null;
    user_id: number | null;
    started_at: string;
    finished_at: string | null;
    duration_ms: number | null;
    success: boolean;
    error_message: string | null;
}

export interface RobotLogListResponse {
    total: number;
    logs: RobotLog[];
    limit: number;
    offset: number;
}

export interface RobotStats {
    total_trades: number;
    successful_trades: number;
    failed_trades: number;
    success_rate: number;
    total_profit: number;
    total_profit_percent: number;
    average_profit_per_trade: number;
    biggest_win: number;
    biggest_loss: number;
    trades_by_day: Array<{date: string, count: number, profit: number}>;
    profit_by_day: Record<string, number>;
    active_since: string | null;
    last_trade_at: string | null;
}

export interface TokenInfo {
    id: number;
    token_name: string | null;
    token_preview: string;
    is_active: boolean;
}

export interface AvailableToken {
    id: number;
    token_name: string | null;
    token_preview: string;
    last_used_at: string | null;
}