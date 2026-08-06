import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Chart, type IChartApi, type ISeriesApi, type Time } from '@/components/ui/Chart'
import { AreaSeries, LineSeries } from 'lightweight-charts'
import { Select } from '@/components/ui/Select'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { Toggle } from '@/components/ui/Toggle'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Skeleton } from '@/components/ui/Skeleton'
import { PageHero } from '@/components/ui/PageHero'
import { StatTile } from '@/components/ui/StatTile'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { analyticsService } from '@/services/analyticsService'
import type { AccountSummary, PortfolioSnapshotSummary, PortfolioStatisticsExtendedResponse, AnalyticsChartSeriesResponse } from '@/types/api'
import { useToast } from '@/components/ui/Toast'
import {
    formatPortfolioAccountLabel,
    formatPortfolioMoney,
    formatPortfolioMoneySigned,
    isBybitPortfolioAccount,
} from '@/utils/portfolioFormat'
import { PortfolioComposition } from '@/components/portfolio/PortfolioComposition'
import { useMediaQuery } from '@/hooks/useMediaQuery'

///@EPIC Frontend.ITEM Portfolio.TOPIC Account Performance Screen [1]
///@ Экран портфеля: выбор счета/периода, таблицы позиций, динамика стоимости,
///@ статистика и графики, собранные из analytics endpoints.
const PERIODS = [
    { label: 'День', days: 1 },
    { label: 'Неделя', days: 7 },
    { label: 'Месяц', days: 30 },
    { label: '3 месяца', days: 90 },
    { label: 'Всё время', days: 3650 },
] as const

/** Mobile period strip: drop "3 месяца" so the control fits without horizontal scroll. */
const MOBILE_PERIOD_DAYS = new Set([1, 7, 30, 3650])

const PERIOD_OPTIONS = PERIODS.map(p => ({ value: String(p.days), label: p.label }))

