import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { BacktestHistoryCard } from '@/pages/robots-v2/components/BacktestHistoryCard'
import { BacktestResultsPanel } from '@/pages/robots-v2/components/BacktestResultsPanel'
import { RobotPageChrome } from '@/pages/robots-v2/components/RobotPageChrome'
import { RobotStageCard } from '@/pages/robots-v2/components/RobotStageCard'
import { RobotV2OptimizationCard } from '@/pages/robots-v2/components/RobotV2OptimizationCard'
import { fmtErr, sessionStateLabel } from '@/pages/robots-v2/formatters'
import { formatBacktestPhaseUnits } from '@/pages/robots-v2/formatBacktestPhaseUnits'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2 } from '@/types/robotV2'
import type {
    BacktestFeeSummary,
    BacktestNarrativeStep,
    BacktestObservability,
    BacktestPortfolioSnapshot,
    RobotBacktestRunDetails,
    RobotHistoryBacktestResult,
} from '@/types/robot'
import type { IChartApi, ISeriesApi, Time } from '@/components/ui/Chart'

function isoDateUtc(d: Date): string {
    return d.toISOString().slice(0, 10)
}

function daysAgoUtc(n: number): string {
    const d = new Date()
    d.setUTCDate(d.getUTCDate() - n)
    return isoDateUtc(d)
}

function todayUtc(): string {
    return isoDateUtc(new Date())
}

function archetypeOf(robot: RobotV2 | null): string {
    const strategy = (robot?.config?.strategy || {}) as Record<string, unknown>
    return String(strategy.archetype || '')
}

function riskCapital(robot: RobotV2 | null): number {
    const risk = (robot?.config?.risk || {}) as Record<string, unknown>
    const n = Number(risk.capital)
    return Number.isFinite(n) && n > 0 ? n : 100_000
}

function tokenIdOf(robot: RobotV2 | null): number | null {
    if (!robot) return null
    const n = Number(robot.tokenId ?? robot.token_id)
    return Number.isFinite(n) && n > 0 ? n : null
}

function statusVariant(status: string): 'up' | 'down' | 'neutral' | 'warn' {
    const s = status.toUpperCase()
    if (s === 'SUCCESS') return 'up'
    if (s === 'FAILED') return 'down'
    if (s === 'CANCELLED') return 'warn'
    if (s === 'RUNNING' || s === 'QUEUED') return 'neutral'
    return 'neutral'
}

function toChartPoints(curve: Array<{ time: string; equity: number }>): Array<{ time: Time; value: number }> {
    const byTime = new Map<number, number>()
    for (const p of curve) {
        const t = Math.floor(new Date(p.time).getTime() / 1000)
        if (!Number.isFinite(t) || !Number.isFinite(p.equity)) continue
        byTime.set(t, p.equity)
    }
    return [...byTime.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([time, value]) => ({ time: time as Time, value }))
}

const PRESETS: Array<{ id: string; label: string; days: number }> = [
    { id: '7d', label: '7 дней', days: 7 },
    { id: '30d', label: '30 дней', days: 30 },
    { id: '90d', label: '90 дней', days: 90 },
    { id: '180d', label: '180 дней', days: 180 },
]

