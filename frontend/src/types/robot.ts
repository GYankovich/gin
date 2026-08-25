///@EPIC Frontend.ITEM Types.TOPIC FrontendSrcTypesRobot [1]
///@ Исходный модуль `frontend/src/types/robot.ts` — автоматическая разметка для Obsidian Source Scanner.

export interface TokenInfo {
    id: number
    name: string
    status: number
    type: number
    typeName: string
}

/**
 * Поддерживаемые стратегии (BRD-ARCH-03 §6). Должно совпадать со списком из
 * `backend/app/modules/robots/schemas.py:GrainSeedConfig.SUPPORTED_STRATEGIES`.
 */
export type RobotStrategyName = 'grain_seed' | 'momentum_breakout' | 'reversion_to_ma'

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
    sell_only_if_has_asset?: boolean
    interval: string
    candle_days?: number
    signal_profile?: 'legacy' | 'tz_signals_v1'
}

export interface MomentumBreakoutStrategyParams {
    lookback_days: number
    entry_minutes_from_open: number
    hold_candles: number
    volume_confirmation: boolean
    volume_multiplier: number
    exit_on_reverse: boolean
    sell_only_if_has_asset?: boolean
    allow_entry_all_day?: boolean
    interval: string
    candle_days?: number
}

export interface ReversionToMaStrategyParams {
    ma_period: number
    deviation_pct: number
    rsi_period: number
    rsi_overbought: number
    rsi_oversold: number
    max_hold_candles: number
    use_volume_filter: boolean
    interval: string
    candle_days?: number
}

/** Любой набор параметров стратегии. Конкретный тип — по дискриминанту `strategy`. */
export type RobotStrategyParams =
    | GrainSeedStrategyParams
    | MomentumBreakoutStrategyParams
    | ReversionToMaStrategyParams
    | Record<string, unknown>

/**
 * Риск-конфиг общий для всех стратегий (`RobotRisk` на бэке — alias на
 * `GrainSeedRisk`, см. BRD-ARCH-03 §7).
 */
export interface GrainSeedRiskConfig {
    stop_loss_percent: number
    take_profit_percent: number
    max_position_percent: number
    max_position_rub: number
    max_daily_loss: number
    /** Риск на сделку (% капитала), зеркало GrainSeedRisk.risk_per_trade_pct. */
    risk_per_trade_pct?: number
    /** Мин. нотионал сделки (₽ / USDT). */
    min_trade_amount_rub?: number
    trading_hours_start: string
    trading_hours_end: string
    allowed_weekdays: number
}

export type RobotRiskConfig = GrainSeedRiskConfig

export interface GrainSeedCostsConfig {
    broker_commission_rate: number
    ndfl_rate: number
}

export type RobotCostsConfig = GrainSeedCostsConfig

/**
 * Конфиг торгового робота. Имя `GrainSeedConfig` сохранено для обратной
 * совместимости с импортами, но `strategy` теперь может быть любой из
 * `RobotStrategyName`, а `strategy_params` — соответствующий им набор.
 */
export interface GrainSeedConfig {
    broker_type: string
    strategy: RobotStrategyName
    strategy_params: RobotStrategyParams
    allowed_figis: string[]
    universe_mode?: 'fixed' | 'dms_pipeline' | 'tqbr_scan'
    fixed_tickers?: string[]
    /** 0 = без авто-пересборки universe в течение дня */
    universe_refresh_minutes?: number
    update_interval_seconds: number
    indicator_update_schedule: Record<string, string>
    risk: RobotRiskConfig
    costs: RobotCostsConfig
}

/** Семантический alias: новые места кода предпочитают `RobotConfig`. */
export type RobotConfig = GrainSeedConfig

export interface PortfolioUpdaterConfig {
    config_version?: number
    schema_profile?: string
    broker_type?: string
    bybit?: {
        testnet?: boolean
        account_type?: string
    }
    [key: string]: unknown
}

/** v3 config + legacy flat GrainSeedConfig / portfolio updater. */
export type RobotConfigPayload =
    | GrainSeedConfig
    | PortfolioUpdaterConfig
    | (Record<string, unknown> & {
          config_version?: number
          schema_profile?: string
          broker_type?: string
      })

export interface RobotScheduleInfo {
    id: number
    schedule_type?: number | null
    interval_seconds?: number | null
    start_time?: string | null
    end_time?: string | null
    weekdays?: number | null
    is_active?: number | null
    priority?: number | null
    description?: string | null
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
    config: RobotConfigPayload | null
    /** Присутствует на GET /robots/id/{id}; в list может отсутствовать. */
    schedule?: RobotScheduleInfo | null
    last_started: string | null
    last_error: string | null
    last_error_at: string | null
    last_stopped: string | null
    usercre: number
    date_creation: string
    usermod: number | null
    date_modification: string | null
}

/** Тело POST /robots/data — зеркало RobotListRequest. */
export interface RobotListRequest {
    robot_status?: number[]
    robot_type?: number[]
    robot_name?: string
    token_type?: number[]
    limit?: number
    offset?: number
    sort_by?: string
    sort_order?: 'asc' | 'desc' | string
}

