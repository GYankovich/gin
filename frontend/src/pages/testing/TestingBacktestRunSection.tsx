import React from 'react'
import { Card } from '@/components/ui/Card'
import { RunControlPanel } from '@/pages/testing/refactored/components/run/RunControlPanel'
import { RunStatusLog } from '@/pages/testing/refactored/components/run/RunStatusLog'

export type TestingBacktestRunSectionProps = {
    running: boolean
    onRunBacktest: () => void
    statusWindow: string[]
    configDirty: boolean
    canRunBacktest: boolean
    hasResult: boolean
    invalidPeriod: boolean
    onRefreshHistory?: () => void
    historyLoading?: boolean
    /** §9.1: отмена фонового прогона, пока идёт опрос GET …/runs/{run_id} */
    pollingRunId?: number | null
    cancellingRun?: boolean
    onCancelBacktest?: () => void | Promise<void>
    runProgress?: {
        percent: number
        etaLabel: string | null
        phaseLabel: string | null
    } | null
    error?: string | null
    onBackToSetup?: () => void
    sticky?: boolean
}

/** Legacy wrapper — composes T3.2 `RunControlPanel` + `RunStatusLog`. */
export function TestingBacktestRunSection({
    running,
    onRunBacktest,
    statusWindow,
    configDirty,
    canRunBacktest,
    hasResult,
    invalidPeriod,
    onRefreshHistory,
    historyLoading = false,
    pollingRunId = null,
    cancellingRun = false,
    onCancelBacktest,
    runProgress = null,
    error = null,
    onBackToSetup,
    sticky = true,
}: TestingBacktestRunSectionProps) {
    return (
        <>
            <RunControlPanel
                running={running}
                hasResult={hasResult}
                error={error}
                onRunBacktest={onRunBacktest}
                configDirty={configDirty}
                canRunBacktest={canRunBacktest}
                invalidPeriod={invalidPeriod}
                onRefreshHistory={onRefreshHistory}
                historyLoading={historyLoading}
                pollingRunId={pollingRunId}
                cancellingRun={cancellingRun}
                onCancelBacktest={onCancelBacktest}
                runProgress={runProgress}
                onBackToSetup={onBackToSetup}
                statusLogCount={statusWindow.length}
                sticky={sticky}
            />
            {statusWindow.length > 0 && (
                <Card className="mb-6 cyber-form-card testing-cyber-card testing-run-status-card">
                    <RunStatusLog statusWindow={statusWindow} />
                </Card>
            )}
        </>
    )
}
