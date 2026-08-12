import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { robotService } from '@/services/robotService'
import { robotV2Service } from '@/services/robotV2Service'
import type { Robot } from '@/types/robot'
import {
    buildTradingRobotConfig,
    buildTradingRobotSchedulePatch,
} from '@/pages/testing/buildTradingRobotConfig'
import { buildTradingRobotConfigV4 } from '@/pages/testing/buildTradingRobotConfigV4'
import {
    isRobotsV2BacktestEnabled,
    isV2BacktestStrategy,
} from '@/pages/testing/refactored/robotsV2BacktestFlag'
import { clampDateToToday, fmtErr, normalizeBacktestResult, toApiDate } from '@/pages/testing/testingUtils'
import { periodSpanDays } from '@/pages/testing/refactored/validation'
import {
    hasBlockingValidationIssues,
    validateTestingFormAsync,
} from '@/pages/testing/refactored/validationAsync'
import {
    formatRunStatusLines,
    pollUntilTerminal,
    runProgressFromStatus,
} from '@/pages/testing/refactored/runner/pollUntilTerminal'
import { isBacktestTerminalStatus } from '@/pages/testing/refactored/types/responses'
import type { UseTestingConfigArgs } from '@/pages/testing/refactored/hooks/useTestingConfig'
import { useTestingConfig } from '@/pages/testing/refactored/hooks/useTestingConfig'
import type { TestingResultsController } from '@/pages/testing/refactored/hooks/useTestingResults'

type ToastLike = {
    show: (message: string, variant?: 'success' | 'error' | 'info' | 'warning', durationMs?: number) => void
}

export type UseTestingRunnerArgs = UseTestingConfigArgs & {
    selectedRobot: Robot | null
    results: TestingResultsController
    toast: ToastLike
    setFromDate: (v: string) => void
    setToDate: (v: string) => void
    setInvalid: (v: Record<string, boolean>) => void
    configDirty: boolean
    setConfigDirty: (v: boolean) => void
    setRobots: Dispatch<SetStateAction<Robot[]>>
}

