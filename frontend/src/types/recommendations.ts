export type RecommendationSeverity = 'info' | 'warning' | 'critical'
export type RecommendationCategory =
    | 'strategy'
    | 'params'
    | 'risk'
    | 'backtest'
    | 'live'
    | 'operational'

export interface SuggestedChange {
    path: string
    current_value?: unknown
    suggested_value?: unknown
    reason?: string | null
}

export interface RecommendationItem {
    id: string
    category: RecommendationCategory
    severity: RecommendationSeverity
    title: string
    message: string
    suggested_changes: SuggestedChange[]
    evidence: Record<string, unknown>
}

export interface BacktestRunInsight {
    run_id: number
    status?: string | null
    total_return_percent?: number | null
    max_drawdown_percent?: number | null
    win_rate_percent?: number | null
    trades_total?: number | null
    sharpe_ratio?: number | null
    requested_from?: string | null
    requested_to?: string | null
    created_at?: string | null
    score?: number | null
}

export interface LiveSituationSummary {
    robot_status?: number | null
    stream_connected_hint?: boolean | null
    last_event_at?: string | null
    open_positions: number
    signal_execution_rate_pct?: number | null
    risk_events_7d: number
    metrics?: Record<string, unknown> | null
}

export interface RobotRecommendationsResponse {
    robot_id: number
    strategy: string
    strategy_title?: string | null
    generated_at: string
    backtest_runs_analyzed: number
    best_backtest_run_id?: number | null
    best_backtest?: BacktestRunInsight | null
    latest_backtest?: BacktestRunInsight | null
    live: LiveSituationSummary
    recommendations: RecommendationItem[]
    config_snapshot_summary: Record<string, unknown>
}
