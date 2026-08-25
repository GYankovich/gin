import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faTowerBroadcast } from '@fortawesome/free-solid-svg-icons'
import { LineSeries } from 'lightweight-charts'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { Chart } from '@/components/ui/Chart'
import { PageHero } from '@/components/ui/PageHero'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Skeleton } from '@/components/ui/Skeleton'
import { StatTile } from '@/components/ui/StatTile'
import { useToast } from '@/components/ui/Toast'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2 } from '@/types/robotV2'
import type { RobotBacktestRunDetails, RobotHistoryBacktestResult } from '@/types/robot'
import type { IChartApi, ISeriesApi, Time } from '@/components/ui/Chart'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'

function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    return err?.message || 'Ошибка'
}

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

function fmtMoney(v: number): string {
    return v.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}

function fmtPct(v: number | null | undefined): string {
    if (v == null || !Number.isFinite(v)) return '—'
    return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
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
    const navigate = useNavigate()
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
        try {
            const data = await robotV2Service.listBacktestRuns({ robotId, limit: 30 })
            setHistory(data.items || [])
        } catch {
            /* history is best-effort until migration */
        }
    }, [robotId])

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
            if (phase === 'FAILED') {
                setError(details.error_message || 'Прогон завершился с ошибкой')
            }
            void loadHistory()
        }
        return st
    }, [loadHistory])

    useEffect(() => {
        if (!runId || !isActive) return
        let stopped = false
        const loop = async () => {
            while (!stopped) {
                try {
                    const st = await poll(runId)
                    const phase = String(st.status || '').toUpperCase()
                    if (phase === 'SUCCESS' || phase === 'FAILED' || phase === 'CANCELLED') return
                } catch {
                    /* keep polling — status GET may time out while the worker holds CPU */
                }
                await new Promise(r => window.setTimeout(r, 1500))
            }
        }
        void loop()
        return () => {
            stopped = true
        }
    }, [runId, isActive, poll])

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
                toast.show(`Прогон #${rid} запущен`, 'success')
            } else {
                setRunId(wrap.data.run_id ?? null)
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
            toast.show('Отмена запрошена', 'info')
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

    const openHistoryRun = async (id: number) => {
        try {
            const details = await robotV2Service.getBacktestRunDetails(id)
            setRunId(id)
            setStatus(details)
            const st = String(details.status || '').toUpperCase()
            setRunning(st === 'RUNNING' || st === 'QUEUED')
            setError(st === 'FAILED' ? (details.error_message || 'Ошибка прогона') : null)
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        }
    }

    const ret = payload.total_return_percent ?? status?.total_return_percent ?? null
    const dd = payload.max_drawdown_percent ?? status?.max_drawdown_percent ?? null
    const finalEq = payload.final_equity ?? status?.final_equity ?? null
    const progress = Number(status?.progress_percent ?? 0)
    const phaseLabel = status?.phase_label || status?.run_phase || (isActive ? 'Запуск…' : '')

    return (
        <div className="page" data-page="robots-v2">
            <PageHero
                eyebrow="BACKTEST NODE"
                title={robot ? `БЭКТЕСТ #${robotId}` : `БЭКТЕСТ #${robotId}`}
                subtitle={
                    <p className="dashboard-hero__sub robots-v2-hero-sub">
                        Исторические свечи · {robot?.name || '…'} · {archetype || '—'}
                        {status ? (
                            <>
                                {' '}
                                <Badge variant={statusVariant(runStatus)}>{runStatus || '—'}</Badge>
                            </>
                        ) : null}
                    </p>
                }
                actions={
                    <>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate('/robots-v2')}
                        >
                            Флот
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate(`/robots-v2/${robotId}/monitor`)}
                        >
                            <FontAwesomeIcon icon={faTowerBroadcast} />
                            Лайв
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate(`/robots-v2/edit/${robotId}`)}
                        >
                            Правка
                        </Button>
                    </>
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
                                options={PRESETS.map(p => ({ value: p.id, label: p.label }))}
                                value={PRESETS.find(p => spanDays === p.days)?.id ?? 'custom'}
                                onChange={id => {
                                    const preset = PRESETS.find(p => p.id === id)
                                    if (!preset) return
                                    setFromDate(daysAgoUtc(preset.days - 1))
                                    setToDate(todayUtc())
                                }}
                            />
                            <div className="robots-v2-inline robots-v2-backtest-dates">
                                <label className="robots-v2-field">
                                    <span>С</span>
                                    <input
                                        type="date"
                                        className="robots-v2-input"
                                        value={fromDate}
                                        max={toDate}
                                        onChange={e => setFromDate(e.target.value)}
                                    />
                                </label>
                                <label className="robots-v2-field">
                                    <span>По</span>
                                    <input
                                        type="date"
                                        className="robots-v2-input"
                                        value={toDate}
                                        min={fromDate}
                                        max={todayUtc()}
                                        onChange={e => setToDate(e.target.value)}
                                    />
                                </label>
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
                        <div className="robots-v2-toolbar__actions">
                            {isActive ? (
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
                            )}
                        </div>
                    </Card>
                )}

                {isActive && (
                    <Card className="dashboard-totals-card robots-v2-stage-card">
                        <div className="dashboard-totals-card__head robots-v2-stage-card__head">
                            <h3 className="dashboard-panel-title">{phaseLabel || 'Прогон'}</h3>
                            <span className="robots-v2-hint">{progress.toFixed(0)}%</span>
                        </div>
                        <div className="robots-v2-stage-progress" aria-label="Прогресс бэктеста">
                            <div
                                className="robots-v2-stage-progress__bar"
                                style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
                            />
                        </div>
                        <div className="robots-v2-stage-meta">
                            {status?.phase_units_total ? (
                                <span className="robots-v2-hint">
                                    {status.phase_units_done ?? 0} / {status.phase_units_total}
                                </span>
                            ) : null}
                        </div>
                    </Card>
                )}

                {error && (
                    <Card className="dashboard-totals-card dashboard-error-card">
                        <p className="dashboard-empty">{error}</p>
                    </Card>
                )}

                {runStatus === 'SUCCESS' && (
                    <>
                        <Card className="dashboard-totals-card">
                            <div className="dashboard-totals-card__head">
                                <h3 className="dashboard-panel-title">Результат</h3>
                            </div>
                            <div className="portfolio-stats-grid dashboard-summary-grid">
                                <StatTile label="Капитал" value={fmtMoney(payload.initial_capital ?? capital)} />
                                <StatTile
                                    label="Equity"
                                    value={fmtMoney(finalEq ?? 0)}
                                    valueClassName={
                                        (finalEq ?? 0) >= (payload.initial_capital ?? capital) ? 'color-up' : 'color-down'
                                    }
                                />
                                <StatTile
                                    label="Доходность"
                                    value={fmtPct(ret)}
                                    valueClassName={(ret ?? 0) >= 0 ? 'color-up' : 'color-down'}
                                />
                                <StatTile
                                    label="Max DD"
                                    value={dd == null ? '—' : `${dd.toFixed(2)}%`}
                                    valueClassName="color-down"
                                />
                                <StatTile label="Сделки" value={trades.length} />
                            </div>
                            {payload.stages && payload.stages.length > 0 && (
                                <p className="robots-v2-hint robots-v2-universe-caption">
                                    {payload.stages.join(' · ')}
                                </p>
                            )}
                        </Card>

                        <Card className="dashboard-assets-card robots-v2-monitor-chart">
                            <div className="dashboard-assets-card__head">
                                <h3 className="dashboard-panel-title">График equity</h3>
                            </div>
                            {chartPoints.length === 0 ? (
                                <p className="robots-v2-hint">Нет точек equity за выбранный период</p>
                            ) : (
                                <Chart
                                    height={280}
                                    onReady={chart => {
                                        if (!chart) {
                                            chartRef.current = null
                                            seriesRef.current = null
                                            return
                                        }
                                        chartRef.current = chart
                                        const series = chart.addSeries(LineSeries, {
                                            color: '#3dd68c',
                                            lineWidth: 2,
                                        })
                                        seriesRef.current = series
                                        if (chartPoints.length) series.setData(chartPoints)
                                    }}
                                />
                            )}
                        </Card>

                        <Card className="dashboard-assets-card">
                            <div className="dashboard-assets-card__head">
                                <h3 className="dashboard-panel-title">Сделки</h3>
                                <span className="robots-v2-hint">{trades.length}</span>
                            </div>
                            {trades.length === 0 ? (
                                <p className="robots-v2-hint">Сделок не было — проверьте период, расписание и сигналы стратегии</p>
                            ) : (
                                <div className="robots-v2-scan-table-wrap">
                                    <table className="robots-v2-table robots-v2-scan-table">
                                        <thead>
                                            <tr>
                                                <th>Время</th>
                                                <th>Тикер</th>
                                                <th>Сторона</th>
                                                <th>Причина</th>
                                                <th>Цена</th>
                                                <th>Кол-во</th>
                                                <th>Комиссия</th>
                                                <th>PnL</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {trades.map(t => {
                                                const pnl = t.pnl_net
                                                const tone =
                                                    pnl == null ? 'neutral' : pnl >= 0 ? 'up' : 'down'
                                                return (
                                                    <tr key={t.id}>
                                                        <td className="mono">
                                                            {t.bar_time ? t.bar_time.replace('T', ' ').slice(0, 19) : '—'}
                                                        </td>
                                                        <td>{t.figi}</td>
                                                        <td>{t.side}</td>
                                                        <td className="robots-v2-scan-reason">{tradeReasonLabel(t.reason || t.kind)}</td>
                                                        <td className="mono">{fmtMoney(t.price)}</td>
                                                        <td className="mono">{t.quantity}</td>
                                                        <td className="mono">{fmtMoney(t.commission)}</td>
                                                        <td className={`mono robots-v2-pnl--${tone}`}>
                                                            {pnl == null ? '—' : fmtMoney(pnl)}
                                                        </td>
                                                    </tr>
                                                )
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Card>

                        <CollapsibleSection
                            title="Сигналы"
                            badge={
                                runSignals.length > 0 ? (
                                    <span className="robots-v2-hint">{runSignals.length}</span>
                                ) : undefined
                            }
                            className="dashboard-assets-card"
                        >
                            {runSignals.length === 0 ? (
                                <p className="robots-v2-hint">Нет сигналов за период</p>
                            ) : (
                                <div className="robots-v2-scan-table-wrap">
                                    <table className="robots-v2-table robots-v2-scan-table">
                                        <thead>
                                            <tr>
                                                <th>Время</th>
                                                <th>Тикер</th>
                                                <th>Сигнал</th>
                                                <th>Цена</th>
                                                <th>Исполнен</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {runSignals.map((s, i) => (
                                                <tr key={String(s.id ?? i)}>
                                                    <td className="mono">
                                                        {s.signal_time
                                                            ? new Date(String(s.signal_time)).toLocaleString('ru-RU')
                                                            : s.created_at
                                                                ? new Date(String(s.created_at)).toLocaleString('ru-RU')
                                                                : '—'}
                                                    </td>
                                                    <td>{String(s.figi ?? s.ticker ?? '—')}</td>
                                                    <td>{String(s.signal_type ?? s.kind ?? '—')}</td>
                                                    <td className="mono">
                                                        {s.price != null ? fmtMoney(Number(s.price)) : '—'}
                                                    </td>
                                                    <td>{s.was_executed ? 'Да' : 'Нет'}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </CollapsibleSection>

                        <CollapsibleSection
                            title="Ордера"
                            badge={
                                runOrders.length > 0 ? (
                                    <span className="robots-v2-hint">{runOrders.length}</span>
                                ) : undefined
                            }
                            className="dashboard-assets-card"
                        >
                            {runOrders.length === 0 ? (
                                <p className="robots-v2-hint">Нет ордеров за период</p>
                            ) : (
                                <div className="robots-v2-scan-table-wrap">
                                    <table className="robots-v2-table robots-v2-scan-table">
                                        <thead>
                                            <tr>
                                                <th>Время</th>
                                                <th>Тикер</th>
                                                <th>Сторона</th>
                                                <th>Статус</th>
                                                <th>Кол-во</th>
                                                <th>Цена</th>
                                                <th>PnL</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {runOrders.map((o, i) => (
                                                <tr key={String(o.id ?? i)}>
                                                    <td className="mono">
                                                        {o.signal_time
                                                            ? new Date(String(o.signal_time)).toLocaleString('ru-RU')
                                                            : o.submitted_at
                                                                ? new Date(String(o.submitted_at)).toLocaleString('ru-RU')
                                                                : '—'}
                                                    </td>
                                                    <td>{String(o.figi ?? o.ticker ?? '—')}</td>
                                                    <td>{String(o.side ?? '—').toUpperCase()}</td>
                                                    <td>{String(o.status ?? '—')}</td>
                                                    <td className="mono">{Number(o.quantity ?? 0).toFixed(2)}</td>
                                                    <td className="mono">
                                                        {o.executed_price != null
                                                            ? fmtMoney(Number(o.executed_price))
                                                            : o.price != null
                                                                ? fmtMoney(Number(o.price))
                                                                : '—'}
                                                    </td>
                                                    <td className="mono">
                                                        {o.pnl_net != null ? fmtMoney(Number(o.pnl_net)) : '—'}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </CollapsibleSection>

                        <CollapsibleSection
                            title="Дневная сводка"
                            badge={
                                dailySummary.length > 0 ? (
                                    <span className="robots-v2-hint">{dailySummary.length}</span>
                                ) : undefined
                            }
                            className="dashboard-assets-card"
                        >
                            {dailySummary.length === 0 ? (
                                <p className="robots-v2-hint">Нет дневной разбивки</p>
                            ) : (
                                <div className="robots-v2-scan-table-wrap">
                                    <table className="robots-v2-table robots-v2-scan-table">
                                        <thead>
                                            <tr>
                                                <th>Дата</th>
                                                <th>Сигналы</th>
                                                <th>Исполнено</th>
                                                <th>Сделки</th>
                                                <th>Accept</th>
                                                <th>Reject</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {dailySummary.map((row, i) => (
                                                <tr key={String(row.date ?? i)}>
                                                    <td className="mono">{String(row.date ?? '—')}</td>
                                                    <td className="mono">{String(row.signals_total ?? '—')}</td>
                                                    <td className="mono">{String(row.signals_executed ?? '—')}</td>
                                                    <td className="mono">{String(row.trades_total ?? '—')}</td>
                                                    <td className="mono">{String(row.candidates_accept ?? '—')}</td>
                                                    <td className="mono">{String(row.candidates_reject ?? '—')}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </CollapsibleSection>
                    </>
                )}

                <Card className="dashboard-assets-card">
                    <div className="dashboard-assets-card__head">
                        <h3 className="dashboard-panel-title">История прогонов</h3>
                        <div className="robots-v2-chip-row">
                            <Button type="button" size="sm" variant="ghost" onClick={() => void loadHistory()}>
                                Refresh
                            </Button>
                            <Button
                                type="button"
                                size="sm"
                                disabled={selectedIds.length !== 2}
                                onClick={() => void onCompare()}
                            >
                                Сравнить
                            </Button>
                        </div>
                    </div>
                    {history.length === 0 ? (
                        <p className="robots-v2-hint">Сохранённых прогонов пока нет</p>
                    ) : (
                        <div className="robots-v2-scan-table-wrap">
                            <table className="robots-v2-table robots-v2-scan-table">
                                <thead>
                                    <tr>
                                        <th />
                                        <th>#</th>
                                        <th>Статус</th>
                                        <th>Период</th>
                                        <th>Капитал</th>
                                        <th>Доходность</th>
                                        <th>Max DD</th>
                                        <th>Сделки</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {history.map(row => {
                                        const on = selectedIds.includes(row.run_id)
                                        const retH = row.total_return_percent
                                        return (
                                            <tr key={row.run_id}>
                                                <td>
                                                    <input
                                                        type="checkbox"
                                                        checked={on}
                                                        onChange={() => toggleSelect(row.run_id)}
                                                    />
                                                </td>
                                                <td>
                                                    <button
                                                        type="button"
                                                        className="robots-v2-chip"
                                                        onClick={() => void openHistoryRun(row.run_id)}
                                                    >
                                                        {row.run_id}
                                                    </button>
                                                </td>
                                                <td>
                                                    <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
                                                </td>
                                                <td className="mono">
                                                    {String(row.requested_from).slice(0, 10)} → {String(row.requested_to).slice(0, 10)}
                                                </td>
                                                <td className="mono">{fmtMoney(row.initial_capital)}</td>
                                                <td className={`mono ${(retH ?? 0) >= 0 ? 'robots-v2-pnl--up' : 'robots-v2-pnl--down'}`}>
                                                    {fmtPct(retH)}
                                                </td>
                                                <td className="mono">
                                                    {row.max_drawdown_percent == null ? '—' : `${row.max_drawdown_percent.toFixed(2)}%`}
                                                </td>
                                                <td className="mono">{row.trades_total}</td>
                                            </tr>
                                        )
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                    {compare && (
                        <div className="robots-v2-form" style={{ marginTop: 'var(--space-3)' }}>
                            <p className="robots-v2-hint">
                                Сравнение #{compare.base_run_id} → #{compare.compare_run_id} (разница = compare − base)
                            </p>
                            <div className="portfolio-stats-grid dashboard-summary-grid">
                                {Object.entries(compare.metrics_diff).map(([key, delta]) => (
                                    <StatTile
                                        key={key}
                                        label={key.replace(/_/g, ' ')}
                                        value={
                                            delta == null
                                                ? '—'
                                                : key.includes('percent')
                                                    ? fmtPct(delta)
                                                    : fmtMoney(delta)
                                        }
                                        valueClassName={(delta ?? 0) >= 0 ? 'color-up' : 'color-down'}
                                    />
                                ))}
                            </div>
                            {Object.keys(compare.config_diff).length > 0 ? (
                                <div className="robots-v2-scan-table-wrap" style={{ marginTop: 'var(--space-2)' }}>
                                    <table className="robots-v2-table robots-v2-scan-table">
                                        <thead>
                                            <tr>
                                                <th>Параметр</th>
                                                <th>#{compare.base_run_id}</th>
                                                <th>#{compare.compare_run_id}</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {Object.entries(compare.config_diff).map(([path, pair]) => (
                                                <tr key={path}>
                                                    <td className="robots-v2-scan-reason">{path}</td>
                                                    <td className="mono">{JSON.stringify(pair.base)}</td>
                                                    <td className="mono">{JSON.stringify(pair.compare)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            ) : (
                                <p className="robots-v2-hint">Конфиги совпадают — отличаются период/капитал или случайность исполнения</p>
                            )}
                        </div>
                    )}
                </Card>
            </div>
        </div>
    )
}
