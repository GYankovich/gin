export type { RobotHistoryBacktestResult, RobotBacktestRunStatus, RobotBacktestRunDetails, RobotBacktestHistoryItem } from '@/types/robot'

export const TERMINAL_BACKTEST_STATUSES = new Set(['SUCCESS', 'FAILED', 'CANCELLED'])

export function isBacktestTerminalStatus(status: string | undefined | null): boolean {
    return TERMINAL_BACKTEST_STATUSES.has(String(status || '').toUpperCase())
}