export default function RobotV2BacktestPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const [searchParams, setSearchParams] = useSearchParams()
    const toast = useToast()

    const [robot, setRobot] = useState<RobotV2 | null>(null)
    const [loading, setLoading] = useState(true)
    const [fromDate, setFromDate] = useState(() => daysAgoUtc(30))
    const [toDate, setToDate] = useState(() => todayUtc())
    const [capital, setCapital] = useState(100_000)
    const [running, setRunning] = useState(false)
    const [cancelling, setCancelling] = useState(false)
    const [runId, setRunId] = useState<number | null>(null)
    const [status, setStatus] = useState<RobotBacktestRunDetails | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [history, setHistory] = useState<Array<{
        run_id: number
        status: string
        requested_from: string
        requested_to: string
        started_at: string
        initial_capital: number
        total_return_percent?: number | null
        max_drawdown_percent?: number | null
        sharpe_ratio?: number | null
        final_equity?: number | null
        trades_total: number
    }>>([])
    const [selectedIds, setSelectedIds] = useState<number[]>([])
    const [compare, setCompare] = useState<{
        metrics_base: Record<string, number | null>
        metrics_compare: Record<string, number | null>
        metrics_diff: Record<string, number | null>
        config_diff: Record<string, { base: unknown; compare: unknown }>
        base_run_id: number
        compare_run_id: number
    } | null>(null)

    const chartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
    const resultAnchorRef = useRef<HTMLDivElement | null>(null)
    const openedFromQueryRef = useRef<number | null>(null)
    const pollFailStreakRef = useRef(0)

    const [historyLoading, setHistoryLoading] = useState(false)
    const [historyError, setHistoryError] = useState<string | null>(null)
    const [openingRun, setOpeningRun] = useState(false)

    const loadRobot = useCallback(async () => {
        if (!Number.isFinite(robotId)) return
        setLoading(true)
        try {
            const r = await robotV2Service.getById(robotId)
            setRobot(r)
            setCapital(riskCapital(r))
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setLoading(false)
        }
    }, [robotId, toast])

    const loadHistory = useCallback(async () => {
        if (!Number.isFinite(robotId)) return
        setHistoryLoading(true)
        try {
            const data = await robotV2Service.listBacktestRuns({ robotId, limit: 30 })
            setHistory(data.items || [])
            setHistoryError(null)
        } catch (e) {
            const msg = fmtErr(e)
            setHistoryError(msg)
            toast.show(`История прогонов: ${msg}`, 'error')
        } finally {
            setHistoryLoading(false)
        }
    }, [robotId, toast])

    useEffect(() => {
        void loadRobot()
        void loadHistory()
    }, [loadRobot, loadHistory])

    const payload = (status?.result_payload || {}) as Partial<RobotHistoryBacktestResult>
    const equityCurve = payload.equity_curve || []
    const trades = payload.trades || []
    const runSignals = status?.signals ?? []
    const runOrders = status?.orders ?? []
    const dailySummary =
        status?.daily_summary
        ?? (payload as { daily_summary?: Array<Record<string, unknown>> }).daily_summary
        ?? []
    const feeSummary = (
        status?.fee_summary
        ?? payload.fee_summary
        ?? null
    ) as BacktestFeeSummary | null
    const portfolioSnapshots = (status?.portfolio_snapshots || []) as BacktestPortfolioSnapshot[]
    const narrative = (
        status?.narrative
        ?? (payload as { narrative?: BacktestNarrativeStep[] }).narrative
        ?? null
    ) as BacktestNarrativeStep[] | null
    const chartPoints = useMemo(() => toChartPoints(equityCurve), [equityCurve])

    useEffect(() => {
        const series = seriesRef.current
        if (!series) return
        series.setData(chartPoints)
    }, [chartPoints])

    const runStatus = String(status?.status || '').toUpperCase()
    const isActive = running || runStatus === 'RUNNING' || runStatus === 'QUEUED'
    const archetype = archetypeOf(robot)
    const scalperBlocked = archetype === 'scalper'
    const spanDays = useMemo(() => {
        const a = Date.parse(`${fromDate}T00:00:00Z`)
        const b = Date.parse(`${toDate}T00:00:00Z`)
        if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return 0
        return Math.round((b - a) / 86_400_000) + 1
    }, [fromDate, toDate])

    const poll = useCallback(async (idToPoll: number) => {
        const st = await robotV2Service.getBacktestRunStatus(idToPoll)
        setStatus(prev => {
            const merged = { ...(prev || {}), ...st } as RobotBacktestRunDetails
            if (!merged.result_payload) merged.result_payload = prev?.result_payload || ({} as RobotHistoryBacktestResult)
            return merged
        })
        const phase = String(st.status || '').toUpperCase()
        if (phase === 'SUCCESS' || phase === 'FAILED' || phase === 'CANCELLED') {
            const details = await robotV2Service.getBacktestRunDetails(idToPoll)
            setStatus(details)
            setRunning(false)
            pollFailStreakRef.current = 0
            if (phase === 'FAILED') {
                setError(details.error_message || 'Прогон завершился с ошибкой')
                toast.show(details.error_message || 'Прогон завершился с ошибкой', 'error')
            } else if (phase === 'CANCELLED') {
                setError(null)
                toast.show('Прогон отменён', 'info')
            } else {
                setError(null)
            }
            void loadHistory()
        }
        return st
    }, [loadHistory, toast])

    useEffect(() => {
        if (!runId || !isActive) return
        let stopped = false
        const loop = async () => {
            while (!stopped) {
                try {
                    const st = await poll(runId)
                    pollFailStreakRef.current = 0
                    const phase = String(st.status || '').toUpperCase()
                    if (phase === 'SUCCESS' || phase === 'FAILED' || phase === 'CANCELLED') return
                } catch (e) {
                    pollFailStreakRef.current += 1
                    if (pollFailStreakRef.current === 5) {
                        toast.show(
                            `Не удаётся получить статус прогона: ${fmtErr(e)}. Повторяем опрос…`,
                            'error',
                        )
                    }
                }
                await new Promise(r => window.setTimeout(r, 1500))
            }
        }
        void loop()
        return () => {
            stopped = true
        }
    }, [runId, isActive, poll, toast])

    const onRun = async () => {
        if (!robot) return
        if (scalperBlocked) {
            toast.show('Scalper нельзя прогнать на свечах — нужны тики и order-flow', 'error')
            return
        }
        if (fromDate > toDate) {
            toast.show('Дата окончания должна быть позже даты начала', 'error')
            return
        }
        setError(null)
        setStatus(null)
        setRunning(true)
        try {
            const wrap = await robotV2Service.runBacktest({
                config: robot.config,
                from_date: `${fromDate}T00:00:00Z`,
                to_date: `${toDate}T23:59:59Z`,
                initial_capital: capital,
                robotId: robot.id,
                tokenId: tokenIdOf(robot),
                asyncExecution: true,
            })
            if (wrap.status === 202) {
                const rid = wrap.data.run_id
                setRunId(rid)
                syncRunQuery(rid)
                toast.show(`Прогон #${rid} запущен`, 'success')
            } else {
                const rid = wrap.data.run_id ?? null
                setRunId(rid)
                syncRunQuery(rid)
                setStatus(wrap.data)
                setRunning(false)
            }
        } catch (e) {
            setRunning(false)
            setError(fmtErr(e))
            toast.show(fmtErr(e), 'error')
        }
    }

    const onCancel = async () => {
        if (!runId) return
        setCancelling(true)
        try {
            await robotV2Service.cancelBacktestRun(runId)
            toast.show('Отмена запрошена…', 'info')
            for (let i = 0; i < 45; i++) {
                const st = await poll(runId)
                const phase = String(st.status || '').toUpperCase()
                if (phase === 'CANCELLED' || phase === 'FAILED' || phase === 'SUCCESS') return
                await new Promise(r => window.setTimeout(r, 1000))
            }
            toast.show('Отмена отправлена — статус обновится при следующем опросе', 'info')
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setCancelling(false)
        }
    }

    const toggleSelect = (id: number) => {
        setSelectedIds(prev => {
            if (prev.includes(id)) return prev.filter(x => x !== id)
            if (prev.length >= 2) return [prev[1], id]
            return [...prev, id]
        })
        setCompare(null)
    }

    const onCompare = async () => {
        if (selectedIds.length !== 2) return
        try {
            const data = await robotV2Service.compareBacktestRuns(selectedIds[0], selectedIds[1])
            setCompare(data)
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        }
    }

    const syncRunQuery = useCallback(
        (id: number | null) => {
            const next = new URLSearchParams(searchParams)
            if (id != null && Number.isFinite(id) && id > 0) {
                next.set('run', String(id))
            } else {
                next.delete('run')
            }
            setSearchParams(next, { replace: true })
        },
        [searchParams, setSearchParams],
    )

    const openHistoryRun = useCallback(
        async (id: number, opts?: { scroll?: boolean }) => {
            setOpeningRun(true)
            try {
                const details = await robotV2Service.getBacktestRunDetails(id)
                setRunId(id)
                setStatus(details)
                syncRunQuery(id)
                const fromIso = String(details.requested_from || '').slice(0, 10)
                const toIso = String(details.requested_to || '').slice(0, 10)
                if (fromIso) setFromDate(fromIso)
                if (toIso) setToDate(toIso)
                const cap = Number(details.initial_capital)
                if (Number.isFinite(cap) && cap > 0) setCapital(cap)
                const st = String(details.status || '').toUpperCase()
                setRunning(st === 'RUNNING' || st === 'QUEUED')
                setError(st === 'FAILED' ? (details.error_message || 'Ошибка прогона') : null)
                if (opts?.scroll !== false) {
                    window.requestAnimationFrame(() => {
                        resultAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    })
                }
            } catch (e) {
                toast.show(fmtErr(e), 'error')
            } finally {
                setOpeningRun(false)
            }
        },
        [syncRunQuery, toast],
    )

    useEffect(() => {
        const raw = searchParams.get('run')
        if (!raw) return
        const qid = Number(raw)
        if (!Number.isFinite(qid) || qid <= 0) return
        if (openedFromQueryRef.current === qid) return
        if (runId === qid && status) {
            openedFromQueryRef.current = qid
            return
        }
        openedFromQueryRef.current = qid
        void openHistoryRun(qid, { scroll: false })
    }, [searchParams, openHistoryRun, runId, status])

    const ret = payload.total_return_percent ?? status?.total_return_percent ?? null
    const dd = payload.max_drawdown_percent ?? status?.max_drawdown_percent ?? null
    const finalEq = payload.final_equity ?? status?.final_equity ?? null
    // Backend also exposes these on details top-level (schemas.RobotV2BacktestDetailsResponse).
    const winRate = payload.win_rate_percent ?? status?.win_rate_percent ?? null
    const sharpe = payload.sharpe_ratio ?? status?.sharpe_ratio ?? null
    const sortino = payload.sortino_ratio ?? status?.sortino_ratio ?? null
    const calmar = payload.calmar_ratio ?? status?.calmar_ratio ?? null
    const progress = Number(status?.progress_percent ?? 0)
    const phaseLabel = status?.phase_label || status?.run_phase || (isActive ? 'Запуск…' : '')

    return (
        <div className="page" data-page="robots">
            <RobotPageChrome
                eyebrow="BACKTEST NODE"
                title={robot ? `БЭКТЕСТ #${robotId}` : `БЭКТЕСТ #${robotId}`}
                robotId={robotId}
                active="backtest"
                subtitle={
                    <p className="dashboard-hero__sub robots-v2-hero-sub">
                        Исторические свечи · {robot?.name || '…'} · {archetype || '—'}
                        {status ? (
                            <>
                                {' '}
                                <Badge variant={statusVariant(runStatus)}>{sessionStateLabel(runStatus) || runStatus || '—'}</Badge>
                            </>
                        ) : null}
                    </p>
                }
                actions={
                    isActive ? (
                        <Button
                            type="button"
                            variant="danger"
                            size="sm"
                            loading={cancelling}
                            onClick={() => void onCancel()}
                        >
                            Отменить
                        </Button>
                    ) : (
                        <Button
                            type="button"
                            size="sm"
                            loading={running}
                            disabled={scalperBlocked || !robot}
                            onClick={() => void onRun()}
                        >
                            Запустить бэктест
                        </Button>
                    )
                }
            />

            <div className="dashboard-layout">
                {loading ? (
                    <Card className="dashboard-totals-card dashboard-skeleton-card">
                        <Skeleton height="120px" />
                    </Card>
                ) : (
                    <Card className="portfolio-toolbar robots-v2-toolbar robots-v2-backtest-toolbar">
                        <div className="robots-v2-backtest-toolbar__main">
                            {scalperBlocked && (
                                <div className="robots-v2-banner robots-v2-banner--error">
                                    Scalper работает на тиках и order-flow. Бар-бэктест для этого архетипа недоступен.
                                </div>
                            )}
                            <SegmentedControl
                                className="portfolio-period-control"
                                aria-label="Период бэктеста"
                                options={[
                                    ...PRESETS.map(p => ({ value: p.id, label: p.label })),
                                    { value: 'custom', label: 'Свой' },
                                ]}
                                value={PRESETS.find(p => spanDays === p.days)?.id ?? 'custom'}
                                onChange={id => {
                                    const preset = PRESETS.find(p => p.id === id)
                                    if (!preset) return
                                    setFromDate(daysAgoUtc(preset.days - 1))
                                    setToDate(todayUtc())
                                }}
                            />
                            <div className="robots-v2-inline robots-v2-backtest-dates">
                                <DateRangePicker
                                    variant="fields"
                                    fromValue={fromDate ? `${fromDate}T00:00` : ''}
                                    toValue={toDate ? `${toDate}T00:00` : ''}
                                    onFromChange={v => setFromDate(v ? v.slice(0, 10) : '')}
                                    onToChange={v => setToDate(v ? v.slice(0, 10) : '')}
                                    fromLabel="С"
                                    toLabel="По"
                                    showLabel={false}
                                />
                                <label className="robots-v2-field">
                                    <span>Капитал</span>
                                    <input
                                        type="number"
                                        className="robots-v2-input"
                                        min={10}
                                        step={1000}
                                        value={capital}
                                        onChange={e => setCapital(Number(e.target.value) || 0)}
                                    />
                                </label>
                            </div>
                            <small className="robots-v2-hint">
                                Реальные свечи MOEX ISS / Bybit klines. Warmup для индикаторов подгружается до даты «С».
                                {spanDays > 0 ? ` · ${spanDays} дн.` : ''}
                                {spanDays > 180 ? ' Длинный период на мелком ТФ может занять несколько минут.' : ''}
                            </small>
                        </div>
                    </Card>
                )}

                <div ref={resultAnchorRef} />

                {(isActive || openingRun) && (
                    <RobotStageCard
                        title={openingRun ? 'Загрузка прогона…' : (phaseLabel || 'Прогон')}
                        progress={progress}
                        ariaLabel="Прогресс бэктеста"
                        meta={
                            status?.phase_units_total ? (
                                <span className="robots-v2-hint">
                                    {formatBacktestPhaseUnits(
                                        status.run_phase,
                                        status.phase_units_done ?? 0,
                                        status.phase_units_total,
                                    )}
                                </span>
                            ) : null
                        }
                    />
                )}

                {(error || (runStatus === 'FAILED' && !isActive)) && (
                    <Card className="dashboard-totals-card dashboard-error-card">
                        <p className="dashboard-empty">
                            {error || status?.error_message || 'Прогон завершился с ошибкой'}
                        </p>
                    </Card>
                )}

                {(runStatus === 'SUCCESS'
                    || (runStatus === 'CANCELLED' && !isActive && (
                        equityCurve.length > 0 || trades.length > 0 || runSignals.length > 0
                    ))) && (
                    <BacktestResultsPanel
                        key={runId ?? 'run'}
                        runId={runId}
                        runStatus={runStatus}
                        partialResult={status?.partial_result ?? (runStatus === 'CANCELLED' ? true : null)}
                        capital={capital}
                        initialCapital={Number(payload.initial_capital ?? capital)}
                        finalEquity={finalEq}
                        totalReturnPercent={ret}
                        maxDrawdownPercent={dd}
                        winRatePercent={winRate}
                        sharpeRatio={sharpe}
                        sortinoRatio={sortino}
                        calmarRatio={calmar}
                        stages={payload.stages}
                        historyStats={(payload.history_stats || null) as Record<string, unknown> | null}
                        fundingChargesTotal={
                            (payload as { funding_charges_total?: number | null }).funding_charges_total
                            ?? null
                        }
                        observability={
                            status?.observability
                            ?? (payload.observability as BacktestObservability | null | undefined)
                            ?? null
                        }
                        executionModel={
                            status?.execution_model
                            ?? (payload as { execution_model?: unknown }).execution_model
                            ?? null
                        }
                        feeSummary={feeSummary}
                        portfolioSnapshots={portfolioSnapshots}
                        narrative={narrative}
                        requestedFrom={status?.requested_from ?? fromDate}
                        requestedTo={status?.requested_to ?? toDate}
                        signalsTotal={status?.signals_total ?? null}
                        trades={trades as unknown as Array<Record<string, unknown>>}
                        chartPoints={chartPoints}
                        signals={runSignals as unknown as Array<Record<string, unknown>>}
                        orders={runOrders as unknown as Array<Record<string, unknown>>}
                        dailySummary={dailySummary as unknown as Array<Record<string, unknown>>}
                        chartRef={chartRef}
                        seriesRef={seriesRef}
                    />
                )}

                {runStatus === 'CANCELLED' && !isActive
                    && equityCurve.length === 0 && trades.length === 0 && runSignals.length === 0 && (
                    <Card className="dashboard-totals-card">
                        <p className="dashboard-empty">Прогон отменён — артефактов нет</p>
                    </Card>
                )}

                {!loading && robot && Number.isFinite(robotId) && (
                    <RobotV2OptimizationCard
                        robotId={robotId}
                        fromDate={fromDate}
                        toDate={toDate}
                        initialCapital={capital}
                        disabled={scalperBlocked || isActive}
                        onOpenRun={id => void openHistoryRun(id)}
                    />
                )}

                <BacktestHistoryCard
                    history={history}
                    historyLoading={historyLoading}
                    historyError={historyError}
                    selectedIds={selectedIds}
                    activeRunId={runId}
                    compare={compare}
                    onRefresh={() => void loadHistory()}
                    onCompare={() => void onCompare()}
                    onToggleSelect={toggleSelect}
                    onOpenRun={id => void openHistoryRun(id)}
                    statusVariant={statusVariant}
                />
            </div>
        </div>
    )
}
