export type OptimizationGoal = 'balanced' | 'max_return' | 'min_drawdown' | 'max_sharpe'
export type OptimizationMode = 'speed' | 'full'

export interface OptimizationParamSuggestion {
    path: string
    current_value?: unknown
    suggested_value?: unknown
    reason?: string | null
}

export interface OptimizationRankItem {
    rank: number
    run_id: number
    score: number
    total_return_percent?: number | null
    max_drawdown_percent?: number | null
    win_rate_percent?: number | null
    trades_total?: number | null
    sharpe_ratio?: number | null
    requested_from?: string | null
    requested_to?: string | null
    started_at?: string | null
    param_summary: Record<string, unknown>
}

export interface OptimizationFailedRunItem {
    run_id: number
    error_message?: string | null
    failure_category: string
    failure_summary?: string | null
    top_rejects: Record<string, number>
    suggested_changes: OptimizationParamSuggestion[]
    param_summary: Record<string, unknown>
    requested_from?: string | null
    requested_to?: string | null
    started_at?: string | null
}

export interface OptimizationRankResponse {
    robot_id: number
    strategy: string
    goal: OptimizationGoal
    runs_analyzed: number
    ranked: OptimizationRankItem[]
    failed_runs: OptimizationFailedRunItem[]
    overfitting_warnings: string[]
}

export interface OptimizationPlanCandidate {
    index: number
    param_summary: Record<string, unknown>
    config_snapshot: Record<string, unknown>
}

export interface OptimizationPlanResponse {
    robot_id: number
    strategy: string
    goal: OptimizationGoal
    mode: OptimizationMode
    total_candidates: number
    candidates: OptimizationPlanCandidate[]
    note: string
}

export interface OptimizationRunRequest {
    goal: OptimizationGoal
    mode: OptimizationMode
    from_date: string
    to_date: string
    initial_capital: number
}

export interface OptimizationSessionFailuresResponse {
    failed_runs: OptimizationFailedRunItem[]
}

export interface OptimizationBatchStartedResponse {
    batch_id: number
    robot_id: number
    goal: OptimizationGoal
    mode: OptimizationMode
    total_candidates: number
    enqueued: number
    run_ids: number[]
    status: string
}

export interface OptimizationBatchProgress {
    queued: number
    running: number
    success: number
    failed: number
    cancelled: number
    done: number
    percent: number
}

export interface OptimizationBatchItem {
    candidate_index: number
    run_id?: number | null
    status: string
    score?: number | null
    param_summary: Record<string, unknown>
    total_return_percent?: number | null
    max_drawdown_percent?: number | null
    sharpe_ratio?: number | null
    trades_total?: number | null
    error_message?: string | null
    failure_category?: string | null
    failure_summary?: string | null
    top_rejects?: Record<string, number>
    suggested_changes?: OptimizationParamSuggestion[]
}

export interface OptimizationBatchStatusResponse {
    batch_id: number
    robot_id: number
    goal: OptimizationGoal
    mode: OptimizationMode
    status: string
    total_candidates: number
    progress: OptimizationBatchProgress
    requested_from?: string | null
    requested_to?: string | null
    initial_capital?: number | null
    overfitting_warnings: string[]
    error_message?: string | null
    created_at?: string | null
    started_at?: string | null
    finished_at?: string | null
    items: OptimizationBatchItem[]
    ranked: OptimizationRankItem[]
}
