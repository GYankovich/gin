/**
 * Каталог полей отбора по схемам бэка:
 *   type2_tinvest → historical_screening (+ grain_seed strategy_params на P1)
 *   type2_bybit   → crypto_universe (+ universe_mode)
 *
 * Не смешиваем рынки в «общие» UI-блоки — только точные backend-пути.
 */

import type { CryptoScreeningFilterType } from '@/pages/testing/cryptoScreeningPipeline'

export type P1Market = 'moex' | 'crypto'

export type P1ScreeningFieldKind = 'number' | 'integer' | 'time' | 'enum' | 'universe_mode'

export type P1ScreeningFieldDef = {
    key: string
    market: P1Market
    label: string
    shortLabel?: string
    tooltip?: string
    kind: P1ScreeningFieldKind
    min?: number
    max?: number
    step?: number
    defaultValue?: number | string
    options?: Array<{ value: string; label: string }>
    /** Путь в конфиге бэка. */
    path: string
    cryptoFilterType?: CryptoScreeningFilterType
    strategyParamKey?: string
    /** На каком stage UI (по умолчанию p1). */
    stage?: 'p1' | 'p2'
}

/** MOEX P1: historical_screening + grain_seed screening params. */
export const MOEX_P1_FIELDS: readonly P1ScreeningFieldDef[] = [
    {
        key: 'lookback_days',
        market: 'moex',
        label: 'Глубина истории (дней)',
        shortLabel: 'Lookback',
        tooltip: 'Сколько календарных дней истории загружать для расчёта индикаторов.',
        kind: 'integer',
        min: 1,
        max: 3650,
        defaultValue: 14,
        path: 'historical_screening.lookback_days',
    },
    {
        key: 'candle_interval',
        market: 'moex',
        label: 'Интервал свечей MOEX',
        tooltip: 'Таймфрейм исторических свечей MOEX для массового отбора кандидатов.',
        kind: 'enum',
        defaultValue: 'CANDLE_INTERVAL_10_MIN',
        options: [
            { value: 'CANDLE_INTERVAL_10_MIN', label: '10 минут' },
            { value: 'CANDLE_INTERVAL_HOUR', label: '1 час' },
            { value: 'CANDLE_INTERVAL_DAY', label: '1 день' },
        ],
        path: 'historical_screening.interval',
    },
    {
        key: 'refresh_daily_at_msk',
        market: 'moex',
        label: 'Пересчёт (MSK)',
        tooltip: 'Время ежедневного пересчёта candidate pool до открытия сессии.',
        kind: 'time',
        defaultValue: '07:00',
        path: 'historical_screening.refresh.daily_at_msk',
    },
    {
        key: 'atr_period',
        market: 'moex',
        label: 'Период ATR',
        shortLabel: 'ATR per',
        tooltip: 'Окно ATR для оценки волатильности (также в historical_screening.filters).',
        kind: 'integer',
        min: 2,
        defaultValue: 14,
        path: 'strategy_params.atr_period',
        strategyParamKey: 'atr_period',
    },
    {
        key: 'atr_min_pct',
        market: 'moex',
        label: 'Мин. ATR (%)',
        shortLabel: 'ATR min',
        tooltip: 'Минимальная волатильность ATR/цена.',
        kind: 'number',
        min: 0,
        step: 0.1,
        defaultValue: 1.5,
        path: 'strategy_params.atr_min_pct',
        strategyParamKey: 'atr_min_pct',
    },
    {
        key: 'adx_period',
        market: 'moex',
        label: 'Период ADX',
        tooltip: 'Количество дней для расчёта ADX — индикатора силы тренда.',
        kind: 'integer',
        min: 2,
        defaultValue: 14,
        path: 'strategy_params.adx_period',
        strategyParamKey: 'adx_period',
    },
    {
        key: 'adx_threshold',
        market: 'moex',
        label: 'Порог ADX',
        tooltip: 'Минимальная сила тренда. Ниже ~20 — флэт; 20–40 — умеренный; выше 40 — сильный.',
        kind: 'number',
        min: 0,
        step: 0.5,
        defaultValue: 22,
        path: 'strategy_params.adx_threshold',
        strategyParamKey: 'adx_threshold',
    },
]

