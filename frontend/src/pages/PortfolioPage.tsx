import React, { useEffect, useState, useCallback, useRef } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Chart, type IChartApi, type ISeriesApi, type Time } from '@/components/ui/Chart'
import { AreaSeries, LineSeries } from 'lightweight-charts'
import { Select } from '@/components/ui/Select'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { Toggle } from '@/components/ui/Toggle'
import { analyticsService } from '@/services/analyticsService'
import type { AccountSummary, PortfolioSnapshotSummary, PortfolioStatisticsExtendedResponse, AnalyticsChartSeriesResponse } from '@/types/api'
import { useToast } from '@/components/ui/Toast'
import {
    formatPortfolioAccountLabel,
    formatPortfolioMoney,
    formatPortfolioMoneySigned,
    isBybitPortfolioAccount,
} from '@/utils/portfolioFormat'
import cyberHero from '@/assets/dashboard/cyber-hero.png'

///@EPIC Frontend.ITEM Portfolio.TOPIC Account Performance Screen [1]
///@ Экран портфеля: выбор счета/периода, таблицы позиций, динамика стоимости,
///@ статистика и графики, собранные из analytics endpoints.
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
    const accountCurrency = selectedAccount?.currency || 'RUB'
    const bybitAccount = isBybitPortfolioAccount(selectedAccount)
    const money = (val: unknown, maxFractionDigits = 2) =>
        formatPortfolioMoney(val, accountCurrency, maxFractionDigits)
    const moneySigned = (val: unknown) => formatPortfolioMoneySigned(val, accountCurrency)
    const [period, setPeriod] = useState(30)
    const [fromDate, setFromDate] = useState(() => new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10))
    const [toDate, setToDate] = useState(() => new Date().toISOString().slice(0, 10))
    const [snapshots, setSnapshots] = useState<PortfolioSnapshotSummary[]>([])
    const [snapshotsLoading, setSnapshotsLoading] = useState(false)
    const [loading, setLoading] = useState(true)
    const [positions, setPositions] = useState<any[]>([])
    const [posLoading, setPosLoading] = useState(false)
    const [operations, setOperations] = useState<any[]>([])
    const [opsLoading, setOpsLoading] = useState(false)
    const [opsSyncing, setOpsSyncing] = useState(false)
    const [stats, setStats] = useState<PortfolioStatisticsExtendedResponse | null>(null)
    const [statsLoading, setStatsLoading] = useState(false)
    const [chartData, setChartData] = useState<AnalyticsChartSeriesResponse | null>(null)
    const [chartLoading, setChartLoading] = useState(false)
    const [chartMode, setChartMode] = useState<'portfolio' | 'instruments'>('portfolio')
    const [selectedFigis, setSelectedFigis] = useState<string[]>([])
    const [crosshairValue, setCrosshairValue] = useState<{ time: string; value: number; delta: number | null; deltaPct: number | null } | null>(null)
    const chartApiRef = useRef<IChartApi | null>(null)
    const drawdownChartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<any> | null>(null)
    const instrumentSeriesRef = useRef<Array<{ figi: string; label: string; series: ISeriesApi<any> }>>([])
    const instrumentPriceLinesRef = useRef<Record<string, any>>({})
    const syncingRangeRef = useRef(false)

    useEffect(() => { loadAccounts() }, [])
    useEffect(() => {
        if (!selectedAccountId) return
        loadSnapshots(selectedAccountId)
        loadOperations(selectedAccountId)
        loadStatistics(selectedAccountId)
        loadChartSeries(selectedAccountId)
    }, [selectedAccountId, fromDate, toDate])

    useEffect(() => {
        const seriesFigis = (chartData?.instruments_series || [])
            .filter(s => Array.isArray(s.points) && s.points.length > 0)
            .map(s => s.figi)
        if (!seriesFigis.length) {
            setSelectedFigis([])
            return
        }
        // По умолчанию отображаем все серии, у которых есть точки в выбранном периоде.
        setSelectedFigis(prev => {
            const kept = prev.filter(f => seriesFigis.includes(f))
            return kept.length ? kept : seriesFigis
        })
    }, [chartData?.instruments_series])

    const loadAccounts = async () => {
        setLoading(true)
        try {
            const summary = await analyticsService.getSummary()
            const accs = summary.accounts ?? []
            setAccounts(accs)
            if (accs.length > 0) {
                const fromUrl = new URLSearchParams(window.location.search).get('accountId')
                const preferred = fromUrl ? accs.find(a => String(a.id) === fromUrl) : null
                const initial = preferred ?? accs[0]
                setSelectedAccountId(initial.id)
                loadPositions(initial.id)
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
        setSnapshotsLoading(true)
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
        setSnapshotsLoading(false)
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
            const data = await analyticsService.getAccountStatisticsExtended({
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

    const loadChartSeries = async (accId: number) => {
        setChartLoading(true)
        try {
            const data = await analyticsService.getAccountChartSeries({
                account_id: accId,
                from_date: `${fromDate}T00:00:00Z`,
                to_date: `${toDate}T23:59:59Z`,
            })
            setChartData(data)
        } catch {
            setChartData(null)
        }
        setChartLoading(false)
    }

    const handleAccountChange = async (val: string) => {
        const id = Number(val)
        setChartData(null)
        setSelectedFigis([])
        setCrosshairValue(null)
        setSelectedAccountId(id)
        const params = new URLSearchParams(window.location.search)
        params.set('accountId', String(id))
        window.history.replaceState(null, '', `${window.location.pathname}?${params}`)
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
        const src = chartData?.portfolio_series ?? []
        const points: Array<{ time: Time; value: number; timestamp: number }> = []
        for (const h of src) {
            const ts = new Date(h.date).getTime()
            const t = toChartTime(h.date)
            if (t == null || Number.isNaN(ts)) continue
            points.push({ time: t, value: Number(h.value ?? 0), timestamp: ts })
        }
        return normalizeSeriesByTime(points)
    }, [chartData?.portfolio_series])

    const drawdownHistory = useCallback(() => {
        const src = chartData?.drawdown_series ?? []
        const points: Array<{ time: Time; value: number; timestamp: number }> = []
        for (const h of src) {
            const ts = new Date(h.date).getTime()
            const t = toChartTime(h.date)
            if (t == null || Number.isNaN(ts)) continue
            points.push({ time: t, value: Number(h.drawdown_percent ?? 0), timestamp: ts })
        }
        return normalizeSeriesByTime(points)
    }, [chartData?.drawdown_series])

    const onChartReady = useCallback((chart: IChartApi) => {
        chartApiRef.current = chart
        instrumentSeriesRef.current = []
        instrumentPriceLinesRef.current = {}
        const data = chartHistory()
        if (!data.length && chartMode === 'portfolio') return
        const indexByTime = new Map<number, number>()
        data.forEach((d, idx) => indexByTime.set(Number(d.time), idx))
        const intraday = isIntradaySeries(data)
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        let series: ISeriesApi<any> | null = null
        if (chartMode === 'portfolio') {
            series = chart.addSeries(AreaSeries, {
                lineColor: isDark ? '#22d3ee' : '#2563eb',
                topColor: isDark ? 'rgba(34,211,238,0.22)' : 'rgba(37,99,235,0.22)',
                bottomColor: 'transparent',
                lineWidth: 2,
                priceLineVisible: false,
                lastValueVisible: true,
            })
            seriesRef.current = series
            if (data.length) {
                series.setData(data.map(d => ({ time: d.time as Time, value: d.value })))
            }
        }

        if (chartMode === 'instruments' && chartData?.instruments_series?.length) {
            chartData.instruments_series
                .filter(s => selectedFigis.includes(s.figi))
                .forEach((s) => {
                const color = getInstrumentColor(s.figi)
                const ls = chart.addSeries(LineSeries, {
                    color,
                    lineWidth: 2,
                    priceLineVisible: false,
                    lastValueVisible: false,
                })
                instrumentSeriesRef.current.push({
                    figi: s.figi,
                    label: s.ticker ? `${s.ticker} (${s.figi})` : s.figi,
                    series: ls,
                })
                instrumentPriceLinesRef.current[s.figi] = ls.createPriceLine({
                    price: 0,
                    color,
                    lineWidth: 1,
                    lineStyle: 2,
                    lineVisible: false,
                    axisLabelVisible: false,
                    title: s.ticker || s.figi,
                })
                const prepared = normalizeSeriesByTime(
                    (s.points || [])
                        .map(p => {
                            const t = toChartTime(p.date)
                            const ts = new Date(p.date).getTime()
                            if (t == null || Number.isNaN(ts)) return null
                            return { time: t, value: Number(p.value || 0), timestamp: ts }
                        })
                        .filter(Boolean) as Array<{ time: Time; value: number; timestamp: number }>
                )
                ls.setData(prepared.map(p => ({ time: p.time as Time, value: p.value })))
            })
        }

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
                Object.values(instrumentPriceLinesRef.current).forEach((pl: any) => {
                    pl.applyOptions({ axisLabelVisible: false, lineVisible: false })
                })
                return
            }
            if (chartMode === 'portfolio' && series) {
                const val = param.seriesData.get(series)
                if (val && val.value != null) {
                    const currTime = Number(param.time)
                    const idx = indexByTime.get(currTime) ?? -1
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
            } else if (chartMode === 'instruments') {
                setCrosshairValue(null)
                instrumentSeriesRef.current.forEach(x => {
                    const point = param.seriesData.get(x.series)
                    const value = point && point.value != null ? Number(point.value) : null
                    const pl = instrumentPriceLinesRef.current[x.figi]
                    if (!pl) return
                    if (value == null) {
                        pl.applyOptions({ axisLabelVisible: false, lineVisible: false })
                    } else {
                        pl.applyOptions({
                            price: value,
                            axisLabelVisible: true,
                            lineVisible: false,
                            title: x.label,
                        })
                    }
                })
            }
        })

        chart.timeScale().subscribeVisibleLogicalRangeChange((range: any) => {
            if (!range) return
            if (!syncingRangeRef.current && drawdownChartRef.current) {
                try {
                    syncingRangeRef.current = true
                    drawdownChartRef.current.timeScale().setVisibleLogicalRange(range)
                } finally {
                    syncingRangeRef.current = false
                }
            }
            if (range.from < 0 && period < 3650) {
                setPeriod(prev => {
                    const nextIdx = PERIODS.findIndex(p => p.days === prev)
                    if (nextIdx < PERIODS.length - 1) return PERIODS[nextIdx + 1].days
                    return prev
                })
            }
        })
    }, [chartHistory, period, chartMode, chartData?.instruments_series, selectedFigis])

    const onDrawdownChartReady = useCallback((chart: IChartApi) => {
        drawdownChartRef.current = chart
        const data = drawdownHistory()
        if (!data.length) return
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        const series = chart.addSeries(LineSeries, {
            color: isDark ? '#f87171' : '#dc2626',
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
        })
        series.setData(data.map(d => ({ time: d.time as Time, value: d.value })))
        chart.timeScale().fitContent()
        chart.timeScale().subscribeVisibleLogicalRangeChange((range: any) => {
            if (!range || !chartApiRef.current) return
            if (!syncingRangeRef.current) {
                try {
                    syncingRangeRef.current = true
                    chartApiRef.current.timeScale().setVisibleLogicalRange(range)
                } finally {
                    syncingRangeRef.current = false
                }
            }
        })
    }, [drawdownHistory])

    const handleSnapshotClick = (snapshot: PortfolioSnapshotSummary) => {
        if (selectedAccountId && snapshot.snapshot_id) {
            loadPositions(selectedAccountId, snapshot.snapshot_id)
        }
    }

    const posColumns: Column<any>[] = [
        { key: 'figi', header: bybitAccount ? 'Символ' : 'FIGI', sortable: true, width: '140px' },
        { key: 'ticker', header: 'Тикер', sortable: true, width: '80px', render: r => r.ticker || '—' },
        { key: 'instrument_type', header: 'Тип', sortable: true, width: '80px' },
        { key: 'quantity', header: 'Кол-во', sortable: true, align: 'right', render: r => Number(r.quantity ?? 0).toLocaleString('ru-RU') },
        { key: 'avg_price', header: 'Средняя', sortable: true, align: 'right', render: r => money(r.avg_price) },
        { key: 'current_price', header: 'Текущая', align: 'right', render: r => money(r.current_price) },
        {
            key: 'expected_yield', header: 'P&L', sortable: true, align: 'right',
            render: r => {
                const v = Number(r.expected_yield ?? 0)
                return <span className={v >= 0 ? 'color-up' : 'color-down'}>{moneySigned(v)}</span>
            },
        },
        {
            key: 'total_value', header: 'Стоимость', sortable: true, align: 'right',
            render: r => money(r.total_value),
        },
    ]

    const historyColumns: Column<PortfolioSnapshotSummary>[] = [
        {
            key: 'date', header: 'Дата и время', sortable: true,
            render: r => new Date(r.date).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }),
        },
        { key: 'total_value', header: 'Стоимость', sortable: true, align: 'right', render: r => money(r.total_value) },
        {
            key: 'daily_yield', header: 'Дневной доход', sortable: true, align: 'right',
            render: r => <span className={r.daily_yield >= 0 ? 'color-up' : 'color-down'}>{moneySigned(r.daily_yield)}</span>,
        },
    ]

    const operationsColumns: Column<any>[] = [
        { key: 'operation_date', header: 'Дата', render: r => new Date(r.operation_date).toLocaleString('ru-RU') },
        { key: 'operation_type', header: 'Тип API', width: '180px' },
        { key: 'type_text', header: 'Описание', render: r => r.type_text || '—' },
        { key: 'figi', header: bybitAccount ? 'Символ' : 'FIGI', render: r => r.figi || '—' },
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
        return (
            <div className="page" data-page="portfolio">
                <PortfolioHero />
                <div className="ops-loader">
                    <div className="soft-loading-bar" />
                    <div className="ops-loader__text">Загрузка портфеля...</div>
                </div>
            </div>
        )
    }

    if (accounts.length === 0) {
        return (
            <div className="page" data-page="portfolio">
                <PortfolioHero />
                <Card className="portfolio-panel">
                    <p className="portfolio-empty">
                        Нет счетов портфеля. Запустите робота обновления портфеля (ByBit или T-Invest), чтобы появились снимки.
                    </p>
                </Card>
            </div>
        )
    }

    return (
        <div className="page" data-page="portfolio">
            <PortfolioHero
                accountLabel={selectedAccount ? formatPortfolioAccountLabel(selectedAccount) : undefined}
            />

            <div className="portfolio-layout">
            <div className="portfolio-toolbar">
                <div className="portfolio-toolbar__account">
                    <Select
                        options={accounts.map(a => ({ value: String(a.id), label: formatPortfolioAccountLabel(a) }))}
                        value={selectedAccountId != null ? String(selectedAccountId) : ''}
                        onChange={handleAccountChange}
                        placeholder="Выберите счёт"
                    />
                </div>

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

                <div className="portfolio-toolbar__range">
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
            </div>

            <Card className="portfolio-panel portfolio-panel--stats">
                <h3 className="dashboard-panel-title">Статистика портфеля</h3>
                {statsLoading ? (
                    <div className="ops-loader">
                        <div className="soft-loading-bar" />
                        <div className="ops-loader__text">Расчет статистики...</div>
                    </div>
                ) : (
                    <div className="portfolio-stats-rows">
                        <div className="portfolio-stats-row-title">Общее</div>
                        <div className="portfolio-stats-grid">
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Собственные средства</div>
                                <div className="portfolio-stat-tile__value">{money(stats?.overall.own_funds)}</div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Текущая стоимость</div>
                                <div className="portfolio-stat-tile__value">{money(stats?.overall.current_total_value)}</div>
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
                                <div className="portfolio-stat-tile__label">Чистый приток капитала</div>
                                <div className={`portfolio-stat-tile__value ${roiClass(stats?.capital_flow.net_capital_inflow)}`}>{moneySigned(stats?.capital_flow.net_capital_inflow)}</div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Дивиденды полученные</div>
                                <div className="portfolio-stat-tile__value color-up">
                                    {money(stats?.capital_flow.dividends_received)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Реализованный P&L (FIFO)</div>
                                <div className={`portfolio-stat-tile__value ${roiClass(stats?.capital_flow.realized_pnl)}`}>
                                    {moneySigned(stats?.capital_flow.realized_pnl)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Нереализованный P&L</div>
                                <div className={`portfolio-stat-tile__value ${roiClass(stats?.capital_flow.unrealized_pnl)}`}>
                                    {moneySigned(stats?.capital_flow.unrealized_pnl)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Win Rate</div>
                                <div className={`portfolio-stat-tile__value ${roiClass((stats?.trading_performance.win_rate_percent ?? 0) - 50)}`}>
                                    {formatPercent(stats?.trading_performance.win_rate_percent)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Profit Factor</div>
                                <div className={`portfolio-stat-tile__value ${profitFactorClass(stats?.trading_performance.profit_factor)}`}>
                                    {formatFactor(stats?.trading_performance.profit_factor)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Макс серия убытков</div>
                                <div className="portfolio-stat-tile__value color-down">
                                    {formatLossStreak(
                                        stats?.trading_performance.max_consecutive_losses,
                                        stats?.trading_performance.max_consecutive_losses_sum,
                                        accountCurrency,
                                    )}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Средняя прибыльная / убыточная</div>
                                <div className="portfolio-stat-tile__value">
                                    {money(stats?.trading_performance.avg_winning_trade)} / {money(stats?.trading_performance.avg_losing_trade)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Avg Win / Avg Loss</div>
                                <div className="portfolio-stat-tile__value">{formatFactor(stats?.trading_performance.avg_win_loss_ratio)}</div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Среднее время удержания</div>
                                <div className="portfolio-stat-tile__value">
                                    {formatHoldTime(stats?.operational_metrics.average_hold_time_hours)} {stats?.operational_metrics.average_hold_time_label ? `(${stats.operational_metrics.average_hold_time_label})` : ''}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Комиссии брокера / вознаграждение</div>
                                <div className="portfolio-stat-tile__value color-down">
                                    {money(stats?.operational_metrics.total_broker_fees)} / {money(stats?.operational_metrics.total_track_fees)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Налоги</div>
                                <div className="portfolio-stat-tile__value color-down">
                                    {money(stats?.operational_metrics.total_taxes)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Портфель vs IMOEX</div>
                                <div className="portfolio-stat-tile__value">
                                    {stats?.benchmark_metrics.benchmark_unavailable
                                        ? 'нет данных'
                                        : `${formatPercent(stats?.benchmark_metrics.portfolio_return_percent)} / ${formatPercent(stats?.benchmark_metrics.imoex_return_percent)}`}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Относительная доходность</div>
                                <div className={`portfolio-stat-tile__value ${roiClass(stats?.benchmark_metrics.relative_return_percent)}`}>
                                    {stats?.benchmark_metrics.benchmark_unavailable ? 'нет данных' : formatPercent(stats?.benchmark_metrics.relative_return_percent)}
                                </div>
                            </div>
                            <div className="portfolio-stat-tile">
                                <div className="portfolio-stat-tile__label">Max Drawdown / Recovery / Current DD</div>
                                <div className="portfolio-stat-tile__value">
                                    {formatPercent(stats?.risk_recovery.max_drawdown_percent, true)} / {formatDays(stats?.risk_recovery.average_recovery_days)} / {formatPercent(stats?.risk_recovery.current_drawdown_percent, true)}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </Card>

            <Card className="portfolio-panel portfolio-panel--chart">
                <div className="portfolio-chart-header">
                    <h3 className="dashboard-panel-title">Стоимость портфеля</h3>
                    <div className="portfolio-chart-header__controls">
                        <Toggle
                            checked={chartMode === 'instruments'}
                            onChange={(on) => setChartMode(on ? 'instruments' : 'portfolio')}
                            label="Посмотреть бумаги"
                        />
                    </div>
                </div>
                {chartMode === 'portfolio' && crosshairValue && (
                    <div className="mono portfolio-crosshair-main">
                        {formatPortfolioMoney(crosshairValue.value, accountCurrency, 0)}
                        {crosshairValue.delta != null && (
                            <span
                                className={crosshairValue.delta >= 0 ? 'color-up' : 'color-down'}
                                style={{ marginLeft: 'var(--space-2)' }}
                            >
                                {formatPortfolioMoneySigned(crosshairValue.delta, accountCurrency)}
                                {crosshairValue.deltaPct != null && (
                                    <span style={{ marginLeft: 4 }}>
                                        ({crosshairValue.deltaPct >= 0 ? '+' : ''}
                                        {crosshairValue.deltaPct.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%)
                                    </span>
                                )}
                            </span>
                        )}
                        <span className="portfolio-crosshair-main__time">
                            {crosshairValue.time}
                        </span>
                    </div>
                )}
                {chartLoading ? (
                    <div className="ops-loader">
                        <div className="soft-loading-bar" />
                        <div className="ops-loader__text">Построение графика...</div>
                    </div>
                ) : (
                    <Chart height={360} onReady={onChartReady} key={`${selectedAccountId}-${fromDate}-${toDate}-${chartMode}-${selectedFigis.join(',')}`} />
                )}
                {chartMode === 'portfolio' && (
                    <div style={{ marginTop: 'var(--space-3)' }}>
                        {chartLoading ? (
                            <div className="ops-loader">
                                <div className="soft-loading-bar" />
                                <div className="ops-loader__text">Построение графика просадки...</div>
                            </div>
                        ) : (
                            <Chart
                                height={140}
                                onReady={onDrawdownChartReady}
                                key={`dd-${selectedAccountId}-${fromDate}-${toDate}-${chartData?.drawdown_series?.length ?? 0}`}
                            />
                        )}
                    </div>
                )}
                {chartMode === 'instruments' && (
                    <div className="portfolio-legend">
                        {(chartData?.instruments_series || [])
                            .filter(s => Array.isArray(s.points) && s.points.length > 0)
                            .map((s) => {
                            const active = selectedFigis.includes(s.figi)
                            return (
                                <button
                                    key={s.figi}
                                    className={`portfolio-legend-item ${active ? 'portfolio-legend-item--active' : ''}`}
                                    onClick={() => {
                                        setSelectedFigis(prev => (
                                            prev.includes(s.figi) ? prev.filter(x => x !== s.figi) : [...prev, s.figi]
                                        ))
                                    }}
                                >
                                    <span className="portfolio-legend-color" style={{ backgroundColor: getInstrumentColor(s.figi) }} />
                                    <span>{s.ticker ? `${s.ticker} (${s.figi})` : s.figi}</span>
                                </button>
                            )
                        })}
                    </div>
                )}
            </Card>

            <CollapsibleSection
                className="portfolio-collapse"
                title="Состав портфеля "
                badge={
                    <span className="portfolio-collapse__count">
                        {positions.length}
                    </span>
                }
                defaultOpen
            >
                {posLoading ? (
                    <div className="ops-loader">
                        <div className="soft-loading-bar" />
                        <div className="ops-loader__text">Загрузка состава портфеля...</div>
                    </div>
                ) : (
                    <DataTable
                        columns={posColumns}
                        data={positions}
                        keyField="figi"
                        emptyText="Нет позиций"
                        mobilePrimary={(r) => `${r.ticker || '—'} (${r.figi || '—'})`}
                        mobileSecondary={(r) => `${Number(r.quantity ?? 0).toLocaleString('ru-RU')} шт. | ${money(r.total_value)}`}
                        mobileDetails={(r) => (
                            <>
                                <div>Тип: {r.instrument_type || '—'}</div>
                                <div>Средняя цена: {money(r.avg_price)}</div>
                                <div>
                                    Текущая цена: {money(r.current_price)}{' '}
                                    <span className={Number(r.expected_yield ?? 0) >= 0 ? 'color-up' : 'color-down'}>
                                        ({Number(r.expected_yield ?? 0) >= 0 ? '+' : ''}
                                        {money(r.expected_yield ?? 0)})
                                    </span>
                                </div>
                                <div>
                                    P&amp;L:{' '}
                                    <span className={Number(r.expected_yield ?? 0) >= 0 ? 'color-up' : 'color-down'}>
                                        {money(r.expected_yield ?? 0)}
                                    </span>
                                </div>
                            </>
                        )}
                    />
                )}
            </CollapsibleSection>

            <CollapsibleSection
                className="portfolio-collapse"
                title="История снимков"
                defaultOpen={false}
            >
                {snapshotsLoading ? (
                    <div className="ops-loader">
                        <div className="soft-loading-bar" />
                        <div className="ops-loader__text">Загрузка истории снимков...</div>
                    </div>
                ) : (
                    <>
                        <DataTable
                            columns={historyColumns}
                            data={snapshots.slice(0, 500)}
                            keyField="date"
                            emptyText="Нет истории"
                            onRowClick={handleSnapshotClick as any}
                            maxHeight={420}
                            mobilePrimary={(r) => new Date(r.date).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                            mobileSecondary={(r) => money(r.total_value, 0)}
                            mobileDetails={(r) => (
                                <>
                                    <div>
                                        Дневной доход:{' '}
                                        <span className={r.daily_yield >= 0 ? 'color-up' : 'color-down'}>
                                            {moneySigned(r.daily_yield)}
                                        </span>
                                    </div>
                                    <button
                                        type="button"
                                        className="btn btn--secondary btn--sm"
                                        style={{ width: 'fit-content' }}
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            handleSnapshotClick(r)
                                        }}
                                    >
                                        Показать состав снимка
                                    </button>
                                </>
                            )}
                        />
                    </>
                )}
            </CollapsibleSection>

            <CollapsibleSection
                className="portfolio-collapse"
                title="История операций"
                defaultOpen={false}
            >
                {opsLoading ? (
                    <div className="ops-loader">
                        <div className="soft-loading-bar" />
                        <div className="ops-loader__text">Загрузка истории операций...</div>
                    </div>
                ) : (
                    <DataTable
                        columns={operationsColumns}
                        data={operations}
                        keyField="operation_id"
                        emptyText="Нет операций за период"
                        maxHeight={420}
                        mobilePrimary={(r) => `${new Date(r.operation_date).toLocaleDateString('ru-RU')} • ${r.type_text || '—'}`}
                        mobileSecondary={(r) => `${Number(r.payment || 0).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${r.currency || ''}`}
                        mobileDetails={(r) => (
                            <>
                                <div>Описание: {r.type_text || '—'}</div>
                                <div>FIGI: {r.figi || '—'}</div>
                                <div>Количество: {Number(r.quantity || 0).toLocaleString('ru-RU')}</div>
                                <div>Цена: {Number(r.price || 0).toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</div>
                                <div>Статус: {r.status || '—'}</div>
                            </>
                        )}
                    />
                )}
            </CollapsibleSection>
            </div>
        </div>
    )
}

function PortfolioHero({ accountLabel }: { accountLabel?: string }) {
    return (
        <header className="dashboard-hero portfolio-hero">
            <div className="dashboard-hero__bg" style={{ backgroundImage: `url(${cyberHero})` }} aria-hidden />
            <div className="dashboard-hero__veil" aria-hidden />
            <div className="dashboard-hero__content">
                <p className="dashboard-hero__eyebrow">GIN // ANALYTICS NODE</p>
                <h1 className="dashboard-hero__title">
                    <span className="dashboard-hero__title-glitch" data-text="ПОРТФЕЛЬ">ПОРТФЕЛЬ</span>
                </h1>
                <p className="dashboard-hero__sub">
                    {accountLabel
                        ? `Счёт · ${accountLabel}`
                        : 'Статистика · графики · позиции · операции'}
                </p>
            </div>
        </header>
    )
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

function formatFactor(val: number | null | undefined): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    return Number(val).toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}

function profitFactorClass(val: number | null | undefined): string {
    if (val == null || Number.isNaN(Number(val))) return ''
    const n = Number(val)
    if (n > 1.5) return 'color-up'
    if (n < 1) return 'color-down'
    return ''
}

function formatLossStreak(count: number | undefined, lossSum: number | null | undefined, currency = 'RUB'): string {
    if (!count) return '—'
    const sumText = lossSum != null ? ` (${formatPortfolioMoney(lossSum, currency)})` : ''
    return `${count} подряд${sumText}`
}

function formatHoldTime(hours: number | null | undefined): string {
    if (hours == null || Number.isNaN(Number(hours))) return '—'
    const h = Number(hours)
    if (h < 24) return `${h.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} ч`
    return `${(h / 24).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} д`
}

function formatDays(days: number | null | undefined): string {
    if (days == null || Number.isNaN(Number(days))) return '—'
    return `${Number(days).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} д`
}

function getInstrumentColor(figi: string): string {
    const palette = ['#3b82f6', '#22c55e', '#a855f7', '#f59e0b', '#ef4444', '#14b8a6', '#f97316', '#84cc16', '#8b5cf6', '#06b6d4']
    let hash = 0
    for (let i = 0; i < figi.length; i += 1) {
        hash = (hash * 31 + figi.charCodeAt(i)) >>> 0
    }
    return palette[hash % palette.length]
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
