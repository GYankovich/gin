import { normalizeTinvestCandleInterval } from '@/pages/testing/tinvestCandleIntervals'
import { parseFixedTickersInput } from '@/utils/universeMode'
import type { RobotStrategyName, RobotStrategyParams } from '@/types/robot'
import type { CryptoUniverseMode, UniverseMode } from '@/utils/universeMode'

export type ConfigValidationIssue = {
    id: string
    message: string
    severity: 'error' | 'warning'
    field?: string
}

export type MoexRobotSettingsInput = {
    robotType: 1 | 2
    hoursFrom: string
    hoursTo: string
    pollValue: number
    pollUnit: 'minutes' | 'hours'
    strategy: RobotStrategyName
    strategyParams: RobotStrategyParams
    interval: string
    capital: number
    stopLossPct: number
    takeProfitPct: number
    maxPositionPct: number
    maxPositionRub: number
}

export type MoexRobotSettingsCheckInput = MoexRobotSettingsInput & {
    name: string
    tokenId: number
    universeMode?: UniverseMode
    fixedTickersText?: string
    isCrypto?: boolean
    cryptoUniverseMode?: CryptoUniverseMode
}

const INTERVAL_MINUTES: Record<string, number> = {
    CANDLE_INTERVAL_1_MIN: 1,
    CANDLE_INTERVAL_2_MIN: 2,
    CANDLE_INTERVAL_3_MIN: 3,
    CANDLE_INTERVAL_5_MIN: 5,
    CANDLE_INTERVAL_10_MIN: 10,
    CANDLE_INTERVAL_15_MIN: 15,
    CANDLE_INTERVAL_30_MIN: 30,
    CANDLE_INTERVAL_HOUR: 60,
    CANDLE_INTERVAL_2_HOUR: 120,
    CANDLE_INTERVAL_4_HOUR: 240,
    CANDLE_INTERVAL_DAY: 1440,
}

export function candleIntervalMinutes(interval: string): number {
    const n = INTERVAL_MINUTES[normalizeTinvestCandleInterval(interval)]
    return n > 0 ? n : 5
}

function parseTimeToMinutes(hhmm: string): number | null {
    const m = String(hhmm || '').match(/^(\d{1,2}):(\d{2})$/)
    if (!m) return null
    return Number(m[1]) * 60 + Number(m[2])
}

function pollIntervalMinutes(pollValue: number, pollUnit: 'minutes' | 'hours'): number {
    return pollUnit === 'minutes' ? Math.max(1, Number(pollValue || 1)) : Math.max(1, Math.round(Number(pollValue || 1) * 60))
}

function maxHoldCandlesForHistory(candleDays: number, intervalMin: number): number {
    const barsPerDay = Math.floor((8 * 60) / Math.max(1, intervalMin))
    return Math.max(1, candleDays * barsPerDay)
}

function strategyParamNumber(params: RobotStrategyParams, key: string, fallback: number): number {
    const raw = params as Record<string, unknown>
    return Number(raw[key] ?? fallback)
}

