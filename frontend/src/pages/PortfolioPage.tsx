import React, { useEffect, useState, useCallback } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Skeleton } from '@/components/ui/Skeleton'
import { Chart, type IChartApi, type Time } from '@/components/ui/Chart'
import { AreaSeries } from 'lightweight-charts'
import { analyticsService } from '@/services/analyticsService'
import { portfolioService } from '@/services/portfolioService'
import type { AccountSummary, AccountDetail, PortfolioSnapshotSummary } from '@/types/api'

const PERIODS = [
    { label: 'Неделя', days: 7 },
    { label: 'Месяц', days: 30 },
    { label: '3 месяца', days: 90 },
    { label: 'Всё время', days: 3650 },
]

export default function PortfolioPage() {
    const [accounts, setAccounts] = useState<AccountSummary[]>([])
    const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
    const [detail, setDetail] = useState<AccountDetail | null>(null)
    const [period, setPeriod] = useState(365)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [portfolioData, setPortfolioData] = useState<any>(null)

    useEffect(() => { loadAccounts() }, [])

    const loadAccounts = async () => {
        setLoading(true)
        try {
            const accs = await analyticsService.getAccounts()
            setAccounts(accs)
            if (accs.length > 0) {
                setSelectedAccountId(accs[0].id)
                await loadDetail(accs[0].id)
            }
            try {
                const pd = await portfolioService.getPortfolioData()
                setPortfolioData(pd)
            } catch { /* may not be available */ }
        } catch { /* */ }
        setLoading(false)
    }

    const loadDetail = async (accId: number) => {
        try {
            const d = await analyticsService.getAccountDetail(accId)
            setDetail(d)
        } catch { /* */ }
    }

    const handleAccountChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
        const id = Number(e.target.value)
        setSelectedAccountId(id)
        setLoading(true)
        await loadDetail(id)
        setLoading(false)
    }

    const handleRefresh = async () => {
        setRefreshing(true)
        try {
            await portfolioService.refreshAll()
            if (selectedAccountId) await loadDetail(selectedAccountId)
        } catch { /* */ }
        setRefreshing(false)
    }

    const chartHistory = useCallback(() => {
        if (!detail?.history) return []
        const cutoff = Date.now() - period * 86400000
        const byDay = new Map<string, number>()
        for (const h of detail.history) {
            if (new Date(h.date).getTime() < cutoff) continue
            byDay.set(h.date.split('T')[0], h.total_value)
        }
        return Array.from(byDay.entries())
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([time, value]) => ({ time: time as Time, value }))
    }, [detail, period])

    const onChartReady = useCallback((chart: IChartApi) => {
        const data = chartHistory()
        if (!data.length) return
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        const series = chart.addSeries(AreaSeries, {
            lineColor: isDark ? '#00ffff' : '#0066cc',
            topColor: isDark ? 'rgba(0,255,255,0.18)' : 'rgba(0,102,204,0.18)',
            bottomColor: 'transparent',
            lineWidth: 2,
        })
        series.setData(data)
        chart.timeScale().fitContent()
    }, [chartHistory])

    const positions: any[] = portfolioData?.portfolio?.positions ?? []

    const posColumns: Column<any>[] = [
        { key: 'figi', header: 'FIGI', sortable: true, width: '140px' },
        { key: 'instrument_type', header: 'Тип', sortable: true, width: '80px' },
        { key: 'quantity', header: 'Кол-во', sortable: true, align: 'right', render: r => r.quantity?.units ?? r.quantity },
        { key: 'average_position_price', header: 'Средняя цена', sortable: true, align: 'right', render: r => formatMoney(r.average_position_price) },
        { key: 'current_price', header: 'Текущая цена', align: 'right', render: r => formatMoney(r.current_price) },
        {
            key: 'expected_yield', header: 'P&L', sortable: true, align: 'right',
            render: r => {
                const v = moneyVal(r.expected_yield)
                return <span className={v >= 0 ? 'color-up' : 'color-down'}>{v >= 0 ? '+' : ''}{v.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽</span>
            },
        },
    ]

    const historyColumns: Column<PortfolioSnapshotSummary>[] = [
        { key: 'date', header: 'Дата', sortable: true, render: r => new Date(r.date).toLocaleDateString('ru-RU') },
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
                <select className="form-select" value={selectedAccountId ?? ''} onChange={handleAccountChange}>
                    {accounts.map(a => <option key={a.id} value={a.id}>{a.name || a.account_id} ({a.type})</option>)}
                </select>

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
                <Chart height={360} onReady={onChartReady} key={`${selectedAccountId}-${period}`} />
            </Card>

            <Card className="mb-6">
                <h3 className="card__section-title">Позиции</h3>
                <DataTable columns={posColumns} data={positions} keyField="figi" emptyText="Нет позиций" />
            </Card>

            <Card>
                <h3 className="card__section-title">История снимков</h3>
                <DataTable columns={historyColumns} data={detail?.history?.slice(0, 50) ?? []} keyField="date" emptyText="Нет истории" />
            </Card>
        </div>
    )
}

function moneyVal(m: any): number {
    if (typeof m === 'number') return m
    if (m && typeof m === 'object') return Number(m.units ?? 0) + Number(m.nano ?? 0) / 1e9
    return 0
}

function formatMoney(m: any): string {
    return moneyVal(m).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ₽'
}
