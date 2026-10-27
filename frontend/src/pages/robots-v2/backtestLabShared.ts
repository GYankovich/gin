import type { Time } from '@/components/ui/Chart'
import type { BacktestHistoryRow } from '@/pages/robots-v2/components/BacktestHistoryCard'
import type { RobotV2 } from '@/types/robotV2'

export function backtestRunPath(runId: number): string {
    return `/backtest/${runId}`
}

export function parseBacktestRunId(raw: string | undefined | null): number | null {
    const n = Number(raw)
    if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) return null
    return n
}

export function backtestStatusVariant(status: string): 'up' | 'down' | 'neutral' | 'warn' {
    const s = status.toUpperCase()
    if (s === 'SUCCESS') return 'up'
    if (s === 'FAILED') return 'down'
    if (s === 'CANCELLED') return 'warn'
    if (s === 'RUNNING' || s === 'QUEUED') return 'neutral'
    return 'neutral'
}

export function toBacktestChartPoints(
    curve: Array<{ time: string; equity: number }>,
): Array<{ time: Time; value: number }> {
    const byTime = new Map<number, number>()
    for (const p of curve) {
        const t = Math.floor(new Date(p.time).getTime() / 1000)
        if (!Number.isFinite(t) || !Number.isFinite(p.equity)) continue
        byTime.set(t, p.equity)
    }
    return [...byTime.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([time, value]) => ({ time: time as Time, value }))
}

export function normalizeHistoryItem(item: Record<string, unknown>): BacktestHistoryRow {
    const robotIdRaw = item.robot_id
    const robotId =
        robotIdRaw == null || robotIdRaw === ''
            ? null
            : Number(robotIdRaw)
    const bound =
        typeof item.bound === 'boolean'
            ? item.bound
            : robotId != null && Number.isFinite(robotId) && robotId > 0
    return {
        run_id: Number(item.run_id),
        status: String(item.status || ''),
        requested_from: String(item.requested_from || ''),
        requested_to: String(item.requested_to || ''),
        started_at: String(item.started_at || ''),
        initial_capital: Number(item.initial_capital) || 0,
        total_return_percent: item.total_return_percent == null ? null : Number(item.total_return_percent),
        max_drawdown_percent: item.max_drawdown_percent == null ? null : Number(item.max_drawdown_percent),
        sharpe_ratio: item.sharpe_ratio == null ? null : Number(item.sharpe_ratio),
        final_equity: item.final_equity == null ? null : Number(item.final_equity),
        trades_total: Number(item.trades_total) || 0,
        signals_logged: Number(item.signals_logged) || 0,
        signals_truncated: Boolean(item.signals_truncated),
        robot_id: robotId != null && Number.isFinite(robotId) && robotId > 0 ? robotId : null,
        bound,
        config_label: item.config_label == null ? null : String(item.config_label),
    }
}

export function tokenIdOf(robot: RobotV2 | null): number | null {
    if (!robot) return null
    const n = Number(robot.tokenId ?? robot.token_id)
    return Number.isFinite(n) && n > 0 ? n : null
}

export function archetypeOfConfig(config: Record<string, unknown> | null | undefined): string {
    const strategy = (config?.strategy || {}) as Record<string, unknown>
    return String(strategy.archetype || '')
}