export function collectMoexSettingsIssues(
    input: MoexRobotSettingsInput & { isCrypto?: boolean },
): ConfigValidationIssue[] {
    const issues: ConfigValidationIssue[] = []
    if (input.robotType !== 2) return issues

    if (!input.isCrypto) {
        const start = parseTimeToMinutes(input.hoursFrom)
        const end = parseTimeToMinutes(input.hoursTo)
        if (start != null && end != null && start >= end) {
            issues.push({
                id: 'hours_order',
                severity: 'error',
                field: 'schedule',
                message: 'Часы работы: «от» должно быть раньше «до»',
            })
        }
    }

    const cycleMin = pollIntervalMinutes(input.pollValue, input.pollUnit)
    const intervalMin = candleIntervalMinutes(input.interval)
    const sp = input.strategyParams

    if (!input.isCrypto && input.strategy === 'momentum_breakout') {
        const entryMin = strategyParamNumber(sp, 'entry_minutes_from_open', 30)
        if (entryMin < cycleMin) {
            issues.push({
                id: 'entry_vs_cycle',
                severity: 'error',
                field: 'strategy',
                message: `Окно входа (${entryMin} мин) не может быть меньше цикла робота (${cycleMin} мин)`,
            })
        }
        const hold = strategyParamNumber(sp, 'hold_candles', 1)
        const candleDays = Math.max(
            1,
            strategyParamNumber(sp, 'candle_days', strategyParamNumber(sp, 'lookback_days', 14)),
        )
        const maxHold = maxHoldCandlesForHistory(candleDays, intervalMin)
        if (hold > maxHold) {
            issues.push({
                id: 'hold_vs_history',
                severity: 'error',
                field: 'strategy',
                message: `Удерживать (${hold} св.) превышает оценку истории (~${maxHold} св. за ${candleDays} дн.)`,
            })
        }
    }

    if (input.strategy === 'reversion_to_ma') {
        const maxHold = strategyParamNumber(sp, 'max_hold_candles', 12)
        const candleDays = Math.max(1, strategyParamNumber(sp, 'candle_days', 14))
        const maxBars = maxHoldCandlesForHistory(candleDays, intervalMin)
        if (maxHold > maxBars) {
            issues.push({
                id: 'max_hold_vs_history',
                severity: 'warning',
                field: 'strategy',
                message: `Макс. удержание (${maxHold}) близко к пределу истории (~${maxBars} св.)`,
            })
        }
    }

    const stop = Number(input.stopLossPct || 0)
    const take = Number(input.takeProfitPct || 0)
    if (stop > 0 && take > 0 && stop >= take) {
        issues.push({
            id: 'stop_take',
            severity: 'warning',
            field: 'risk',
            message: 'Стоп-лосс (%) обычно меньше тейк-профита (%)',
        })
    }

    const cap = Number(input.capital || 0)
    if (!input.isCrypto && cap > 0 && cap < 10_000) {
        issues.push({
            id: 'capital_min',
            severity: 'error',
            field: 'risk',
            message: 'Бюджет не может быть меньше 10 000 ₽',
        })
    }

    const maxPct = Number(input.maxPositionPct || 0)
    const maxRub = Number(input.maxPositionRub || 0)
    if (!input.isCrypto && cap > 0 && maxPct > 0 && maxRub > 0) {
        const pctRub = (cap * maxPct) / 100
        const diff = Math.abs(pctRub - maxRub) / Math.max(maxRub, pctRub, 1)
        if (diff > 0.35) {
            issues.push({
                id: 'position_pct_rub',
                severity: 'warning',
                field: 'risk',
                message: `Макс. доля (${maxPct}% ≈ ${Math.round(pctRub).toLocaleString('ru-RU')} ₽) и лимит ${Math.round(maxRub).toLocaleString('ru-RU')} ₽ расходятся`,
            })
        }
    }

    return issues
}

export function collectIssues(input: MoexRobotSettingsCheckInput): ConfigValidationIssue[] {
    const issues: ConfigValidationIssue[] = []
    if (!input.name.trim()) {
        issues.push({ id: 'name', severity: 'error', field: 'name', message: 'Укажите название робота' })
    }
    if (!input.tokenId) {
        issues.push({ id: 'token', severity: 'error', field: 'token', message: 'Выберите токен' })
    }
    const requiresFixedInstruments =
        input.robotType === 2 &&
        (input.isCrypto
            ? input.cryptoUniverseMode === 'fixed'
            : input.universeMode === 'fixed')
    if (
        requiresFixedInstruments &&
        !parseFixedTickersInput(String(input.fixedTickersText || '')).length
    ) {
        issues.push({
            id: 'fixed_tickers',
            severity: 'error',
            field: 'universe',
            message: input.isCrypto
                ? 'Укажите символы ByBit (например BTCUSDT)'
                : 'Укажите тикеры для режима «Фиксированный список»',
        })
    }
    issues.push(...collectMoexSettingsIssues(input))
    return issues
}

export function hasBlockingValidationIssues(issues: ConfigValidationIssue[]): boolean {
    return issues.some(i => i.severity === 'error')
}
