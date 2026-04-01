import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Select } from '@/components/ui/Select'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { EventFeed, type FeedEvent } from '@/components/ui/EventFeed'
import { Skeleton } from '@/components/ui/Skeleton'
import { Chart, type IChartApi, type Time } from '@/components/ui/Chart'
import { LineSeries } from 'lightweight-charts'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAuthStore } from '@/stores/authStore'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'

const SERIES_COLORS = [
    '#00ffff', '#ff00ff', '#00ffaa', '#ffaa00', '#aa00ff',
    '#ff3366', '#66ffcc', '#ff9900', '#33ccff', '#ff66cc',
]

interface PricePoint {
    figi: string
    price: number
    time: string
}

interface LogLine {
    id: number
    level: string
    text: string
    time: string
}

export default function LivePage() {
    const [robots, setRobots] = useState<Robot[]>([])
    const [selectedRobot, setSelectedRobot] = useState<number | null>(null)
    const [loading, setLoading] = useState(true)
    const [signals, setSignals] = useState<FeedEvent[]>([])
    const [orders, setOrders] = useState<FeedEvent[]>([])
    const [prices, setPrices] = useState<Record<string, { price: number; change: number; time: string }>>({})
    const [logs, setLogs] = useState<LogLine[]>([])
    const [logFilter, setLogFilter] = useState('ALL')
    const logIdRef = useRef(0)
    const signalIdRef = useRef(0)

    const [availableFigis, setAvailableFigis] = useState<string[]>([])
    const [selectedFigis, setSelectedFigis] = useState<string[]>([])
    const chartRef = useRef<IChartApi | null>(null)
    const seriesMapRef = useRef<Map<string, any>>(new Map())
    const priceHistoryRef = useRef<Map<string, { time: Time; value: number }[]>>(new Map())
    const initialPricesRef = useRef<Map<string, number>>(new Map())

    const token = useAuthStore(s => s.token)

    useEffect(() => {
        robotService.list().then(r => {
            const tradingActive = r.items.filter(rb => rb.type === 2 && rb.status === 1)
            setRobots(tradingActive)
            setLoading(false)
        }).catch(() => setLoading(false))
    }, [])

    const resetChartState = useCallback(() => {
        setSignals([])
        setOrders([])
        setPrices({})
        setLogs([])
        setAvailableFigis([])
        setSelectedFigis([])
        priceHistoryRef.current.clear()
        initialPricesRef.current.clear()
        seriesMapRef.current.clear()
        chartRef.current = null
    }, [])

    const wsUrl = useMemo(() => {
        if (!selectedRobot || !token) return ''
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        return `${proto}://${window.location.host}/ws/live?robot_id=${selectedRobot}&token=${encodeURIComponent(token)}`
    }, [selectedRobot, token])

    const appendPriceToChart = useCallback((figi: string, price: number, timeStr: string) => {
        if (!chartRef.current) return
        if (!selectedFigis.includes(figi) && selectedFigis.length > 0) return

        const now = Math.floor(Date.now() / 1000) as Time

        if (!priceHistoryRef.current.has(figi)) {
            priceHistoryRef.current.set(figi, [])
        }
        const hist = priceHistoryRef.current.get(figi)!
        hist.push({ time: now, value: price })

        if (!initialPricesRef.current.has(figi)) {
            initialPricesRef.current.set(figi, price)
        }

        if (!seriesMapRef.current.has(figi)) {
            const idx = availableFigis.indexOf(figi)
            const color = SERIES_COLORS[idx >= 0 ? idx % SERIES_COLORS.length : seriesMapRef.current.size % SERIES_COLORS.length]
            const series = chartRef.current.addSeries(LineSeries, {
                color,
                lineWidth: 2,
                title: figi.slice(-4),
                priceScaleId: 'right',
            })
            seriesMapRef.current.set(figi, series)
        }

        const series = seriesMapRef.current.get(figi)!
        series.update({ time: now, value: price })
    }, [availableFigis, selectedFigis])

    const onWsMessage = useCallback((data: any) => {
        if (!data || !data.type) return

        if (data.type === 'init') {
            const figis: string[] = data.figis ?? []
            setAvailableFigis(figis)
            setSelectedFigis(figis)
            return
        }

        if (data.type === 'price') {
            const figi = data.figi as string
            const price = data.price as number
            const ts = data.time
                ? new Date(data.time).toLocaleTimeString('ru-RU')
                : new Date().toLocaleTimeString('ru-RU')

            setPrices(prev => {
                const prevPrice = prev[figi]?.price ?? price
                const change = prevPrice > 0 ? ((price - prevPrice) / prevPrice) * 100 : 0
                return { ...prev, [figi]: { price, change, time: ts } }
            })

            appendPriceToChart(figi, price, ts)
        }

        if (data.type === 'signal') {
            setSignals(prev => [{
                id: ++signalIdRef.current,
                type: (data.side === 'buy' ? 'buy' : 'sell') as FeedEvent['type'],
                text: `${data.figi} @ ${data.price}`,
                time: data.time ?? new Date().toLocaleTimeString('ru-RU'),
            }, ...prev].slice(0, 100))
        }

        if (data.type === 'order') {
            setOrders(prev => [{
                id: ++signalIdRef.current,
                type: (data.status === 'filled' ? 'buy' : 'info') as FeedEvent['type'],
                text: `${data.side?.toUpperCase()} ${data.figi} x${data.quantity} — ${data.status}`,
                time: data.time ?? new Date().toLocaleTimeString('ru-RU'),
            }, ...prev].slice(0, 100))
        }

        if (data.type === 'log') {
            setLogs(prev => [...prev, {
                id: ++logIdRef.current,
                level: data.level ?? 'INFO',
                text: data.message ?? JSON.stringify(data),
                time: data.time ?? new Date().toLocaleTimeString('ru-RU'),
            }].slice(-500))
        }

        if (data.type === 'error') {
            setLogs(prev => [...prev, {
                id: ++logIdRef.current,
                level: 'ERROR',
                text: data.message ?? 'Unknown error',
                time: new Date().toLocaleTimeString('ru-RU'),
            }].slice(-500))
        }
    }, [appendPriceToChart])

    const { connected } = useWebSocket({ url: wsUrl, onMessage: onWsMessage, enabled: !!selectedRobot })

    const handleRobotChange = (val: string) => {
        const num = val ? Number(val) : null
        resetChartState()
        setSelectedRobot(num)
    }

    const handleStart = async () => {
        if (!selectedRobot) return
        try { await robotService.changeStatus(selectedRobot, 1) } catch { /* */ }
    }

    const handleStop = async () => {
        if (!selectedRobot) return
        try { await robotService.changeStatus(selectedRobot, 2) } catch { /* */ }
    }

    const toggleFigi = (figi: string) => {
        setSelectedFigis(prev => {
            const next = prev.includes(figi)
                ? prev.filter(f => f !== figi)
                : [...prev, figi]

            const chart = chartRef.current
            if (chart) {
                for (const [f, series] of seriesMapRef.current.entries()) {
                    series.applyOptions({ visible: next.includes(f) })
                }
            }
            return next
        })
    }

    const onChartReady = useCallback((chart: IChartApi) => {
        chartRef.current = chart
        chart.timeScale().applyOptions({
            timeVisible: true,
            secondsVisible: true,
            rightOffset: 5,
        })
    }, [])

    const priceRows = Object.entries(prices).map(([figi, d]) => ({ figi, ...d }))
    const priceColumns: Column<any>[] = [
        {
            key: 'figi', header: 'FIGI',
            render: r => {
                const idx = availableFigis.indexOf(r.figi)
                const color = SERIES_COLORS[idx >= 0 ? idx % SERIES_COLORS.length : 0]
                return <span style={{ borderLeft: `3px solid ${color}`, paddingLeft: 6 }}>{r.figi}</span>
            },
        },
        { key: 'price', header: 'Цена', align: 'right' as const, render: r => <span className="mono">{r.price?.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</span> },
        {
            key: 'change', header: 'Изм. %', align: 'right' as const,
            render: r => <span className={r.change >= 0 ? 'color-up' : 'color-down'}>{r.change >= 0 ? '+' : ''}{r.change?.toFixed(4)}%</span>,
        },
        { key: 'time', header: 'Время', render: r => <span className="mono">{r.time}</span> },
    ]

    const filteredLogs = logFilter === 'ALL' ? logs : logs.filter(l => l.level === logFilter)

    const downloadLog = () => {
        const text = logs.map(l => `[${l.time}] [${l.level}] ${l.text}`).join('\n')
        const blob = new Blob([text], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = 'live-log.txt'; a.click()
        URL.revokeObjectURL(url)
    }

    if (loading) return <div className="page"><h1 className="page__title">Live</h1><Skeleton height="400px" /></div>

    return (
        <div className="page">
            <h1 className="page__title">Live-режим</h1>

            <div className="portfolio-toolbar">
                <Select
                    options={[{ value: '', label: 'Выберите робота' }, ...robots.map(r => ({ value: String(r.id), label: r.name }))]}
                    value={selectedRobot != null ? String(selectedRobot) : ''}
                    onChange={handleRobotChange}
                    placeholder="Выберите робота"
                />
                <Badge variant={connected ? 'up' : 'neutral'}>
                    <span className={`status-dot status-dot--${connected ? 'active' : 'inactive'}`} />
                    {connected ? 'Онлайн' : 'Оффлайн'}
                </Badge>
                <Button variant="primary" size="sm" onClick={handleStart} disabled={!selectedRobot}>Старт</Button>
                <Button variant="danger" size="sm" onClick={handleStop} disabled={!selectedRobot}>Стоп</Button>
            </div>

            {availableFigis.length > 1 && (
                <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginBottom: 'var(--space-4)' }}>
                    {availableFigis.map((figi, idx) => {
                        const color = SERIES_COLORS[idx % SERIES_COLORS.length]
                        const active = selectedFigis.includes(figi)
                        return (
                            <button
                                key={figi}
                                className="tag"
                                style={{
                                    borderColor: color,
                                    opacity: active ? 1 : 0.4,
                                    cursor: 'pointer',
                                }}
                                onClick={() => toggleFigi(figi)}
                            >
                                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: color, marginRight: 6 }} />
                                {figi}
                            </button>
                        )
                    })}
                </div>
            )}

            {robots.length === 0 && (
                <Card>
                    <div className="event-feed__empty">Нет активных торговых роботов (тип 2, статус: включён)</div>
                </Card>
            )}

            <div className="live-grid">
                <div className="live-grid__chart">
                    <Card>
                        <h3 className="card__section-title">График цен</h3>
                        <Chart height={420} onReady={onChartReady} key={selectedRobot ?? 'empty'} />
                    </Card>
                </div>

                <div className="live-grid__feeds">
                    <Card>
                        <h3 className="card__section-title">Цены</h3>
                        <DataTable columns={priceColumns} data={priceRows} keyField="figi" emptyText="Ожидание данных..." />
                    </Card>

                    <Card>
                        <h3 className="card__section-title">Сигналы</h3>
                        <EventFeed events={signals} maxHeight="200px" />
                    </Card>

                    <Card>
                        <h3 className="card__section-title">Заявки</h3>
                        <EventFeed events={orders} maxHeight="200px" />
                    </Card>
                </div>
            </div>

            <Card className="mt-6">
                <div className="card__header">
                    <h3>Консоль логов</h3>
                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                        {['ALL', 'INFO', 'ERROR', 'DEBUG'].map(f => (
                            <button key={f} className={`tf-btn ${f === logFilter ? 'tf-btn--active' : ''}`} onClick={() => setLogFilter(f)}>{f}</button>
                        ))}
                        <Button variant="ghost" size="sm" onClick={downloadLog}>Скачать</Button>
                    </div>
                </div>
                <div className="log-console" style={{ maxHeight: '320px' }}>
                    {filteredLogs.length === 0 && <div style={{ color: 'var(--text-muted)' }}>Логи пусты</div>}
                    {filteredLogs.map(l => (
                        <div key={l.id} className={`log-console__line--${l.level.toLowerCase()}`}>
                            [{l.time}] [{l.level}] {l.text}
                        </div>
                    ))}
                </div>
            </Card>
        </div>
    )
}
