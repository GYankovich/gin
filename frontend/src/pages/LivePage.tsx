import React, { useEffect, useState, useCallback, useRef } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { EventFeed, type FeedEvent } from '@/components/ui/EventFeed'
import { Skeleton } from '@/components/ui/Skeleton'
import { Chart, type IChartApi, type Time } from '@/components/ui/Chart'
import { CandlestickSeries } from 'lightweight-charts'
import { useWebSocket } from '@/hooks/useWebSocket'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'

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

    useEffect(() => {
        robotService.list().then(r => { setRobots(r.items); setLoading(false) }).catch(() => setLoading(false))
    }, [])

    const wsUrl = selectedRobot ? `ws://${window.location.host}/ws/live?robot_id=${selectedRobot}` : ''

    const onWsMessage = useCallback((data: any) => {
        if (!data || !data.type) return

        if (data.type === 'price') {
            setPrices(prev => ({
                ...prev,
                [data.figi]: { price: data.price, change: data.change ?? 0, time: data.time ?? new Date().toLocaleTimeString('ru-RU') },
            }))
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
    }, [])

    const { connected } = useWebSocket({ url: wsUrl, onMessage: onWsMessage, enabled: !!selectedRobot })

    const handleStart = async () => {
        if (!selectedRobot) return
        try { await robotService.changeStatus(selectedRobot, 1) } catch { /* */ }
    }

    const handleStop = async () => {
        if (!selectedRobot) return
        try { await robotService.changeStatus(selectedRobot, 0) } catch { /* */ }
    }

    const onCandleChartReady = useCallback((chart: IChartApi) => {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        chart.addSeries(CandlestickSeries, {
            upColor: isDark ? '#00ffaa' : '#00aa66',
            downColor: isDark ? '#ff3366' : '#cc3333',
            borderUpColor: isDark ? '#00ffaa' : '#00aa66',
            borderDownColor: isDark ? '#ff3366' : '#cc3333',
            wickUpColor: isDark ? '#00ffaa' : '#00aa66',
            wickDownColor: isDark ? '#ff3366' : '#cc3333',
        })
    }, [])

    const priceRows = Object.entries(prices).map(([figi, d]) => ({ figi, ...d }))
    const priceColumns: Column<any>[] = [
        { key: 'figi', header: 'FIGI' },
        { key: 'price', header: 'Цена', align: 'right', render: r => <span className="mono">{r.price?.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}</span> },
        {
            key: 'change', header: 'Изм. %', align: 'right',
            render: r => <span className={r.change >= 0 ? 'color-up' : 'color-down'}>{r.change >= 0 ? '+' : ''}{r.change?.toFixed(2)}%</span>,
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
                <select className="form-select" value={selectedRobot ?? ''} onChange={e => setSelectedRobot(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Выберите робота</option>
                    {robots.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                </select>
                <Badge variant={connected ? 'up' : 'neutral'}>
                    <span className={`status-dot status-dot--${connected ? 'active' : 'inactive'}`} />
                    {connected ? 'Онлайн' : 'Оффлайн'}
                </Badge>
                <Button variant="primary" size="sm" onClick={handleStart} disabled={!selectedRobot}>Старт</Button>
                <Button variant="danger" size="sm" onClick={handleStop} disabled={!selectedRobot}>Стоп</Button>
            </div>

            <div className="live-grid">
                <div className="live-grid__chart">
                    <Card>
                        <h3 className="card__section-title">Свечной график</h3>
                        <Chart height={420} onReady={onCandleChartReady} key={selectedRobot} />
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
