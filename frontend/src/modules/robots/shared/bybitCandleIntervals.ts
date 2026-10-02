/**
 * Интервалы свечей ByBit (linear/spot kline API).
 * Хранятся в strategy_params.interval как строки «1m», «5m», …
 */
export const BYBIT_CANDLE_INTERVAL_VALUES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'] as const

export type BybitCandleInterval = (typeof BYBIT_CANDLE_INTERVAL_VALUES)[number]

const LABELS: Record<BybitCandleInterval, string> = {
    '1m': '1m',
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1h',
    '4h': '4h',
    '1d': '1d',
}

export const BYBIT_CANDLE_INTERVAL_OPTIONS = BYBIT_CANDLE_INTERVAL_VALUES.map(value => ({
    value,
    label: LABELS[value],
}))

const ALLOWED = new Set<string>(BYBIT_CANDLE_INTERVAL_VALUES)

/** T-Invest enum → ближайший ByBit UI-интервал (§3.2). */
export const TINVEST_ENUM_TO_BYBIT_INTERVAL: Record<string, BybitCandleInterval> = {
    CANDLE_INTERVAL_1_MIN: '1m',
    CANDLE_INTERVAL_5_MIN: '5m',
    CANDLE_INTERVAL_10_MIN: '15m',
    CANDLE_INTERVAL_15_MIN: '30m',
    CANDLE_INTERVAL_30_MIN: '1h',
    CANDLE_INTERVAL_HOUR: '4h',
    CANDLE_INTERVAL_4_HOUR: '1d',
    CANDLE_INTERVAL_DAY: '1d',
}

/** ByBit UI → T-Invest enum (§3.2). */
export const BYBIT_INTERVAL_TO_TINVEST_ENUM: Record<BybitCandleInterval, string> = {
    '1m': 'CANDLE_INTERVAL_1_MIN',
    '5m': 'CANDLE_INTERVAL_5_MIN',
    '15m': 'CANDLE_INTERVAL_10_MIN',
    '30m': 'CANDLE_INTERVAL_15_MIN',
    '1h': 'CANDLE_INTERVAL_30_MIN',
    '4h': 'CANDLE_INTERVAL_HOUR',
    '1d': 'CANDLE_INTERVAL_4_HOUR',
}

export const DEFAULT_BYBIT_CANDLE_INTERVAL: BybitCandleInterval = '5m'

/** Нормализует значение к ByBit UI-формату. */
export function normalizeBybitCandleInterval(
    value: string | null | undefined,
    fallback: BybitCandleInterval = DEFAULT_BYBIT_CANDLE_INTERVAL,
): BybitCandleInterval {
    const raw = String(value ?? '').trim()
    const lower = raw.toLowerCase()
    if (ALLOWED.has(lower)) return lower as BybitCandleInterval

    const upper = raw.toUpperCase().replace(/\s/g, '')
    if (upper in TINVEST_ENUM_TO_BYBIT_INTERVAL) {
        return TINVEST_ENUM_TO_BYBIT_INTERVAL[upper]
    }

    const tokenMap: Array<[string[], BybitCandleInterval]> = [
        [['1_MIN', '1M', 'M1', 'I1'], '1m'],
        [['5_MIN', '5M', 'M5', 'I5'], '5m'],
        [['15_MIN', '15M', 'M15', 'I15'], '15m'],
        [['30_MIN', '30M', 'M30', 'I30'], '30m'],
        [['4_HOUR', '4H', 'H4', '240'], '4h'],
        [['HOUR', '60_MIN', '1H', '60M', 'M60'], '1h'],
        [['DAY', 'D1', '24H', '1D'], '1d'],
    ]
    for (const [tokens, iv] of tokenMap) {
        if (tokens.some(t => upper.includes(t))) return iv
    }

    return fallback
}
