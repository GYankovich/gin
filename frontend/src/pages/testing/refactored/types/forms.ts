import type { PipelineFilter } from '@/pages/testing/testingPipeline'
import type { CryptoUniverseMode, UniverseMode } from '@/utils/universeMode'
import {
    DEFAULT_EXECUTION_LATENCY_SEC,
    DEFAULT_MAX_DRAWDOWN_PCT,
    defaultSlippagePct,
    normalizeFundingMode,
    type FundingSimulationMode,
} from '@/pages/testing/executionRiskDefaults'
import type { CryptoUniverseFormFields } from '@/modules/robots/config/cryptoUniverseDefaults'

export type TestingMarket = 'moex' | 'crypto'

/**
 * Unified flat form state for refactored testing UI.
 *
 * Field groups (§7.2):
 * - Group 1 (always): market, robotId, strategy, capital, dates, strategyParams, risk (except commission),
 *   pollValue, pollUnit
 * - Group 2 (MOEX): tradingHours*, allowedWeekdays, ndflPct, brokerCommissionPct, universeMode, filters, fixedTickersText
 * - Group 3 (Crypto): bybit*, fees, backtestExecution*, cryptoUniverse*, cryptoMin*
 *
 * Nested read-model: `toFormSectionsView()` in formStateViews.ts (§8.1).
 */
export type TestingFormState = {
    // === Group 1: base ===
    market: TestingMarket
    brokerType: string
    robotId: number | null
    fromDate: string
    toDate: string
    capital: number
    strategy: string
    strategyParams: Record<string, unknown>
    interval: string
    stopLossPct: number
    takeProfitPct: number
    maxPositionPct: number
    maxPositionRub: number
    /** Daily loss limit in percent (not currency). */
    maxDailyLossPct: number
    /** Slippage applied in backtest execution model, percent. */
    slippagePct: number
    /** Signal-to-fill delay in seconds (backtest execution model). */
    executionLatencySec: number
    /** Portfolio drawdown cap — stops backtest when breached, percent. */
    maxDrawdownPct: number
    pollValue: number
    pollUnit: 'minutes' | 'hours'
    // === Group 2: MOEX ===
    tradingHoursStart: string
    tradingHoursEnd: string
    allowedWeekdays: number
    brokerCommissionPct: number
    ndflPct: number
    pipelineMode: 'ALL' | 'ANY'
    filters: PipelineFilter[]
    universeMode: UniverseMode
    universeRefreshMinutes: number
    fixedTickersText: string
    // === Group 3: Crypto (universe + ByBit) ===
    cryptoUniverseMode: CryptoUniverseMode
} & CryptoUniverseFormFields & {
    bybitTestnet: boolean
    instrumentCategory: 'spot' | 'linear' | 'inverse'
    leverage: number
    makerFeePct: number
    takerFeePct: number
    fundingMode: FundingSimulationMode
    backtestExecution: 'limit_maker' | 'market_taker'
    backtestFeeModel: 'maker_taker' | 'taker_only' | 'maker_only'
    maintenanceMarginPct: number
}

export type ValidationIssue = {
    field: string
    message: string
    severity?: 'error' | 'warning'
}
