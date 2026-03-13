// Типы для роботов
export interface RobotToken {
    id: number;
    token_name: string | null;
    token_preview: string;
    is_active: boolean;
}

export interface Robot {
    id: number;
    name: string;
    description: string | null;
    robot_type: 'grid' | 'trend' | 'arbitrage';
    token_id: number | null;
    token?: RobotToken | null;

    // Статус
    status: 'active' | 'stopped' | 'error';
    is_active: number;

    // Параметры стратегии
    strategy_params: Record<string, any>;

    // Риск-менеджмент
    max_daily_loss: number | null;
    max_position_size: number | null;
    allowed_instruments: string[] | null;

    // Статистика
    total_trades: number;
    successful_trades: number;
    total_profit: number;
    total_profit_percent: number;

    // Временные метки
    created_at: string;
    updated_at: string | null;
    started_at: string | null;
    stopped_at: string | null;
    last_error: string | null;
    last_error_at: string | null;
}

export interface RobotCreate {
    name: string;
    description?: string;
    robot_type: string;
    token_id?: number;
    strategy_params: Record<string, any>;
    max_daily_loss?: number;
    max_position_size?: number;
    allowed_instruments?: string[];
}

export interface RobotUpdate {
    name?: string;
    description?: string;
    token_id?: number | null;
    strategy_params?: Record<string, any>;
    max_daily_loss?: number | null;
    max_position_size?: number | null;
    allowed_instruments?: string[] | null;
    status?: string;
}

// Типы для сделок
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
    order_id: string | null;
    profit: number | null;
    profit_percent: number | null;
    status: 'open' | 'closed' | 'cancelled';
    created_at: string;
    closed_at: string | null;
}

// Типы для логов
export interface RobotLog {
    id: number;
    robot_id: number;
    level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG';
    message: string;
    details: Record<string, any> | null;
    created_at: string;
}

// Типы для статистики
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

// Типы для токенов
export interface AvailableToken {
    id: number;
    token_name: string | null;
    token_preview: string;
    last_used_at: string | null;
}