/** Run + poll + cancel for history-backtest (T1.3). */
export function useTestingRunner({
    form,
    robotType,
    selectedRobot,
    results,
    toast,
    setFromDate,
    setToDate,
    setInvalid,
    configDirty,
    setConfigDirty,
    setRobots,
}: UseTestingRunnerArgs) {
    const config = useTestingConfig({ form, robotType })
    const pollRunIdRef = useRef<number | null>(null)
    const resumeLatchRef = useRef(false)

    const [running, setRunning] = useState(false)
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

    const applyRunStatus = useCallback(
        (status: Parameters<typeof formatRunStatusLines>[0], runId: number) => {
            setRunProgress(runProgressFromStatus(status))
            results.setStatusWindow(formatRunStatusLines(status, `Прогон #${runId}`))
        },
        [results],
    )

    const pollRun = useCallback(
        async (runId: number) => {
            pollRunIdRef.current = runId
            setPollingRunId(runId)
            const v2 = isRobotsV2BacktestEnabled()
            const backtestApi = v2
                ? {
                      getStatus: (id: number) => robotV2Service.getBacktestRunStatus(id),
                      getDetails: (id: number) => robotV2Service.getBacktestRunDetails(id),
                  }
                : undefined
            return pollUntilTerminal(runId, {
                onStatus: (status, rid) => applyRunStatus(status, rid),
                onTerminal: (status, rid) => {
                    const prog = runProgressFromStatus(status)
                    setRunProgress({
                        ...prog,
                        percent: status.status.toUpperCase() === 'SUCCESS' ? 100 : prog.percent,
                        etaLabel: null,
                    })
                    applyRunStatus(status, rid)
                },
            }, backtestApi)
        },
        [applyRunStatus],
    )

    const cancelActivePoll = useCallback(async () => {
        const rid = pollRunIdRef.current ?? pollingRunId
        if (rid == null) return
        setCancellingRun(true)
        try {
            await (isRobotsV2BacktestEnabled()
                ? robotV2Service.cancelBacktestRun(rid)
                : robotService.cancelHistoryBacktestRun(rid))
            toast.show('Запрос на отмену отправлен', 'info', 3500)
        } catch (e: unknown) {
            toast.show(fmtErr(e), 'error', 4500)
        } finally {
            setCancellingRun(false)
        }
    }, [pollingRunId, toast])

    const persistRobotConfig = useCallback(async (): Promise<boolean> => {
        if (!selectedRobot) return false
        try {
            const current = await robotService.getById(selectedRobot.id)
            const currentCfg = { ...((current.config || {}) as Record<string, unknown>) }
            const existingParams = (currentCfg.strategy_params as Record<string, unknown>) || {}
            const sameStrategy = String(currentCfg.strategy ?? '') === form.strategy
            const existingFigis = Array.isArray(currentCfg.allowed_figis)
                ? (currentCfg.allowed_figis as string[])
                : []
            const patchConfig = config.buildPayload({
                mergeStrategyParamsFrom: sameStrategy ? existingParams : undefined,
                preserveAllowedFigis: existingFigis,
            })
            if (currentCfg.instrument_map) {
                patchConfig.instrument_map = currentCfg.instrument_map
            }
            const schedule = buildTradingRobotSchedulePatch({
                ...config.snapshot,
                pollValue: form.pollValue,
                pollUnit: form.pollUnit,
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
    }, [selectedRobot, form.strategy, form.pollValue, form.pollUnit, config, setRobots, setConfigDirty, toast])

    const runBacktest = useCallback(async () => {
        pollRunIdRef.current = null
        setPollingRunId(null)
        setRunning(true)
        setRunProgress(null)
        setError(null)
        results.clearResult()
        results.setStatusWindow([
            'Подготовка данных: при необходимости свечи дозагружаются на сервере',
            'Расчёт бэктеста…',
        ])
        try {
            const issues = await validateTestingFormAsync(form, { robotType })
            if (hasBlockingValidationIssues(issues)) {
                const invalidFields: Record<string, boolean> = {}
                for (const i of issues) {
                    if (i.severity !== 'warning') invalidFields[i.field] = true
                }
                setInvalid(invalidFields)
                toast.show(issues.map(i => i.message).join('; '), 'error', 5000)
                results.setStatusWindow([])
                return
            }
            const warnings = issues.filter(i => i.severity === 'warning')
            if (warnings.length > 0) {
                toast.show(warnings.map(i => i.message).join('; '), 'warning', 6000)
            }

            const fromClamped = clampDateToToday(form.fromDate)
            const toClamped = clampDateToToday(form.toDate)
            if (fromClamped !== form.fromDate) setFromDate(fromClamped)
            if (toClamped !== form.toDate) setToDate(toClamped)

            if (selectedRobot && configDirty) {
                const ok = await persistRobotConfig()
                if (!ok) {
                    results.setStatusWindow([])
                    return
                }
            }
            setInvalid({})

            const cfg = selectedRobot?.config as Record<string, unknown> | undefined
            const daysSpan = periodSpanDays(fromClamped, toClamped) ?? 1
            const effectiveStrategy = form.strategy || (cfg?.strategy as string) || 'grain_seed'
            const useV2Backtest = isRobotsV2BacktestEnabled()
            if (useV2Backtest && !isV2BacktestStrategy(effectiveStrategy)) {
                toast.show(
                    'Robots v2 backtest поддерживает momentum_breakout и reversion_to_ma. Отключите VITE_ROBOTS_V2_BACKTEST или смените стратегию.',
                    'error',
                    7000,
                )
                results.setStatusWindow([])
                return
            }
            const sameStrategyAsRobot = !!cfg && String(cfg.strategy ?? '') === effectiveStrategy
            const baseFromRobot =
                selectedRobot && sameStrategyAsRobot
                    ? ((cfg?.strategy_params as Record<string, unknown>) || {})
                    : undefined

            const backtestConfig = useV2Backtest
                ? buildTradingRobotConfigV4({
                      ...config.snapshot,
                      strategy: effectiveStrategy,
                  })
                : buildTradingRobotConfig({
                      ...config.snapshot,
                      strategy: effectiveStrategy,
                      mergeStrategyParamsFrom: baseFromRobot,
                  })
            const schedule = buildTradingRobotSchedulePatch({
                ...config.snapshot,
                pollValue: form.pollValue,
                pollUnit: form.pollUnit,
            })

            const fromIso = `${toApiDate(fromClamped)}T00:00:00Z`
            const toIso = `${toApiDate(toClamped)}T23:59:59Z`

            const btWrap = useV2Backtest
                ? await robotV2Service.runBacktest({
                      config: backtestConfig,
                      from_date: fromIso,
                      to_date: toIso,
                      initial_capital: form.capital,
                      robotId: selectedRobot?.id ?? null,
                      tokenId: selectedRobot?.token?.id ?? null,
                      asyncExecution: true,
                  })
                : selectedRobot
                  ? await robotService.runHistoryBacktest({
                        robot_id: selectedRobot.id,
                        from_date: fromIso,
                        to_date: toIso,
                        initial_capital: form.capital,
                        token_id: selectedRobot.token?.id,
                        type: 2,
                        async_execution: true,
                        config: backtestConfig,
                        ...schedule,
                    })
                  : await robotService.runHistoryBacktest({
                        robot_id: null,
                        strategy: effectiveStrategy,
                        from_date: fromIso,
                        to_date: toIso,
                        initial_capital: form.capital,
                        async_execution: true,
                        config: backtestConfig,
                        ...schedule,
                    })

            if (btWrap.status === 202) {
                const rid = btWrap.data.run_id
                results.setStatusWindow(
                    [
                        `Прогон #${rid} принят (HTTP 202, async_execution; ~${daysSpan} календарных дн.)`,
                        btWrap.data.message ||
                            (useV2Backtest
                                ? `Опрос: GET /api/v2/robots/backtest/runs/${rid}/status`
                                : 'Опрос: GET /api/robots/history-backtest/runs/{run_id}'),
                    ].filter(Boolean),
                )
                const details = await pollRun(rid)
                if (details) {
                    results.ingestRunDetails(details)
                } else {
                    toast.show(
                        `Прогон #${rid}: опрос остановлен или прогон завис. Проверьте статус в истории или отмените прогон.`,
                        'warning',
                        8000,
                    )
                    void results.refreshHistoryBacktests()
                }
            } else {
                const bt = btWrap.data
                results.setStatusWindow(bt.stages ?? ['Backtest завершен'])
                if (bt.run_id) {
                    try {
                        const details = useV2Backtest
                            ? await robotV2Service.getBacktestRunDetails(bt.run_id)
                            : await robotService.getHistoryBacktestRunDetails(bt.run_id)
                        results.ingestRunDetails(details)
                    } catch {
                        results.ingestRawResult(normalizeBacktestResult(bt))
                    }
                } else {
                    results.ingestRawResult(normalizeBacktestResult(bt))
                }
            }
            results.setChartLegend({ time: '' })
        } catch (e: unknown) {
            const msg = fmtErr(e)
            setError(msg)
            toast.show(msg, 'error', 4000)
            results.setStatusWindow([msg])
        } finally {
            pollRunIdRef.current = null
            setPollingRunId(null)
            setRunning(false)
            setRunProgress(null)
        }
    }, [
        config,
        form,
        selectedRobot,
        configDirty,
        persistRobotConfig,
        pollRun,
        results,
        setFromDate,
        setToDate,
        setInvalid,
        toast,
    ])

    useEffect(() => {
        if (resumeLatchRef.current) return
        resumeLatchRef.current = true
        let cancelled = false
        void (async () => {
            try {
                const active = await robotService.getActiveHistoryBacktestRun()
                if (cancelled || !active) return
                if (isBacktestTerminalStatus(active.status)) return
                setRunning(true)
                applyRunStatus(active, active.run_id)
                results.setStatusWindow([
                    'Обнаружен незавершённый прогон (GET /api/robots/history-backtest/runs/active)',
                    ...formatRunStatusLines(active, `Прогон #${active.run_id}`),
                ])
                const details = await pollRun(active.run_id)
                if (cancelled) return
                if (details) {
                    results.ingestRunDetails(details)
                    results.setChartLegend({ time: '' })
                    toast.show('Фоновый прогон завершён', 'success', 4000)
                    void results.refreshHistoryBacktests()
                }
            } catch {
                /* no active run */
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
        // eslint-disable-next-line react-hooks/exhaustive-deps -- resume once on mount
    }, [])

    return {
        pipelinePayload: config.pipelinePayload,
        running,
        error,
        pollingRunId,
        cancellingRun,
        cancelActivePoll,
        runProgress,
        persistRobotConfig,
        runBacktest,
        validate: config.validate,
        buildPayload: config.buildPayload,
    }
}
