import { useCallback, useMemo } from 'react'
import { useToast } from '@/components/ui/Toast'
import type { RecommendationItem } from '@/types/recommendations'
import {
    applyRecommendationItem,
    countApplicableChanges,
    type RecommendationFormActions,
} from '@/pages/testing/recommendationApply'
import type { useTestingRobotForm } from '@/pages/testing/hooks/useTestingRobotForm'
import { useDismissedRecommendations } from '@/pages/testing/hooks/useDismissedRecommendations'

type TestingForm = ReturnType<typeof useTestingRobotForm>

export function buildFormActions(form: TestingForm): RecommendationFormActions {
    return {
        setStopLossPct: form.setStopLossPct,
        setTakeProfitPct: form.setTakeProfitPct,
        setMaxPositionPct: form.setMaxPositionPct,
        setMaxDailyLoss: form.setMaxDailyLoss,
        setSlippagePct: form.setSlippagePct,
        setTradingHoursStart: form.setTradingHoursStart,
        setTradingHoursEnd: form.setTradingHoursEnd,
        setAllowedWeekdays: form.setAllowedWeekdays,
        setStrategyParam: form.setStrategyParam,
        setInterval: form.setInterval,
        setFundingMode: form.setFundingMode,
        setBacktestExecution: form.setBacktestExecution,
        setBacktestFeeModel: form.setBacktestFeeModel,
        setLeverage: form.setLeverage,
        setInstrumentCategory: form.setInstrumentCategory,
        cryptoFilters: form.cryptoFilters,
        setCryptoFilters: form.setCryptoFilters,
    }
}

export function useRecommendationActions(form: TestingForm) {
    const toast = useToast()
    const { dismissedIds, dismiss, clearAll, isDismissed, dismissedCount } = useDismissedRecommendations(
        form.robotId,
    )

    const filterVisible = useCallback(
        (items: RecommendationItem[] | undefined | null): RecommendationItem[] => {
            if (!items?.length) return []
            return items.filter(item => !isDismissed(item.id))
        },
        [isDismissed],
    )

    const applyItem = useCallback(
        (item: RecommendationItem) => {
            const applicable = countApplicableChanges(item)
            if (applicable === 0) {
                toast.show('Нет полей для автоприменения — см. текст рекомендации', 'info', 3000)
                return
            }
            const result = applyRecommendationItem(item, buildFormActions(form))
            if (result.applied > 0) {
                form.setConfigDirty(true)
                toast.show(`Применено изменений: ${result.applied}`, 'success', 2500)
                dismiss(item.id)
            }
            if (result.skipped.length > 0 && result.applied === 0) {
                toast.show('Изменения требуют ручной настройки в форме', 'info', 3500)
            } else if (result.skipped.length > 0) {
                toast.show(`Часть полей пропущена (${result.skipped.length}) — настройте вручную`, 'info', 3500)
            }
        },
        [dismiss, form, toast],
    )

    const canApply = useCallback((item: RecommendationItem) => countApplicableChanges(item) > 0, [])

    const meta = useMemo(
        () => ({ dismissedCount, hasDismissed: dismissedCount > 0 }),
        [dismissedCount],
    )

    return {
        filterVisible,
        applyItem,
        dismiss,
        clearDismissed: clearAll,
        canApply,
        dismissedIds,
        ...meta,
    }
}
