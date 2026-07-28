import { useEffect, useMemo } from 'react'
import { useToast } from '@/components/ui/Toast'
import { useMoexCandleJobState } from '@/pages/testing/hooks/useMoexCandleJobState'
import { useTestingBacktest } from '@/pages/testing/hooks/useTestingBacktest'
import { useTestingCreateRobot } from '@/pages/testing/hooks/useTestingCreateRobot'
import { useTestingRobotForm } from '@/pages/testing/hooks/useTestingRobotForm'
import { useTestingRecommendations } from '@/pages/testing/hooks/useTestingRecommendations'
import { useTestingOptimization } from '@/pages/testing/hooks/useTestingOptimization'
import { useTestingUniverse } from '@/pages/testing/hooks/useTestingUniverse'
import { parseFixedTickersInput } from '@/utils/universeMode'

/** @deprecated T6 — use `useTestingRefactoredPage` (config / runner / results). Legacy: `VITE_TESTING_LEGACY=true`. */
export function useTestingPage() {
    const toast = useToast()
    const form = useTestingRobotForm()

    const backtest = useTestingBacktest({
        selectedRobot: form.selectedRobot,
        filters: form.filters,
        fromDate: form.fromDate,
        toDate: form.toDate,
        setFromDate: form.setFromDate,
        setToDate: form.setToDate,
        setInvalid: form.setInvalid,
        configDirty: form.configDirty,
        setConfigDirty: form.setConfigDirty,
        setRobots: form.setRobots,
        toast,
        capital: form.capital,
        strategy: form.strategy,
        strategyParams: form.strategyParams,
        interval: form.interval,
        stopLossPct: form.stopLossPct,
        takeProfitPct: form.takeProfitPct,
        maxPositionPct: form.maxPositionPct,
        maxPositionRub: form.maxPositionRub,
        maxDailyLoss: form.maxDailyLoss,
        slippagePct: form.slippagePct,
        executionLatencySec: form.executionLatencySec,
        maxDrawdownPct: form.maxDrawdownPct,
        tradingHoursStart: form.tradingHoursStart,
        tradingHoursEnd: form.tradingHoursEnd,
        allowedWeekdays: form.allowedWeekdays,
        brokerCommissionPct: form.brokerCommissionPct,
        ndflPct: form.ndflPct,
        brokerType: form.brokerType,
        bybitTestnet: form.bybitTestnet,
        instrumentCategory: form.instrumentCategory,
        leverage: form.leverage,
        makerFeePct: form.makerFeePct,
        takerFeePct: form.takerFeePct,
        fundingMode: form.fundingMode,
        pollValue: form.pollValue,
        pollUnit: form.pollUnit,
        pipelineMode: form.pipelineMode,
        universeRefreshMinutes: form.universeRefreshMinutes,
        universeMode: form.universeMode,
        fixedTickersText: form.fixedTickersText,
        cryptoUniverseMode: form.cryptoUniverseMode,
        ...({
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
        }),
    })

    const tradingFormSnapshot = useMemo(
        () => ({
            strategy: form.strategy,
            strategyParams: form.strategyParams,
            interval: form.interval,
            capital: form.capital,
            brokerType: form.brokerType,
            stopLossPct: form.stopLossPct,
            takeProfitPct: form.takeProfitPct,
            maxPositionPct: form.maxPositionPct,
            maxPositionRub: form.maxPositionRub,
            maxDailyLoss: form.maxDailyLoss,
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
            universeRefreshMinutes: form.universeRefreshMinutes,
            universeMode: form.universeMode,
            fixedTickers: parseFixedTickersInput(form.fixedTickersText),
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
            leverage: form.leverage,
            makerFeePct: form.makerFeePct,
            takerFeePct: form.takerFeePct,
            fundingMode: form.fundingMode,
            pollValue: form.pollValue,
            pollUnit: form.pollUnit,
            mergeStrategyParamsFrom: undefined as Record<string, unknown> | undefined,
        }),
        [
            form.strategy,
            form.strategyParams,
            form.interval,
            form.capital,
            form.brokerType,
            form.stopLossPct,
            form.takeProfitPct,
            form.maxPositionPct,
            form.maxPositionRub,
            form.maxDailyLoss,
            form.slippagePct,
            form.executionLatencySec,
            form.maxDrawdownPct,
            form.tradingHoursStart,
            form.tradingHoursEnd,
            form.allowedWeekdays,
            form.brokerCommissionPct,
            form.ndflPct,
            form.pipelineMode,
            form.filters,
            form.universeRefreshMinutes,
            form.universeMode,
            form.fixedTickersText,
            form.cryptoUniverseMode,
            form.cryptoMinVolume24hUsd,
            form.cryptoMinLastPrice,
            form.cryptoMaxSpreadBps,
            form.cryptoMaxFundingRatePct,
            form.cryptoMinFundingRatePct,
            form.cryptoMinOpenInterestUsd,
            form.cryptoMinLsr,
            form.cryptoMaxLsr,
            form.cryptoMinRvol,
            form.cryptoMinAtrPercent,
            form.cryptoMaxAtrPercent,
            form.cryptoLookbackDays,
            form.bybitTestnet,
            form.instrumentCategory,
            form.leverage,
            form.makerFeePct,
            form.takerFeePct,
            form.fundingMode,
            form.pollValue,
            form.pollUnit,
        ],
    )

    const universe = useTestingUniverse({
        selectedRobot: form.selectedRobot,
        toast,
        setRobots: form.setRobots,
    })

    const createRobot = useTestingCreateRobot(
        tradingFormSnapshot,
        form.setRobots,
        form.setRobotId,
        toast,
    )

    const recommendations = useTestingRecommendations(form.robotId)
    const optimization = useTestingOptimization(form.robotId)

    useEffect(() => {
        if (backtest.result) {
            void recommendations.refresh()
            void optimization.refreshRank()
        }
    }, [backtest.result, recommendations.refresh, optimization.refreshRank])

    const moexJob = useMoexCandleJobState({
        fromDate: form.fromDate,
        toDate: form.toDate,
        signalInterval: form.interval,
        selectedRobot: form.selectedRobot,
        pipelinePayload: backtest.pipelinePayload,
        pipelineMode: form.pipelineMode,
        toast,
    })

    return { form, backtest, moexJob, createRobot, recommendations, optimization, universe }
}

export type TestingPageController = ReturnType<typeof useTestingPage>
