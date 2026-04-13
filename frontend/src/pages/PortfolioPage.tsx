import React, { useEffect, useState, useCallback, useRef } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Skeleton } from '@/components/ui/Skeleton'
import { Chart, type IChartApi, type ISeriesApi, type Time } from '@/components/ui/Chart'
import { AreaSeries } from 'lightweight-charts'
import { Select } from '@/components/ui/Select'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { analyticsService } from '@/services/analyticsService'
import type { AccountSummary, PortfolioSnapshotSummary, AccountStatisticsResponse } from '@/types/api'
import { useToast } from '@/components/ui/Toast'

const PERIODS = [
    { label: 'День', days: 1 },
    { label: 'Неделя', days: 7 },
    { label: 'Месяц', days: 30 },
    { label: '3 месяца', days: 90 },
    { label: 'Всё время', days: 3650 },
]

export default function PortfolioPage() {
    const toast = useToast()
    const [accounts, setAccounts] = useState<AccountSummary[]>([])
    const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
    const selectedAccount = accounts.find(a => a.id === selectedAccountId) ?? null
    const [period, setPeriod] = useState(30)
    const [fromDate, setFromDate] = useState(() => new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10))
    const [toDate, setToDate] = useState(() => new Date().toISOString().slice(0, 10))
    const [snapshots, setSnapshots] = useState<PortfolioSnapshotSummary[]>([])
    const [loading, setLoading] = useState(true)
    const [positions, setPositions] = useState<any[]>([])
    const [posLoading, setPosLoading] = useState(false)
    const [operations, setOperations] = useState<any[]>([])
    const [opsLoading, setOpsLoading] = useState(false)
    const [opsSyncing, setOpsSyncing] = useState(false)
    const [stats, setStats] = useState<AccountStatisticsResponse | null>(null)
    const [statsLoading, setStatsLoading] = useState(false)
    const [crosshairValue, setCrosshairValue] = useState<{ time: string; value: number; delta: number | null; deltaPct: number | null } | null>(null)
    const chartApiRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<any> | null>(null)

    useEffect(() => { loadAccounts() }, [])
    useEffect(() => {
        if (!selectedAccountId) return
        loadSnapshots(selectedAccountId)
        loadOperations(selectedAccountId)
        loadStatistics(selectedAccountId)
    }, [selectedAccountId, fromDate, toDate])

    const loadAccounts = async () => {
        setLoading(true)
        try {
            const summary = await analyticsService.getSummary()
            const accs = summary.accounts ?? []
            setAccounts(accs)
            if (accs.length > 0) {
                setSelectedAccountId(accs[0].id)
                loadPositions(accs[0].id)
            }
        } catch { /* */ }
        setLoading(false)
    }

    const loadPositions = async (accId: number, snapshotId?: number) => {
        setPosLoading(true)
        try {
            const pos = await analyticsService.getAccountPositions(accId, snapshotId)
            setPositions(pos)
        } catch { setPositions([]) }
        setPosLoading(false)
    }

    const loadSnapshots = async (accId: number) => {
        try {
            const data = await analyticsService.getSnapshotsByPeriod({
                account_id: accId,
                from_date: `${fromDate}T00:00:00Z`,
                to_date: `${toDate}T23:59:59Z`,
            })
            setSnapshots(data.history ?? [])
        } catch {
            setSnapshots([])
        }
    }

    const loadOperations = async (accId: number) => {
        setOpsLoading(true)
        try {
            const res = await analyticsService.getOperationsByPeriod({
                account_id: accId,
                from_date: `${fromDate}T00:00:00Z`,
                to_date: `${toDate}T23:59:59Z`,
            })
            setOperations(res.items ?? [])
        } catch {
            setOperations([])
        }
        setOpsLoading(false)
    }

    const loadStatistics = async (accId: number) => {
        setStatsLoading(true)
        try {
            const data = await analyticsService.getAccountStatistics({
                account_id: accId,
                from_date: `${fromDate}T00:00:00Z`,
                to_date: `${toDate}T23:59:59Z`,
            })
            setStats(data)
        } catch {
            setStats(null)
        }
        setStatsLoading(false)
    }

    const handleAccountChange = async (val: string) => {
        const id = Number(val)
        setSelectedAccountId(id)
        setLoading(true)
        loadPositions(id)
        setLoading(false)
    }

    const handleSyncOperations = async () => {
        if (!selectedAccountId) return
        if (!selectedAccount?.last_token_id) {
            toast.show('Для выбранного счета не найден tokenId. Обновите портфель.', 'warning')
            return
        }
        setOpsSyncing(true)
        try {
            await analyticsService.syncOperations({
                account_id: selectedAccount?.account_id || '',
                from_date: `${fromDate}T00:00:00Z`,
                to_date: `${toDate}T23:59:59Z`,
                tokenId: Number(selectedAccount.last_token_id),
                state: 'OPERATION_STATE_UNSPECIFIED',
            })
            await loadOperations(selectedAccountId)
            await loadStatistics(selectedAccountId)
        } catch {
            toast.show('Ошибка синхронизации операций', 'error')
        }
        setOpsSyncing(false)
    }

    const chartHistory = useCallback(() => {
        if (!snapshots.length) return []
        const fromTs = new Date(`${fromDate}T00:00:00Z`).getTime()
        const toTs = new Date(`${toDate}T23:59:59Z`).getTime()
        const points: Array<{ time: Time; value: number; timestamp: number }> = []
        for (const h of snapshots) {
            const ts = new Date(h.date).getTime()
            if (ts < fromTs || ts > toTs) continue
            const t = toChartTime(h.date)
            if (t == null) continue
            points.push({ time: t, value: h.total_value, timestamp: ts })
        }
        return normalizeSeriesByTime(points)
    }, [snapshots, fromDate, toDate])

    const onChartReady = useCallback((chart: IChartApi) => {
        chartApiRef.current = chart
        const data = chartHistory()
        if (!data.length) return
        const intraday = isIntradaySeries(data)
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
            timeVisible: intraday,
            secondsVisible: false,
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
                const currTime = Number(param.time)
                const idx = data.findIndex(d => Number(d.time) === currTime)
                const prev = idx > 0 ? data[idx - 1]?.value : null
                const delta = prev != null ? val.value - prev : null
                const deltaPct = prev != null && prev !== 0 ? (delta! / prev) * 100 : null
                setCrosshairValue({
                    time: formatCrosshairTime(param.time),
                    value: val.value,
                    delta: delta != null ? Number(delta.toFixed(2)) : null,
                    deltaPct: deltaPct != null ? Number(deltaPct.toFixed(2)) : null,
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

    const operationsColumns: Column<any>[] = [
        { key: 'operation_date', header: 'Дата', render: r => new Date(r.operation_date).toLocaleString('ru-RU') },
        { key: 'operation_type', header: 'Тип API', width: '180px' },
        { key: 'type_text', header: 'Описание', render: r => r.type_text || '—' },
        { key: 'figi', header: 'FIGI', render: r => r.figi || '—' },
        { key: 'quantity', header: 'Кол-во', align: 'right', render: r => Number(r.quantity || 0).toLocaleString('ru-RU') },
        { key: 'price', header: 'Цена', align: 'right', render: r => Number(r.price || 0).toLocaleString('ru-RU', { maximumFractionDigits: 4 }) },
        {
            key: 'payment',
            header: 'Сумма',
            align: 'right',
            render: r => {
                const v = Number(r.payment || 0)
                return <span className={v >= 0 ? 'color-up' : 'color-down'}>{v.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} {r.currency || ''}</span>
            },
        },
        { key: 'status', header: 'Статус', width: '160px' },
    ]

    if (loading) {
        return <div className="page"><h1 className="page__title">Портфель</h1><Skeleton height="400px" /><Skeleton height="300px" /></div>
    }

    return (
        <div className="page" data-page="portfolio">
            {/*<h1 className="page__title">Портфель</h1>*/}

            <div className="portfolio-toolbar">
                <Select
                    options={accounts.map(a => ({ value: String(a.id), label: `${a.name || a.account_id} (${a.type})` }))}
                    value={selectedAccountId != null ? String(selectedAccountId) : ''}
                    onChange={handleAccountChange}
                    placeholder="Выберите счёт"
                />

                <div className="tf-selector">
                    {PERIODS.map(p => (
                        <button key={p.days} className={`tf-btn ${p.days === period ? 'tf-btn--active' : ''}`} onClick={() => {
                            setPeriod(p.days)
                            const now = new Date()
                            const from = new Date(Date.now() - p.days * 86400000)
                            const f = from.toISOString().slice(0, 10)
                            const t = now.toISOString().slice(0, 10)
                            setFromDate(f)
                            setToDate(t)
                        }}>
                            {p.label}
                        </button>
                    ))}
                </div>

                <DateRangePicker
                    fromValue={`${fromDate}T00:00`}
                    toValue={`${toDate}T00:00`}
                    onFromChange={v => {
                        setPeriod(0)
                        setFromDate(v.slice(0, 10))
                    }}
                    onToChange={v => {
                        setPeriod(0)
                        setToDate(v.slice(0, 10))
                    }}
                    fromLabel="Период"
                    toLabel="по"
                />
            </div>

            <Card className="mb-6">
                <h3 className="card__section-title">Статистика портфеля</h3>
                {statsLoading ? (
                    <Skeleton height="110px" />
                ) : (
                    <div className="portfolio-stats-rows">
                        <div className="portfolio-stats-row-title">Общее</div>
                        <div className="portfolio-stats-grid">
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Собственные средства</div>
                                <div className="portfolio-stat-tile__value">{formatMoney(stats?.overall.own_funds)}</div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Текущая стоимость</div>
                                <div className="portfolio-stat-tile__value">{formatMoney(stats?.overall.current_total_value)}</div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">ROI общий</div>
                                <div className={`portfolio-stat-tile__value ${roiClass(stats?.overall.roi_percent)}`}>
                                    {formatPercent(stats?.overall.roi_percent)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">ROI среднемесячный (весь период)</div>
                                <div className={`portfolio-stat-tile__value ${roiClass(stats?.overall.avg_monthly_roi_percent)}`}>
                                    {formatPercent(stats?.overall.avg_monthly_roi_percent)}
                                </div>
                            </div>
                        </div>

                        <div className="portfolio-stats-row-title">Выбранный период</div>
                        <div className="portfolio-stats-grid">
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Входящая сумма периода</div>
                                <div className="portfolio-stat-tile__value">{formatMoney(stats?.period.period_inflow)}</div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Макс просадка</div>
                                <div className={`portfolio-stat-tile__value ${roiClass(stats?.period.max_drawdown_percent, true)}`}>
                                    {formatPercent(stats?.period.max_drawdown_percent, true)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Макс рост</div>
                                <div className={`portfolio-stat-tile__value ${roiClass(stats?.period.max_growth_percent)}`}>
                                    {formatPercent(stats?.period.max_growth_percent)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Крайняя сумма периода</div>
                                <div className="portfolio-stat-tile__value">{formatMoney(stats?.period.end_value)}</div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">ROI периода</div>
                                <div className={`portfolio-stat-tile__value ${roiClass(stats?.period.period_roi_percent)}`}>
                                    {formatPercent(stats?.period.period_roi_percent)}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </Card>

            <Card className="mb-6">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                    <h3 className="card__section-title">Стоимость портфеля</h3>
                    {crosshairValue && (
                        <div className="mono" style={{ fontSize: 'var(--text-lg)', color: 'var(--color-primary)' }}>
                            {crosshairValue.value.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                            {crosshairValue.delta != null && (
                                <span
                                    className={crosshairValue.delta >= 0 ? 'color-up' : 'color-down'}
                                    style={{ fontSize: 'var(--text-sm)', marginLeft: 'var(--space-2)' }}
                                >
                                    {crosshairValue.delta >= 0 ? '+' : ''}
                                    {crosshairValue.delta.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽
                                    {crosshairValue.deltaPct != null && (
                                        <span style={{ marginLeft: 4 }}>
                                            ({crosshairValue.deltaPct >= 0 ? '+' : ''}
                                            {crosshairValue.deltaPct.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%)
                                        </span>
                                    )}
                                </span>
                            )}
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginLeft: 'var(--space-2)' }}>
                                {crosshairValue.time}
                            </span>
                        </div>
                    )}
                </div>
                <Chart height={360} onReady={onChartReady} key={`${selectedAccountId}-${fromDate}-${toDate}`} />
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
                    data={snapshots.slice(0, 500)}
                    keyField="date"
                    emptyText="Нет истории"
                    onRowClick={handleSnapshotClick as any}
                    maxHeight={420}
                />
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
                    Нажмите на строку, чтобы увидеть состав на момент снимка
                </p>
            </Card>

            <Card className="mt-6">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                    <h3 className="card__section-title" style={{ margin: 0 }}>История операций</h3>
                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
                        <Button size="sm" onClick={handleSyncOperations} loading={opsSyncing}>Синхронизировать</Button>
                    </div>
                </div>
                <div style={{ marginTop: 'var(--space-3)' }}>
                    {opsLoading ? (
                        <div className="ops-loader">
                            <div className="soft-loading-bar" />
                            <div className="ops-loader__text">Загрузка истории операций...</div>
                        </div>
                    ) : (
                        <DataTable columns={operationsColumns} data={operations} keyField="operation_id" emptyText="Нет операций за период" maxHeight={420} />
                    )}
                </div>
            </Card>
        </div>
    )
}

function formatMoney(val: any): string {
    const n = Number(val ?? 0)
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ₽'
}

function formatPercent(val: number | null | undefined, drawdown = false): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    if (drawdown) return `${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`
    return `${n >= 0 ? '+' : ''}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`
}

function roiClass(val: number | null | undefined, drawdown = false): string {
    if (val == null || Number.isNaN(Number(val))) return ''
    const n = Number(val)
    if (drawdown) return n > 0 ? 'color-down' : 'color-up'
    return n >= 0 ? 'color-up' : 'color-down'
}

function toChartTime(value: string): Time | null {
    const ms = new Date(value).getTime()
    if (Number.isNaN(ms)) return null
    return Math.floor(ms / 1000) as Time
}

function normalizeSeriesByTime(data: Array<{ time: Time; value: number; timestamp: number }>) {
    const byTime = new Map<number, { time: Time; value: number; timestamp: number }>()
    for (const item of data) {
        const key = Number(item.time)
        byTime.set(key, item)
    }
    return Array.from(byTime.values()).sort((a, b) => Number(a.time) - Number(b.time))
}

function isIntradaySeries(data: Array<{ timestamp: number }>) {
    return data.some(p => {
        const d = new Date(p.timestamp)
        return d.getHours() !== 0 || d.getMinutes() !== 0 || d.getSeconds() !== 0
    })
}

function formatCrosshairTime(time: Time): string {
    if (typeof time === 'number') {
        const d = new Date(time * 1000)
        const hasTime = d.getHours() !== 0 || d.getMinutes() !== 0 || d.getSeconds() !== 0
        return d.toLocaleString('ru-RU', hasTime
            ? { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }
            : { day: '2-digit', month: '2-digit', year: 'numeric' })
    }
    if (typeof time === 'string') return time
    const y = Number((time as any).year)
    const m = Number((time as any).month)
    const d = Number((time as any).day)
    const dt = new Date(y, m - 1, d)
    return dt.toLocaleDateString('ru-RU')
}
