export interface StrategyInfo {
    name: string;
    title: string;
    description: string;
    params_schema: Record<string, any>;
}

export interface TradingRobot {
    id: number;
    name: string;
    strategy_name: string;
    token_id: number;
    account_id: string;
    is_active: boolean;
    total_trades: number;
    total_profit: number;
    last_run_at: string | null;
    created_at: string;

    // Параметры стратегии
    max_position_size_percent: number;
    stop_loss_percent: number;
    take_profit_percent: number | null;
    daily_loss_limit: number | null;
    max_trades_per_day: number | null;
    schedule_cron: string | null;
    strategy_params: Record<string, any>;
}

export interface TradingRobotCreate {
    name: string;
    strategy_name: string;
    token_id: number;
    account_id: string;
    max_position_size_percent: number;
    stop_loss_percent: number;
    take_profit_percent?: number | null;
    daily_loss_limit?: number | null;
    max_trades_per_day?: number | null;
    schedule_cron?: string | null;
    strategy_params?: Record<string, any>;
}

export interface TradingRobotUpdate {
    name?: string;
    max_position_size_percent?: number;
    stop_loss_percent?: number;
    take_profit_percent?: number | null;
    daily_loss_limit?: number | null;
    max_trades_per_day?: number | null;
    schedule_cron?: string | null;
    is_active?: boolean;
    strategy_params?: Record<string, any>;
}

export interface RobotTrade {
    id: number;
    figi: string;
    direction: 'BUY' | 'SELL';
    quantity: number;
    price: number;
    total_value: number;
    opened_at: string;
    closed_at: string | null;
    profit: number | null;
    status: 'OPEN' | 'CLOSED' | 'CANCELLED';
}

export interface ApiToken {
    id: number;
    name: string | null;
    token_type: string;
    is_active: boolean;
    masked_token: string;
}