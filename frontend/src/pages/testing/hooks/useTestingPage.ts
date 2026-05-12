import { useToast } from '@/components/ui/Toast'
import { useMoexCandleJobState } from '@/pages/testing/hooks/useMoexCandleJobState'
import { useTestingBacktest } from '@/pages/testing/hooks/useTestingBacktest'
import { useTestingRobotForm } from '@/pages/testing/hooks/useTestingRobotForm'

/** Собирает форму робота, MOEX job state и сценарий history-backtest для страницы «Тестирование». */
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
        interval: form.interval,
        stopLossPct: form.stopLossPct,
        takeProfitPct: form.takeProfitPct,
        maxPositionPct: form.maxPositionPct,
        maxPositionRub: form.maxPositionRub,
        brokerCommissionPct: form.brokerCommissionPct,
        ndflPct: form.ndflPct,
        brokerType: form.brokerType,
        pollValue: form.pollValue,
        pollUnit: form.pollUnit,
        pipelineMode: form.pipelineMode,
    })

    const moexJob = useMoexCandleJobState({
        fromDate: form.fromDate,
        toDate: form.toDate,
        signalInterval: form.interval,
        selectedRobot: form.selectedRobot,
        pipelinePayload: backtest.pipelinePayload,
        pipelineMode: form.pipelineMode,
        toast,
    })

    return { form, backtest, moexJob }
}

export type TestingPageController = ReturnType<typeof useTestingPage>
