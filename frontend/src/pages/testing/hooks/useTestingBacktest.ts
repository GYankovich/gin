import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react'
import type { Time } from '@/components/ui/Chart'
import { robotService } from '@/services/robotService'
import type { Robot, RobotBacktestHistoryItem, RobotHistoryBacktestResult } from '@/types/robot'
import { buildPipelineFiltersPayload, normalizeSignalInterval, toChartTime, type PipelineFilter } from '@/pages/testing/testingPipeline'
import { clampDateToToday, fmtErr, normalizeBacktestResult, toApiDate } from '@/pages/testing/testingUtils'

type ToastLike = {
    show: (message: string, variant?: 'success' | 'error' | 'info' | 'warning', durationMs?: number) => void
}

export type UseTestingBacktestArgs = {
    selectedRobot: Robot | null
    filters: PipelineFilter[]
    fromDate: string
    toDate: string
    setFromDate: Dispatch<SetStateAction<string>>
    setToDate: Dispatch<SetStateAction<string>>
    setInvalid: Dispatch<SetStateAction<Record<string, boolean>>>
    configDirty: boolean
    setConfigDirty: Dispatch<SetStateAction<boolean>>
    setRobots: Dispatch<SetStateAction<Robot[]>>
    toast: ToastLike
    capital: number
    strategy: string
    interval: string
    stopLossPct: number
    takeProfitPct: number
    maxPositionPct: number
    maxPositionRub: number
    brokerCommissionPct: number
    ndflPct: number
    brokerType: string
    pollValue: number
    pollUnit: 'minutes' | 'hours'
    pipelineMode: 'ALL' | 'ANY'
}

