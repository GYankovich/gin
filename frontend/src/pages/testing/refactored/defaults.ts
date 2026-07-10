import { getStrategyParamsPreset } from '@/pages/testing/strategyPresets'
import { defaultIntervalForMarket } from '@/pages/testing/strategyIntervals'
import type { TestingFormState, TestingMarket } from '@/pages/testing/refactored/types/forms'
import {
    DEFAULT_EXECUTION_LATENCY_SEC,
    DEFAULT_MAX_DRAWDOWN_PCT,
    defaultSlippagePct,
} from '@/pages/testing/executionRiskDefaults'
import {
    cryptoUniverseFieldsFromPreset,
    moexTestingPipelineFromPreset,
} from '@/modules/robots/config/universeFilterPresets'

const DEFAULT_STRATEGY = 'grain_seed'

export function defaultCapitalForMarket(market: TestingMarket): number {
    return market === 'crypto' ? 10_000 : 1_000_000
}

export function createDefaultTestingFormState(market: TestingMarket = 'moex'): TestingFormState {
    const strategy = market === 'crypto' ? 'reversion_to_ma' : DEFAULT_STRATEGY
    const preset = getStrategyParamsPreset(strategy)
    const interval = defaultIntervalForMarket(market)
    return {
        market,
        brokerType: market === 'crypto' ? 'bybit' : 'tinvest',
        robotId: null,
        fromDate: '',
        toDate: '',
        capital: defaultCapitalForMarket(market),
        strategy,
        strategyParams: { ...preset, interval },
        interval,
        stopLossPct: 2,
        takeProfitPct: 3,
        maxPositionPct: 10,
        maxPositionRub: market === 'crypto' ? 0 : 50_000,
        maxDailyLossPct: 5,
        slippagePct: defaultSlippagePct(market),
        executionLatencySec: DEFAULT_EXECUTION_LATENCY_SEC,
        maxDrawdownPct: DEFAULT_MAX_DRAWDOWN_PCT,
        tradingHoursStart: market === 'crypto' ? '00:00' : '10:00',
        tradingHoursEnd: market === 'crypto' ? '23:59' : '18:45',
        allowedWeekdays: market === 'crypto' ? 127 : 31,
        brokerCommissionPct: market === 'crypto' ? 0 : 0.05,
        ndflPct: market === 'crypto' ? 0 : 15,
        pipelineMode: 'ALL',
        filters: market === 'crypto' ? [] : moexTestingPipelineFromPreset('moderate').filters,
        universeMode: 'dms_pipeline',
        universeRefreshMinutes: 0,
        fixedTickersText: market === 'crypto' ? '' : '',
        cryptoUniverseMode: 'auto',
        ...cryptoUniverseFieldsFromPreset('moderate'),
        bybitTestnet: false,
        instrumentCategory: 'linear',
        leverage: 1,
        makerFeePct: 0.01,
        takerFeePct: 0.06,
        fundingMode: 'historical',
        backtestExecution: 'market_taker',
        backtestFeeModel: 'maker_taker',
        maintenanceMarginPct: 0.5,
        pollValue: 5,
        pollUnit: 'minutes',
    }
}
