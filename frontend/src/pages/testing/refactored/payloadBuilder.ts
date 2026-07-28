import {
    buildTradingRobotConfig,
    buildTradingRobotSchedulePatch,
    type TradingRobotFormSnapshot,
} from '@/pages/testing/buildTradingRobotConfig'
import { parseFixedTickersInput } from '@/utils/universeMode'
import { toApiDate } from '@/pages/testing/testingUtils'
import type { TestingFormState } from '@/pages/testing/refactored/types/forms'
import type { BuildBacktestRequestInput, UnifiedHistoryBacktestRequest } from '@/pages/testing/refactored/types/requests'

export function formStateToSnapshot(
    form: TestingFormState,
    extra?: Pick<TradingRobotFormSnapshot, 'mergeStrategyParamsFrom' | 'preserveAllowedFigis'>,
): TradingRobotFormSnapshot {
    return {
        strategy: form.strategy,
        strategyParams: form.strategyParams,
        interval: form.interval,
        capital: form.capital,
        brokerType: form.brokerType,
        stopLossPct: form.stopLossPct,
        takeProfitPct: form.takeProfitPct,
        maxPositionPct: form.maxPositionPct,
        maxPositionRub: form.maxPositionRub,
        maxDailyLoss: form.maxDailyLossPct,
        slippagePct: form.slippagePct,
        executionLatencySec: form.executionLatencySec,
        maxDrawdownPct: form.maxDrawdownPct,
        tradingHoursStart: form.tradingHoursStart,
        tradingHoursEnd: form.tradingHoursEnd,
        allowedWeekdays: form.allowedWeekdays,
        brokerCommissionPct: form.brokerCommissionPct,
        ndflPct: form.ndflPct,
        pipelineMode: form.pipelineMode,
        filters: form.filters,
        universeMode: form.universeMode,
        fixedTickers: parseFixedTickersInput(form.fixedTickersText),
        universeRefreshMinutes: form.universeRefreshMinutes,
        cryptoUniverseMode: form.cryptoUniverseMode,
        cryptoMinVolume24hUsd: form.cryptoMinVolume24hUsd,
        cryptoMinLastPrice: form.cryptoMinLastPrice,
        cryptoMaxSpreadBps: form.cryptoMaxSpreadBps,
        cryptoMaxFundingRatePct: form.cryptoMaxFundingRatePct,
        cryptoMinFundingRatePct: form.cryptoMinFundingRatePct,
        cryptoMinOpenInterestUsd: form.cryptoMinOpenInterestUsd,
        cryptoMinLsr: form.cryptoMinLsr,
        cryptoMaxLsr: form.cryptoMaxLsr,
        cryptoMinRvol: form.cryptoMinRvol,
        cryptoMinAtrPercent: form.cryptoMinAtrPercent,
        cryptoMaxAtrPercent: form.cryptoMaxAtrPercent,
        cryptoLookbackDays: form.cryptoLookbackDays,
        bybitTestnet: form.bybitTestnet,
        instrumentCategory: form.instrumentCategory,
        leverage: form.brokerType === 'bybit' ? 1 : form.leverage,
        makerFeePct: form.makerFeePct,
        takerFeePct: form.takerFeePct,
        fundingMode: form.fundingMode,
        backtestExecution: form.backtestExecution,
        backtestFeeModel: form.backtestFeeModel,
        maintenanceMarginPct: form.maintenanceMarginPct,
        mergeStrategyParamsFrom: extra?.mergeStrategyParamsFrom,
        preserveAllowedFigis: extra?.preserveAllowedFigis,
    }
}

export function buildBacktestConfigFromForm(
    form: TestingFormState,
    extra?: Pick<TradingRobotFormSnapshot, 'mergeStrategyParamsFrom' | 'preserveAllowedFigis'>,
): Record<string, unknown> {
    return buildTradingRobotConfig(formStateToSnapshot(form, extra))
}

/**
 * Builds POST /robots/history-backtest payload.
 * Config assembly follows §8.3: common fields + MOEX section (costs, universe, pipeline) or
 * Crypto section (bybit, costs, crypto_universe) via `buildTradingRobotConfig`.
 */
export function buildHistoryBacktestRequest(input: BuildBacktestRequestInput): UnifiedHistoryBacktestRequest {
    const { form, selectedRobotId, selectedRobotType, tokenId, mergeStrategyParamsFrom } = input
    const fromClamped = form.fromDate
    const toClamped = form.toDate
    const config = buildBacktestConfigFromForm(form, { mergeStrategyParamsFrom })
    const schedule = buildTradingRobotSchedulePatch({
        ...formStateToSnapshot(form),
        pollValue: form.pollValue,
        pollUnit: form.pollUnit,
    })

    if (selectedRobotId != null) {
        return {
            robot_id: selectedRobotId,
            from_date: `${toApiDate(fromClamped)}T00:00:00Z`,
            to_date: `${toApiDate(toClamped)}T23:59:59Z`,
            initial_capital: form.capital,
            token_id: tokenId ?? undefined,
            type: selectedRobotType ?? 2,
            async_execution: true,
            config,
            ...schedule,
        }
    }

    return {
        robot_id: null,
        strategy: form.strategy,
        from_date: `${toApiDate(fromClamped)}T00:00:00Z`,
        to_date: `${toApiDate(toClamped)}T23:59:59Z`,
        initial_capital: form.capital,
        async_execution: true,
        config,
        ...schedule,
    }
}