export function useTestingBacktest({
    selectedRobot,
    filters,
    fromDate,
    toDate,
    setFromDate,
    setToDate,
    setInvalid,
    configDirty,
    setConfigDirty,
    setRobots,
    toast,
    capital,
    strategy,
    interval,
    stopLossPct,
    takeProfitPct,
    maxPositionPct,
    maxPositionRub,
    brokerCommissionPct,
    ndflPct,
    brokerType,
    pollValue,
    pollUnit,
    pipelineMode,
}: UseTestingBacktestArgs) {
    const pipelinePayload = useMemo(() => buildPipelineFiltersPayload(filters), [filters])

    const [running, setRunning] = useState(false)
    const [statusWindow, setStatusWindow] = useState<string[]>([])
    const [result, setResult] = useState<RobotHistoryBacktestResult | null>(null)
    const [historyRuns, setHistoryRuns] = useState<RobotBacktestHistoryItem[]>([])
    const [historyLoading, setHistoryLoading] = useState(false)
    const [historySearch, setHistorySearch] = useState('')
    const [historyMinReturn, setHistoryMinReturn] = useState<number | null>(null)
    const [compareLeftId, setCompareLeftId] = useState<number | null>(null)
    const [compareRightId, setCompareRightId] = useState<number | null>(null)
    const [priceCurve, setPriceCurve] = useState<Array<{ time: Time; value: number }>>([])
    const [chartLegend, setChartLegend] = useState<{ time: string; equity?: number; price?: number }>({ time: '' })
    const [activeDetailsTab, setActiveDetailsTab] = useState<'trades' | 'signals' | 'orders' | 'portfolio'>('trades')
    const [runSignals, setRunSignals] = useState<Array<Record<string, unknown>>>([])
    const [runOrders, setRunOrders] = useState<Array<Record<string, unknown>>>([])
    const [runPortfolioSnapshots, setRunPortfolioSnapshots] = useState<Array<Record<string, unknown>>>([])
    const [, setError] = useState<string | null>(null)

    const refreshHistoryBacktests = useCallback(async () => {
        if (!selectedRobot) {
            setHistoryRuns([])
            return
        }
        setHistoryLoading(true)
        try {
            const data = await robotService.listHistoryBacktests({ robotId: selectedRobot.id, limit: 30 })
            setHistoryRuns(data.items || [])
        } catch {
            setHistoryRuns([])
        } finally {
            setHistoryLoading(false)
        }
    }, [selectedRobot])

    useEffect(() => {
        void refreshHistoryBacktests()
    }, [refreshHistoryBacktests])

    const openHistoryBacktestRun = useCallback(async (r: RobotBacktestHistoryItem) => {
        try {
            const details = await robotService.getHistoryBacktestRun(r.id)
            const payload = (details.result_payload || {}) as RobotHistoryBacktestResult
            setResult(
                normalizeBacktestResult({
                    ...payload,
                    run_id: details.run_id,
                    stages: payload.stages ?? [`Загружен прогон #${details.run_id}`],
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
    }, [])

    const filteredHistoryRuns = useMemo(() => {
        const q = historySearch.trim().toLowerCase()
        return historyRuns.filter(r => {
            if (historyMinReturn != null && r.total_return_percent < historyMinReturn) return false
            if (!q) return true
            const text = `${r.id} ${r.total_return_percent} ${r.final_equity} ${r.created_at}`.toLowerCase()
            return text.includes(q)
        })
    }, [historyRuns, historySearch, historyMinReturn])

    const persistRobotConfig = useCallback(async (): Promise<boolean> => {
        if (!selectedRobot) return false
        try {
            const current = await robotService.getById(selectedRobot.id)
            const currentCfg = { ...((current.config || {}) as Record<string, unknown>) }
            const nextStrategyParams = {
                ...((currentCfg.strategy_params as Record<string, unknown>) || {}),
                initial_capital: Number(capital || 1_000_000),
                interval: normalizeSignalInterval(interval),
            }
            const nextRisk = {
                ...((currentCfg.risk as Record<string, unknown>) || {}),
                stop_loss_percent: Number(stopLossPct || 0),
                take_profit_percent: Number(takeProfitPct || 0),
                max_position_percent: Number(maxPositionPct || 0),
                max_position_rub: Number(maxPositionRub || 0),
            }
            const nextCosts = {
                ...((currentCfg.costs as Record<string, unknown>) || {}),
                broker_commission_rate: Number((Number(brokerCommissionPct || 0) / 100).toFixed(6)),
                ndfl_rate: Number((Number(ndflPct || 0) / 100).toFixed(6)),
            }
            const patchConfig = {
                ...currentCfg,
                broker_type: brokerType || (currentCfg.broker_type as string) || 'tinvest',
                strategy: strategy || (currentCfg.strategy as string) || 'grain_seed',
                strategy_params: nextStrategyParams,
                risk: nextRisk,
                costs: nextCosts,
                pipeline: {
                    mode: pipelineMode,
                    filters: pipelinePayload,
                },
            }
            const pollHours = pollUnit === 'minutes' ? Number(pollValue) / 60 : Number(pollValue)
            await robotService.updateRobot(selectedRobot.id, {
                config: patchConfig as Record<string, unknown>,
                poll_interval_hours: Number(pollHours.toFixed(4)),
            })
            const refreshed = await robotService.getById(selectedRobot.id)
            setRobots(prev => prev.map(r => (r.id === refreshed.id ? refreshed : r)))
            setConfigDirty(false)
            return true
        } catch {
            toast.show('Не удалось применить параметры робота', 'error')
            return false
        }
    }, [
        selectedRobot,
        capital,
        interval,
        stopLossPct,
        takeProfitPct,
        maxPositionPct,
        maxPositionRub,
        brokerCommissionPct,
        ndflPct,
        brokerType,
        strategy,
        pipelineMode,
        pipelinePayload,
        pollValue,
        pollUnit,
        setRobots,
        setConfigDirty,
        toast,
    ])

    const runBacktest = useCallback(async () => {
        setRunning(true)
        setError(null)
        setResult(null)
        setPriceCurve([])
        setRunSignals([])
        setRunOrders([])
        setRunPortfolioSnapshots([])
        setActiveDetailsTab('trades')
        setStatusWindow([
            'Подготовка данных: при необходимости свечи дозагружаются на сервере',
            'Расчёт бэктеста…',
        ])
        try {
            if (!selectedRobot) {
                toast.show('Выберите робота', 'error', 4000)
                setStatusWindow([])
                setRunning(false)
                return
            }
            if (selectedRobot.type !== 2) {
                toast.show('Backtest доступен только для роботов type=2', 'error', 4000)
                setStatusWindow([])
                setRunning(false)
                return
            }
            if (!fromDate || !toDate) {
                setInvalid({ period: true })
                toast.show('Выберите период бэктеста', 'error', 4000)
                setStatusWindow([])
                setRunning(false)
                return
            }
            const fromClamped = clampDateToToday(fromDate)
            const toClamped = clampDateToToday(toDate)
            if (fromClamped !== fromDate) setFromDate(fromClamped)
            if (toClamped !== toDate) setToDate(toClamped)
            if (configDirty) {
                const ok = await persistRobotConfig()
                if (!ok) {
                    setStatusWindow([])
                    setRunning(false)
                    return
                }
            }
            setInvalid({})
            const pollHours = pollUnit === 'minutes' ? Number(pollValue) / 60 : Number(pollValue)
            const cfg = selectedRobot.config as Record<string, unknown> | undefined
            const risk = (cfg?.risk as Record<string, unknown>) || {}
            const bt = await robotService.runHistoryBacktest({
                robot_id: selectedRobot.id,
                from_date: `${toApiDate(fromClamped)}T00:00:00Z`,
                to_date: `${toApiDate(toClamped)}T23:59:59Z`,
                initial_capital: capital,
                token_id: selectedRobot.token?.id,
                type: 2,
                poll_interval_hours: Number(pollHours.toFixed(4)),
                trading_hours_start: String(risk?.trading_hours_start || '').replace(' MSK', '') || '09:00',
                trading_hours_end: String(risk?.trading_hours_end || '').replace(' MSK', '') || '18:45',
                allowed_weekdays: Number(risk?.allowed_weekdays ?? 31),
                config: {
                    strategy: strategy || (cfg?.strategy as string) || 'grain_seed',
                    broker_type: brokerType || (cfg?.broker_type as string) || 'tinvest',
                    strategy_params: {
                        ...((cfg?.strategy_params as Record<string, unknown>) || {}),
                        interval: normalizeSignalInterval(interval),
                        initial_capital: Number(capital || 1_000_000),
                    },
                    pipeline: {
                        filters: pipelinePayload,
                        mode: pipelineMode,
                    },
                    costs: {
                        broker_commission_rate: Number((Number(brokerCommissionPct || 0) / 100).toFixed(6)),
                        ndfl_rate: Number((Number(ndflPct || 0) / 100).toFixed(6)),
                    },
                    risk: {
                        stop_loss_percent: Number(stopLossPct || 0),
                        take_profit_percent: Number(takeProfitPct || 0),
                        max_position_percent: Number(maxPositionPct || 0),
                        max_position_rub: Number(maxPositionRub || 0),
                    },
                },
            })
            setStatusWindow(bt.stages ?? ['Backtest завершен'])
            setResult(normalizeBacktestResult(bt))
            if (bt.run_id) {
                try {
                    const details = await robotService.getHistoryBacktestRun(bt.run_id)
                    setRunSignals((details.signals || []) as Array<Record<string, unknown>>)
                    setRunOrders((details.orders || []) as Array<Record<string, unknown>>)
                    setRunPortfolioSnapshots((details.portfolio_snapshots || []) as Array<Record<string, unknown>>)
                } catch {
                    setRunSignals([])
                    setRunOrders([])
                    setRunPortfolioSnapshots([])
                }
            }
            setChartLegend({ time: '' })
        } catch (e: unknown) {
            const msg = fmtErr(e)
            setError(msg)
            toast.show(msg, 'error', 4000)
            setStatusWindow([msg])
        }
        setRunning(false)
    }, [
        selectedRobot,
        fromDate,
        toDate,
        setFromDate,
        setToDate,
        setInvalid,
        configDirty,
        persistRobotConfig,
        pollUnit,
        pollValue,
        capital,
        strategy,
        interval,
        brokerType,
        brokerCommissionPct,
        ndflPct,
        stopLossPct,
        takeProfitPct,
        maxPositionPct,
        maxPositionRub,
        pipelineMode,
        pipelinePayload,
        toast,
    ])

    return {
        pipelinePayload,
        running,
        statusWindow,
        result,
        historyRuns,
        historyLoading,
        historySearch,
        setHistorySearch,
        historyMinReturn,
        setHistoryMinReturn,
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
        persistRobotConfig,
        runBacktest,
        refreshHistoryBacktests,
        openHistoryBacktestRun,
        filteredHistoryRuns,
    }
}
