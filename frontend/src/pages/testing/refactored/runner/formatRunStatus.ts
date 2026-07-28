import type { RobotBacktestRunStatus } from '@/types/robot'
import { isBacktestTerminalStatus } from '@/pages/testing/refactored/types/responses'

export const BACKTEST_POLL_INTERVAL_MS = 2000
export const BACKTEST_POLL_MAX_TICKS = 7200

export function formatEtaSeconds(sec: number | null | undefined): string | null {
    if (sec == null || !Number.isFinite(sec)) return null
    const s = Math.max(0, Math.round(sec))
    if (s < 60) return `~${s} с`
    const m = Math.floor(s / 60)
    const r = s % 60
    if (m < 60) return r > 0 ? `~${m} мин ${r} с` : `~${m} мин`
    const h = Math.floor(m / 60)
    const rm = m % 60
    return rm > 0 ? `~${h} ч ${rm} мин` : `~${h} ч`
}

export function formatRunStatusLines(details: RobotBacktestRunStatus, runLabel: string): string[] {
    const st = String(details.status || '').toUpperCase()
    const lines: string[] = [`${runLabel}: ${st}`]
    if (details.phase_label || details.run_phase) {
        lines.push(`фаза: ${details.phase_label || details.run_phase}`)
    }
    if (details.progress_percent != null && Number.isFinite(details.progress_percent)) {
        lines.push(`общий прогресс: ${details.progress_percent.toFixed(1)}%`)
    }
    if (
        details.phase_units_total != null &&
        details.phase_units_total > 0 &&
        details.phase_units_done != null
    ) {
        lines.push(`шаг фазы: ${details.phase_units_done}/${details.phase_units_total}`)
    }
    const eta = formatEtaSeconds(details.eta_seconds)
    if (eta) {
        const conf =
            details.eta_confidence === 'low'
                ? ' (оценка грубая)'
                : details.eta_confidence === 'high'
                  ? ''
                  : ' (уточняется)'
        lines.push(`осталось: ${eta}${conf}`)
    }
    if (details.current_trade_date) lines.push(`текущий торговый день: ${details.current_trade_date}`)
    if (details.trade_dates_total != null && details.trade_dates_remaining != null) {
        const done = details.trade_dates_total - details.trade_dates_remaining
        lines.push(`календарные дни: ${done}/${details.trade_dates_total}`)
    }
    if (details.cancel_requested) {
        lines.push('отмена запрошена — дождитесь завершения текущего шага')
    }
    if (details.error_message) {
        lines.push(`ошибка: ${details.error_message}`)
    }
    if (isBacktestTerminalStatus(details.status) && details.partial_result) {
        lines.push('результат неполный (симуляция остановлена до конца выбранного периода)')
    }
    return lines
}

export function runProgressFromStatus(status: RobotBacktestRunStatus): {
    percent: number
    etaLabel: string | null
    phaseLabel: string | null
    runPhase: string | null
    phaseUnitsDone: number | null
    phaseUnitsTotal: number | null
} {
    const pct = status.progress_percent
    return {
        percent: pct != null && Number.isFinite(pct) ? Math.min(100, Math.max(0, pct)) : 0,
        etaLabel: formatEtaSeconds(status.eta_seconds),
        phaseLabel: status.phase_label || status.run_phase || null,
        runPhase: status.run_phase ?? null,
        phaseUnitsDone: status.phase_units_done ?? null,
        phaseUnitsTotal: status.phase_units_total ?? null,
    }
}