/**
 * Crypto P1: crypto_universe.* (UI funding в %, бэк — доля).
 * Порядок = поля Typed CryptoUniverseConfig.
 */
export const CRYPTO_UNIVERSE_FIELDS: readonly P1ScreeningFieldDef[] = [
    {
        key: 'universe_mode',
        market: 'crypto',
        label: 'Режим universe',
        tooltip: 'universe_mode + crypto_universe.enabled (auto ↔ enabled=true)',
        kind: 'universe_mode',
        path: 'universe_mode',
        stage: 'p1',
    },
    {
        key: 'min_volume_24h_usd',
        market: 'crypto',
        label: 'Мин. объём 24h (USD)',
        shortLabel: 'Vol 24h',
        kind: 'integer',
        min: 0,
        step: 100_000,
        defaultValue: 50_000_000,
        path: 'crypto_universe.min_volume_24h_usd',
        cryptoFilterType: 'min_volume_24h_usd',
    },
    {
        key: 'min_last_price',
        market: 'crypto',
        label: 'Мин. цена (USDT)',
        shortLabel: 'Price',
        kind: 'number',
        min: 0,
        step: 0.001,
        defaultValue: 0.01,
        path: 'crypto_universe.min_last_price',
        cryptoFilterType: 'min_last_price',
    },
    {
        key: 'max_spread_bps',
        market: 'crypto',
        label: 'Макс. спред (bps)',
        shortLabel: 'Spread',
        kind: 'integer',
        min: 0,
        step: 1,
        defaultValue: 15,
        path: 'crypto_universe.max_spread_bps',
        cryptoFilterType: 'max_spread_bps',
    },
    {
        key: 'min_funding_rate_pct',
        market: 'crypto',
        label: 'Мин. funding (%)',
        shortLabel: 'Fund↓',
        tooltip: 'В UI %; в конфиг пишется crypto_universe.min_funding_rate как доля (/100).',
        kind: 'number',
        step: 0.001,
        defaultValue: -0.01,
        path: 'crypto_universe.min_funding_rate',
        cryptoFilterType: 'min_funding_rate_pct',
    },
    {
        key: 'max_funding_rate_pct',
        market: 'crypto',
        label: 'Макс. funding (%)',
        shortLabel: 'Fund↑',
        tooltip: 'В UI %; в конфиг пишется crypto_universe.max_funding_rate как доля (/100).',
        kind: 'number',
        step: 0.001,
        defaultValue: 0.02,
        path: 'crypto_universe.max_funding_rate',
        cryptoFilterType: 'max_funding_rate_pct',
    },
    {
        key: 'min_open_interest_usd',
        market: 'crypto',
        label: 'Мин. Open Interest (USD)',
        shortLabel: 'OI',
        kind: 'integer',
        min: 0,
        step: 1_000_000,
        defaultValue: 10_000_000,
        path: 'crypto_universe.min_open_interest_usd',
        cryptoFilterType: 'min_open_interest_usd',
    },
    {
        key: 'min_lsr',
        market: 'crypto',
        label: 'Long/Short Ratio (min)',
        shortLabel: 'LSR↓',
        kind: 'number',
        step: 0.1,
        defaultValue: 0.5,
        path: 'crypto_universe.min_lsr',
        cryptoFilterType: 'min_lsr',
    },
    {
        key: 'max_lsr',
        market: 'crypto',
        label: 'Long/Short Ratio (max)',
        shortLabel: 'LSR↑',
        kind: 'number',
        step: 0.1,
        defaultValue: 1.5,
        path: 'crypto_universe.max_lsr',
        cryptoFilterType: 'max_lsr',
    },
    {
        key: 'min_rvol',
        market: 'crypto',
        label: 'Мин. Relative Volume',
        shortLabel: 'RVOL',
        kind: 'number',
        step: 0.1,
        defaultValue: 2.0,
        path: 'crypto_universe.min_rvol',
        cryptoFilterType: 'min_rvol',
    },
    {
        key: 'min_atr_percent',
        market: 'crypto',
        label: 'Мин. ATR (%)',
        shortLabel: 'ATR min',
        kind: 'number',
        min: 0,
        step: 0.1,
        defaultValue: 1.5,
        path: 'crypto_universe.min_atr_percent',
        cryptoFilterType: 'min_atr_percent',
    },
    {
        key: 'max_atr_percent',
        market: 'crypto',
        label: 'Макс. ATR (%)',
        shortLabel: 'ATR max',
        kind: 'number',
        min: 0,
        step: 0.1,
        defaultValue: 10,
        path: 'crypto_universe.max_atr_percent',
        cryptoFilterType: 'max_atr_percent',
    },
    {
        key: 'lookback_days',
        market: 'crypto',
        label: 'Глубина истории (дней)',
        shortLabel: 'Lookback',
        kind: 'integer',
        min: 1,
        max: 365,
        defaultValue: 20,
        path: 'crypto_universe.lookback_days',
        cryptoFilterType: 'lookback_days',
    },
    {
        key: 'funding_lookback_hours',
        market: 'crypto',
        label: 'Окно funding (ч)',
        shortLabel: 'Fund h',
        kind: 'integer',
        min: 1,
        max: 72,
        defaultValue: 8,
        path: 'crypto_universe.funding_lookback_hours',
        cryptoFilterType: 'funding_lookback_hours',
    },
    {
        key: 'refresh_every_minutes',
        market: 'crypto',
        label: 'Пересчёт (мин)',
        shortLabel: 'Refresh',
        kind: 'integer',
        min: 0,
        max: 10080,
        defaultValue: 60,
        path: 'crypto_universe.refresh.every_minutes',
        cryptoFilterType: 'refresh_every_minutes',
    },
]

