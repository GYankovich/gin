import {
    BYBIT_CANDLE_INTERVAL_OPTIONS,
    BYBIT_INTERVAL_TO_TINVEST_ENUM,
    DEFAULT_BYBIT_CANDLE_INTERVAL,
    TINVEST_ENUM_TO_BYBIT_INTERVAL,
    normalizeBybitCandleInterval,
    type BybitCandleInterval,
} from '@/pages/testing/bybitCandleIntervals'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'
import {
    DEFAULT_TINVEST_TESTING_INTERVAL,
    MOEX_TESTING_CANDLE_INTERVAL_OPTIONS,
    normalizeTinvestCandleInterval,
    type TinvestCandleInterval,
} from '@/pages/testing/tinvestCandleIntervals'

function isCryptoBrokerType(value: string): boolean {
    return String(value || '').trim().toLowerCase() === 'bybit'
}
import type { StrategyParamField } from '@/pages/testing/strategyPresets'

export const MOEX_INTERVAL_FIELD: StrategyParamField = {
    key: 'interval',
    label: 'Таймфрейм стратегии',
    kind: 'enum',
    description:
        'Синхронизирован с блоком «Время и данные». Для M5/M1 нужен T-Invest cache (MOEX ISS не отдаёт 5-минутки).',
    options: MOEX_TESTING_CANDLE_INTERVAL_OPTIONS,
    group: 'candles',
}

export const CRYPTO_INTERVAL_FIELD: StrategyParamField = {
    key: 'interval',
    label: 'Таймфрейм стратегии',
    kind: 'enum',
    description: 'Интервал свечей ByBit для WebSocket и расчёта сигналов.',
    options: BYBIT_CANDLE_INTERVAL_OPTIONS,
    group: 'candles',
}

export function getStrategyIntervalFieldForMarket(market: TestingMarket): StrategyParamField {
    return market === 'crypto' ? CRYPTO_INTERVAL_FIELD : MOEX_INTERVAL_FIELD
}

export function defaultIntervalForMarket(market: TestingMarket): string {
    return market === 'crypto' ? DEFAULT_BYBIT_CANDLE_INTERVAL : DEFAULT_TINVEST_TESTING_INTERVAL
}

export function normalizeStrategyInterval(
    value: string | null | undefined,
    marketOrBroker: TestingMarket | string,
): string {
    const isCrypto =
        marketOrBroker === 'crypto' || isCryptoBrokerType(String(marketOrBroker))
    if (isCrypto) {
        return normalizeBybitCandleInterval(value)
    }
    return normalizeTinvestCandleInterval(value)
}

/** Конвертация при переключении MOEX ↔ Crypto (§3.2). */
export function convertIntervalForMarket(
    interval: string,
    targetMarket: TestingMarket,
): string {
    const raw = String(interval || '').trim()
    if (!raw) return defaultIntervalForMarket(targetMarket)

    if (targetMarket === 'crypto') {
        const upper = raw.toUpperCase().replace(/\s/g, '')
        if (upper in TINVEST_ENUM_TO_BYBIT_INTERVAL) {
            return TINVEST_ENUM_TO_BYBIT_INTERVAL[upper]
        }
        return normalizeBybitCandleInterval(raw)
    }

    const lower = raw.toLowerCase()
    if (lower in BYBIT_INTERVAL_TO_TINVEST_ENUM) {
        return BYBIT_INTERVAL_TO_TINVEST_ENUM[lower as BybitCandleInterval]
    }
    return normalizeTinvestCandleInterval(raw)
}

export {
    DEFAULT_BYBIT_CANDLE_INTERVAL,
    DEFAULT_TINVEST_TESTING_INTERVAL,
    normalizeBybitCandleInterval,
    normalizeTinvestCandleInterval,
    type BybitCandleInterval,
    type TinvestCandleInterval,
}
