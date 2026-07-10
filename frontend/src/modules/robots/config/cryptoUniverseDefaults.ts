/** Shared defaults for ByBit crypto universe screening (BRD v1.0). */

import {
    CRYPTO_UNIVERSE_FILTER_PRESETS,
    type UniverseFilterPresetId,
} from '@/modules/robots/config/universeFilterPresets'

export const CRYPTO_UNIVERSE_DEFAULTS = {
    minVolume24hUsd: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minVolume24hUsd,
    minLastPrice: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minLastPrice,
    maxSpreadBps: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.maxSpreadBps,
    maxFundingRatePct: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.maxFundingRatePct,
    minFundingRatePct: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minFundingRatePct,
    minOpenInterestUsd: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minOpenInterestUsd,
    minLsr: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minLsr,
    maxLsr: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.maxLsr,
    minRvol: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minRvol,
    minAtrPercent: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.minAtrPercent,
    maxAtrPercent: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.maxAtrPercent,
    lookbackDays: CRYPTO_UNIVERSE_FILTER_PRESETS.moderate.lookbackDays,
} as const

export type CryptoUniversePresetId = UniverseFilterPresetId

/** @deprecated Импортируйте CRYPTO_UNIVERSE_FILTER_PRESETS из universeFilterPresets */
export const CRYPTO_UNIVERSE_PRESETS = CRYPTO_UNIVERSE_FILTER_PRESETS

export type CryptoUniverseFormFields = {
    cryptoMinVolume24hUsd: number
    cryptoMinLastPrice: number
    cryptoMaxSpreadBps: number
    cryptoMaxFundingRatePct: number
    cryptoMinFundingRatePct: number
    cryptoMinOpenInterestUsd: number
    cryptoMinLsr: number
    cryptoMaxLsr: number
    cryptoMinRvol: number
    cryptoMinAtrPercent: number
    cryptoMaxAtrPercent: number
    cryptoLookbackDays: number
    cryptoFundingLookbackHours: number
    cryptoRefreshEveryMinutes: number
}

export function defaultCryptoUniverseFormFields(): CryptoUniverseFormFields {
    const d = CRYPTO_UNIVERSE_DEFAULTS
    return {
        cryptoMinVolume24hUsd: d.minVolume24hUsd,
        cryptoMinLastPrice: d.minLastPrice,
        cryptoMaxSpreadBps: d.maxSpreadBps,
        cryptoMaxFundingRatePct: d.maxFundingRatePct,
        cryptoMinFundingRatePct: d.minFundingRatePct,
        cryptoMinOpenInterestUsd: d.minOpenInterestUsd,
        cryptoMinLsr: d.minLsr,
        cryptoMaxLsr: d.maxLsr,
        cryptoMinRvol: d.minRvol,
        cryptoMinAtrPercent: d.minAtrPercent,
        cryptoMaxAtrPercent: d.maxAtrPercent,
        cryptoLookbackDays: d.lookbackDays,
        cryptoFundingLookbackHours: 8,
        cryptoRefreshEveryMinutes: 60,
    }
}
