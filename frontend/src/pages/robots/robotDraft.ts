import type { BybitAccountType } from '@/modules/robots/config/builders/buildPortfolioConfig'
import type { CryptoScreeningFilterType } from '@/pages/testing/cryptoScreeningPipeline'
import type { FundingSimulationMode } from '@/pages/testing/executionRiskDefaults'
import type { TradingRobotStrategyDraft } from '@/pages/robots/useTradingRobotStrategyForm'
import type { CryptoUniverseMode } from '@/utils/universeMode'
import type { PipelineFilterType } from '@/pages/robots/pipelineFilterMeta'

export type DraftSnapshot = {
    name: string
    tokenId: number
    robotType: 1 | 2
    pollValue: number
    pollUnit: 'minutes' | 'hours'
    brokerCommissionRate: number
    ndflRate: number
    hoursFrom: string
    hoursTo: string
    weekdaysMask: number
    pipelineMode: 'ALL' | 'ANY'
    universeMode: 'fixed' | 'dms_pipeline' | 'tqbr_scan'
    fixedTickersText: string
    historicalEnabled: boolean
    historicalInterval: string
    historicalLookbackDays: number
    historicalDailyAtMsk: string
    paperRefreshMinutes: number
    strategy: TradingRobotStrategyDraft
    bybitTestnet: boolean
    instrumentCategory: 'spot' | 'linear' | 'inverse'
    leverage: number
    makerFeePct: number
    takerFeePct: number
    fundingMode: FundingSimulationMode
    backtestExecution: 'limit_maker' | 'market_taker'
    backtestFeeModel: 'maker_taker' | 'taker_only' | 'maker_only'
    maintenanceMarginPct: number
    cryptoUniverseMode: CryptoUniverseMode
    cryptoFilters: Array<{ type: CryptoScreeningFilterType; value: number }>
    portfolioBrokerType: string
    portfolioBybitTestnet: boolean
    portfolioBybitAccountType: BybitAccountType
    /** Из config.execution_model / risk — не константы UI. */
    slippagePct: number
    executionLatencySec: number
    maxDrawdownPct: number
    filters: Array<{
        type: PipelineFilterType
        min?: number
        max_percent?: number
        min_percent?: number
        period?: number
        eq?: string
        direction?: 'BOTH' | 'UP_ONLY' | 'DOWN_ONLY'
        max_steps?: number
        min_ratio?: number
        list?: string[] | null
    }>
}

export type PortfolioDirtySnapshot = Pick<
    DraftSnapshot,
    | 'name'
    | 'tokenId'
    | 'robotType'
    | 'pollValue'
    | 'pollUnit'
    | 'hoursFrom'
    | 'hoursTo'
    | 'weekdaysMask'
    | 'portfolioBrokerType'
    | 'portfolioBybitTestnet'
    | 'portfolioBybitAccountType'
>

export function dirtySnapshotFromDraft(draft: DraftSnapshot): DraftSnapshot | PortfolioDirtySnapshot {
    if (draft.robotType === 1) {
        return {
            name: draft.name,
            tokenId: draft.tokenId,
            robotType: draft.robotType,
            pollValue: draft.pollValue,
            pollUnit: draft.pollUnit,
            hoursFrom: draft.hoursFrom,
            hoursTo: draft.hoursTo,
            weekdaysMask: draft.weekdaysMask,
            portfolioBrokerType: draft.portfolioBrokerType,
            portfolioBybitTestnet: draft.portfolioBybitTestnet,
            portfolioBybitAccountType: draft.portfolioBybitAccountType,
        }
    }
    return draft
}

export function serializeDirtySnapshot(draft: DraftSnapshot | PortfolioDirtySnapshot): string {
    return JSON.stringify(draft)
}
