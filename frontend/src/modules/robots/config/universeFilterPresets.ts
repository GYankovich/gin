/**
 * Пресеты фильтров universe: MOEX pipeline (П2) и ByBit crypto screening.
 * Единый источник для /testing и настроек робота.
 */

import type { PipelineFilter } from '@/pages/testing/testingPipeline'
import type { CryptoUniverseFormFields } from '@/modules/robots/config/cryptoUniverseDefaults'

export type UniverseFilterPresetId = 'conservative' | 'moderate' | 'aggressive'

export const UNIVERSE_FILTER_PRESET_META: Record<
    UniverseFilterPresetId,
    { label: string; shortLabel: string; hint: string }
> = {
    conservative: {
        label: 'Консервативная',
        shortLabel: 'Консерв.',
        hint: 'Высокая ликвидность, узкие спреды, меньше инструментов',
    },
    moderate: {
        label: 'Умеренная',
        shortLabel: 'Умерен.',
        hint: 'Баланс ликвидности и охвата universe',
    },
    aggressive: {
        label: 'Агрессивная',
        shortLabel: 'Агресс.',
        hint: 'Шире universe, мягче пороги объёма и волатильности',
    },
}

/** П2 snapshot-фильтры (как в редакторе робота; без П1/ATR истории). */
export const MOEX_P2_SNAPSHOT_FILTER_PRESETS: Record<
    UniverseFilterPresetId,
    { mode: 'ALL' | 'ANY'; filters: Array<Omit<PipelineFilter, 'id'>> }
> = {
    conservative: {
        mode: 'ALL',
        filters: [
            { type: 'security_status', eq: 'A' },
            { type: 'trading_status', eq: 'T' },
            { type: 'volume', min: 100_000_000 },
            { type: 'gap', max_percent: 1.5, direction: 'BOTH' },
            { type: 'spread', max_percent: 0.1 },
            { type: 'turnover', min_percent: 0.5 },
        ],
    },
    moderate: {
        mode: 'ALL',
        filters: [
            { type: 'security_status', eq: 'A' },
            { type: 'trading_status', eq: 'T' },
            { type: 'volume', min: 50_000_000 },
            { type: 'gap', max_percent: 2.5, direction: 'BOTH' },
            { type: 'spread', max_percent: 0.15 },
            { type: 'turnover', min_percent: 0.3 },
        ],
    },
    aggressive: {
        mode: 'ALL',
        filters: [
            { type: 'security_status', eq: 'A' },
            { type: 'trading_status', eq: 'T' },
            { type: 'volume', min: 20_000_000 },
            { type: 'gap', max_percent: 4.0, direction: 'BOTH' },
            { type: 'spread', max_percent: 0.25 },
            { type: 'turnover', min_percent: 0.15 },
        ],
    },
}

/** Полный pipeline для страницы «Тестирование» (П2 + num_trades, ATR, gap_retention). */
export const MOEX_TESTING_PIPELINE_FILTER_PRESETS: Record<
    UniverseFilterPresetId,
    { mode: 'ALL' | 'ANY'; filters: Array<Omit<PipelineFilter, 'id'>> }
> = {
    conservative: {
        mode: 'ALL',
        filters: [
            { type: 'security_status', eq: 'A' },
            { type: 'trading_status', eq: 'T' },
            { type: 'volume', min: 100_000_000 },
            { type: 'num_trades', min: 200 },
            { type: 'gap', max_percent: 1.5, direction: 'BOTH' },
            { type: 'spread', max_percent: 0.1 },
            { type: 'atr', min_percent: 2.0, period: 14 },
            { type: 'turnover', min_percent: 0.5 },
            { type: 'gap_retention', min_ratio: 0.6 },
        ],
    },
    moderate: {
        mode: 'ALL',
        filters: [
            { type: 'security_status', eq: 'A' },
            { type: 'trading_status', eq: 'T' },
            { type: 'volume', min: 50_000_000 },
            { type: 'num_trades', min: 100 },
            { type: 'gap', max_percent: 2.5, direction: 'BOTH' },
            { type: 'spread', max_percent: 0.15 },
            { type: 'atr', min_percent: 1.5, period: 14 },
            { type: 'turnover', min_percent: 0.1 },
            { type: 'gap_retention', min_ratio: 0.5 },
        ],
    },
    aggressive: {
        mode: 'ALL',
        filters: [
            { type: 'security_status', eq: 'A' },
            { type: 'trading_status', eq: 'T' },
            { type: 'volume', min: 20_000_000 },
            { type: 'num_trades', min: 50 },
            { type: 'gap', max_percent: 4.0, direction: 'BOTH' },
            { type: 'spread', max_percent: 0.25 },
            { type: 'atr', min_percent: 1.0, period: 14 },
            { type: 'turnover', min_percent: 0.05 },
            { type: 'gap_retention', min_ratio: 0.4 },
        ],
    },
}

