import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import type { Time } from '@/components/ui/Chart'
import { robotService } from '@/services/robotService'
import type {
    Robot,
    RobotBacktestHistoryItem,
    RobotBacktestRunDetails,
    RobotBacktestRunStatus,
    RobotHistoryBacktestResult,
} from '@/types/robot'
import { toChartTime, type PipelineFilter, buildPipelineFiltersPayload } from '@/pages/testing/testingPipeline'
import { clampDateToToday, fmtErr, normalizeBacktestResult, toApiDate } from '@/pages/testing/testingUtils'
import { getStrategyMeta } from '@/pages/testing/strategyPresets'
import { buildTradingRobotConfig, buildTradingRobotSchedulePatch } from '@/pages/testing/buildTradingRobotConfig'
import { isCryptoBroker } from '@/modules/robots/config/builders/buildCryptoConfig'
import { parseFixedTickersInput } from '@/utils/universeMode'
import { runProgressFromStatus } from '@/pages/testing/refactored/runner/formatRunStatus'
import type { CryptoUniverseFormFields } from '@/modules/robots/config/cryptoUniverseDefaults'
import { defaultCryptoUniverseFormFields } from '@/modules/robots/config/cryptoUniverseDefaults'

type ToastLike = {
    show: (message: string, variant?: 'success' | 'error' | 'info' | 'warning', durationMs?: number) => void
}

const TERMINAL_BACKTEST = new Set(['SUCCESS', 'FAILED', 'CANCELLED'])

function isBacktestTerminal(status: string | undefined | null): boolean {
    return TERMINAL_BACKTEST.has(String(status || '').toUpperCase())
}

function formatEtaSeconds(sec: number | null | undefined): string | null {
    if (sec == null || !Number.isFinite(sec)) return null
    const s = Math.max(0, Math.round(sec))
    if (s < 60) return `~${s} с`
    const m = Math.floor(s / 60)
    const r = s % 60
    if (m < 60) return r > 0 ? `~${m} мин ${r} с` : `~${m} мин`
    const h = Math.floor(m / 60)
    const rm = m % 60
    return rm > 0 ? `~${h} ч ${rm} мин` : `~${h} ч`
}

function formatRunStatusLines(details: RobotBacktestRunStatus, runLabel: string): string[] {
    const st = String(details.status || '').toUpperCase()
    const lines: string[] = [`${runLabel}: ${st}`]
    if (details.phase_label || details.run_phase) {
        lines.push(`фаза: ${details.phase_label || details.run_phase}`)
    }
    if (details.progress_percent != null && Number.isFinite(details.progress_percent)) {
        lines.push(`общий прогресс: ${details.progress_percent.toFixed(1)}%`)
    }
    if (
        details.phase_units_total != null &&
        details.phase_units_total > 0 &&
        details.phase_units_done != null
    ) {
        lines.push(`шаг фазы: ${details.phase_units_done}/${details.phase_units_total}`)
    }
    const eta = formatEtaSeconds(details.eta_seconds)
    if (eta) {
        const conf =
            details.eta_confidence === 'low'
                ? ' (оценка грубая)'
                : details.eta_confidence === 'high'
                  ? ''
                  : ' (уточняется)'
        lines.push(`осталось: ${eta}${conf}`)
    }
    if (details.current_trade_date) lines.push(`текущий торговый день: ${details.current_trade_date}`)
    if (details.trade_dates_total != null && details.trade_dates_remaining != null) {
        const done = details.trade_dates_total - details.trade_dates_remaining
        lines.push(`календарные дни: ${done}/${details.trade_dates_total}`)
    }
    if (details.cancel_requested) {
        lines.push('отмена запрошена — дождитесь завершения текущего шага')
    }
    if (details.error_message) {
        lines.push(`ошибка: ${details.error_message}`)
    }
    if (isBacktestTerminal(details.status) && details.partial_result) {
        lines.push('результат неполный (симуляция остановлена до конца выбранного периода)')
    }
    return lines
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
    /**
     * Текущие параметры выбранной стратегии (как в `strategyPresets.ts`).
     * Сюда уже включены `interval` и (для grain_seed) `signal_profile`.
     */
    strategyParams: Record<string, unknown>
    interval: string
    stopLossPct: number
    takeProfitPct: number
    maxPositionPct: number
    maxPositionRub: number
    maxDailyLoss: number
    slippagePct?: number
    executionLatencySec?: number
    maxDrawdownPct?: number
    tradingHoursStart: string
    tradingHoursEnd: string
    allowedWeekdays: number
    brokerCommissionPct: number
    ndflPct: number
    brokerType: string
    bybitTestnet?: boolean
    instrumentCategory?: 'spot' | 'linear' | 'inverse'
    leverage?: number
    makerFeePct?: number
    takerFeePct?: number
    fundingMode?: import('@/pages/testing/executionRiskDefaults').FundingSimulationMode
    pollValue: number
    pollUnit: 'minutes' | 'hours'
    pipelineMode: 'ALL' | 'ANY'
    universeRefreshMinutes: number
    universeMode: 'fixed' | 'dms_pipeline' | 'tqbr_scan'
    fixedTickersText: string
    cryptoUniverseMode?: 'fixed' | 'auto'
} & Partial<CryptoUniverseFormFields>

