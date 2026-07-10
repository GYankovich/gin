import { useCallback, useEffect, useMemo, useState } from 'react'
import type { Time } from '@/components/ui/Chart'
import { robotService } from '@/services/robotService'
import type { RobotBacktestHistoryItem, RobotBacktestRunDetails, RobotHistoryBacktestResult } from '@/types/robot'
import { toChartTime } from '@/pages/testing/testingPipeline'
import { fmtErr, normalizeBacktestResult } from '@/pages/testing/testingUtils'
import { getStrategyMeta } from '@/pages/testing/strategyPresets'

export type UseTestingResultsArgs = {
    selectedRobotId: number | null
}

/** History list, filters, compare, run details ingestion (T1.4). */
export function useTestingResults({ selectedRobotId }: UseTestingResultsArgs) {
    const [result, setResult] = useState<RobotHistoryBacktestResult | null>(null)
    const [historyRuns, setHistoryRuns] = useState<RobotBacktestHistoryItem[]>([])
    const [historyLoading, setHistoryLoading] = useState(false)
    const [historyError, setHistoryError] = useState<string | null>(null)
    const [historySearch, setHistorySearch] = useState('')
    const [historyMinReturn, setHistoryMinReturn] = useState<number | null>(null)
    const [historyMarketFilter, setHistoryMarketFilter] = useState<'all' | 'tinvest' | 'bybit'>('all')
    const [historyStatusFilter, setHistoryStatusFilter] = useState<'all' | 'SUCCESS' | 'FAILED'>('all')
    const [compareLeftId, setCompareLeftId] = useState<number | null>(null)
    const [compareRightId, setCompareRightId] = useState<number | null>(null)
    const [priceCurve, setPriceCurve] = useState<Array<{ time: Time; value: number }>>([])
    const [chartLegend, setChartLegend] = useState<{ time: string; equity?: number; price?: number }>({ time: '' })
    const [activeDetailsTab, setActiveDetailsTab] = useState<'trades' | 'signals' | 'orders' | 'portfolio'>('trades')
    const [runSignals, setRunSignals] = useState<Array<Record<string, unknown>>>([])
    const [runOrders, setRunOrders] = useState<Array<Record<string, unknown>>>([])
    const [runPortfolioSnapshots, setRunPortfolioSnapshots] = useState<Array<Record<string, unknown>>>([])
    const [statusWindow, setStatusWindow] = useState<string[]>([])

    const refreshHistoryBacktests = useCallback(async () => {
        setHistoryLoading(true)
        setHistoryError(null)
        try {
            const data = await robotService.listHistoryBacktests({
                robotId: selectedRobotId ?? null,
                limit: 50,
                broker_type: historyMarketFilter === 'all' ? undefined : historyMarketFilter,
            })
            setHistoryRuns(data.items || [])
        } catch (e: unknown) {
            setHistoryError(fmtErr(e))
            setHistoryRuns([])
        } finally {
            setHistoryLoading(false)
        }
    }, [selectedRobotId, historyMarketFilter])

    useEffect(() => {
        void refreshHistoryBacktests()
    }, [refreshHistoryBacktests])

    const filteredHistoryRuns = useMemo(() => {
        const q = historySearch.trim().toLowerCase()
        return historyRuns.filter(r => {
            if (historyStatusFilter !== 'all') {
                const st = String(r.status ?? '').toUpperCase()
                if (st !== historyStatusFilter) return false
            }
            if (historyMinReturn != null && r.total_return_percent < historyMinReturn) return false
            if (!q) return true
            const stratKey =
                String(r.strategy ?? '').trim().toLowerCase() ||
                String((r.result_payload as { strategy?: string } | undefined)?.strategy ?? '').trim().toLowerCase()
            const stratLabel =
                String(r.strategy_title ?? '').trim() ||
                (stratKey ? getStrategyMeta(stratKey).title : '')
            const text = `${r.id} ${r.status ?? ''} ${r.run_phase ?? ''} ${r.error_message ?? ''} ${stratKey} ${stratLabel} ${r.total_return_percent} ${r.final_equity} ${r.created_at}`.toLowerCase()
            return text.includes(q)
        })
    }, [historyRuns, historySearch, historyMinReturn, historyStatusFilter])

    const ingestRunDetails = useCallback((details: RobotBacktestRunDetails) => {
        const payload = (details.result_payload || {}) as RobotHistoryBacktestResult
        setResult(
            normalizeBacktestResult({
                ...payload,
                run_id: details.run_id,
                stages:
                    payload.stages ?? [`Прогон #${details.run_id} (${String(details.status)})`],
            }),
        )
        const snapshots = details.portfolio_snapshots || []
        const curve = snapshots
            .map((s: Record<string, unknown>) => {
                const t = s.snapshot_time ?? s.time
                const eq = Number(s.equity)
                if (!t || !Number.isFinite(eq)) return null
                return { time: toChartTime(t), value: eq }
            })
            .filter(Boolean) as Array<{ time: Time; value: number }>
        setPriceCurve(curve)
        setRunSignals((details.signals || []) as Array<Record<string, unknown>>)
        setRunOrders((details.orders || []) as Array<Record<string, unknown>>)
        setRunPortfolioSnapshots((details.portfolio_snapshots || []) as Array<Record<string, unknown>>)
    }, [])

    const openHistoryBacktestRun = useCallback(
        async (r: RobotBacktestHistoryItem) => {
            try {
                const details = await robotService.getHistoryBacktestRunDetails(r.id)
                ingestRunDetails(details)
                setActiveDetailsTab('trades')
                setStatusWindow([`Загружен прогон #${details.run_id} от ${new Date(r.created_at).toLocaleString('ru-RU')}`])
            } catch {
                setResult(normalizeBacktestResult(r.result_payload))
                setRunSignals([])
                setRunOrders([])
                setRunPortfolioSnapshots([])
                setActiveDetailsTab('trades')
                setStatusWindow([`Загружен прогон #${r.id} от ${new Date(r.created_at).toLocaleString('ru-RU')}`])
            }
        },
        [ingestRunDetails],
    )

    const openHistoryBacktestRunById = useCallback(
        async (runId: number) => {
            const fromHistory = historyRuns.find(r => r.id === runId)
            if (fromHistory) {
                await openHistoryBacktestRun(fromHistory)
                return
            }
            try {
                const details = await robotService.getHistoryBacktestRunDetails(runId)
                ingestRunDetails(details)
                setActiveDetailsTab('trades')
                setStatusWindow([`Загружен прогон #${details.run_id}`])
            } catch (e: unknown) {
                setStatusWindow([`Не удалось загрузить прогон #${runId}: ${fmtErr(e)}`])
            }
        },
        [historyRuns, openHistoryBacktestRun, ingestRunDetails],
    )

    const clearResult = useCallback(() => {
        setResult(null)
        setPriceCurve([])
        setRunSignals([])
        setRunOrders([])
        setRunPortfolioSnapshots([])
        setActiveDetailsTab('trades')
        setChartLegend({ time: '' })
    }, [])

    const ingestRawResult = useCallback((payload: RobotHistoryBacktestResult) => {
        setResult(payload)
        setRunSignals([])
        setRunOrders([])
        setRunPortfolioSnapshots([])
    }, [])

    return {
        result,
        historyRuns,
        historyLoading,
        historyError,
        historySearch,
        setHistorySearch,
        historyMinReturn,
        setHistoryMinReturn,
        historyMarketFilter,
        setHistoryMarketFilter,
        historyStatusFilter,
        setHistoryStatusFilter,
        compareLeftId,
        setCompareLeftId,
        compareRightId,
        setCompareRightId,
        priceCurve,
        chartLegend,
        setChartLegend,
        activeDetailsTab,
        setActiveDetailsTab,
        runSignals,
        runOrders,
        runPortfolioSnapshots,
        statusWindow,
        setStatusWindow,
        refreshHistoryBacktests,
        filteredHistoryRuns,
        ingestRunDetails,
        openHistoryBacktestRun,
        openHistoryBacktestRunById,
        clearResult,
        ingestRawResult,
    }
}

export type TestingResultsController = ReturnType<typeof useTestingResults>