export interface RobotListResponse {
    total: number
    items: Robot[]
    limit: number
    offset: number
}

export interface RobotUniverseActiveCounts {
    robot_id: number
    today: string
    today_active: number
    yesterday: string
    yesterday_active: number
    source: string
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
    reason?: string | null
    kind?: string | null
}

export interface RobotHistoryBacktestResult {
    run_id?: number
    initial_capital: number
    final_equity: number
    total_return_percent: number
    max_drawdown_percent: number | null
    trades: RobotHistoryBacktestTrade[]
    equity_curve: { time: string; equity: number }[]
    stages?: string[]
    history_stats?: {
        processed: number
        skipped_fetch: number
        skipped_empty: number
        total_trade_dates: number
        trading_days_with_equity?: number
        calendar_days?: number
        annualization_days?: number
        annualized_return_percent?: number | null
    }
    fee_summary?: {
        maker_commission?: number
        taker_commission?: number
        total_commission?: number
        total_funding?: number
    }
    margin_summary?: {
        enabled?: boolean
        leverage?: number
        maintenance_margin_rate?: number
        liquidations?: number
    }
}

/** Ответ POST /robots/history-backtest/runs/{id}/cancel. */
export interface RobotBacktestCancelResponse {
    run_id: number
    cancel_requested: boolean
}

/** Ответ POST /robots/history-backtest при HTTP 202 (async_execution). */
export interface RobotHistoryBacktestQueuedResponse {
    run_id: number
    status: string
    message?: string
}

export interface RobotBacktestHistoryItem {
    id: number
    robot_id?: number | null
    broker_type?: string | null
    market_profile?: string | null
    /** grain_seed | momentum_breakout | reversion_to_ma — из config_snapshot прогона */
    strategy?: string | null
    /** Человекочитаемое название с бэкенда (По зёрнышку…, Пробой максимума, …) */
    strategy_title?: string | null
    status?: string | null
    run_phase?: string | null
    error_message?: string | null
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

export interface RobotBacktestCompareResponse {
    comparison_id: number
    name: string
    base_run_id: number
    compare_run_id: number
    metrics_base: Record<string, number | null>
    metrics_compare: Record<string, number | null>
    metrics_diff: Record<string, number | null>
    config_diff: Record<string, { base: unknown; compare: unknown }>
}

/** Лёгкий статус прогона (GET …/runs/{id}/status). */
export interface RobotBacktestRunStatus {
    run_id: number
    robot_id?: number | null
    status: string
    requested_from: string
    requested_to: string
    started_at: string
    finished_at?: string | null
    initial_capital: number
    partial_result?: boolean | null
    progress_percent?: number | null
    eta_seconds?: number | null
    eta_confidence?: 'low' | 'medium' | 'high' | string | null
    phase_units_done?: number | null
    phase_units_total?: number | null
    run_phase?: string | null
    phase_label?: string | null
    current_trade_date?: string | null
    trade_dates_total?: number | null
    trade_dates_remaining?: number | null
    cancel_requested?: boolean | null
    error_message?: string | null
}

export interface RobotBacktestRunDetails extends RobotBacktestRunStatus {
    total_return_percent?: number | null
    max_drawdown_percent?: number | null
    final_equity?: number | null
    trades_total: number
    result_payload: RobotHistoryBacktestResult
    signals: Array<Record<string, any>>
    orders: Array<Record<string, any>>
    portfolio_snapshots: Array<{ time?: string; snapshot_time?: string; equity?: number } & Record<string, any>>
    daily_summary?: Array<Record<string, unknown>>
}

/** Ответ POST /robots/jobs/historical-screening (П1 → candidate_pool). */
export interface RobotHistoricalScreeningResponse {
    robot_id: number
    tickers: string[]
    passed: number
    scanned: number
    as_of?: string | null
    message?: string | null
    skipped?: boolean
}

/** Ответ POST /robots/jobs/paper-selection (П2 → allowed_figis). */
export interface RobotPaperSelectionResponse {
    robot_id: number
    allowed_figis: string[]
    accepted_tickers: string[]
    snapshot_id?: number | null
    analyzer_written_rows: number
    recomputed: boolean
    universe_mode?: string | null
    message?: string | null
    candidate_pool_size: number
}

/** Ответ POST /robots/jobs/crypto-screening (async enqueue). */
export interface RobotCryptoScreeningResponse {
    robot_id: number
    status?: string
    job_id?: string | null
    started_at?: string | null
    symbols: string[]
    accepted: number
    scanned: number
    rejected?: number
    message?: string | null
    skipped?: boolean
    reused?: boolean
}

/** GET /robots/{id}/crypto-screening/status */
export interface RobotCryptoScreeningStatus {
    robot_id: number
    status: 'idle' | 'queued' | 'running' | 'success' | 'failed' | string
    job_id?: string | null
    started_at?: string | null
    finished_at?: string | null
    error?: string | null
    message?: string | null
    last_completed_at?: string | null
    universe_updated_at?: string | null
}
