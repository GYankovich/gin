export const TINVEST_CANDLE_INTERVAL_VALUES = [
    'CANDLE_INTERVAL_1_MIN',
    'CANDLE_INTERVAL_2_MIN',
    'CANDLE_INTERVAL_3_MIN',
    'CANDLE_INTERVAL_5_MIN',
    'CANDLE_INTERVAL_10_MIN',
    'CANDLE_INTERVAL_15_MIN',
    'CANDLE_INTERVAL_30_MIN',
    'CANDLE_INTERVAL_HOUR',
    'CANDLE_INTERVAL_2_HOUR',
    'CANDLE_INTERVAL_4_HOUR',
    'CANDLE_INTERVAL_DAY',
    'CANDLE_INTERVAL_WEEK',
    'CANDLE_INTERVAL_MONTH',
] as const

export type TinvestCandleInterval = (typeof TINVEST_CANDLE_INTERVAL_VALUES)[number]

const LABELS: Record<TinvestCandleInterval, string> = {
    CANDLE_INTERVAL_1_MIN: '1 мин',
    CANDLE_INTERVAL_2_MIN: '2 мин',
    CANDLE_INTERVAL_3_MIN: '3 мин',
    CANDLE_INTERVAL_5_MIN: '5 мин',
    CANDLE_INTERVAL_10_MIN: '10 мин',
    CANDLE_INTERVAL_15_MIN: '15 мин',
    CANDLE_INTERVAL_30_MIN: '30 мин',
    CANDLE_INTERVAL_HOUR: '1 час',
    CANDLE_INTERVAL_2_HOUR: '2 часа',
    CANDLE_INTERVAL_4_HOUR: '4 часа',
    CANDLE_INTERVAL_DAY: '1 день',
    CANDLE_INTERVAL_WEEK: '1 неделя',
    CANDLE_INTERVAL_MONTH: '1 месяц',
}

export const TINVEST_CANDLE_INTERVAL_OPTIONS = TINVEST_CANDLE_INTERVAL_VALUES.map(value => ({
    value,
    label: LABELS[value],
}))

/** Подмножество для страницы /testing (§3.2 MOEX). */
export const MOEX_TESTING_CANDLE_INTERVAL_VALUES = [
    'CANDLE_INTERVAL_1_MIN',
    'CANDLE_INTERVAL_5_MIN',
    'CANDLE_INTERVAL_10_MIN',
    'CANDLE_INTERVAL_15_MIN',
    'CANDLE_INTERVAL_30_MIN',
    'CANDLE_INTERVAL_HOUR',
    'CANDLE_INTERVAL_4_HOUR',
    'CANDLE_INTERVAL_DAY',
] as const satisfies readonly TinvestCandleInterval[]

const TESTING_LABELS: Record<(typeof MOEX_TESTING_CANDLE_INTERVAL_VALUES)[number], string> = {
    CANDLE_INTERVAL_1_MIN: '1m',
    CANDLE_INTERVAL_5_MIN: '5m',
    CANDLE_INTERVAL_10_MIN: '10m',
    CANDLE_INTERVAL_15_MIN: '15m',
    CANDLE_INTERVAL_30_MIN: '30m',
    CANDLE_INTERVAL_HOUR: '1h',
    CANDLE_INTERVAL_4_HOUR: '4h',
    CANDLE_INTERVAL_DAY: '1d',
}

export const MOEX_TESTING_CANDLE_INTERVAL_OPTIONS = MOEX_TESTING_CANDLE_INTERVAL_VALUES.map(value => ({
    value,
    label: TESTING_LABELS[value],
}))

export const DEFAULT_TINVEST_TESTING_INTERVAL: TinvestCandleInterval = 'CANDLE_INTERVAL_5_MIN'

const ALLOWED = new Set<string>(TINVEST_CANDLE_INTERVAL_VALUES)
const TESTING_ALLOWED = new Set<string>(MOEX_TESTING_CANDLE_INTERVAL_VALUES)

/** Нормализует значение интервала к enum T-Invest; неизвестное → fallback. */
export function normalizeTinvestCandleInterval(
    value: string | null | undefined,
    fallback: TinvestCandleInterval = DEFAULT_TINVEST_TESTING_INTERVAL,
): TinvestCandleInterval {
    const v = String(value || '').trim().toUpperCase()
    if (TESTING_ALLOWED.has(v)) return v as TinvestCandleInterval
    if (ALLOWED.has(v)) return v as TinvestCandleInterval
    if (v.includes('1_MIN') && !v.includes('10_MIN') && !v.includes('15_MIN') && !v.includes('30_MIN')) {
        return 'CANDLE_INTERVAL_1_MIN'
    }
    if (v.includes('2_MIN') && !v.includes('12_MIN')) return 'CANDLE_INTERVAL_2_MIN'
    if (v.includes('3_MIN')) return 'CANDLE_INTERVAL_3_MIN'
    if (v.includes('5_MIN')) return 'CANDLE_INTERVAL_5_MIN'
    if (v.includes('10_MIN')) return 'CANDLE_INTERVAL_10_MIN'
    if (v.includes('15_MIN')) return 'CANDLE_INTERVAL_15_MIN'
    if (v.includes('30_MIN')) return 'CANDLE_INTERVAL_30_MIN'
    if (v.includes('2_HOUR')) return 'CANDLE_INTERVAL_2_HOUR'
    if (v.includes('4_HOUR')) return 'CANDLE_INTERVAL_4_HOUR'
    if (v.includes('HOUR') || v.includes('60')) return 'CANDLE_INTERVAL_HOUR'
    if (v.includes('WEEK')) return 'CANDLE_INTERVAL_WEEK'
    if (v.includes('MONTH')) return 'CANDLE_INTERVAL_MONTH'
    if (v.includes('DAY') || v.includes('24')) return 'CANDLE_INTERVAL_DAY'
    return fallback
}
