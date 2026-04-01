import React, { useEffect, useState, useCallback, useRef } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Skeleton } from '@/components/ui/Skeleton'
import { Chart, type IChartApi, type ISeriesApi, type Time } from '@/components/ui/Chart'
import { AreaSeries } from 'lightweight-charts'
import { Select } from '@/components/ui/Select'
import { analyticsService } from '@/services/analyticsService'
import { portfolioService } from '@/services/portfolioService'
import type { AccountSummary, AccountDetail, PortfolioSnapshotSummary } from '@/types/api'

const PERIODS = [
    { label: 'День', days: 1 },
    { label: 'Неделя', days: 7 },
    { label: 'Месяц', days: 30 },
    { label: '3 месяца', days: 90 },
    { label: 'Всё время', days: 3650 },
]

export default function PortfolioPage() {
    const [accounts, setAccounts] = useState<AccountSummary[]>([])
    const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
    const [detail, setDetail] = useState<AccountDetail | null>(null)
    const [period, setPeriod] = useState(30)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [positions, setPositions] = useState<any[]>([])
    const [posLoading, setPosLoading] = useState(false)
    const [crosshairValue, setCrosshairValue] = useState<{ time: string; value: number } | null>(null)
    const chartApiRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<any> | null>(null)

    useEffect(() => { loadAccounts() }, [])

    const loadAccounts = async () => {
        setLoading(true)
        try {
            const summary = await analyticsService.getSummary()
            const accs = summary.accounts ?? []
            setAccounts(accs)
            if (accs.length > 0) {
                setSelectedAccountId(accs[0].id)
                await loadDetail(accs[0].id)
                loadPositions(accs[0].id)
            }
        } catch { /* */ }
        setLoading(false)
    }

    const loadDetail = async (accId: number) => {
        try {
            const d = await analyticsService.getAccountDetail(accId)
            setDetail(d)
        } catch { /* */ }
    }

    const loadPositions = async (accId: number, snapshotId?: number) => {
        setPosLoading(true)
        try {
            const pos = await analyticsService.getAccountPositions(accId, snapshotId)
            setPositions(pos)
        } catch { setPositions([]) }
        setPosLoading(false)
    }

    const handleAccountChange = async (val: string) => {
        const id = Number(val)
        setSelectedAccountId(id)
        setLoading(true)
        await loadDetail(id)
        loadPositions(id)
        setLoading(false)
    }

    const handleRefresh = async () => {
        setRefreshing(true)
        try {
            await portfolioService.refreshAll()
            if (selectedAccountId) {
                await loadDetail(selectedAccountId)
                loadPositions(selectedAccountId)
            }
        } catch { /* */ }
        setRefreshing(false)
    }

    const chartHistory = useCallback(() => {
        if (!detail?.history) return []
        const cutoff = Date.now() - period * 86400000
        const byDay = new Map<string, { time: string; value: number; fullDate: string }>()
        for (const h of detail.history) {
            const ts = new Date(h.date).getTime()
            if (ts < cutoff) continue
            const day = h.date.split('T')[0]
            byDay.set(day, { time: day, value: h.total_value, fullDate: h.date })
        }
        return Array.from(byDay.values())
            .sort((a, b) => a.time.localeCompare(b.time))
    }, [detail, period])

    const onChartReady = useCallback((chart: IChartApi) => {
        chartApiRef.current = chart
        const data = chartHistory()
        if (!data.length) return
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        const series = chart.addSeries(AreaSeries, {
            lineColor: isDark ? '#00ffff' : '#0066cc',
            topColor: isDark ? 'rgba(0,255,255,0.18)' : 'rgba(0,102,204,0.18)',
            bottomColor: 'transparent',
            lineWidth: 2,
        })
        seriesRef.current = series
        series.setData(data.map(d => ({ time: d.time as Time, value: d.value })))

        chart.applyOptions({
            crosshair: {
                mode: 0,
                vertLine: { labelVisible: true },
                horzLine: { labelVisible: true },
            },
        })

        chart.timeScale().applyOptions({
            timeVisible: false,
            minBarSpacing: 6,
        })

        chart.timeScale().fitContent()

        chart.subscribeCrosshairMove((param: any) => {
            if (!param || !param.time || !param.seriesData?.size) {
                setCrosshairValue(null)
                return
            }
            const val = param.seriesData.get(series)
            if (val && val.value != null) {
                setCrosshairValue({
                    time: String(param.time),
                    value: val.value,
                })
            } else {
                setCrosshairValue(null)
            }
        })

        chart.timeScale().subscribeVisibleLogicalRangeChange((range: any) => {
            if (!range) return
            if (range.from < 0 && period < 3650) {
                setPeriod(prev => {
                    const nextIdx = PERIODS.findIndex(p => p.days === prev)
                    if (nextIdx < PERIODS.length - 1) return PERIODS[nextIdx + 1].days
                    return prev
                })
            }
        })
    }, [chartHistory, period])

    const handleSnapshotClick = (snapshot: PortfolioSnapshotSummary) => {
        if (selectedAccountId && snapshot.snapshot_id) {
            loadPositions(selectedAccountId, snapshot.snapshot_id)
        }
    }

    const posColumns: Column<any>[] = [
        { key: 'figi', header: 'FIGI', sortable: true, width: '140px' },
        { key: 'ticker', header: 'Тикер', sortable: true, width: '80px', render: r => r.ticker || '—' },
        { key: 'instrument_type', header: 'Тип', sortable: true, width: '80px' },
        { key: 'quantity', header: 'Кол-во', sortable: true, align: 'right', render: r => Number(r.quantity ?? 0).toLocaleString('ru-RU') },
        { key: 'avg_price', header: 'Средняя', sortable: true, align: 'right', render: r => formatMoney(r.avg_price) },
        { key: 'current_price', header: 'Текущая', align: 'right', render: r => formatMoney(r.current_price) },
        {
            key: 'expected_yield', header: 'P&L', sortable: true, align: 'right',
            render: r => {
                const v = Number(r.expected_yield ?? 0)
                return <span className={v >= 0 ? 'color-up' : 'color-down'}>{v >= 0 ? '+' : ''}{v.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽</span>
            },
        },
        {
            key: 'total_value', header: 'Стоимость', sortable: true, align: 'right',
            render: r => formatMoney(r.total_value),
        },
    ]

    const historyColumns: Column<PortfolioSnapshotSummary>[] = [
        {
            key: 'date', header: 'Дата и время', sortable: true,
            render: r => new Date(r.date).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }),
        },
        { key: 'total_value', header: 'Стоимость', sortable: true, align: 'right', render: r => r.total_value.toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽' },
        {
            key: 'daily_yield', header: 'Дневной доход', sortable: true, align: 'right',
            render: r => <span className={r.daily_yield >= 0 ? 'color-up' : 'color-down'}>{r.daily_yield >= 0 ? '+' : ''}{r.daily_yield.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽</span>,
        },
    ]

    if (loading) {
        return <div className="page"><h1 className="page__title">Портфель</h1><Skeleton height="400px" /><Skeleton height="300px" /></div>
    }

    return (
        <div className="page">
            <h1 className="page__title">Портфель</h1>

            <div className="portfolio-toolbar">
                <Select
                    options={accounts.map(a => ({ value: String(a.id), label: `${a.name || a.account_id} (${a.type})` }))}
                    value={selectedAccountId != null ? String(selectedAccountId) : ''}
                    onChange={handleAccountChange}
                    placeholder="Выберите счёт"
                />

                <div className="tf-selector">
                    {PERIODS.map(p => (
                        <button key={p.days} className={`tf-btn ${p.days === period ? 'tf-btn--active' : ''}`} onClick={() => setPeriod(p.days)}>
                            {p.label}
                        </button>
                    ))}
                </div>

                <Button variant="secondary" size="sm" loading={refreshing} onClick={handleRefresh}>Обновить</Button>
            </div>

            <Card className="mb-6">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                    <h3 className="card__section-title">Стоимость портфеля</h3>
                    {crosshairValue && (
                        <div className="mono" style={{ fontSize: 'var(--text-lg)', color: 'var(--color-primary)' }}>
                            {crosshairValue.value.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginLeft: 'var(--space-2)' }}>
                                {crosshairValue.time}
                            </span>
                        </div>
                    )}
                </div>
                <Chart height={360} onReady={onChartReady} key={`${selectedAccountId}-${period}`} />
            </Card>

            <Card className="mb-6">
                <h3 className="card__section-title">Состав портфеля</h3>
                {posLoading ? <Skeleton height="200px" /> : (
                    <DataTable columns={posColumns} data={positions} keyField="figi" emptyText="Нет позиций" />
                )}
            </Card>

            <Card>
                <h3 className="card__section-title">История снимков</h3>
                <DataTable
                    columns={historyColumns}
                    data={detail?.history?.slice(0, 50) ?? []}
                    keyField="date"
                    emptyText="Нет истории"
                    onRowClick={handleSnapshotClick as any}
                />
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
                    Нажмите на строку, чтобы увидеть состав на момент снимка
                </p>
            </Card>
        </div>
    )
}

function formatMoney(val: any): string {
    const n = Number(val ?? 0)
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ₽'
}
