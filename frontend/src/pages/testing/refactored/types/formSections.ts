import type { PipelineFilter } from '@/pages/testing/testingPipeline'
import type { CryptoUniverseMode, UniverseMode } from '@/utils/universeMode'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'

/** §8.1 — risk block (Group 1; brokerCommission only MOEX). */
export type TestingRiskSection = {
    stopLossPct: number
    takeProfitPct: number
    maxPositionPct: number
    maxPositionAmount: number
    maxDailyLossPct: number
    slippagePct?: number
    executionLatencySec?: number
    maxDrawdownPct?: number
    brokerCommissionPct?: number
}

/** §8.1 — MOEX-only fields (Group 2). */
export type TestingMoexSection = {
    tradingHoursStart: string
    tradingHoursEnd: string
    weekdaysMask: number
    ndflPct: number
    universeMode: UniverseMode
    pipelineMode: 'ALL' | 'ANY'
    pipelineFilters: PipelineFilter[]
    fixedTickers: string[]
    universeRefreshMinutes: number
}

/** §8.1 — Crypto-only fields (Group 3). */
export type TestingCryptoSection = {
    testnet: boolean
    instrumentCategory: 'linear' | 'inverse' | 'spot'
    leverage: number
    makerFeePct: number
    takerFeePct: number
    executionModel: 'limit_maker' | 'market_taker'
    feeModel: 'maker_taker' | 'taker_only' | 'maker_only'
    maintenanceMarginPct: number
    fundingMode: 'off' | 'historical' | 'forecast' | 'average'
    universeMode: CryptoUniverseMode
    minVolume24hUsd: number
    minLastPrice: number
    maxSpreadBps: number
    maxFundingRatePct: number
    minFundingRatePct: number
    minOpenInterestUsd: number
    minLsr: number
    maxLsr: number
    minRvol: number
    minAtrPct: number
    maxAtrPct: number
    lookbackDays: number
    fixedSymbols: string[]
}

/** §8.1 — advanced block (Group 1; market-independent). */
export type TestingAdvancedSection = {
    pollValue: number
    pollUnit: 'minutes' | 'hours'
}

/** Nested read-model over flat `TestingFormState` (§8.1 STATE MAP). */
export type TestingFormSectionsView = {
    market: TestingMarket
    robotId: number | null
    strategy: string
    capital: number
    fromDate: string | null
    toDate: string | null
    strategyParams: Record<string, unknown>
    interval: string
    risk: TestingRiskSection
    moex?: TestingMoexSection
    crypto?: TestingCryptoSection
    advanced: TestingAdvancedSection
}
