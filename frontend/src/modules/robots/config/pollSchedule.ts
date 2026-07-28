export const PORTFOLIO_POLL_MINUTE_OPTIONS = [1, 2, 5, 10, 15, 30, 60] as const
export const TRADING_POLL_MINUTE_OPTIONS = [1, 2, 5, 10, 15, 30, 60] as const

export type PollMinuteOptions = readonly number[]

/** Snap interval to the nearest allowed minute option (for Select value). */
export function snapPollMinutes(value: number, options: PollMinuteOptions): number {
    const minutes = Math.max(1, Math.round(Number(value) || 1))
    if (options.some(o => o === minutes)) return minutes
    return options.reduce((best, cur) =>
        Math.abs(cur - minutes) < Math.abs(best - minutes) ? cur : best,
    options[0])
}

export function pollMinuteOptionsForRobotType(robotType: 1 | 2): PollMinuteOptions {
    return robotType === 1 ? PORTFOLIO_POLL_MINUTE_OPTIONS : TRADING_POLL_MINUTE_OPTIONS
}

/** Resolve poll interval from API schedule/config into UI minutes. */
export function resolvePollMinutesFromRobot(
    schedule: { interval_seconds?: number | null } | null | undefined,
    cfg: Record<string, unknown>,
    robotType: 1 | 2,
): number {
    const intervalSec =
        schedule?.interval_seconds != null ? Number(schedule.interval_seconds) : null
    const fromSchedule =
        intervalSec != null && Number.isFinite(intervalSec)
            ? Math.max(1, Math.round(intervalSec / 60))
            : null
    const pollHours = cfg.poll_interval_hours != null ? Number(cfg.poll_interval_hours) : null
    const fromCfg =
        pollHours != null && Number.isFinite(pollHours)
            ? Math.max(1, Math.round(pollHours * 60))
            : null
    const fallback = robotType === 2 ? 5 : 60
    const raw = fromSchedule ?? fromCfg ?? fallback
    return snapPollMinutes(raw, pollMinuteOptionsForRobotType(robotType))
}