export type CryptoUniversePresetValues = {
    label: string
    minVolume24hUsd: number
    minLastPrice: number
    maxSpreadBps: number
    maxFundingRatePct: number
    minFundingRatePct: number
    minOpenInterestUsd: number
    minLsr: number
    maxLsr: number
    minRvol: number
    minAtrPercent: number
    maxAtrPercent: number
    lookbackDays: number
}

export const CRYPTO_UNIVERSE_FILTER_PRESETS: Record<UniverseFilterPresetId, CryptoUniversePresetValues> = {
    conservative: {
        label: UNIVERSE_FILTER_PRESET_META.conservative.label,
        minVolume24hUsd: 100_000_000,
        minLastPrice: 0.10,
        maxSpreadBps: 10,
        maxFundingRatePct: 0.01,
        minFundingRatePct: -0.005,
        minOpenInterestUsd: 25_000_000,
        minLsr: 0.7,
        maxLsr: 1.3,
        minRvol: 2.5,
        minAtrPercent: 2.0,
        maxAtrPercent: 7.0,
        lookbackDays: 30,
    },
    moderate: {
        label: UNIVERSE_FILTER_PRESET_META.moderate.label,
        minVolume24hUsd: 50_000_000,
        minLastPrice: 0.05,
        maxSpreadBps: 15,
        maxFundingRatePct: 0.02,
        minFundingRatePct: -0.01,
        minOpenInterestUsd: 20_000_000,
        minLsr: 0.5,
        maxLsr: 1.5,
        minRvol: 2.0,
        minAtrPercent: 1.5,
        maxAtrPercent: 10.0,
        lookbackDays: 20,
    },
    aggressive: {
        label: UNIVERSE_FILTER_PRESET_META.aggressive.label,
        minVolume24hUsd: 10_000_000,
        minLastPrice: 0.01,
        maxSpreadBps: 25,
        maxFundingRatePct: 0.05,
        minFundingRatePct: -0.02,
        minOpenInterestUsd: 5_000_000,
        minLsr: 0.3,
        maxLsr: 2.0,
        minRvol: 1.5,
        minAtrPercent: 1.0,
        maxAtrPercent: 15.0,
        lookbackDays: 14,
    },
}

export function pipelineFiltersWithIds(
    defs: Array<Omit<PipelineFilter, 'id'>>,
    idPrefix = 'preset',
): PipelineFilter[] {
    const stamp = Date.now()
    return defs.map((f, idx) => ({
        ...f,
        id: `${idPrefix}-${f.type}-${idx}-${stamp}`,
    }))
}

export function moexTestingPipelineFromPreset(presetId: UniverseFilterPresetId): {
    mode: 'ALL' | 'ANY'
    filters: PipelineFilter[]
} {
    const preset = MOEX_TESTING_PIPELINE_FILTER_PRESETS[presetId]
    return {
        mode: preset.mode,
        filters: pipelineFiltersWithIds(preset.filters, presetId),
    }
}

export function cryptoUniverseFieldsFromPreset(presetId: UniverseFilterPresetId): CryptoUniverseFormFields {
    const p = CRYPTO_UNIVERSE_FILTER_PRESETS[presetId]
    return {
        cryptoMinVolume24hUsd: p.minVolume24hUsd,
        cryptoMinLastPrice: p.minLastPrice,
        cryptoMaxSpreadBps: p.maxSpreadBps,
        cryptoMaxFundingRatePct: p.maxFundingRatePct,
        cryptoMinFundingRatePct: p.minFundingRatePct,
        cryptoMinOpenInterestUsd: p.minOpenInterestUsd,
        cryptoMinLsr: p.minLsr,
        cryptoMaxLsr: p.maxLsr,
        cryptoMinRvol: p.minRvol,
        cryptoMinAtrPercent: p.minAtrPercent,
        cryptoMaxAtrPercent: p.maxAtrPercent,
        cryptoLookbackDays: p.lookbackDays,
        cryptoFundingLookbackHours: 8,
        cryptoRefreshEveryMinutes: 60,
    }
}
