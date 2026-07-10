import type { CryptoUniverseFormFields } from '@/modules/robots/config/cryptoUniverseDefaults'
import {
    CRYPTO_UNIVERSE_FILTER_PRESETS,
    type UniverseFilterPresetId,
} from '@/modules/robots/config/universeFilterPresets'
import {
    getCryptoFilterFieldMeta,
    getCryptoFilterTypesInRegistryOrder,
} from '@/modules/robots/config/p1ScreeningFields'

/** Поля crypto_universe, редактируемые на P1 (funding в UI как %). */
export type CryptoScreeningFilterType =
    | 'min_volume_24h_usd'
    | 'min_last_price'
    | 'max_spread_bps'
    | 'min_funding_rate_pct'
    | 'max_funding_rate_pct'
    | 'min_open_interest_usd'
    | 'min_lsr'
    | 'max_lsr'
    | 'min_rvol'
    | 'min_atr_percent'
    | 'max_atr_percent'
    | 'lookback_days'
    | 'funding_lookback_hours'
    | 'refresh_every_minutes'

export type CryptoScreeningFilter = {
    id: string
    type: CryptoScreeningFilterType
    value: number
}

type CryptoFilterMeta = {
    label: string
    step?: number
    min?: number
    max?: number
    integer?: boolean
    defaultValue: number
}

export const CRYPTO_FILTER_META: Record<CryptoScreeningFilterType, CryptoFilterMeta> = {
    min_volume_24h_usd: {
        label: getCryptoFilterFieldMeta('min_volume_24h_usd')?.label ?? 'Мин. объём 24h (USD)',
        step: 100000,
        min: 0,
        integer: true,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minVolume24hUsd,
    },
    min_last_price: {
        label: getCryptoFilterFieldMeta('min_last_price')?.label ?? 'Мин. цена (USDT)',
        step: 0.001,
        min: 0,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minLastPrice,
    },
    max_spread_bps: {
        label: getCryptoFilterFieldMeta('max_spread_bps')?.label ?? 'Макс. спред (bps)',
        step: 1,
        min: 0,
        integer: true,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.maxSpreadBps,
    },
    min_funding_rate_pct: {
        label: getCryptoFilterFieldMeta('min_funding_rate_pct')?.label ?? 'Мин. funding (%)',
        step: 0.001,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minFundingRatePct,
    },
    max_funding_rate_pct: {
        label: getCryptoFilterFieldMeta('max_funding_rate_pct')?.label ?? 'Макс. funding (%)',
        step: 0.001,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.maxFundingRatePct,
    },
    min_open_interest_usd: {
        label: getCryptoFilterFieldMeta('min_open_interest_usd')?.label ?? 'Мин. Open Interest (USD)',
        step: 1000000,
        min: 0,
        integer: true,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minOpenInterestUsd,
    },
    min_lsr: {
        label: getCryptoFilterFieldMeta('min_lsr')?.label ?? 'Long/Short Ratio (min)',
        step: 0.1,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minLsr,
    },
    max_lsr: {
        label: getCryptoFilterFieldMeta('max_lsr')?.label ?? 'Long/Short Ratio (max)',
        step: 0.1,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.maxLsr,
    },
    min_rvol: {
        label: getCryptoFilterFieldMeta('min_rvol')?.label ?? 'Мин. Relative Volume',
        step: 0.1,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minRvol,
    },
    min_atr_percent: {
        label: getCryptoFilterFieldMeta('min_atr_percent')?.label ?? 'Мин. ATR (%)',
        step: 0.1,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minAtrPercent,
    },
    max_atr_percent: {
        label: getCryptoFilterFieldMeta('max_atr_percent')?.label ?? 'Макс. ATR (%)',
        step: 0.1,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.maxAtrPercent,
    },
    lookback_days: {
        label: getCryptoFilterFieldMeta('lookback_days')?.label ?? 'Глубина истории (дней)',
        min: 1,
        max: 365,
        integer: true,
        defaultValue: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.lookbackDays,
    },
    funding_lookback_hours: {
        label: getCryptoFilterFieldMeta('funding_lookback_hours')?.label ?? 'Окно funding (ч)',
        min: 1,
        max: 72,
        integer: true,
        defaultValue: 8,
    },
    refresh_every_minutes: {
        label: getCryptoFilterFieldMeta('refresh_every_minutes')?.label ?? 'Пересчёт (мин)',
        min: 0,
        max: 10080,
        integer: true,
        defaultValue: 60,
    },
}

