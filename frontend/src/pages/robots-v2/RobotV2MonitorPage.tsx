import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { KpiTile } from '@/components/ui/KpiTile'
import { Chart } from '@/components/ui/Chart'
import { useToast } from '@/components/ui/Toast'
import { useWebSocket } from '@/hooks/useWebSocket'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2, RobotV2Status } from '@/types/robotV2'
import type { IChartApi, ISeriesApi, Time } from '@/components/ui/Chart'
import { LineSeries } from 'lightweight-charts'

function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    return err?.message || 'Ошибка'
}

function pick<T>(obj: RobotV2Status, camel: keyof RobotV2Status, snake: string): T | undefined {
    const anyObj = obj as Record<string, unknown>
    return (obj[camel] ?? anyObj[snake]) as T | undefined
}

export default function RobotV2MonitorPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const navigate = useNavigate()
    const toast = useToast()

    const [robot, setRobot] = useState<RobotV2 | null>(null)
    const [status, setStatus] = useState<RobotV2Status | null>(null)
    const [events, setEvents] = useState<Array<{ ts: string; type: string; payload: unknown }>>([])
    const [equityPoints, setEquityPoints] = useState<Array<{ time: Time; value: number }>>([])
    const [busy, setBusy] = useState(false)

    const chartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)

    const refresh = useCallback(async () => {
        if (!Number.isFinite(robotId)) return
        try {
            const [r, s] = await Promise.all([
                robotV2Service.getById(robotId),
                robotV2Service.getStatus(robotId),
            ])
            setRobot(r)
            setStatus(s)
            const curve = pick<Array<{ time?: string; equity?: number }>>(s, 'equityCurve', 'equity_curve')
            if (Array.isArray(curve) && curve.length > 0) {
                const points = curve
                    .map(p => {
                        const eq = Number(p.equity)
                        if (!Number.isFinite(eq)) return null
                        let tSec: number
                        if (p.time) {
                            const ms = Date.parse(String(p.time))
                            tSec = Number.isFinite(ms) ? Math.floor(ms / 1000) : Math.floor(Date.now() / 1000)
                        } else {
                            tSec = Math.floor(Date.now() / 1000)
                        }
                        return { time: tSec as Time, value: eq }
                    })
                    .filter((x): x is { time: Time; value: number } => x != null)
                if (points.length) {
                    setEquityPoints(points.slice(-200))
                }
            } else {
                const eq = pick<number>(s, 'equity', 'equity')
                if (eq != null && Number.isFinite(eq)) {
                    const t = Math.floor(Date.now() / 1000) as Time
                    setEquityPoints(prev => {
                        const next = [...prev, { time: t, value: Number(eq) }]
                        return next.slice(-200)
                    })
                }
            }
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        }
    }, [robotId, toast])

    useEffect(() => {
        void refresh()
        const timer = window.setInterval(() => void refresh(), 5000)
        return () => window.clearInterval(timer)
    }, [refresh])

    useEffect(() => {
        const series = seriesRef.current
        if (!series || equityPoints.length === 0) return
        series.setData(equityPoints)
    }, [equityPoints])

    const wsUrl = Number.isFinite(robotId) ? robotV2Service.buildStreamUrl(robotId) : ''
    const sessionRunning =
        String(pick(status || ({} as RobotV2Status), 'sessionState', 'session_state') || '').toUpperCase() === 'RUNNING'
    useWebSocket({
        url: wsUrl,
        enabled: Boolean(wsUrl) && sessionRunning,
        onMessage: (msg: { type?: string; robotId?: number; [k: string]: unknown }) => {
            if (!msg || typeof msg !== 'object') return
            const type = String(msg.type || 'event')
            if (type === 'ping') return
            setEvents(prev => [{ ts: new Date().toISOString(), type, payload: msg }, ...prev].slice(0, 80))
            if (type === 'equity_snapshot' && Array.isArray(msg.points)) {
                const points = (msg.points as Array<{ time?: string; equity?: number }>)
                    .map(p => {
                        const eq = Number(p.equity)
                        if (!Number.isFinite(eq)) return null
                        const ms = p.time ? Date.parse(String(p.time)) : NaN
                        const tSec = Number.isFinite(ms) ? Math.floor(ms / 1000) : Math.floor(Date.now() / 1000)
                        return { time: tSec as Time, value: eq }
                    })
                    .filter((x): x is { time: Time; value: number } => x != null)
                if (points.length) setEquityPoints(points.slice(-200))
                return
            }
            if (type === 'cycle' && typeof msg.equity === 'number') {
                const t = Math.floor(Date.now() / 1000) as Time
                setEquityPoints(prev => [...prev, { time: t, value: Number(msg.equity) }].slice(-200))
            }
        },
    })

    const onStart = async () => {
        setBusy(true)
        try {
            const risk = (robot?.config?.risk || {}) as Record<string, unknown>
            await robotV2Service.start(robotId, { virtualCapital: Number(risk.capital || 100_000) })
            toast.show('Started', 'success')
            await refresh()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusy(false)
        }
    }

    const onStop = async (mode: 'soft' | 'hard') => {
        setBusy(true)
        try {
            await robotV2Service.stop(robotId, mode)
            toast.show(`Stopped (${mode})`, 'info')
            await refresh()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusy(false)
        }
    }

    const equity = pick<number>(status || ({} as RobotV2Status), 'equity', 'equity') ?? 0
    const cash = pick<number>(status || ({} as RobotV2Status), 'cash', 'cash') ?? 0
    const cycle = pick<number>(status || ({} as RobotV2Status), 'cycleNumber', 'cycle_number') ?? 0
    const sessionState = pick<string>(status || ({} as RobotV2Status), 'sessionState', 'session_state') || '—'
    const isRunning = String(sessionState).toUpperCase() === 'RUNNING'
    const positions = pick<Array<Record<string, unknown>>>(status || ({} as RobotV2Status), 'openPositions', 'open_positions') || []
    const decisions = pick<Array<Record<string, unknown>>>(status || ({} as RobotV2Status), 'decisions', 'decisions') || []
    const universe = pick<string[]>(status || ({} as RobotV2Status), 'universe', 'universe') || []

    return (
        <div className="robots-v2-page" data-page="robots-v2">
            <header className="robots-v2-page__header">
                <div>
                    <button type="button" className="robots-v2-linkish" onClick={() => navigate('/robots-v2')}>
                        ← Флот v2
                    </button>
                    <h1 className="robots-v2-page__title">{robot?.name || `Robot #${robotId}`}</h1>
                    <p className="robots-v2-page__subtitle">
                        Monitor · session {sessionState} ·{' '}
                        <Badge variant={isRunning ? 'up' : 'neutral'}>
                            {isRunning ? 'RUNNING' : 'IDLE'}
                        </Badge>
                    </p>
                </div>
                <div className="robots-v2-page__actions">
                    <Button type="button" variant="ghost" onClick={() => navigate(`/robots-v2/edit/${robotId}`)}>
                        Edit
                    </Button>
                    <Button type="button" variant="ghost" onClick={() => navigate(`/robots-v2/${robotId}/logs`)}>
                        Logs
                    </Button>
                    {isRunning ? (
                        <>
                            <Button type="button" variant="secondary" loading={busy} onClick={() => void onStop('soft')}>
                                Soft stop
                            </Button>
                            <Button type="button" variant="danger" loading={busy} onClick={() => void onStop('hard')}>
                                Hard stop
                            </Button>
                        </>
                    ) : (
                        <Button type="button" loading={busy} onClick={() => void onStart()}>
                            Start
                        </Button>
                    )}
                </div>
            </header>

            <div className="robots-v2-kpi-row">
                <KpiTile label="Equity" value={equity} format={v => v.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} />
                <KpiTile label="Cash" value={cash} format={v => v.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} />
                <KpiTile label="Cycle" value={cycle} />
                <KpiTile label="Positions" value={positions.length} />
            </div>

            <div className="robots-v2-monitor-grid">
                <Card className="robots-v2-monitor-chart">
                    <h3 className="dashboard-panel-title">Equity</h3>
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
                            if (equityPoints.length) series.setData(equityPoints)
                        }}
                    />
                </Card>

                <Card>
                    <h3 className="dashboard-panel-title">Positions</h3>
                    {positions.length === 0 ? (
                        <p className="robots-v2-hint">Нет открытых позиций</p>
                    ) : (
                        <table className="robots-v2-table">
                            <thead>
                                <tr>
                                    <th>Ticker</th>
                                    <th>Side</th>
                                    <th>Qty</th>
                                    <th>Entry</th>
                                </tr>
                            </thead>
                            <tbody>
                                {positions.map((p, i) => (
                                    <tr key={`${p.ticker}-${i}`}>
                                        <td>{String(p.ticker ?? p.figi ?? '—')}</td>
                                        <td>{String(p.side ?? '—')}</td>
                                        <td className="mono">{String(p.quantity ?? '—')}</td>
                                        <td className="mono">{String(p.entry_price ?? p.avg_entry_price ?? '—')}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Card>

                <Card>
                    <h3 className="dashboard-panel-title">Universe</h3>
                    <div className="robots-v2-chip-row">
                        {universe.length === 0 && <span className="robots-v2-hint">—</span>}
                        {universe.map(t => (
                            <span key={t} className="robots-v2-chip robots-v2-chip--on">{t}</span>
                        ))}
                    </div>
                </Card>

                <Card>
                    <h3 className="dashboard-panel-title">Decisions</h3>
                    <ul className="robots-v2-event-list">
                        {decisions.slice(0, 12).map((d, i) => (
                            <li key={i}>
                                <strong>{String(d.code ?? '—')}</strong> {String(d.message ?? '')}{' '}
                                {d.ticker ? `(${String(d.ticker)})` : ''}
                            </li>
                        ))}
                        {decisions.length === 0 && <li className="robots-v2-hint">Пока нет решений риска</li>}
                    </ul>
                </Card>

                <Card className="robots-v2-monitor-events">
                    <h3 className="dashboard-panel-title">Live stream</h3>
                    <ul className="robots-v2-event-list">
                        {events.map((ev, i) => (
                            <li key={`${ev.ts}-${i}`}>
                                <span className="mono">{new Date(ev.ts).toLocaleTimeString('ru-RU')}</span>{' '}
                                <Badge variant="cyan">{ev.type}</Badge>
                            </li>
                        ))}
                        {events.length === 0 && <li className="robots-v2-hint">Ожидание WS-событий…</li>}
                    </ul>
                </Card>
            </div>
        </div>
    )
}