export default function PortfolioPage() {
    const toast = useToast()
    const isMobile = useMediaQuery('(max-width: 767px)')
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
    const seriesRef = useRef<ISeriesApi<any> | null>(null)
    const instrumentSeriesRef = useRef<Array<{ figi: string; label: string; series: ISeriesApi<any> }>>([])
    const instrumentPriceLinesRef = useRef<Record<string, any>>({})

    useEffect(() => { loadAccounts() }, [])
    useEffect(() => {
        if (!selectedAccountId) return
        loadSnapshots(selectedAccountId)
        loadOperations(selectedAccountId)
        loadStatistics(selectedAccountId)
        loadChartSeries(selectedAccountId)
    }, [selectedAccountId, fromDate, toDate])

    useEffect(() => {
        if (!isMobile || MOBILE_PERIOD_DAYS.has(period)) return
        setPeriod(30)
        const now = new Date()
        setFromDate(new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10))
        setToDate(now.toISOString().slice(0, 10))
    }, [isMobile, period])

    const periodOptions = useMemo(
        () => (isMobile ? PERIOD_OPTIONS.filter(p => MOBILE_PERIOD_DAYS.has(Number(p.value))) : PERIOD_OPTIONS),
        [isMobile],
    )

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

    const onChartReady = useCallback((chart: IChartApi | null) => {
        if (!chart) {
            chartApiRef.current = null
            seriesRef.current = null
            instrumentSeriesRef.current = []
            instrumentPriceLinesRef.current = {}
            return
        }
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
                    label: instrumentChartLabel(s),
                    series: ls,
                })
                instrumentPriceLinesRef.current[s.figi] = ls.createPriceLine({
                    price: 0,
                    color,
                    lineWidth: 1,
                    lineStyle: 2,
                    lineVisible: false,
                    axisLabelVisible: false,
                    title: instrumentChartLabel(s),
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
            if (range.from < 0 && period < 3650) {
                setPeriod(prev => {
                    const nextIdx = PERIODS.findIndex(p => p.days === prev)
                    if (nextIdx < PERIODS.length - 1) return PERIODS[nextIdx + 1].days
                    return prev
                })
            }
        })
    }, [chartHistory, period, chartMode, chartData?.instruments_series, selectedFigis])

    const handleSnapshotClick = (snapshot: PortfolioSnapshotSummary) => {
        if (selectedAccountId && snapshot.snapshot_id) {
            loadPositions(selectedAccountId, snapshot.snapshot_id)
        }
    }

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
        {
            key: 'operation_type_name',
            header: 'Операция',
            width: '180px',
            render: r => String(r.operation_type_name || r.operation_type || '—'),
        },
        { key: 'type_text', header: 'Описание', render: r => r.type_text || '—' },
        {
            key: 'ticker_name',
            header: 'Актив',
            render: r => String(r.ticker_name || r.ticker || r.figi || '—'),
        },
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
        {
            key: 'status_name',
            header: 'Статус',
            width: '160px',
            render: r => String(r.status_name || r.status || '—'),
        },
    ]

    if (loading) {
        return (
            <div className="page" data-page="portfolio">
                <PageHero
                    eyebrow="ANALYTICS NODE"
                    title="ПОРТФЕЛЬ"
                    subtitle="Статистика · позиции · операции"
                />
                <PortfolioSkeleton />
            </div>
        )
    }

    if (accounts.length === 0) {
        return (
            <div className="page" data-page="portfolio">
                <PageHero
                    eyebrow="ANALYTICS NODE"
                    title="ПОРТФЕЛЬ"
                    subtitle="Статистика · позиции · операции"
                />
                <Card className="dashboard-totals-card dashboard-error-card">
                    <div className="dashboard-error-card__robot" aria-hidden>
                        <RobotIllustration size={96} mode="inactive" interactive={false} />
                    </div>
                    <p className="dashboard-empty">
                        Нет счетов портфеля. Запустите робота обновления портфеля (ByBit или T-Invest), чтобы появились снимки.
                    </p>
                </Card>
            </div>
        )
    }

    const applyPeriod = (days: number) => {
        setPeriod(days)
        const now = new Date()
        const from = new Date(Date.now() - days * 86400000)
        setFromDate(from.toISOString().slice(0, 10))
        setToDate(now.toISOString().slice(0, 10))
    }

    const hasChartData = chartMode === 'instruments'
        ? (chartData?.instruments_series || []).some(s => Array.isArray(s.points) && s.points.length > 0)
        : (chartData?.portfolio_series?.length ?? 0) > 0

    const instrumentLegendItems = (chartData?.instruments_series || [])
        .filter(s => Array.isArray(s.points) && s.points.length > 0)
    const allInstrumentFigis = instrumentLegendItems.map(s => s.figi)
    const allInstrumentsSelected = allInstrumentFigis.length > 0
        && allInstrumentFigis.every(figi => selectedFigis.includes(figi))
    const chartHeight = isMobile ? 240 : 360
    const periodStatsClassName = isMobile
        ? 'portfolio-stats-grid dashboard-summary-grid'
        : 'portfolio-stats-grid'

    const periodStatsGrid = (
        <div className={periodStatsClassName}>
            <StatTile
                label="Чистый приток капитала"
                valueClassName={roiClass(stats?.capital_flow.net_capital_inflow)}
                value={moneySigned(stats?.capital_flow.net_capital_inflow)}
            />
            <StatTile
                label="Дивиденды полученные"
                valueClassName="color-up"
                value={money(stats?.capital_flow.dividends_received)}
            />
            <StatTile
                label="Реализованный P&L (FIFO)"
                valueClassName={roiClass(stats?.capital_flow.realized_pnl)}
                value={moneySigned(stats?.capital_flow.realized_pnl)}
            />
            <StatTile
                label="Нереализованный P&L"
                valueClassName={roiClass(stats?.capital_flow.unrealized_pnl)}
                value={moneySigned(stats?.capital_flow.unrealized_pnl)}
            />
            <StatTile
                label="Win Rate"
                valueClassName={roiClass((stats?.trading_performance.win_rate_percent ?? 0) - 50)}
                value={formatPercent(stats?.trading_performance.win_rate_percent)}
            />
            <StatTile
                label="Profit Factor"
                valueClassName={profitFactorClass(stats?.trading_performance.profit_factor)}
                value={formatFactor(stats?.trading_performance.profit_factor)}
            />
            <StatTile
                label="Макс серия убытков"
                valueClassName="color-down"
                value={formatLossStreak(
                    stats?.trading_performance.max_consecutive_losses,
                    stats?.trading_performance.max_consecutive_losses_sum,
                    accountCurrency,
                )}
            />
            <StatTile
                label="Средняя прибыльная / убыточная"
                value={`${money(stats?.trading_performance.avg_winning_trade)} / ${money(stats?.trading_performance.avg_losing_trade)}`}
            />
            <StatTile
                label="Avg Win / Avg Loss"
                value={formatFactor(stats?.trading_performance.avg_win_loss_ratio)}
            />
            <StatTile
                label="Среднее время удержания"
                value={
                    <>
                        {formatHoldTime(stats?.operational_metrics.average_hold_time_hours)}
                        {stats?.operational_metrics.average_hold_time_label
                            ? ` (${stats.operational_metrics.average_hold_time_label})`
                            : ''}
                    </>
                }
            />
            <StatTile
                label="Комиссии брокера / вознаграждение"
                valueClassName="color-down"
                value={`${money(stats?.operational_metrics.total_broker_fees)} / ${money(stats?.operational_metrics.total_track_fees)}`}
            />
            <StatTile
                label="Налоги"
                valueClassName="color-down"
                value={money(stats?.operational_metrics.total_taxes)}
            />
            <StatTile
                label="Портфель vs IMOEX"
                value={
                    stats?.benchmark_metrics.benchmark_unavailable
                        ? 'нет данных'
                        : `${formatPercent(stats?.benchmark_metrics.portfolio_return_percent)} / ${formatPercent(stats?.benchmark_metrics.imoex_return_percent)}`
                }
            />
            <StatTile
                label="Относительная доходность"
                valueClassName={roiClass(stats?.benchmark_metrics.relative_return_percent)}
                value={
                    stats?.benchmark_metrics.benchmark_unavailable
                        ? 'нет данных'
                        : formatPercent(stats?.benchmark_metrics.relative_return_percent)
                }
            />
            <StatTile
                label="Max Drawdown / Recovery / Current DD"
                value={`${formatPercent(stats?.risk_recovery.max_drawdown_percent, true)} / ${formatDays(stats?.risk_recovery.average_recovery_days)} / ${formatPercent(stats?.risk_recovery.current_drawdown_percent, true)}`}
            />
        </div>
    )

    const chartBody = (
        <>
            <div className={`portfolio-chart-header${isMobile ? ' portfolio-chart-header--mobile' : ''}`}>
                {!isMobile && <h3 className="dashboard-panel-title">Стоимость портфеля</h3>}
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
                <div aria-busy="true" aria-label="Построение графика" style={{ marginTop: 'var(--space-3)' }}>
                    <Skeleton width="100%" height={`${chartHeight}px`} borderRadius="8px" />
                </div>
            ) : (
                <Chart
                    height={chartHeight}
                    onReady={onChartReady}
                    key={`${selectedAccountId}-${fromDate}-${toDate}-${chartMode}-${selectedFigis.join(',')}`}
                />
            )}
            <div className="portfolio-chart-midbar">
                {chartMode === 'instruments' && (
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="dashboard-settings-group__bulk"
                        disabled={allInstrumentFigis.length === 0}
                        onClick={() => setSelectedFigis(allInstrumentsSelected ? [] : allInstrumentFigis)}
                    >
                        {allInstrumentsSelected ? 'Снять все' : 'Выделить все'}
                    </Button>
                )}
                <Toggle
                    checked={chartMode === 'instruments'}
                    onChange={(on) => setChartMode(on ? 'instruments' : 'portfolio')}
                    label="Посмотреть бумаги"
                />
            </div>
            {chartMode === 'instruments' && (
                <div className="portfolio-legend">
                    {instrumentLegendItems.map((s) => {
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
                                <span>{instrumentChartLabel(s)}</span>
                            </button>
                        )
                    })}
                </div>
            )}
        </>
    )

    return (
        <div className="page" data-page="portfolio">
            <PageHero
                eyebrow="ANALYTICS NODE"
                title="ПОРТФЕЛЬ"
                subtitle="Статистика · позиции · операции"
            />

            <div className="dashboard-layout">
            <Card className="portfolio-toolbar">
                <div className="portfolio-toolbar__account">
                    <Select
                        options={accounts.map(a => ({ value: String(a.id), label: formatPortfolioAccountLabel(a) }))}
                        value={selectedAccountId != null ? String(selectedAccountId) : ''}
                        onChange={handleAccountChange}
                        placeholder="Выберите счёт"
                    />
                </div>

                <SegmentedControl
                    className="portfolio-period-control"
                    aria-label="Период"
                    options={periodOptions}
                    value={String(period)}
                    onChange={(v) => applyPeriod(Number(v))}
                />

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
                        showLabel={false}
                    />
                </div>
            </Card>

            <Card className="dashboard-totals-card">
                <div className="dashboard-totals-card__head">
                    <h3 className="dashboard-panel-title">Статистика портфеля</h3>
                </div>
                {statsLoading ? (
                    <div className="portfolio-stats-rows" aria-busy="true" aria-label="Расчет статистики">
                        <Skeleton width="72px" height="12px" borderRadius="4px" />
                        <div className="portfolio-stats-grid">
                            {[0, 1, 2, 3].map((i) => (
                                <div key={i} className="portfolio-stat-tile">
                                    <Skeleton width="70%" height="12px" borderRadius="4px" />
                                    <div style={{ marginTop: 'var(--space-2)' }}>
                                        <Skeleton width="55%" height="20px" borderRadius="4px" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div className="portfolio-stats-rows">
                        <div className="portfolio-stats-row-title">Общее</div>
                        <div className="portfolio-stats-grid dashboard-summary-grid">
                            <StatTile label="Собственные средства" value={money(stats?.overall.own_funds)} />
                            <StatTile label="Текущая стоимость" value={money(stats?.overall.current_total_value)} />
                            <StatTile
                                label="ROI общий"
                                valueClassName={roiClass(stats?.overall.roi_percent)}
                                value={formatPercent(stats?.overall.roi_percent)}
                            />
                            <StatTile
                                label="ROI среднемесячный (весь период)"
                                valueClassName={roiClass(stats?.overall.avg_monthly_roi_percent)}
                                value={formatPercent(stats?.overall.avg_monthly_roi_percent)}
                            />
                        </div>

                        {isMobile ? (
                            <CollapsibleSection
                                className="portfolio-collapse portfolio-stats-period-collapse"
                                title="Выбранный период "
                                defaultOpen={false}
                            >
                                {periodStatsGrid}
                            </CollapsibleSection>
                        ) : (
                            <>
                                <div className="portfolio-stats-row-title">Выбранный период</div>
                                {periodStatsGrid}
                            </>
                        )}
                    </div>
                )}
            </Card>

            {chartLoading || hasChartData ? (
                isMobile ? (
                    <CollapsibleSection
                        className="dashboard-assets-collapse"
                        title="Стоимость портфеля "
                        defaultOpen={false}
                    >
                        {chartBody}
                    </CollapsibleSection>
                ) : (
                    <Card className="dashboard-assets-card">
                        {chartBody}
                    </Card>
                )
            ) : (
                <Card className="dashboard-assets-card dashboard-error-card">
                    <div className="dashboard-error-card__robot" aria-hidden>
                        <RobotIllustration size={96} mode="inactive" interactive={false} />
                    </div>
                    <p className="dashboard-empty">
                        Нет данных графика за выбранный период.
                    </p>
                </Card>
            )}

            <PortfolioComposition
                positions={positions}
                loading={posLoading}
                currency={accountCurrency}
                bybitAccount={bybitAccount}
                defaultOpen={!isMobile}
            />

            <CollapsibleSection
                className="portfolio-collapse"
                title="История снимков"
                badge={
                    <span className="portfolio-collapse__count">{snapshots.length}</span>
                }
                defaultOpen={false}
            >
                {snapshotsLoading ? (
                    <div aria-busy="true" aria-label="Загрузка истории снимков">
                        <Skeleton width="100%" height="120px" borderRadius="8px" />
                    </div>
                ) : (
                    <DataTable
                        columns={historyColumns}
                        data={snapshots.slice(0, 500)}
                        keyField="date"
                        emptyText="Нет истории"
                        onRowClick={handleSnapshotClick as any}
                        maxHeight={420}
                        mobilePrimary={(r) => (
                            <div className="portfolio-mobile-split">
                                <span className="portfolio-mobile-split__muted mono">
                                    {new Date(r.date).toLocaleString('ru-RU', {
                                        day: '2-digit',
                                        month: '2-digit',
                                        year: 'numeric',
                                        hour: '2-digit',
                                        minute: '2-digit',
                                    })}
                                </span>
                                <span className="portfolio-mobile-split__value mono">
                                    {money(r.total_value, 0)}
                                </span>
                            </div>
                        )}
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
                )}
            </CollapsibleSection>

            <CollapsibleSection
                className="portfolio-collapse"
                title="История операций"
                badge={
                    <span className="portfolio-collapse__count">{operations.length}</span>
                }
                defaultOpen={false}
            >
                {opsLoading ? (
                    <div aria-busy="true" aria-label="Загрузка истории операций">
                        <Skeleton width="100%" height="120px" borderRadius="8px" />
                    </div>
                ) : (
                    <DataTable
                        columns={operationsColumns}
                        data={operations}
                        keyField="operation_id"
                        emptyText="Нет операций за период"
                        maxHeight={420}
                        mobilePrimary={(r) => {
                            const payment = Number(r.payment || 0)
                            return (
                                <div className="portfolio-mobile-stack">
                                    <div className="portfolio-mobile-split">
                                        <span className="portfolio-mobile-split__muted mono">
                                            {new Date(r.operation_date).toLocaleString('ru-RU', {
                                                day: '2-digit',
                                                month: '2-digit',
                                                year: 'numeric',
                                                hour: '2-digit',
                                                minute: '2-digit',
                                            })}
                                        </span>
                                        <span className="portfolio-mobile-split__type">
                                            {r.operation_type_name || r.operation_type || '—'}
                                        </span>
                                    </div>
                                    <div className="portfolio-mobile-split">
                                        <span className="portfolio-mobile-split__asset">
                                            {r.short_name || r.ticker || '—'}
                                        </span>
                                        <span className={`portfolio-mobile-split__value mono ${payment >= 0 ? 'color-up' : 'color-down'}`}>
                                            {payment.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}
                                            {r.currency ? ` ${r.currency}` : ''}
                                        </span>
                                    </div>
                                </div>
                            )
                        }}
                        mobileDetails={(r) => (
                            <>
                                <div className="portfolio-mobile-split__asset-full">
                                    {r.ticker_name || r.short_name || r.ticker || r.figi || '—'}
                                </div>
                                <div>Описание: {r.type_text || '—'}</div>
                                <div>Количество: {Number(r.quantity || 0).toLocaleString('ru-RU')}</div>
                                <div>Цена: {Number(r.price || 0).toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</div>
                                <div>Статус: {r.status_name || r.status || '—'}</div>
                            </>
                        )}
                    />
                )}
            </CollapsibleSection>
            </div>
        </div>
    )
}

function PortfolioSkeleton() {
    return (
        <div className="dashboard-layout" aria-busy="true" aria-label="Загрузка портфеля">
            <Skeleton width="100%" height="56px" borderRadius="8px" />
            <Card className="dashboard-totals-card dashboard-skeleton-card">
                <div className="dashboard-totals-card__head">
                    <Skeleton width="160px" height="18px" borderRadius="4px" />
                </div>
                <div className="portfolio-stats-grid dashboard-summary-grid">
                    {[0, 1, 2, 3].map((i) => (
                        <div key={i} className="portfolio-stat-tile">
                            <Skeleton width="70%" height="12px" borderRadius="4px" />
                            <div style={{ marginTop: 'var(--space-2)' }}>
                                <Skeleton width="55%" height="20px" borderRadius="4px" />
                            </div>
                        </div>
                    ))}
                </div>
            </Card>
            <Card className="dashboard-assets-card dashboard-skeleton-card">
                <div className="dashboard-assets-card__head">
                    <Skeleton width="140px" height="18px" borderRadius="4px" />
                </div>
                <Skeleton width="100%" height="280px" borderRadius="8px" />
            </Card>
        </div>
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

function instrumentChartLabel(s: { figi: string; name?: string | null; ticker?: string | null }): string {
    const name = String(s.name || s.ticker || '').trim()
    return name ? `${name} (${s.figi})` : s.figi
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
