import { parseFixedTickersInput } from '@/utils/universeMode'
import type { TestingFormState } from '@/pages/testing/refactored/types/forms'
import type {
    TestingCryptoSection,
    TestingFormSectionsView,
    TestingMoexSection,
    TestingRiskSection,
} from '@/pages/testing/refactored/types/formSections'
import { isCryptoMarket, isMoexMarket, showBrokerCommission } from '@/pages/testing/refactored/visibility'

function toRiskSection(form: TestingFormState): TestingRiskSection {
    const risk: TestingRiskSection = {
        stopLossPct: form.stopLossPct,
        takeProfitPct: form.takeProfitPct,
        maxPositionPct: form.maxPositionPct,
        maxPositionAmount: form.maxPositionRub,
        maxDailyLossPct: form.maxDailyLossPct,
        slippagePct: form.slippagePct,
        executionLatencySec: form.executionLatencySec,
        maxDrawdownPct: form.maxDrawdownPct,
    }
    if (showBrokerCommission(form.market)) {
        risk.brokerCommissionPct = form.brokerCommissionPct
    }
    return risk
}

function toMoexSection(form: TestingFormState): TestingMoexSection | undefined {
    if (!isMoexMarket(form.market)) return undefined
    return {
        tradingHoursStart: form.tradingHoursStart,
        tradingHoursEnd: form.tradingHoursEnd,
        weekdaysMask: form.allowedWeekdays,
        ndflPct: form.ndflPct,
        universeMode: form.universeMode,
        pipelineMode: form.pipelineMode,
        pipelineFilters: form.filters,
        fixedTickers: parseFixedTickersInput(form.fixedTickersText),
        universeRefreshMinutes: form.universeRefreshMinutes,
    }
}

function toCryptoSection(form: TestingFormState): TestingCryptoSection | undefined {
    if (!isCryptoMarket(form.market)) return undefined
    return {
        testnet: form.bybitTestnet,
        instrumentCategory: form.instrumentCategory,
        leverage: form.leverage,
        makerFeePct: form.makerFeePct,
        takerFeePct: form.takerFeePct,
        executionModel: form.backtestExecution,
        feeModel: form.backtestFeeModel,
        maintenanceMarginPct: form.maintenanceMarginPct,
        fundingMode: form.fundingMode,
        universeMode: form.cryptoUniverseMode,
        minVolume24hUsd: form.cryptoMinVolume24hUsd,
        minLastPrice: form.cryptoMinLastPrice,
        maxSpreadBps: form.cryptoMaxSpreadBps,
        maxFundingRatePct: form.cryptoMaxFundingRatePct,
        minFundingRatePct: form.cryptoMinFundingRatePct,
        minOpenInterestUsd: form.cryptoMinOpenInterestUsd,
        minLsr: form.cryptoMinLsr,
        maxLsr: form.cryptoMaxLsr,
        minRvol: form.cryptoMinRvol,
        minAtrPct: form.cryptoMinAtrPercent,
        maxAtrPct: form.cryptoMaxAtrPercent,
        lookbackDays: form.cryptoLookbackDays,
        fixedSymbols: parseFixedTickersInput(form.fixedTickersText),
    }
}

/** Flat storage → nested §8.1 view (read-only projection). */
export function toFormSectionsView(form: TestingFormState): TestingFormSectionsView {
    return {
        market: form.market,
        robotId: form.robotId,
        strategy: form.strategy,
        capital: form.capital,
        fromDate: form.fromDate || null,
        toDate: form.toDate || null,
        strategyParams: form.strategyParams,
        interval: form.interval,
        risk: toRiskSection(form),
        moex: toMoexSection(form),
        crypto: toCryptoSection(form),
        advanced: {
            pollValue: form.pollValue,
            pollUnit: form.pollUnit,
        },
    }
}
