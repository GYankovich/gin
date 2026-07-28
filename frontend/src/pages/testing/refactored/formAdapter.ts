import { isCryptoBroker } from '@/modules/robots/config/builders/buildCryptoConfig'
import type { CryptoUniverseFormFields } from '@/modules/robots/config/cryptoUniverseDefaults'
import type { TestingFormState } from '@/pages/testing/refactored/types/forms'
import type { FundingSimulationMode } from '@/pages/testing/executionRiskDefaults'
import type { PipelineFilter } from '@/pages/testing/testingPipeline'
import type { CryptoUniverseMode, UniverseMode } from '@/utils/universeMode'

/** Maps legacy `useTestingRobotForm` fields → unified `TestingFormState` (T1 bridge). */
export function legacyFormToTestingFormState(input: {
    robotId: number | null
    brokerType: string
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
    maxDailyLoss: number
    slippagePct: number
    executionLatencySec: number
    maxDrawdownPct: number
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
    pollValue: number
    pollUnit: 'minutes' | 'hours'
}): TestingFormState {
    return {
        market: isCryptoBroker(input.brokerType) ? 'crypto' : 'moex',
        brokerType: input.brokerType,
        robotId: input.robotId,
        fromDate: input.fromDate,
        toDate: input.toDate,
        capital: input.capital,
        strategy: input.strategy,
        strategyParams: input.strategyParams,
        interval: input.interval,
        stopLossPct: input.stopLossPct,
        takeProfitPct: input.takeProfitPct,
        maxPositionPct: input.maxPositionPct,
        maxPositionRub: input.maxPositionRub,
        maxDailyLossPct: input.maxDailyLoss,
        slippagePct: input.slippagePct,
        executionLatencySec: input.executionLatencySec,
        maxDrawdownPct: input.maxDrawdownPct,
        tradingHoursStart: input.tradingHoursStart,
        tradingHoursEnd: input.tradingHoursEnd,
        allowedWeekdays: input.allowedWeekdays,
        brokerCommissionPct: input.brokerCommissionPct,
        ndflPct: input.ndflPct,
        pipelineMode: input.pipelineMode,
        filters: input.filters,
        universeMode: input.universeMode,
        universeRefreshMinutes: input.universeRefreshMinutes,
        fixedTickersText: input.fixedTickersText,
        cryptoUniverseMode: input.cryptoUniverseMode,
        cryptoMinVolume24hUsd: input.cryptoMinVolume24hUsd,
        cryptoMinLastPrice: input.cryptoMinLastPrice,
        cryptoMaxSpreadBps: input.cryptoMaxSpreadBps,
        cryptoMaxFundingRatePct: input.cryptoMaxFundingRatePct,
        cryptoMinFundingRatePct: input.cryptoMinFundingRatePct,
        cryptoMinOpenInterestUsd: input.cryptoMinOpenInterestUsd,
        cryptoMinLsr: input.cryptoMinLsr,
        cryptoMaxLsr: input.cryptoMaxLsr,
        cryptoMinRvol: input.cryptoMinRvol,
        cryptoMinAtrPercent: input.cryptoMinAtrPercent,
        cryptoMaxAtrPercent: input.cryptoMaxAtrPercent,
        cryptoLookbackDays: input.cryptoLookbackDays,
        cryptoFundingLookbackHours: input.cryptoFundingLookbackHours,
        cryptoRefreshEveryMinutes: input.cryptoRefreshEveryMinutes,
        bybitTestnet: input.bybitTestnet,
        instrumentCategory: input.instrumentCategory,
        leverage: input.leverage,
        makerFeePct: input.makerFeePct,
        takerFeePct: input.takerFeePct,
        fundingMode: input.fundingMode,
        backtestExecution: input.backtestExecution,
        backtestFeeModel: input.backtestFeeModel,
        maintenanceMarginPct: input.maintenanceMarginPct,
        pollValue: input.pollValue,
        pollUnit: input.pollUnit,
    }
}
