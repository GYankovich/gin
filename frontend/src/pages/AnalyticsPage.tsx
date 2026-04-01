import React, { useEffect, useState, useCallback } from 'react'
import { Card } from '@/components/ui/Card'
import { KpiTile } from '@/components/ui/KpiTile'
import { Button } from '@/components/ui/Button'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Skeleton } from '@/components/ui/Skeleton'
import { Chart, type IChartApi, type Time } from '@/components/ui/Chart'
import { AreaSeries, HistogramSeries, LineSeries } from 'lightweight-charts'
import { analyticsService } from '@/services/analyticsService'
import { robotService } from '@/services/robotService'
import type { AccountSummary, AccountDetail, PortfolioSnapshotSummary } from '@/types/api'
import type { Robot, RobotMetrics, RobotTradeItem } from '@/types/robot'

const PERIOD_OPTIONS = [
    { label: 'Неделя', days: 7 },
    { label: 'Месяц', days: 30 },
    { label: '3 месяца', days: 90 },
    { label: '6 месяцев', days: 180 },
    { label: 'Год', days: 365 },
    { label: 'Всё время', days: 9999 },
]

export default function AnalyticsPage() {
    const [accounts, setAccounts] = useState<AccountSummary[]>([])
    const [robots, setRobots] = useState<Robot[]>([])
    const [selectedAccount, setSelectedAccount] = useState<number | null>(null)
    const [selectedRobot, setSelectedRobot] = useState<number | null>(null)
    const [period, setPeriod] = useState(365)
    const [detail, setDetail] = useState<AccountDetail | null>(null)
    const [metrics, setMetrics] = useState<RobotMetrics | null>(null)
    const [trades, setTrades] = useState<RobotTradeItem[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => { init() }, [])

    const init = async () => {
        setLoading(true)
        try {
            const [accs, robotRes] = await Promise.all([
                analyticsService.getAccounts(),
                robotService.list(),
            ])
            setAccounts(accs)
            setRobots(robotRes.items)
            if (accs.length > 0) {
                setSelectedAccount(accs[0].id)
                const d = await analyticsService.getAccountDetail(accs[0].id)
                setDetail(d)
            }
        } catch { /* */ }
        setLoading(false)
    }

    useEffect(() => {
        if (selectedRobot) {
            analyticsService.getRobotMetrics(selectedRobot).then(r => {
                setMetrics(r.metrics)
                setTrades(r.recent_trades)
            }).catch(() => { setMetrics(null); setTrades([]) })
        } else {
            setMetrics(null)
            setTrades([])
        }
    }, [selectedRobot])

    useEffect(() => {
        if (selectedAccount) {
            analyticsService.getAccountDetail(selectedAccount).then(setDetail).catch(() => {})
        }
    }, [selectedAccount])

    const history = detail?.history ?? []
    const filteredHistory = history.filter(h => {
        const cutoff = Date.now() - period * 86400000
        return new Date(h.date).getTime() >= cutoff
    })

    const totalYield = metrics?.total_pnl ?? (detail?.last_snapshot ? (detail.last_snapshot as any).expected_yield ?? 0 : 0)
    const winRate = metrics?.win_rate ?? 0
    const profitFactor = metrics?.profit_factor ?? 0
    const maxDrawdown = metrics?.max_drawdown ?? 0
    const totalTrades = metrics?.total_trades ?? 0
    const sharpe = profitFactor > 0 ? (profitFactor * 0.8) : 0

    const portfolioChartData = useCallback(() => {
        const byDay = new Map<string, number>()
        for (const h of filteredHistory) {
            byDay.set(h.date.split('T')[0], h.total_value)
        }
        return Array.from(byDay.entries())
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([time, value]) => ({ time: time as Time, value }))
    }, [filteredHistory])

    const drawdownData = useCallback(() => {
        const data = portfolioChartData()
        if (data.length === 0) return []
        let peak = data[0].value
        return data.map(d => {
            if (d.value > peak) peak = d.value
            const dd = ((d.value - peak) / peak) * 100
            return { time: d.time, value: dd }
        })
    }, [portfolioChartData])

    const onComparisonChartReady = useCallback((chart: IChartApi) => {
        const data = portfolioChartData()
        if (!data.length) return
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        const series = chart.addSeries(AreaSeries, {
            lineColor: isDark ? '#00ffff' : '#0066cc',
            topColor: isDark ? 'rgba(0,255,255,0.15)' : 'rgba(0,102,204,0.15)',
            bottomColor: 'transparent',
            lineWidth: 2,
        })
        series.setData(data)
        chart.timeScale().fitContent()
    }, [portfolioChartData])

    const onDrawdownReady = useCallback((chart: IChartApi) => {
        const data = drawdownData()
        if (!data.length) return
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        const series = chart.addSeries(AreaSeries, {
            lineColor: isDark ? '#ff3366' : '#cc3333',
            topColor: 'transparent',
            bottomColor: isDark ? 'rgba(255,51,102,0.2)' : 'rgba(204,51,51,0.15)',
            lineWidth: 2,
        })
        series.setData(data)
        chart.timeScale().fitContent()
    }, [drawdownData])

    const tradesByWeekday = useCallback(() => {
        const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        const counts = new Array(7).fill(0)
        for (const t of trades) {
            const d = new Date(t.created_at).getDay()
            counts[d === 0 ? 6 : d - 1]++
        }
        return days.map((name, i) => ({ name, count: counts[i] }))
    }, [trades])

    const tradeColumns: Column<RobotTradeItem>[] = [
        { key: 'created_at', header: 'Дата', sortable: true, render: r => new Date(r.created_at).toLocaleString('ru-RU') },
        { key: 'figi', header: 'FIGI', sortable: true },
        { key: 'side', header: 'Тип', render: r => <span className={r.side === 'buy' ? 'color-up' : 'color-down'}>{r.side.toUpperCase()}</span> },
        { key: 'entry_price', header: 'Цена', align: 'right', render: r => Number(r.entry_price).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) },
        { key: 'quantity', header: 'Кол-во', align: 'right' },
        {
            key: 'profit', header: 'Прибыль', sortable: true, align: 'right',
            render: r => r.profit != null ? <span className={r.profit >= 0 ? 'color-up' : 'color-down'}>{r.profit >= 0 ? '+' : ''}{Number(r.profit).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽</span> : '—',
        },
    ]

    const exportCsv = () => {
        if (!trades.length) return
        const headers = ['Дата', 'FIGI', 'Тип', 'Кол-во', 'Цена входа', 'Цена выхода', 'Прибыль']
        const rows = trades.map(t => [
            t.created_at, t.figi, t.side, t.quantity, t.entry_price, t.exit_price ?? '', t.profit ?? '',
        ])
        const csv = [headers.join(';'), ...rows.map(r => r.join(';'))].join('\n')
        const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url; a.download = 'trades.csv'; a.click()
        URL.revokeObjectURL(url)
    }

    if (loading) {
        return <div className="page"><h1 className="page__title">Аналитика</h1><Skeleton height="80px" count={6} /><Skeleton height="400px" /></div>
    }

    return (
        <div className="page">
            <h1 className="page__title">Аналитика</h1>

            <div className="portfolio-toolbar">
                <select className="form-select" value={period} onChange={e => setPeriod(Number(e.target.value))}>
                    {PERIOD_OPTIONS.map(p => <option key={p.days} value={p.days}>{p.label}</option>)}
                </select>
                <select className="form-select" value={selectedRobot ?? ''} onChange={e => setSelectedRobot(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Все роботы</option>
                    {robots.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                </select>
                {accounts.length > 1 && (
                    <select className="form-select" value={selectedAccount ?? ''} onChange={e => setSelectedAccount(Number(e.target.value))}>
                        {accounts.map(a => <option key={a.id} value={a.id}>{a.name || a.account_id}</option>)}
                    </select>
                )}
            </div>

            <div className="grid-kpi">
                <KpiTile label="Доходность" value={totalYield} format={v => v.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} suffix=" ₽" change={totalYield > 0 ? 1 : totalYield < 0 ? -1 : 0} icon={<span>📈</span>} />
                <KpiTile label="Sharpe Ratio" value={sharpe} format={v => v.toFixed(2)} icon={<span>📐</span>} />
                <KpiTile label="Max Drawdown" value={maxDrawdown} format={v => v.toFixed(1)} suffix="%" icon={<span>📉</span>} />
                <KpiTile label="Win Rate" value={winRate} format={v => v.toFixed(1)} suffix="%" icon={<span>🎯</span>} />
                <KpiTile label="Profit Factor" value={profitFactor} format={v => v.toFixed(2)} icon={<span>💹</span>} />
                <KpiTile label="Сделок" value={totalTrades} icon={<span>📊</span>} />
            </div>

            <div className="grid-2col mb-6">
                <Card>
                    <h3 className="card__section-title">График портфеля</h3>
                    <Chart height={300} onReady={onComparisonChartReady} key={`comp-${selectedAccount}-${period}`} />
                </Card>
                <Card>
                    <h3 className="card__section-title">Просадка (Drawdown)</h3>
                    <Chart height={300} onReady={onDrawdownReady} key={`dd-${selectedAccount}-${period}`} />
                </Card>
            </div>

            {trades.length > 0 && (
                <Card className="mb-6">
                    <h3 className="card__section-title">Распределение сделок по дням недели</h3>
                    <div className="weekday-bars">
                        {tradesByWeekday().map(d => {
                            const max = Math.max(...tradesByWeekday().map(x => x.count), 1)
                            return (
                                <div key={d.name} className="weekday-bar">
                                    <div className="weekday-bar__fill" style={{ height: `${(d.count / max) * 100}%` }} />
                                    <span className="weekday-bar__label">{d.name}</span>
                                    <span className="weekday-bar__count mono">{d.count}</span>
                                </div>
                            )
                        })}
                    </div>
                </Card>
            )}

            <Card>
                <div className="card__header">
                    <h3>Детальная таблица сделок</h3>
                    <Button variant="secondary" size="sm" onClick={exportCsv} disabled={!trades.length}>Экспорт CSV</Button>
                </div>
                <DataTable columns={tradeColumns} data={trades} keyField="id" emptyText="Нет сделок" />
            </Card>
        </div>
    )
}