/** @deprecated используйте MOEX_P1_FIELDS / CRYPTO_UNIVERSE_FIELDS */
export const P1_SCREENING_FIELDS: readonly P1ScreeningFieldDef[] = [
    ...MOEX_P1_FIELDS,
    ...CRYPTO_UNIVERSE_FIELDS,
]

export function getP1Field(key: string, market?: P1Market): P1ScreeningFieldDef | undefined {
    const pool = market === 'moex' ? MOEX_P1_FIELDS : market === 'crypto' ? CRYPTO_UNIVERSE_FIELDS : P1_SCREENING_FIELDS
    return pool.find(f => f.key === key)
}

export function getP1FieldsForMarket(
    market: P1Market,
    stage: 'p1' | 'p2' = 'p1',
): P1ScreeningFieldDef[] {
    const pool = market === 'moex' ? MOEX_P1_FIELDS : CRYPTO_UNIVERSE_FIELDS
    return pool.filter(f => (f.stage ?? 'p1') === stage)
}

/** Crypto filter types в порядке CryptoUniverseConfig. */
export function getCryptoFilterTypesInRegistryOrder(): CryptoScreeningFilterType[] {
    const types: CryptoScreeningFilterType[] = []
    for (const f of CRYPTO_UNIVERSE_FIELDS) {
        if (f.cryptoFilterType && !types.includes(f.cryptoFilterType)) {
            types.push(f.cryptoFilterType)
        }
    }
    return types
}

export function getCryptoFilterFieldMeta(
    type: CryptoScreeningFilterType,
): Pick<P1ScreeningFieldDef, 'label' | 'shortLabel' | 'tooltip'> | undefined {
    const def = CRYPTO_UNIVERSE_FIELDS.find(f => f.cryptoFilterType === type)
    if (!def) return undefined
    return {
        label: def.label,
        shortLabel: def.shortLabel,
        tooltip: def.tooltip,
    }
}