const TYPE_TO_FIELD: Record<CryptoScreeningFilterType, keyof CryptoUniverseFormFields> = {
    min_volume_24h_usd: 'cryptoMinVolume24hUsd',
    min_last_price: 'cryptoMinLastPrice',
    max_spread_bps: 'cryptoMaxSpreadBps',
    min_funding_rate_pct: 'cryptoMinFundingRatePct',
    max_funding_rate_pct: 'cryptoMaxFundingRatePct',
    min_open_interest_usd: 'cryptoMinOpenInterestUsd',
    min_lsr: 'cryptoMinLsr',
    max_lsr: 'cryptoMaxLsr',
    min_rvol: 'cryptoMinRvol',
    min_atr_percent: 'cryptoMinAtrPercent',
    max_atr_percent: 'cryptoMaxAtrPercent',
    lookback_days: 'cryptoLookbackDays',
    funding_lookback_hours: 'cryptoFundingLookbackHours',
    refresh_every_minutes: 'cryptoRefreshEveryMinutes',
}

const PRESET_VALUE_GETTERS: Record<
    CryptoScreeningFilterType,
    (preset: (typeof CRYPTO_UNIVERSE_FILTER_PRESETS)[UniverseFilterPresetId]) => number
> = {
    min_volume_24h_usd: p => p.minVolume24hUsd,
    min_last_price: p => p.minLastPrice,
    max_spread_bps: p => p.maxSpreadBps,
    min_funding_rate_pct: p => p.minFundingRatePct,
    max_funding_rate_pct: p => p.maxFundingRatePct,
    min_open_interest_usd: p => p.minOpenInterestUsd,
    min_lsr: p => p.minLsr,
    max_lsr: p => p.maxLsr,
    min_rvol: p => p.minRvol,
    min_atr_percent: p => p.minAtrPercent,
    max_atr_percent: p => p.maxAtrPercent,
    lookback_days: p => p.lookbackDays,
    funding_lookback_hours: () => 8,
    refresh_every_minutes: () => 60,
}

export const CRYPTO_SCREENING_FILTER_TYPES = getCryptoFilterTypesInRegistryOrder()

function cryptoFiltersWithIds(
    defs: Array<{ type: CryptoScreeningFilterType; value: number }>,
    idPrefix = 'preset',
): CryptoScreeningFilter[] {
    const stamp = Date.now()
    return defs.map((f, idx) => ({
        id: `${idPrefix}-${f.type}-${idx}-${stamp}`,
        type: f.type,
        value: f.value,
    }))
}

export function cryptoScreeningFiltersFromPreset(presetId: UniverseFilterPresetId): CryptoScreeningFilter[] {
    const preset = CRYPTO_UNIVERSE_FILTER_PRESETS[presetId]
    const defs = CRYPTO_SCREENING_FILTER_TYPES.map(type => ({
        type,
        value: PRESET_VALUE_GETTERS[type](preset),
    }))
    return cryptoFiltersWithIds(defs, presetId)
}

export function createDefaultCryptoScreeningFilters(): CryptoScreeningFilter[] {
    return cryptoScreeningFiltersFromPreset('moderate')
}

/** Всегда полный набор полей crypto_universe (как на бэке). */
export function cryptoFieldsFromFilters(filters: CryptoScreeningFilter[]): CryptoUniverseFormFields {
    const byType = new Map(filters.map(f => [f.type, f.value]))
    const result = {} as CryptoUniverseFormFields
    for (const type of CRYPTO_SCREENING_FILTER_TYPES) {
        result[TYPE_TO_FIELD[type]] = byType.has(type)
            ? (byType.get(type) as number)
            : CRYPTO_FILTER_META[type].defaultValue
    }
    return result
}

/** Гидратация: всегда все типы, без отбрасывания «inactive». */
export function cryptoFiltersFromFields(fields: CryptoUniverseFormFields): CryptoScreeningFilter[] {
    const defs = CRYPTO_SCREENING_FILTER_TYPES.map(type => ({
        type,
        value: Number(fields[TYPE_TO_FIELD[type]] ?? CRYPTO_FILTER_META[type].defaultValue),
    }))
    return cryptoFiltersWithIds(defs, 'hydrate')
}

/** Дополнить список до полного набора crypto_universe (после старых сейвов). */
export function ensureCompleteCryptoFilters(filters: CryptoScreeningFilter[]): CryptoScreeningFilter[] {
    const byType = new Map(filters.map(f => [f.type, f]))
    const stamp = Date.now()
    return CRYPTO_SCREENING_FILTER_TYPES.map((type, idx) => {
        const existing = byType.get(type)
        if (existing) return existing
        return {
            id: `fill-${type}-${idx}-${stamp}`,
            type,
            value: CRYPTO_FILTER_META[type].defaultValue,
        }
    })
}

export function upsertCryptoFilterValue(
    filters: CryptoScreeningFilter[],
    type: CryptoScreeningFilterType,
    value: number,
): CryptoScreeningFilter[] {
    const complete = ensureCompleteCryptoFilters(filters)
    const idx = complete.findIndex(f => f.type === type)
    if (idx < 0) return complete
    if (Math.abs(complete[idx].value - value) < 1e-9) return complete
    const next = [...complete]
    next[idx] = { ...complete[idx], value }
    return next
}

export function defaultValueForCryptoFilterType(type: CryptoScreeningFilterType): number {
    return CRYPTO_FILTER_META[type].defaultValue
}
