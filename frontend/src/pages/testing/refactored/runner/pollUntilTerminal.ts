import { robotService } from '@/services/robotService'
import type { RobotBacktestRunDetails, RobotBacktestRunStatus } from '@/types/robot'
import {
    BACKTEST_POLL_INTERVAL_MS,
    BACKTEST_POLL_MAX_TICKS,
    formatRunStatusLines,
    runProgressFromStatus,
} from '@/pages/testing/refactored/runner/formatRunStatus'
import { isBacktestTerminalStatus } from '@/pages/testing/refactored/types/responses'

export type PollUntilTerminalCallbacks = {
    onStatus?: (status: RobotBacktestRunStatus, runId: number) => void
    onTerminal?: (status: RobotBacktestRunStatus, runId: number) => void
}

/** Poll GET /history-backtest/runs/{id}/status until terminal or max ticks (T1.3). */
export async function pollUntilTerminal(
    runId: number,
    callbacks?: PollUntilTerminalCallbacks,
): Promise<RobotBacktestRunDetails | null> {
    let details: RobotBacktestRunDetails | null = null
    try {
        for (let i = 0; i < BACKTEST_POLL_MAX_TICKS; i++) {
            const status = await robotService.getHistoryBacktestRunStatus(runId)
            callbacks?.onStatus?.(status, runId)
            if (isBacktestTerminalStatus(status.status)) {
                details = await robotService.getHistoryBacktestRunDetails(runId)
                callbacks?.onTerminal?.(status, runId)
                break
            }
            await new Promise<void>(resolve => {
                setTimeout(resolve, BACKTEST_POLL_INTERVAL_MS)
            })
        }
        if (!details) {
            try {
                const last = await robotService.getHistoryBacktestRunStatus(runId)
                callbacks?.onStatus?.(last, runId)
            } catch {
                /* ignore */
            }
        }
        return details
    } catch {
        return null
    }
}

export { formatRunStatusLines, runProgressFromStatus }
