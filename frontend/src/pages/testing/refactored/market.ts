import type { Robot } from '@/types/robot'
import { isCryptoBroker } from '@/modules/robots/config/builders/buildCryptoConfig'
import { deriveMarketProfile } from '@/modules/robots/config/resolveProfile'
import type { PipelineFilter } from '@/pages/testing/testingPipeline'
import { createDefaultTestingFormState } from '@/pages/testing/refactored/defaults'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'
import { createDefaultCryptoScreeningFilters, type CryptoScreeningFilter } from '@/pages/testing/cryptoScreeningPipeline'
import type { FundingSimulationMode } from '@/pages/testing/executionRiskDefaults'
import type { CryptoUniverseMode, UniverseMode } from '@/utils/universeMode'

export type { TestingMarket }

export const TESTING_MARKET_OPTIONS: Array<{
    value: TestingMarket
    label: string
    description: string
    currency: '₽' | 'USDT'
}> = [
    {
        value: 'moex',
        label: 'MOEX',
        description: 'Акции РФ, T-Invest / Sandbox',
        currency: '₽',
    },
    {
        value: 'crypto',
        label: 'Crypto',
        description: 'ByBit spot / linear',
        currency: 'USDT',
    },
]

export function marketFromBroker(brokerType: string): TestingMarket {
    return isCryptoBroker(brokerType) ? 'crypto' : 'moex'
}

export function brokerForMarket(market: TestingMarket): string {
    return market === 'crypto' ? 'bybit' : 'tinvest'
}

export function currencyForMarket(market: TestingMarket): '₽' | 'USDT' {
    return market === 'crypto' ? 'USDT' : '₽'
}

const CRYPTO_EXCLUDED_STRATEGIES = new Set(['momentum_breakout'])

export function strategyOptionsForMarket(
    options: Array<{ value: string; label: string }>,
    market: TestingMarket,
): Array<{ value: string; label: string }> {
    if (market === 'crypto') {
        return options.filter(o => !CRYPTO_EXCLUDED_STRATEGIES.has(o.value))
    }
    return options
}

export function robotMatchesMarket(robot: Robot, market: TestingMarket): boolean {
    const profile = deriveMarketProfile(robot)
    return market === 'crypto' ? profile === 'crypto' : profile === 'moex'
}

export type TestingMarketPresetSetters = {
    setBrokerType: (v: string) => void
    setCapital: (v: number) => void
    setStrategy: (v: string) => void
    setStrategyParams: (v: Record<string, unknown>) => void
    setIntervalState: (v: string) => void
    setStopLossPct: (v: number) => void
    setTakeProfitPct: (v: number) => void
    setMaxPositionPct: (v: number) => void
    setMaxPositionRub: (v: number) => void
    setMaxDailyLoss: (v: number) => void
    setTradingHoursStart: (v: string) => void
    setTradingHoursEnd: (v: string) => void
    setAllowedWeekdays: (v: number) => void
    setBrokerCommissionPct: (v: number) => void
    setNdflPct: (v: number) => void
    setPipelineMode: (v: 'ALL' | 'ANY') => void
    setFilters: (v: PipelineFilter[]) => void
    setUniverseMode: (v: UniverseMode) => void
    setUniverseRefreshMinutes: (v: number) => void
    setFixedTickersText: (v: string) => void
    setCryptoUniverseMode: (v: CryptoUniverseMode) => void
    setCryptoFilters: (v: CryptoScreeningFilter[]) => void
    setBybitTestnet: (v: boolean) => void
    setInstrumentCategory: (v: 'spot' | 'linear' | 'inverse') => void
    setLeverage: (v: number) => void
    setMakerFeePct: (v: number) => void
    setTakerFeePct: (v: number) => void
    setFundingMode: (v: FundingSimulationMode) => void
    setSlippagePct: (v: number) => void
    setExecutionLatencySec: (v: number) => void
    setMaxDrawdownPct: (v: number) => void
    setBacktestExecution: (v: 'limit_maker' | 'market_taker') => void
    setBacktestFeeModel: (v: 'maker_taker' | 'taker_only' | 'maker_only') => void
    setMaintenanceMarginPct: (v: number) => void
}

/** Apply market-specific defaults (T2.1); dates are preserved by caller. */
export function applyTestingMarketPresets(market: TestingMarket, setters: TestingMarketPresetSetters): void {
    const d = createDefaultTestingFormState(market)
    setters.setBrokerType(d.brokerType)
    setters.setCapital(d.capital)
    setters.setStrategy(d.strategy)
    setters.setStrategyParams(d.strategyParams)
    setters.setIntervalState(d.interval)
    setters.setStopLossPct(d.stopLossPct)
    setters.setTakeProfitPct(d.takeProfitPct)
    setters.setMaxPositionPct(d.maxPositionPct)
    setters.setMaxPositionRub(d.maxPositionRub)
    setters.setMaxDailyLoss(d.maxDailyLossPct)
    setters.setTradingHoursStart(d.tradingHoursStart)
    setters.setTradingHoursEnd(d.tradingHoursEnd)
    setters.setAllowedWeekdays(d.allowedWeekdays)
    setters.setBrokerCommissionPct(d.brokerCommissionPct)
    setters.setNdflPct(d.ndflPct)
    setters.setPipelineMode(d.pipelineMode)
    setters.setFilters(d.filters)
    setters.setUniverseMode(d.universeMode)
    setters.setUniverseRefreshMinutes(d.universeRefreshMinutes)
    setters.setFixedTickersText(d.fixedTickersText)
    setters.setCryptoUniverseMode(d.cryptoUniverseMode)
    setters.setCryptoFilters(createDefaultCryptoScreeningFilters())
    setters.setBybitTestnet(d.bybitTestnet)
    setters.setInstrumentCategory(d.instrumentCategory)
    setters.setLeverage(d.leverage)
    setters.setMakerFeePct(d.makerFeePct)
    setters.setTakerFeePct(d.takerFeePct)
    setters.setFundingMode(d.fundingMode)
    setters.setSlippagePct(d.slippagePct)
    setters.setExecutionLatencySec(d.executionLatencySec)
    setters.setMaxDrawdownPct(d.maxDrawdownPct)
    setters.setBacktestExecution(d.backtestExecution)
    setters.setBacktestFeeModel(d.backtestFeeModel)
    setters.setMaintenanceMarginPct(d.maintenanceMarginPct)
}