/** @deprecated T6 — use `useTestingRunner` + `useTestingResults`. Legacy: `VITE_TESTING_LEGACY=true`. */
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
    strategyParams,
    interval,
    stopLossPct,
    takeProfitPct,
    maxPositionPct,
    maxPositionRub,
    maxDailyLoss,
    slippagePct,
    executionLatencySec,
    maxDrawdownPct,
    tradingHoursStart,
    tradingHoursEnd,
    allowedWeekdays,
    brokerCommissionPct,
    ndflPct,
    brokerType,
    bybitTestnet,
    instrumentCategory,
    leverage,
    makerFeePct,
    takerFeePct,
    fundingMode,
    pollValue,
    pollUnit,
    pipelineMode,
    universeRefreshMinutes,
    universeMode,
    fixedTickersText,
    cryptoUniverseMode = 'auto',
    cryptoMinVolume24hUsd,
    cryptoMinLastPrice,
    cryptoMaxSpreadBps,
    cryptoMaxFundingRatePct,
    cryptoMinFundingRatePct,
    cryptoMinOpenInterestUsd,
    cryptoMinLsr,
    cryptoMaxLsr,
    cryptoMinRvol,
    cryptoMinAtrPercent,
    cryptoMaxAtrPercent,
    cryptoLookbackDays,
}: UseTestingBacktestArgs) {
    const cryptoDefaults = defaultCryptoUniverseFormFields()
    const formSnapshot = useMemo(
        () => ({
            strategy,
            strategyParams,
            interval,
            capital,
            brokerType,
            stopLossPct,
            takeProfitPct,
            maxPositionPct,
            maxPositionRub,
            maxDailyLoss,
            slippagePct,
            executionLatencySec,
            maxDrawdownPct,
            tradingHoursStart,
            tradingHoursEnd,
            allowedWeekdays,
            brokerCommissionPct,
            ndflPct,
            pipelineMode,
            filters,
            universeRefreshMinutes,
            universeMode,
            fixedTickers: parseFixedTickersInput(fixedTickersText),
            cryptoUniverseMode,
            cryptoMinVolume24hUsd: cryptoMinVolume24hUsd ?? cryptoDefaults.cryptoMinVolume24hUsd,
            cryptoMinLastPrice: cryptoMinLastPrice ?? cryptoDefaults.cryptoMinLastPrice,
            cryptoMaxSpreadBps: cryptoMaxSpreadBps ?? cryptoDefaults.cryptoMaxSpreadBps,
            cryptoMaxFundingRatePct: cryptoMaxFundingRatePct ?? cryptoDefaults.cryptoMaxFundingRatePct,
            cryptoMinFundingRatePct: cryptoMinFundingRatePct ?? cryptoDefaults.cryptoMinFundingRatePct,
            cryptoMinOpenInterestUsd: cryptoMinOpenInterestUsd ?? cryptoDefaults.cryptoMinOpenInterestUsd,
            cryptoMinLsr: cryptoMinLsr ?? cryptoDefaults.cryptoMinLsr,
            cryptoMaxLsr: cryptoMaxLsr ?? cryptoDefaults.cryptoMaxLsr,
            cryptoMinRvol: cryptoMinRvol ?? cryptoDefaults.cryptoMinRvol,
            cryptoMinAtrPercent: cryptoMinAtrPercent ?? cryptoDefaults.cryptoMinAtrPercent,
            cryptoMaxAtrPercent: cryptoMaxAtrPercent ?? cryptoDefaults.cryptoMaxAtrPercent,
            cryptoLookbackDays: cryptoLookbackDays ?? cryptoDefaults.cryptoLookbackDays,
            bybitTestnet,
            instrumentCategory,
            leverage,
            makerFeePct,
            takerFeePct,
            fundingMode,
        }),
        [
            strategy,
            strategyParams,
            interval,
            capital,
            brokerType,
            stopLossPct,
            takeProfitPct,
            maxPositionPct,
            maxPositionRub,
            maxDailyLoss,
            slippagePct,
            executionLatencySec,
            maxDrawdownPct,
            tradingHoursStart,
            tradingHoursEnd,
            allowedWeekdays,
            brokerCommissionPct,
            ndflPct,
            pipelineMode,
            filters,
            universeRefreshMinutes,
            universeMode,
            fixedTickersText,
            cryptoUniverseMode,
            cryptoMinVolume24hUsd,
            cryptoMinLastPrice,
            cryptoMaxSpreadBps,
            cryptoMaxFundingRatePct,
            cryptoMinFundingRatePct,
            cryptoMinOpenInterestUsd,
            cryptoMinLsr,
            cryptoMaxLsr,
            cryptoMinRvol,
            cryptoMinAtrPercent,
            cryptoMaxAtrPercent,
            cryptoLookbackDays,
            cryptoDefaults,
            bybitTestnet,
            instrumentCategory,
            leverage,
            makerFeePct,
            takerFeePct,
            fundingMode,
        ],
    )

    const pipelinePayload = useMemo(
        () => buildPipelineFiltersPayload(filters),
        [filters],
    )

    const [running, setRunning] = useState(false)
    const [statusWindow, setStatusWindow] = useState<string[]>([])
    const [result, setResult] = useState<RobotHistoryBacktestResult | null>(null)
    const [historyRuns, setHistoryRuns] = useState<RobotBacktestHistoryItem[]>([])
    const [historyLoading, setHistoryLoading] = useState(false)
    const [historyError, setHistoryError] = useState<string | null>(null)
    const [historySearch, setHistorySearch] = useState('')
    const [historyMinReturn, setHistoryMinReturn] = useState<number | null>(null)
    const [historyMarketFilter, setHistoryMarketFilter] = useState<'all' | 'tinvest' | 'bybit'>('all')
    const [compareLeftId, setCompareLeftId] = useState<number | null>(null)
    const [compareRightId, setCompareRightId] = useState<number | null>(null)
    const [priceCurve, setPriceCurve] = useState<Array<{ time: Time; value: number }>>([])
    const [chartLegend, setChartLegend] = useState<{ time: string; equity?: number; price?: number }>({ time: '' })
    const [activeDetailsTab, setActiveDetailsTab] = useState<'trades' | 'signals' | 'orders' | 'portfolio'>('trades')
    const [runSignals, setRunSignals] = useState<Array<Record<string, unknown>>>([])
    const [runOrders, setRunOrders] = useState<Array<Record<string, unknown>>>([])
    const [runPortfolioSnapshots, setRunPortfolioSnapshots] = useState<Array<Record<string, unknown>>>([])
    const [error, setError] = useState<string | null>(null)
    const [pollingRunId, setPollingRunId] = useState<number | null>(null)
    const [cancellingRun, setCancellingRun] = useState(false)
    const [runProgress, setRunProgress] = useState<{
        percent: number
        etaLabel: string | null
        phaseLabel: string | null
        runPhase: string | null
        phaseUnitsDone: number | null
        phaseUnitsTotal: number | null
    } | null>(null)
    const pollRunIdRef = useRef<number | null>(null)
    const resumeLatchRef = useRef(false)

    const refreshHistoryBacktests = useCallback(async () => {
        setHistoryLoading(true)
        setHistoryError(null)
        try {
            const data = await robotService.listHistoryBacktests({
                robotId: selectedRobot?.id ?? null,
                limit: 30,
                broker_type: historyMarketFilter === 'all' ? undefined : historyMarketFilter,
            })
            setHistoryRuns(data.items || [])
        } catch (e: unknown) {
            setHistoryError(fmtErr(e))
            setHistoryRuns([])
        } finally {
            setHistoryLoading(false)
        }
    }, [selectedRobot?.id, historyMarketFilter])

    useEffect(() => {
        void refreshHistoryBacktests()
    }, [refreshHistoryBacktests])

    const filteredHistoryRuns = useMemo(() => {
        const q = historySearch.trim().toLowerCase()
        return historyRuns.filter(r => {
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
    }, [historyRuns, historySearch, historyMinReturn])

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

    const applyRunStatus = useCallback((status: RobotBacktestRunStatus, runId: number) => {
        setRunProgress(runProgressFromStatus(status))
        setStatusWindow(formatRunStatusLines(status, `Прогон #${runId}`))
    }, [])

    const pollUntilTerminal = useCallback(async (runId: number): Promise<RobotBacktestRunDetails | null> => {
        pollRunIdRef.current = runId
        setPollingRunId(runId)
        const maxTicks = 7200
        let details: RobotBacktestRunDetails | null = null
        try {
            for (let i = 0; i < maxTicks; i++) {
                const status = await robotService.getHistoryBacktestRunStatus(runId)
                applyRunStatus(status, runId)
                if (isBacktestTerminal(status.status)) {
                    details = await robotService.getHistoryBacktestRunDetails(runId)
                    const prog = runProgressFromStatus(status)
                    setRunProgress({
                        ...prog,
                        percent: status.status.toUpperCase() === 'SUCCESS' ? 100 : prog.percent,
                        etaLabel: null,
                    })
                    break
                }
                await new Promise<void>(resolve => {
                    setTimeout(resolve, 2000)
                })
            }
            if (!details) {
                try {
                    const last = await robotService.getHistoryBacktestRunStatus(runId)
                    applyRunStatus(last, runId)
                } catch {
                    /* ignore */
                }
            }
            return details
        } catch {
            return null
        }
    }, [applyRunStatus])

    const cancelActivePoll = useCallback(async () => {
        const rid = pollRunIdRef.current ?? pollingRunId
        if (rid == null) return
        setCancellingRun(true)
        try {
            await robotService.cancelHistoryBacktestRun(rid)
            toast.show('Запрос на отмену отправлен', 'info', 3500)
        } catch (e: unknown) {
            toast.show(fmtErr(e), 'error', 4500)
        } finally {
            setCancellingRun(false)
        }
    }, [pollingRunId, toast])

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

    const persistRobotConfig = useCallback(async (): Promise<boolean> => {
        if (!selectedRobot) return false
        try {
            const current = await robotService.getById(selectedRobot.id)
            const currentCfg = { ...((current.config || {}) as Record<string, unknown>) }
            const existingParams = (currentCfg.strategy_params as Record<string, unknown>) || {}
            const sameStrategy = String(currentCfg.strategy ?? '') === strategy
            const existingFigis = Array.isArray(currentCfg.allowed_figis)
                ? (currentCfg.allowed_figis as string[])
                : []
            const patchConfig = buildTradingRobotConfig({
                ...formSnapshot,
                mergeStrategyParamsFrom: sameStrategy ? existingParams : undefined,
                preserveAllowedFigis: existingFigis,
            })
            if (currentCfg.instrument_map) {
                patchConfig.instrument_map = currentCfg.instrument_map
            }
            const schedule = buildTradingRobotSchedulePatch({
                ...formSnapshot,
                pollValue,
                pollUnit,
            })
            await robotService.updateRobot(selectedRobot.id, {
                config: patchConfig,
                ...schedule,
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
        formSnapshot,
        pollValue,
        pollUnit,
        setRobots,
        setConfigDirty,
        toast,
    ])

    const runBacktest = useCallback(async () => {
        pollRunIdRef.current = null
        setPollingRunId(null)
        setRunning(true)
        setRunProgress(null)
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
            if (!fromDate || !toDate) {
                setInvalid({ period: true })
                toast.show('Выберите период бэктеста', 'error', 4000)
                setStatusWindow([])
                return
            }
            const fromClamped = clampDateToToday(fromDate)
            const toClamped = clampDateToToday(toDate)
            if (fromClamped !== fromDate) setFromDate(fromClamped)
            if (toClamped !== toDate) setToDate(toClamped)
            if (selectedRobot && selectedRobot.type !== 2) {
                toast.show('Backtest доступен только для торговых роботов type=2', 'error', 4000)
                setStatusWindow([])
                return
            }
            if (isCryptoBroker(brokerType)) {
                if (cryptoUniverseMode === 'fixed' && !parseFixedTickersInput(fixedTickersText).length) {
                    toast.show('Укажите символы ByBit (например BTCUSDT)', 'error', 4000)
                    setStatusWindow([])
                    return
                }
            } else if (universeMode === 'fixed' && !parseFixedTickersInput(fixedTickersText).length) {
                toast.show('Укажите тикеры для режима «Фиксированный список»', 'error', 4000)
                setStatusWindow([])
                return
            }
            if (selectedRobot && configDirty) {
                const ok = await persistRobotConfig()
                if (!ok) {
                    setStatusWindow([])
                    return
                }
            }
            setInvalid({})
            const cfg = selectedRobot?.config as Record<string, unknown> | undefined
            const fromD = new Date(fromClamped)
            const toD = new Date(toClamped)
            const daysSpan = Math.max(1, Math.ceil((toD.getTime() - fromD.getTime()) / 86_400_000) + 1)

            const effectiveStrategy = strategy || (cfg?.strategy as string) || 'grain_seed'
            const sameStrategyAsRobot = !!cfg && String(cfg.strategy ?? '') === effectiveStrategy
            const baseFromRobot =
                selectedRobot && sameStrategyAsRobot
                    ? ((cfg?.strategy_params as Record<string, unknown>) || {})
                    : undefined
            const backtestConfig = buildTradingRobotConfig({
                ...formSnapshot,
                strategy: effectiveStrategy,
                mergeStrategyParamsFrom: baseFromRobot,
            })
            const schedule = buildTradingRobotSchedulePatch({
                ...formSnapshot,
                pollValue,
                pollUnit,
            })

            const btWrap = selectedRobot
                ? await robotService.runHistoryBacktest({
                      robot_id: selectedRobot.id,
                      from_date: `${toApiDate(fromClamped)}T00:00:00Z`,
                      to_date: `${toApiDate(toClamped)}T23:59:59Z`,
                      initial_capital: capital,
                      token_id: selectedRobot.token?.id,
                      type: 2,
                      async_execution: true,
                      config: backtestConfig,
                      ...schedule,
                  })
                : await robotService.runHistoryBacktest({
                      robot_id: null,
                      strategy: effectiveStrategy,
                      from_date: `${toApiDate(fromClamped)}T00:00:00Z`,
                      to_date: `${toApiDate(toClamped)}T23:59:59Z`,
                      initial_capital: capital,
                      async_execution: true,
                      config: backtestConfig,
                      ...schedule,
                  })
            if (btWrap.status === 202) {
                const rid = btWrap.data.run_id
                setStatusWindow(
                    [
                        `Прогон #${rid} принят (HTTP 202, async_execution; ~${daysSpan} календарных дн.)`,
                        btWrap.data.message || 'Опрос: GET /api/robots/history-backtest/runs/{run_id}',
                    ].filter(Boolean),
                )
                const details = await pollUntilTerminal(rid)
                if (details) {
                    ingestRunDetails(details)
                } else {
                    toast.show(
                        `Прогон #${rid}: опрос остановлен или прогон завис. Проверьте статус в истории или отмените прогон.`,
                        'warning',
                        8000,
                    )
                    void refreshHistoryBacktests()
                }
            } else {
                const bt = btWrap.data
                setStatusWindow(bt.stages ?? ['Backtest завершен'])
                if (bt.run_id) {
                    try {
                        const details = await robotService.getHistoryBacktestRunDetails(bt.run_id)
                        ingestRunDetails(details)
                    } catch {
                        setResult(normalizeBacktestResult(bt))
                        setRunSignals([])
                        setRunOrders([])
                        setRunPortfolioSnapshots([])
                    }
                } else {
                    setResult(normalizeBacktestResult(bt))
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
        } finally {
            pollRunIdRef.current = null
            setPollingRunId(null)
            setRunning(false)
            setRunProgress(null)
        }
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
        formSnapshot,
        toast,
        ingestRunDetails,
        pollUntilTerminal,
        applyRunStatus,
    ])

    useEffect(() => {
        if (resumeLatchRef.current) return
        resumeLatchRef.current = true
        let cancelled = false
        void (async () => {
            try {
                const active = await robotService.getActiveHistoryBacktestRun()
                if (cancelled || !active) return
                if (isBacktestTerminal(active.status)) return
                setRunning(true)
                applyRunStatus(active, active.run_id)
                setStatusWindow([
                    'Обнаружен незавершённый прогон (GET /api/robots/history-backtest/runs/active)',
                    ...formatRunStatusLines(active, `Прогон #${active.run_id}`),
                ])
                const details = await pollUntilTerminal(active.run_id)
                if (cancelled) return
                if (details) {
                    ingestRunDetails(details)
                    setChartLegend({ time: '' })
                    toast.show('Фоновый прогон завершён', 'success', 4000)
                    void refreshHistoryBacktests()
                }
            } catch {
                // нет активного прогона или сеть — не мешаем работе страницы
            } finally {
                if (!cancelled) {
                    setRunning(false)
                    pollRunIdRef.current = null
                    setPollingRunId(null)
                }
            }
        })()
        return () => {
            cancelled = true
            resumeLatchRef.current = false
        }
        // Восстановление по §9.1: один раз при монтировании; замыкание refreshHistoryBacktests — снимок первого рендера.
        // eslint-disable-next-line react-hooks/exhaustive-deps -- намеренно без зависимостей
    }, [])

    return {
        pipelinePayload,
        running,
        statusWindow,
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
        error,
        persistRobotConfig,
        runBacktest,
        refreshHistoryBacktests,
        openHistoryBacktestRun,
        filteredHistoryRuns,
        pollingRunId,
        cancellingRun,
        cancelActivePoll,
        runProgress,
    }
}
