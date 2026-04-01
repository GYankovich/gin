import React, { useEffect, useState, useCallback } from 'react'
import { KpiTile } from '@/components/ui/KpiTile'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { EventFeed, type FeedEvent } from '@/components/ui/EventFeed'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { Chart, type IChartApi, type Time } from '@/components/ui/Chart'
import { AreaSeries } from 'lightweight-charts'
import { analyticsService } from '@/services/analyticsService'
import { robotService } from '@/services/robotService'
import type { OverallSummary, AccountDetail } from '@/types/api'
import type { Robot } from '@/types/robot'

const TIMEFRAMES = ['1W', '1M', '3M', '6M', '1Y', 'ALL'] as const

export default function DashboardPage() {
    const [summary, setSummary] = useState<OverallSummary | null>(null)
    const [detail, setDetail] = useState<AccountDetail | null>(null)
    const [robots, setRobots] = useState<Robot[]>([])
    const [loading, setLoading] = useState(true)
    const [tf, setTf] = useState<string>('1Y')

    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        setLoading(true)
        try {
            const [sum, robotRes] = await Promise.all([
                analyticsService.getSummary(),
                robotService.list(),
            ])
            setSummary(sum)
            setRobots(robotRes.items)

            if (sum.accounts.length > 0) {
                const d = await analyticsService.getAccountDetail(sum.accounts[0].id)
                setDetail(d)
            }
        } catch { /* handled by interceptor */ }
        setLoading(false)
    }

    const activeRobots = robots.filter(r => r.status === 1).length
    const totalYield = summary ? (summary.total_expected_yield / Math.max(summary.total_value - summary.total_expected_yield, 1)) * 100 : 0
    const dailyYield = summary ? (summary.total_daily_yield / Math.max(summary.total_value - summary.total_daily_yield, 1)) * 100 : 0

    const chartData = useCallback(() => {
        if (!detail?.history) return []
        const now = Date.now()
        const tfDays: Record<string, number> = { '1W': 7, '1M': 30, '3M': 90, '6M': 180, '1Y': 365, 'ALL': 99999 }
        const cutoff = now - (tfDays[tf] || 365) * 86400000

        const byDay = new Map<string, number>()
        for (const h of detail.history) {
            const ts = new Date(h.date).getTime()
            if (ts < cutoff) continue
            const day = h.date.split('T')[0]
            byDay.set(day, h.total_value)
        }
        return Array.from(byDay.entries())
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([time, value]) => ({ time: time as Time, value }))
    }, [detail, tf])

    const onChartReady = useCallback((chart: IChartApi) => {
        const data = chartData()
        if (data.length === 0) return
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        const series = chart.addSeries(AreaSeries, {
            lineColor: isDark ? '#00ffff' : '#0066cc',
            topColor: isDark ? 'rgba(0,255,255,0.18)' : 'rgba(0,102,204,0.18)',
            bottomColor: 'transparent',
            lineWidth: 2,
        })
        series.setData(data)
        chart.timeScale().fitContent()
    }, [chartData])

    const distribution = detail?.distribution || []

    const distColors = ['#00ffff', '#ff00ff', '#aa00ff', '#00ffaa', '#ffaa00', '#ff3366']

    const events: FeedEvent[] = robots.slice(0, 10).map((r, i) => ({
        id: r.id,
        type: r.status === 1 ? 'info' : 'signal',
        text: `${r.name} — ${r.statusName}`,
        time: r.last_started ? new Date(r.last_started).toLocaleTimeString('ru-RU') : '—',
    }))

    if (loading) {
        return (
            <div className="page">
                <h1 className="page__title">Дашборд</h1>
                <div className="grid-kpi"><Skeleton height="80px" count={6} /></div>
                <Skeleton height="360px" />
            </div>
        )
    }

    return (
        <div className="page">
            <div className="dashboard-header">
                <h1 className="page__title">Дашборд</h1>
                <RobotIllustration size={64} />
            </div>

            <div className="grid-kpi">
                <KpiTile
                    label="Общая стоимость"
                    value={summary?.total_value ?? 0}
                    format={v => v.toLocaleString('ru-RU', { maximumFractionDigits: 0 })}
                    suffix=" ₽"
                    icon={<span>💰</span>}
                />
                <KpiTile
                    label="Доходность"
                    value={totalYield}
                    format={v => v.toFixed(1)}
                    suffix="%"
                    change={totalYield}
                    icon={<span>📈</span>}
                />
                <KpiTile
                    label="Доходность сегодня"
                    value={dailyYield}
                    format={v => v.toFixed(2)}
                    suffix="%"
                    change={dailyYield}
                    icon={<span>📊</span>}
                />
                <KpiTile
                    label="Активных роботов"
                    value={activeRobots}
                    icon={<span>🤖</span>}
                />
                <KpiTile
                    label="Всего роботов"
                    value={robots.length}
                    icon={<span>⚙</span>}
                />
                <KpiTile
                    label="Счетов"
                    value={summary?.accounts_count ?? 0}
                    icon={<span>🏦</span>}
                />
            </div>

            <div className="grid-2col">
                <Card>
                    <div className="card__header">
                        <h3>Стоимость портфеля</h3>
                        <div className="tf-selector">
                            {TIMEFRAMES.map(t => (
                                <button key={t} className={`tf-btn ${t === tf ? 'tf-btn--active' : ''}`} onClick={() => setTf(t)}>{t}</button>
                            ))}
                        </div>
                    </div>
                    <Chart height={320} onReady={onChartReady} key={tf} />
                </Card>

                <Card>
                    <h3 style={{ marginBottom: 'var(--space-4)' }}>Распределение портфеля</h3>
                    {distribution.length === 0 ? (
                        <div className="event-feed__empty">Нет данных</div>
                    ) : (
                        <div className="distribution-list">
                            {distribution.map((d, i) => (
                                <div key={d.instrument_type} className="dist-row">
                                    <span className="dist-color" style={{ background: distColors[i % distColors.length] }} />
                                    <span className="dist-label">{d.instrument_type}</span>
                                    <span className="dist-bar-wrap">
                                        <span className="dist-bar" style={{ width: `${d.percentage}%`, background: distColors[i % distColors.length] }} />
                                    </span>
                                    <span className="dist-pct mono">{d.percentage.toFixed(1)}%</span>
                                    <span className="dist-val mono">{d.value.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽</span>
                                </div>
                            ))}
                        </div>
                    )}
                </Card>
            </div>

            <Card className="mt-6">
                <h3 style={{ marginBottom: 'var(--space-4)' }}>Активность роботов</h3>
                <EventFeed events={events} maxHeight="280px" />
            </Card>
        </div>
    )
}
