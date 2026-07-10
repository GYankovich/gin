import { useCallback, useEffect, useRef, useState } from 'react'
import { optimizationService } from '@/services/optimizationService'
import type {
    OptimizationBatchStatusResponse,
    OptimizationFailedRunItem,
    OptimizationGoal,
    OptimizationMode,
    OptimizationPlanResponse,
    OptimizationRankResponse,
} from '@/types/optimization'
import { toApiDate } from '@/pages/testing/testingUtils'

export type OptimizationRunPeriod = {
    fromDate: string
    toDate: string
    initialCapital: number
}

export function useTestingOptimization(robotId: number | null) {
    const [goal, setGoal] = useState<OptimizationGoal>('balanced')
    const [rankData, setRankData] = useState<OptimizationRankResponse | null>(null)
    const [sessionFailures, setSessionFailures] = useState<OptimizationFailedRunItem[]>([])
    const [planData, setPlanData] = useState<OptimizationPlanResponse | null>(null)
    const [batchData, setBatchData] = useState<OptimizationBatchStatusResponse | null>(null)
    const [loadingRank, setLoadingRank] = useState(false)
    const [loadingPlan, setLoadingPlan] = useState(false)
    const [startingBatch, setStartingBatch] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

    const stopPolling = useCallback(() => {
        if (pollRef.current) {
            clearInterval(pollRef.current)
            pollRef.current = null
        }
    }, [])

    const refreshBatch = useCallback(
        async (batchId?: number) => {
            if (!robotId) {
                setBatchData(null)
                return null
            }
            try {
                const data = batchId
                    ? await optimizationService.getBatchStatus(robotId, batchId)
                    : await optimizationService.getActiveBatch(robotId)
                setBatchData(data)
                return data
            } catch (e) {
                setError(e instanceof Error ? e.message : 'Не удалось загрузить статус оптимизации')
                return null
            }
        },
        [robotId],
    )

    const startPolling = useCallback(
        (batchId: number) => {
            stopPolling()
            pollRef.current = setInterval(() => {
                void refreshBatch(batchId)
            }, 5000)
        },
        [refreshBatch, stopPolling],
    )

    const refreshSessionFailures = useCallback(async () => {
        setError(null)
        try {
            const data = await optimizationService.sessionFailures()
            setSessionFailures(data.failed_runs ?? [])
        } catch (e) {
            setSessionFailures([])
            setError(e instanceof Error ? e.message : 'Не удалось загрузить ошибки прогонов')
        }
    }, [])

    const refreshRank = useCallback(async () => {
        if (!robotId) {
            setRankData(null)
            await refreshSessionFailures()
            return
        }
        setLoadingRank(true)
        setError(null)
        try {
            const data = await optimizationService.rankBacktests(robotId, goal)
            setRankData(data)
            setSessionFailures([])
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Не удалось загрузить ранжирование')
            setRankData(null)
            await refreshSessionFailures()
        } finally {
            setLoadingRank(false)
        }
    }, [robotId, goal, refreshSessionFailures])

    const loadPlan = useCallback(
        async (mode: OptimizationMode = 'speed') => {
            if (!robotId) return
            setLoadingPlan(true)
            setError(null)
            try {
                const data = await optimizationService.planOptimization(robotId, goal, mode)
                setPlanData(data)
            } catch (e) {
                setError(e instanceof Error ? e.message : 'Не удалось построить план')
                setPlanData(null)
            } finally {
                setLoadingPlan(false)
            }
        },
        [robotId, goal],
    )

    const runBatch = useCallback(
        async (mode: OptimizationMode, period: OptimizationRunPeriod) => {
            if (!robotId) return null
            setStartingBatch(true)
            setError(null)
            try {
                const started = await optimizationService.runOptimizationBatch(robotId, {
                    goal,
                    mode,
                    from_date: `${toApiDate(period.fromDate)}T00:00:00Z`,
                    to_date: `${toApiDate(period.toDate)}T23:59:59Z`,
                    initial_capital: period.initialCapital,
                })
                const status = await optimizationService.getBatchStatus(robotId, started.batch_id)
                setBatchData(status)
                startPolling(started.batch_id)
                return started
            } catch (e) {
                setError(e instanceof Error ? e.message : 'Не удалось запустить сетку')
                return null
            } finally {
                setStartingBatch(false)
            }
        },
        [goal, robotId, startPolling],
    )

    const cancelBatch = useCallback(async () => {
        if (!robotId || !batchData?.batch_id) return
        setError(null)
        try {
            await optimizationService.cancelBatch(robotId, batchData.batch_id)
            await refreshBatch(batchData.batch_id)
            stopPolling()
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Не удалось отменить оптимизацию')
        }
    }, [batchData?.batch_id, refreshBatch, robotId, stopPolling])

    useEffect(() => {
        void refreshRank()
    }, [refreshRank])

    useEffect(() => {
        if (!robotId) {
            setBatchData(null)
            stopPolling()
            return
        }
        void refreshBatch().then(data => {
            if (data && (data.status === 'running' || data.status === 'queued')) {
                startPolling(data.batch_id)
            }
        })
    }, [robotId, refreshBatch, startPolling, stopPolling])

    useEffect(() => {
        if (batchData?.status === 'completed' || batchData?.status === 'cancelled' || batchData?.status === 'failed') {
            stopPolling()
            void refreshRank()
        }
    }, [batchData?.status, refreshRank, stopPolling])

    useEffect(() => () => stopPolling(), [stopPolling])

    return {
        goal,
        setGoal,
        rankData,
        sessionFailures,
        planData,
        batchData,
        loadingRank,
        loadingPlan,
        startingBatch,
        error,
        refreshRank,
        loadPlan,
        runBatch,
        cancelBatch,
        refreshBatch,
    }
}
