import type { TestingFormState } from '@/pages/testing/refactored/types/forms'

/** Body for POST /api/robots/history-backtest (async 202). */
export interface UnifiedHistoryBacktestRequest {
    robot_id: number | null
    strategy?: string
    from_date: string
    to_date: string
    initial_capital: number
    token_id?: number
    type?: number
    async_execution: boolean
    config: Record<string, unknown>
    poll_interval_hours?: number
    trading_hours_start?: string
    trading_hours_end?: string
    allowed_weekdays?: number
}

export type BuildBacktestRequestInput = {
    form: TestingFormState
    selectedRobotId: number | null
    selectedRobotType?: number | null
    tokenId?: number | null
    mergeStrategyParamsFrom?: Record<string, unknown>
}
