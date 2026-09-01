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
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { analyticsService } from '@/services/analyticsService'
import type {
    AccountSummary,
    AnalyticsOperationItem,
    PortfolioSnapshotSummary,
    PortfolioStatisticsExtendedResponse,
    AnalyticsChartSeriesResponse,
} from '@/types/api'
import { useToast } from '@/components/ui/Toast'
import {
    formatPortfolioAccountLabel,
    formatPortfolioAccountPlatformTag,
    formatPortfolioMoney,
    formatPortfolioMoneySigned,
    isBybitPortfolioAccount,
} from '@/utils/portfolioFormat'
import { PortfolioComposition } from '@/components/portfolio/PortfolioComposition'
import { Tooltip } from '@/components/ui/Tooltip'
import { useMediaQuery } from '@/hooks/useMediaQuery'

const RETRY_MIN_MS = 1800
const OBSERVATION_LOOKBACK_DAYS = 3650
const HISTORY_PAGE_SIZE = 50

const CHART_ZOOM_DAYS = { day: 1, week: 7, month: 30, year: 365 } as const
type ChartZoom = keyof typeof CHART_ZOOM_DAYS | 'all'
type HistoryTab = 'snapshots' | 'operations'

const CHART_ZOOM_OPTIONS: Array<{ value: ChartZoom; label: string }> = [
    { value: 'day', label: 'День' },
    { value: 'week', label: 'Неделя' },
    { value: 'month', label: 'Месяц' },
    { value: 'year', label: 'Год' },
    { value: 'all', label: 'Всё' },
]

const CHART_ZOOM_OPTIONS_MOBILE: Array<{ value: ChartZoom; label: string }> = [
    { value: 'day', label: 'Дн' },
    { value: 'week', label: 'Нед' },
    { value: 'month', label: 'Мес' },
    { value: 'year', label: 'Год' },
    { value: 'all', label: 'Всё' },
]

const HISTORY_TAB_OPTIONS: Array<{ value: HistoryTab; label: string }> = [
    { value: 'snapshots', label: 'Снимки' },
    { value: 'operations', label: 'Операции' },
]

function todayIsoDate(): string {
    return new Date().toISOString().slice(0, 10)
}

function isoDateDaysAgo(days: number): string {
    return new Date(Date.now() - days * 86400000).toISOString().slice(0, 10)
}

function toApiFromDate(iso: string): string {
    return `${iso}T00:00:00Z`
}

function toApiToDate(iso: string): string {
    return `${iso}T23:59:59Z`
}

function resolveObservationWindow() {
    return {
        from: isoDateDaysAgo(OBSERVATION_LOOKBACK_DAYS),
        to: todayIsoDate(),
    }
}

function buildHistoryDatePayload(from: string | null, to: string | null) {
    if (from && to) {
        return { from_date: toApiFromDate(from), to_date: toApiToDate(to) }
    }
    return {}
}

function historyCountText(count: number | null): string {
    return count == null ? '…' : count.toLocaleString('ru-RU')
}

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

    const [historyFrom, setHistoryFrom] = useState<string | null>(null)
    const [historyTo, setHistoryTo] = useState<string | null>(null)
    const historyPeriodActive = !!(historyFrom && historyTo)
    const [historyTab, setHistoryTab] = useState<HistoryTab>('snapshots')

    const [snapshots, setSnapshots] = useState<PortfolioSnapshotSummary[]>([])
    const [snapshotsCount, setSnapshotsCount] = useState<number | null>(null)
    const [snapshotsLoading, setSnapshotsLoading] = useState(false)
    const [snapshotsLoadingMore, setSnapshotsLoadingMore] = useState(false)

    const [operations, setOperations] = useState<AnalyticsOperationItem[]>([])
    const [operationsCount, setOperationsCount] = useState<number | null>(null)
    const [opsLoading, setOpsLoading] = useState(false)
    const [opsLoadingMore, setOpsLoadingMore] = useState(false)
    const [opsSyncing, setOpsSyncing] = useState(false)

    const [loading, setLoading] = useState(true)
    const [positions, setPositions] = useState<any[]>([])
    const [posLoading, setPosLoading] = useState(false)

    const [stats, setStats] = useState<PortfolioStatisticsExtendedResponse | null>(null)
    const [statsLoading, setStatsLoading] = useState(false)
    const [statsError, setStatsError] = useState(false)
    const [statsRetrying, setStatsRetrying] = useState(false)

    const [chartData, setChartData] = useState<AnalyticsChartSeriesResponse | null>(null)
    const [chartLoading, setChartLoading] = useState(false)
    const [chartError, setChartError] = useState(false)
    const [chartRetrying, setChartRetrying] = useState(false)
    const [chartMode, setChartMode] = useState<'portfolio' | 'instruments'>('portfolio')
    const [chartZoom, setChartZoom] = useState<ChartZoom>('month')
    const [chartSectionOpen, setChartSectionOpen] = useState(false)
    const [selectedFigis, setSelectedFigis] = useState<string[]>([])
    const [crosshairValue, setCrosshairValue] = useState<{
        time: string
        value: number
        delta: number | null
        deltaPct: number | null
    } | null>(null)

    const chartApiRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<any> | null>(null)
    const instrumentSeriesRef = useRef<Array<{ figi: string; label: string; series: ISeriesApi<any> }>>([])
    const instrumentPriceLinesRef = useRef<Record<string, any>>({})
    const earliestSnapshotRef = useRef<string | null>(null)
    const snapshotsLoadingMoreGuard = useRef(false)
    const opsLoadingMoreGuard = useRef(false)

    const snapshotsRef = useRef(snapshots)
    const operationsRef = useRef(operations)
    const snapshotsCountRef = useRef(snapshotsCount)
    const operationsCountRef = useRef(operationsCount)
    const historyFromRef = useRef(historyFrom)
    const historyToRef = useRef(historyTo)

    snapshotsRef.current = snapshots
    operationsRef.current = operations
    snapshotsCountRef.current = snapshotsCount
    operationsCountRef.current = operationsCount
    historyFromRef.current = historyFrom
    historyToRef.current = historyTo

    const freeCash = useMemo(() => computeFreeCash(positions), [positions])

    const portfolioGain = useMemo(() => {
        const own = Number(stats?.overall.own_funds)
        const total = Number(stats?.overall.current_total_value)
        if (!Number.isFinite(own) || !Number.isFinite(total)) {
            return { abs: null as number | null, pct: null as number | null }
        }
        return {
            abs: total - own,
            pct: stats?.overall.roi_percent ?? null,
        }
    }, [stats?.overall.current_total_value, stats?.overall.own_funds, stats?.overall.roi_percent])

    const portfolioSparkline = useMemo(
        () => buildPortfolioReturnSparkline(chartData?.portfolio_series),
        [chartData?.portfolio_series],
    )

    const imoexSparkline = useMemo(() => {
        const series = stats?.benchmark_metrics.imoex_series
        if (!series?.length) return []
        return series.slice(-36).map(p => Number(p.return_percent))
    }, [stats?.benchmark_metrics.imoex_series])

    useEffect(() => { loadAccounts() }, [])

    useEffect(() => {
        if (!selectedAccountId) return
        const periodReady = historyPeriodActive || (!historyFrom && !historyTo)
        if (!periodReady) return
        loadSnapshots(selectedAccountId, { reset: true })
        loadOperations(selectedAccountId, { reset: true })
    }, [selectedAccountId, historyFrom, historyTo])

    useEffect(() => {
        if (!selectedAccountId) return
        setChartZoom('month')
        earliestSnapshotRef.current = null
        loadStatistics(selectedAccountId)
        loadChartSeries(selectedAccountId)
    }, [selectedAccountId])

    useEffect(() => {
        const seriesFigis = (chartData?.instruments_series || [])
            .filter(s => Array.isArray(s.points) && s.points.length > 0)
            .map(s => s.figi)
        if (!seriesFigis.length) {
            setSelectedFigis([])
            return
        }
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
        } catch {
            setPositions([])
        }
        setPosLoading(false)
    }

    const resolveEarliestSnapshotDate = async (
        accId: number,
        count: number,
        loaded: PortfolioSnapshotSummary[],
    ) => {
        if (count <= 0) {
            earliestSnapshotRef.current = null
            return
        }
        if (loaded.length >= count) {
            const oldest = loaded[loaded.length - 1]
            earliestSnapshotRef.current = oldest?.date ? oldest.date.slice(0, 10) : null
            return
        }
        try {
            const res = await analyticsService.getSnapshotsByPeriod({
                account_id: accId,
                limit: 1,
                offset: Math.max(0, count - 1),
            })
            const oldest = res.history?.[0]
            earliestSnapshotRef.current = oldest?.date ? oldest.date.slice(0, 10) : null
        } catch {
            /* keep previous */
        }
    }

    const loadSnapshots = async (
        accId: number,
        opts?: { reset?: boolean; offset?: number; from?: string | null; to?: string | null },
    ) => {
        const reset = opts?.reset ?? true
        const offset = opts?.offset ?? 0
        const from = opts?.from !== undefined ? opts.from : historyFromRef.current
        const to = opts?.to !== undefined ? opts.to : historyToRef.current
        const periodReady = !!(from && to)
        const allTime = !from && !to
        if (!periodReady && !allTime) return

        if (reset) {
            setSnapshotsLoading(true)
            setSnapshots([])
            setSnapshotsCount(null)
        } else {
            if (snapshotsLoadingMoreGuard.current) return
            snapshotsLoadingMoreGuard.current = true
            setSnapshotsLoadingMore(true)
        }

        try {
            const data = await analyticsService.getSnapshotsByPeriod({
                account_id: accId,
                ...buildHistoryDatePayload(from, to),
                limit: HISTORY_PAGE_SIZE,
                offset,
            })
            const rows = data.history ?? []
            setSnapshotsCount(data.count)
            setSnapshots(prev => (reset ? rows : [...prev, ...rows]))
            if (reset && allTime) {
                await resolveEarliestSnapshotDate(accId, data.count, rows)
            }
        } catch {
            if (reset) {
                setSnapshots([])
                setSnapshotsCount(0)
            } else {
                toast.show('Не удалось загрузить снимки', 'error')
            }
        }

        setSnapshotsLoading(false)
        setSnapshotsLoadingMore(false)
        snapshotsLoadingMoreGuard.current = false
    }

    const loadOperations = async (
        accId: number,
        opts?: { reset?: boolean; offset?: number; from?: string | null; to?: string | null },
    ) => {
        const reset = opts?.reset ?? true
        const offset = opts?.offset ?? 0
        const from = opts?.from !== undefined ? opts.from : historyFromRef.current
        const to = opts?.to !== undefined ? opts.to : historyToRef.current
        const periodReady = !!(from && to)
        const allTime = !from && !to
        if (!periodReady && !allTime) return

        if (reset) {
            setOpsLoading(true)
            setOperations([])
            setOperationsCount(null)
        } else {
            if (opsLoadingMoreGuard.current) return
            opsLoadingMoreGuard.current = true
            setOpsLoadingMore(true)
        }

        try {
            const res = await analyticsService.getOperationsByPeriod({
                account_id: accId,
                ...buildHistoryDatePayload(from, to),
                limit: HISTORY_PAGE_SIZE,
                offset,
            })
            const rows = res.items ?? []
            setOperationsCount(res.count)
            setOperations(prev => (reset ? rows : [...prev, ...rows]))
        } catch {
            if (reset) {
                setOperations([])
                setOperationsCount(0)
            } else {
                toast.show('Не удалось загрузить операции', 'error')
            }
        }

        setOpsLoading(false)
        setOpsLoadingMore(false)
        opsLoadingMoreGuard.current = false
    }

    const loadStatistics = async (accId: number, opts?: { fromRetry?: boolean }) => {
        const fromRetry = !!opts?.fromRetry
        const started = Date.now()
        if (fromRetry) setStatsRetrying(true)
        else setStatsLoading(true)
        setStatsError(false)

        let ok = false
        const { from, to } = resolveObservationWindow()
        try {
            const data = await analyticsService.getAccountStatisticsExtended({
                account_id: accId,
                from_date: toApiFromDate(from),
                to_date: toApiToDate(to),
            })
            setStats(data)
            ok = true
        } catch {
            setStats(null)
            setStatsError(true)
        }

        if (fromRetry && !ok) {
            const wait = RETRY_MIN_MS - (Date.now() - started)
            if (wait > 0) await new Promise(r => window.setTimeout(r, wait))
        }

        setStatsLoading(false)
        setStatsRetrying(false)
    }

    const loadChartSeries = async (accId: number, opts?: { fromRetry?: boolean }) => {
        const fromRetry = !!opts?.fromRetry
        const started = Date.now()
        if (fromRetry) setChartRetrying(true)
        else setChartLoading(true)
        setChartError(false)

        let ok = false
        const { from, to } = resolveObservationWindow()
        try {
            const data = await analyticsService.getAccountChartSeries({
                account_id: accId,
                from_date: toApiFromDate(from),
                to_date: toApiToDate(to),
            })
            setChartData(data)
            ok = true
            const first = data.portfolio_series?.[0]?.date
            if (first && !earliestSnapshotRef.current) {
                earliestSnapshotRef.current = first.slice(0, 10)
            }
        } catch {
            setChartData(null)
            setChartError(true)
        }

        if (fromRetry && !ok) {
            const wait = RETRY_MIN_MS - (Date.now() - started)
            if (wait > 0) await new Promise(r => window.setTimeout(r, wait))
        }

        setChartLoading(false)
        setChartRetrying(false)
    }

    const handleAccountChange = async (val: string) => {
        const id = Number(val)
        setChartData(null)
        setSelectedFigis([])
        setCrosshairValue(null)
        setStatsError(false)
        setChartError(false)
        setChartZoom('month')
        setHistoryFrom(null)
        setHistoryTo(null)
        setHistoryTab('snapshots')
        earliestSnapshotRef.current = null
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
            let from: string
            let to: string
            if (historyPeriodActive && historyFrom && historyTo) {
                from = historyFrom
                to = historyTo
            } else {
                from = earliestSnapshotRef.current ?? resolveObservationWindow().from
                to = todayIsoDate()
            }

            await analyticsService.syncOperations({
                account_id: selectedAccount.account_id || '',
                from_date: toApiFromDate(from),
                to_date: toApiToDate(to),
                tokenId: Number(selectedAccount.last_token_id),
                state: 'OPERATION_STATE_UNSPECIFIED',
            })
            await loadOperations(selectedAccountId, { reset: true })
            await loadStatistics(selectedAccountId)
        } catch {
            toast.show('Ошибка синхронизации операций', 'error')
        }
        setOpsSyncing(false)
    }

    const loadMoreSnapshots = useCallback(() => {
        if (!selectedAccountId) return
        const count = snapshotsCountRef.current
        const loaded = snapshotsRef.current.length
        if (count == null || loaded >= count || snapshotsLoadingMoreGuard.current || snapshotsLoading) return
        loadSnapshots(selectedAccountId, { reset: false, offset: loaded })
    }, [selectedAccountId, snapshotsLoading])

    const loadMoreOperations = useCallback(() => {
        if (!selectedAccountId) return
        const count = operationsCountRef.current
        const loaded = operationsRef.current.length
        if (count == null || loaded >= count || opsLoadingMoreGuard.current || opsLoading) return
        loadOperations(selectedAccountId, { reset: false, offset: loaded })
    }, [selectedAccountId, opsLoading])

    const handleSnapshotsScroll = (event: React.UIEvent<HTMLDivElement>) => {
        const el = event.currentTarget
        if (el.scrollTop + el.clientHeight < el.scrollHeight - 72) return
        loadMoreSnapshots()
    }

    const handleOperationsScroll = (event: React.UIEvent<HTMLDivElement>) => {
        const el = event.currentTarget
        if (el.scrollTop + el.clientHeight < el.scrollHeight - 72) return
        loadMoreOperations()
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

    const applyChartZoom = useCallback((chart: IChartApi, zoom: ChartZoom) => {
        const data = chartHistory()
        if (!data.length) {
            chart.timeScale().fitContent()
            return
        }

        const width = Math.max(120, chart.timeScale().width() || 400)
        const minTs = data[0].timestamp
        const maxTs = data[data.length - 1].timestamp
        const lastPoint = data[data.length - 1]

        requestAnimationFrame(() => {
            if (zoom === 'all') {
                chart.timeScale().applyOptions({ minBarSpacing: 0.01 })
                chart.timeScale().fitContent()
                return
            }

            const windowMs = CHART_ZOOM_DAYS[zoom] * 86400000
            let center = maxTs
            try {
                const range = chart.timeScale().getVisibleRange()
                if (range?.from != null && range?.to != null) {
                    const fromMs = typeof range.from === 'number'
                        ? range.from * 1000
                        : new Date(range.from.year, range.from.month - 1, range.from.day).getTime()
                    const toMs = typeof range.to === 'number'
                        ? range.to * 1000
                        : new Date(range.to.year, range.to.month - 1, range.to.day).getTime()
                    if (Number.isFinite(fromMs) && Number.isFinite(toMs) && toMs >= fromMs) {
                        center = (fromMs + toMs) / 2
                    }
                }
            } catch { /* */ }

            let fromTs = center - windowMs / 2
            let toTs = center + windowMs / 2
            if (fromTs < minTs) {
                toTs += minTs - fromTs
                fromTs = minTs
            }
            if (toTs > maxTs) {
                fromTs -= toTs - maxTs
                toTs = maxTs
            }
            fromTs = Math.max(minTs, fromTs)
            toTs = Math.min(maxTs, toTs)

            let fromIdx = 0
            for (let i = 0; i < data.length; i += 1) {
                if (data[i].timestamp >= fromTs) {
                    fromIdx = i
                    break
                }
            }
            let toIdx = data.length - 1
            for (let i = data.length - 1; i >= 0; i -= 1) {
                if (data[i].timestamp <= toTs) {
                    toIdx = i
                    break
                }
            }

            const visibleBars = Math.max(1, toIdx - fromIdx + 1)
            const barSpacing = Math.max(0.5, (width - 16) / visibleBars)
            chart.timeScale().applyOptions({ minBarSpacing: 0.01, barSpacing })

            const fromSec = Math.floor(fromTs / 1000)
            const toSec = Math.floor(toTs / 1000)
            try {
                chart.timeScale().setVisibleRange({ from: fromSec as Time, to: toSec as Time })
            } catch {
                try {
                    chart.timeScale().setVisibleLogicalRange({ from: fromIdx - 0.5, to: toIdx + 0.5 })
                } catch {
                    chart.timeScale().fitContent()
                }
            }

        })
    }, [chartHistory])

    useEffect(() => {
        const chart = chartApiRef.current
        if (!chart || chartLoading || chartError) return
        applyChartZoom(chart, chartZoom)
    }, [chartZoom, applyChartZoom, chartLoading, chartError, chartData, chartMode])

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
                            .filter(Boolean) as Array<{ time: Time; value: number; timestamp: number }>,
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

        applyChartZoom(chart, chartZoom)

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
    }, [chartHistory, chartMode, chartData?.instruments_series, selectedFigis, chartZoom, applyChartZoom])

    const handleSnapshotClick = (snapshot: PortfolioSnapshotSummary) => {
        if (selectedAccountId && snapshot.snapshot_id) {
            loadPositions(selectedAccountId, snapshot.snapshot_id)
        }
    }

    const historyColumns: Column<PortfolioSnapshotSummary>[] = [
        {
            key: 'date',
            header: 'Дата и время',
            sortable: true,
            render: r => new Date(r.date).toLocaleString('ru-RU', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            }),
        },
        {
            key: 'total_value',
            header: 'Стоимость',
            sortable: true,
            align: 'right',
            render: r => money(r.total_value),
        },
        {
            key: 'daily_yield',
            header: 'Дневной доход',
            sortable: true,
            align: 'right',
            render: r => (
                <span className={r.daily_yield >= 0 ? 'color-up' : 'color-down'}>
                    {moneySigned(r.daily_yield)}
                </span>
            ),
        },
    ]

    const operationsColumns: Column<AnalyticsOperationItem>[] = [
        {
            key: 'operation_date',
            header: 'Дата',
            render: r => new Date(r.operation_date).toLocaleString('ru-RU'),
        },
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
        {
            key: 'quantity',
            header: 'Кол-во',
            align: 'right',
            render: r => Number(r.quantity || 0).toLocaleString('ru-RU'),
        },
        {
            key: 'price',
            header: 'Цена',
            align: 'right',
            render: r => Number(r.price || 0).toLocaleString('ru-RU', { maximumFractionDigits: 4 }),
        },
        {
            key: 'payment',
            header: 'Сумма',
            align: 'right',
            render: r => {
                const v = Number(r.payment || 0)
                return (
                    <span className={v >= 0 ? 'color-up' : 'color-down'}>
                        {v.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} {r.currency || ''}
                    </span>
                )
            },
        },
        {
            key: 'status_name',
            header: 'Статус',
            width: '160px',
            render: r => String(r.status_name || r.status || '—'),
        },
    ]

    const snapshotsEmptyText = historyPeriodActive
        ? 'Нет снимков за выбранный период'
        : 'Нет истории'
    const operationsEmptyText = historyPeriodActive
        ? 'Нет операций за выбранный период'
        : 'Нет операций'

    const historyLoadMoreFooter = (loadingMore: boolean) => (
        loadingMore ? (
            <div
                className="portfolio-history-loadmore"
                aria-busy="true"
                aria-label="Загрузка следующей страницы"
            >
                <Skeleton width="100%" height="28px" borderRadius="6px" />
            </div>
        ) : null
    )

    const snapshotsTable = snapshotsLoading ? (
        <div aria-busy="true" aria-label="Загрузка истории снимков">
            <Skeleton width="100%" height="120px" borderRadius="8px" />
        </div>
    ) : (
        <DataTable
            columns={historyColumns}
            data={snapshots}
            keyField="date"
            emptyText={snapshotsEmptyText}
            onRowClick={handleSnapshotClick as any}
            onScroll={handleSnapshotsScroll}
            footer={historyLoadMoreFooter(snapshotsLoadingMore)}
            maxHeight={isMobile ? 320 : 420}
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
    )

    const operationsTable = opsLoading ? (
        <div aria-busy="true" aria-label="Загрузка истории операций">
            <Skeleton width="100%" height="120px" borderRadius="8px" />
        </div>
    ) : (
        <DataTable
            columns={operationsColumns}
            data={operations}
            keyField="operation_id"
            emptyText={operationsEmptyText}
            onScroll={handleOperationsScroll}
            footer={historyLoadMoreFooter(opsLoadingMore)}
            maxHeight={isMobile ? 320 : 420}
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
    )

    if (loading) {
        return (
            <div className="page" data-page="portfolio">
                <PageHero
                    className="dashboard-hero--node"
                    eyebrow="PORTFOLIO NODE"
                    title="ПОРТФЕЛЬ"
                />
                <PortfolioSkeleton isMobile={isMobile} />
            </div>
        )
    }

    if (accounts.length === 0) {
        return (
            <div className="page" data-page="portfolio">
                <PageHero
                    className="dashboard-hero--node"
                    eyebrow="PORTFOLIO NODE"
                    title="ПОРТФЕЛЬ"
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

    const chartHeight = isMobile ? 240 : 360
    const hasChartData = chartMode === 'instruments'
        ? (chartData?.instruments_series || []).some(s => Array.isArray(s.points) && s.points.length > 0)
        : (chartData?.portfolio_series?.length ?? 0) > 0

    const instrumentLegendItems = (chartData?.instruments_series || [])
        .filter(s => Array.isArray(s.points) && s.points.length > 0)
    const allInstrumentFigis = instrumentLegendItems.map(s => s.figi)
    const allInstrumentsSelected = allInstrumentFigis.length > 0
        && allInstrumentFigis.every(figi => selectedFigis.includes(figi))

    const papersToggle = (
        <Toggle
            checked={chartMode === 'instruments'}
            onChange={(on) => {
                setChartMode(on ? 'instruments' : 'portfolio')
                if (isMobile) setChartSectionOpen(true)
            }}
            label={isMobile ? 'бумаги' : 'Посмотреть бумаги'}
        />
    )

    const chartZoomControl = (
        <SegmentedControl
            className="portfolio-chart-zoom"
            aria-label="Масштаб графика"
            options={isMobile ? CHART_ZOOM_OPTIONS_MOBILE : CHART_ZOOM_OPTIONS}
            value={chartZoom}
            onChange={(v) => setChartZoom(v as ChartZoom)}
        />
    )

    const chartHeaderControls = (
        <div className="portfolio-chart-header__controls">
            {chartZoomControl}
            {papersToggle}
        </div>
    )

    const statsErrorCard = statsError ? (
        <div className={`dashboard-error-card${statsRetrying ? ' dashboard-error-card--retrying' : ''}`}>
            <div className="dashboard-error-card__robot" aria-hidden>
                <RobotIllustration size={96} mode={statsRetrying ? 'default' : 'inactive'} interactive={false} />
            </div>
            <p className="dashboard-empty">Не удалось загрузить статистику.</p>
            {statsRetrying && (
                <div className="dashboard-error-card__loader" aria-hidden>
                    <div className="soft-loading-bar" />
                </div>
            )}
            <div className="dashboard-error-card__actions">
                <Button
                    onClick={() => selectedAccountId && loadStatistics(selectedAccountId, { fromRetry: true })}
                    loading={statsRetrying}
                    disabled={statsRetrying}
                >
                    Повторить
                </Button>
            </div>
        </div>
    ) : null

    const chartErrorCard = chartError ? (
        <div className={`dashboard-error-card${chartRetrying ? ' dashboard-error-card--retrying' : ''}`}>
            <div className="dashboard-error-card__robot" aria-hidden>
                <RobotIllustration size={96} mode={chartRetrying ? 'default' : 'inactive'} interactive={false} />
            </div>
            <p className="dashboard-empty">Не удалось загрузить график.</p>
            {chartRetrying && (
                <div className="dashboard-error-card__loader" aria-hidden>
                    <div className="soft-loading-bar" />
                </div>
            )}
            <div className="dashboard-error-card__actions">
                <Button
                    onClick={() => selectedAccountId && loadChartSeries(selectedAccountId, { fromRetry: true })}
                    loading={chartRetrying}
                    disabled={chartRetrying}
                >
                    Повторить
                </Button>
            </div>
        </div>
    ) : null

    const detailsBlock = (
        <div className="portfolio-stats-grid portfolio-stats-grid--details">
            <SummaryMetric
                label="Чистый приток капитала"
                valueClassName={roiClass(stats?.capital_flow.net_capital_inflow)}
                value={moneySigned(stats?.capital_flow.net_capital_inflow)}
            />
            <SummaryMetric
                label="Дивиденды полученные"
                valueClassName="color-up"
                value={money(stats?.capital_flow.dividends_received)}
            />
            <SummaryMetric
                label="Реализованный P&L"
                valueClassName={roiClass(stats?.capital_flow.realized_pnl)}
                value={moneySigned(stats?.capital_flow.realized_pnl)}
            />
            <SummaryMetric
                label="Нереализованный P&L"
                valueClassName={roiClass(stats?.capital_flow.unrealized_pnl)}
                value={moneySigned(stats?.capital_flow.unrealized_pnl)}
            />
            <SummaryMetric
                label="Серия убытков"
                valueClassName="color-down"
                value={formatLossStreakCount(stats?.trading_performance.max_consecutive_losses)}
            />
            <SummaryMetric
                label="Avg Win / Avg Loss"
                value={formatFactor(stats?.trading_performance.avg_win_loss_ratio)}
            />
            <SummaryMetric
                label="Среднее время удержания"
                value={(
                    <>
                        {formatHoldTime(stats?.operational_metrics.average_hold_time_hours)}
                        {stats?.operational_metrics.average_hold_time_label
                            ? ` (${stats.operational_metrics.average_hold_time_label})`
                            : ''}
                    </>
                )}
            />
            <SummaryMetric
                label="Комиссии / вознаграждение"
                valueClassName="color-down"
                value={`${money(stats?.operational_metrics.total_broker_fees)} / ${money(stats?.operational_metrics.total_track_fees)}`}
            />
            <SummaryMetric
                label="Налоги"
                valueClassName="color-down"
                value={money(stats?.operational_metrics.total_taxes)}
            />
            <SummaryMetric
                label="Recovery / Current DD"
                value={`${formatDays(stats?.risk_recovery.average_recovery_days)} / ${formatPercent(stats?.risk_recovery.current_drawdown_percent, true)}`}
            />
        </div>
    )

    const summaryCard = (
        <Card className="dashboard-totals-card">
            <div className="dashboard-totals-card__head">
                <h3 className="dashboard-panel-title">Сводка</h3>
                <IconSummary />
            </div>
            {statsLoading ? (
                <div className="portfolio-stats-rows portfolio-summary" aria-busy="true" aria-label="Расчет статистики">
                    <div className="portfolio-summary-hero portfolio-summary-hero--split">
                        <span className="dashboard-summary-metric__label portfolio-summary-hero__label">Стоимость</span>
                        <div className="portfolio-summary-hero__head">
                            <Skeleton width="36px" height="10px" borderRadius="4px" />
                            <Skeleton width="112px" height="10px" borderRadius="4px" />
                        </div>
                        <Skeleton width="68%" height="32px" borderRadius="4px" />
                        <span className="portfolio-summary-hero__own-value-skeleton">
                            <Skeleton width="96px" height="32px" borderRadius="4px" />
                        </span>
                    </div>
                    {[0, 1, 2].map(i => (
                        <div key={i} className="portfolio-summary-block">
                            <Skeleton width="120px" height="12px" borderRadius="4px" />
                            <div className="portfolio-summary-block__grid portfolio-summary-block__grid--3">
                                {[0, 1, 2].map(j => (
                                    <div key={j} className="dashboard-summary-metric">
                                        <Skeleton width="80%" height="10px" borderRadius="4px" />
                                        <Skeleton width="60%" height="18px" borderRadius="4px" />
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            ) : statsErrorCard ? (
                statsErrorCard
            ) : (
                <div className="portfolio-stats-rows portfolio-summary">
                    <div className="portfolio-summary-hero portfolio-summary-hero--split">
                        <span className="dashboard-summary-metric__label portfolio-summary-hero__label">Стоимость</span>
                        <div className="portfolio-summary-hero__head">
                            <span className="dashboard-summary-metric__label">СВОИ:</span>
                            <span className={`portfolio-summary-hero__delta mono ${deltaClass(portfolioGain.abs)}`}>
                                {formatAbsWithPercent(portfolioGain.abs, portfolioGain.pct, accountCurrency)}
                            </span>
                        </div>
                        <div className="portfolio-summary-hero__value mono">
                            {money(stats?.overall.current_total_value)}
                        </div>
                        <span className="portfolio-summary-hero__own-value mono">
                            {money(stats?.overall.own_funds)}
                        </span>
                    </div>

                    <SummaryBlock title="Состояние портфеля">
                        <div className="portfolio-summary-block__grid portfolio-summary-block__grid--1">
                            <SummaryMetric
                                label="Свободные средства"
                                value={freeCash != null ? money(freeCash) : '—'}
                            />
                        </div>
                    </SummaryBlock>

                    <SummaryBlock title="Доходность">
                        <div className="portfolio-summary-block__grid portfolio-summary-block__grid--2">
                            <SummaryMetric
                                label="Общий ROI"
                                valueClassName={roiClass(stats?.overall.roi_percent)}
                                value={formatPercentWithArrow(stats?.overall.roi_percent)}
                            />
                            <SummaryMetric
                                label="ROI за месяц"
                                valueClassName={roiClass(stats?.overall.avg_monthly_roi_percent)}
                                value={formatPercentWithArrow(stats?.overall.avg_monthly_roi_percent)}
                            />
                        </div>
                    </SummaryBlock>

                    <SummaryBlock title="Риски и качество">
                        <div className="portfolio-summary-block__grid portfolio-summary-block__grid--2">
                            <SummaryMetric
                                label="Max Drawdown"
                                value={formatPercentWithArrow(stats?.risk_recovery.max_drawdown_percent, true)}
                            />
                            <SummaryMetric
                                label="Win Rate"
                                valueClassName={roiClass((stats?.trading_performance.win_rate_percent ?? 0) - 50)}
                                value={formatPercentWithArrow(stats?.trading_performance.win_rate_percent)}
                            />
                            <SummaryMetric
                                label="Profit Factor"
                                valueClassName={profitFactorClass(stats?.trading_performance.profit_factor)}
                                value={formatFactor(stats?.trading_performance.profit_factor)}
                            />
                            <SummaryMetric
                                label="Средняя приб. / убыточная"
                                value={`${money(stats?.trading_performance.avg_winning_trade)} / ${money(stats?.trading_performance.avg_losing_trade)}`}
                            />
                        </div>
                    </SummaryBlock>

                    <SummaryBlock title="Детали">
                        {detailsBlock}
                    </SummaryBlock>
                </div>
            )}
        </Card>
    )

    const chartBody = (
        <>
            {!isMobile && (
                <div className="dashboard-assets-card__head">
                    <h3 className="dashboard-panel-title">
                        <IconChart />
                        Стоимость портфеля
                    </h3>
                    {chartHeaderControls}
                </div>
            )}
            {isMobile && (
                <div className="portfolio-chart-header portfolio-chart-header--mobile">
                    {chartZoomControl}
                </div>
            )}
            {chartMode === 'portfolio' && (
                <div
                    className={`mono portfolio-crosshair-main${crosshairValue ? '' : ' portfolio-crosshair-main--idle'}`}
                    aria-hidden={!crosshairValue}
                >
                    {crosshairValue ? (
                        <>
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
                            <span className="portfolio-crosshair-main__time">{crosshairValue.time}</span>
                        </>
                    ) : (
                        <span className="portfolio-crosshair-main__placeholder">&nbsp;</span>
                    )}
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
                    key={`${selectedAccountId}-${chartMode}-${selectedFigis.join(',')}`}
                />
            )}
            {chartMode === 'instruments' && (
                <div className="portfolio-chart-midbar">
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
                </div>
            )}
            {chartMode === 'instruments' && (
                <div className="portfolio-legend">
                    {instrumentLegendItems.map((s) => {
                        const active = selectedFigis.includes(s.figi)
                        return (
                            <button
                                key={s.figi}
                                type="button"
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
            {chartMode === 'portfolio' && !chartLoading && !statsLoading && stats && !chartError && (
                <div className="portfolio-chart-imoex">
                    <h4 className="portfolio-summary-block__title">Сравнение с IMOEX</h4>
                    <div className="portfolio-summary-block__grid portfolio-summary-block__grid--3">
                        <SummaryMetric
                            label="Доходность IMOEX"
                            valueClassName={roiClass(stats.benchmark_metrics.imoex_return_percent)}
                            value={
                                stats.benchmark_metrics.benchmark_unavailable
                                    ? 'нет данных'
                                    : formatPercentWithArrow(stats.benchmark_metrics.imoex_return_percent)
                            }
                        />
                        <SummaryMetric
                            label="К IMOEX"
                            valueClassName={roiClass(stats.benchmark_metrics.relative_return_percent)}
                            value={
                                stats.benchmark_metrics.benchmark_unavailable
                                    ? 'нет данных'
                                    : formatPercentWithArrow(stats.benchmark_metrics.relative_return_percent)
                            }
                        />
                        <SummaryMetric
                            label="Портфель за период"
                            valueClassName={roiClass(stats.benchmark_metrics.portfolio_return_percent)}
                            value={formatPercentWithArrow(stats.benchmark_metrics.portfolio_return_percent)}
                        />
                    </div>
                    {portfolioSparkline.length >= 2 ? (
                        <PortfolioSparkline
                            portfolio={portfolioSparkline}
                            benchmark={imoexSparkline}
                            unavailable={stats.benchmark_metrics.benchmark_unavailable}
                        />
                    ) : null}
                </div>
            )}
        </>
    )

    const chartCard = chartError ? (
        isMobile ? (
            <CollapsibleSection
                className="dashboard-assets-collapse"
                title={(
                    <span className="dashboard-collapse__label">
                        <IconChart />
                        Стоимость портфеля
                    </span>
                )}
                headerEnd={papersToggle}
                open={chartSectionOpen}
                onOpenChange={setChartSectionOpen}
                defaultOpen={false}
            >
                {chartErrorCard}
            </CollapsibleSection>
        ) : (
            <Card className="dashboard-assets-card">
                <div className="dashboard-assets-card__head">
                    <h3 className="dashboard-panel-title">
                        <IconChart />
                        Стоимость портфеля
                    </h3>
                    {chartHeaderControls}
                </div>
                {chartErrorCard}
            </Card>
        )
    ) : chartLoading || hasChartData ? (
        isMobile ? (
            <CollapsibleSection
                className="dashboard-assets-collapse"
                title={(
                    <span className="dashboard-collapse__label">
                        <IconChart />
                        Стоимость портфеля
                    </span>
                )}
                headerEnd={papersToggle}
                open={chartSectionOpen}
                onOpenChange={setChartSectionOpen}
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
            {!isMobile && (
                <div className="dashboard-assets-card__head">
                    <h3 className="dashboard-panel-title">
                        <IconChart />
                        Стоимость портфеля
                    </h3>
                    {chartHeaderControls}
                </div>
            )}
            <div className="dashboard-error-card__robot" aria-hidden>
                <RobotIllustration size={96} mode="inactive" interactive={false} />
            </div>
            <p className="dashboard-empty">Нет данных графика.</p>
        </Card>
    )

    return (
        <div className="page" data-page="portfolio">
            <PageHero
                className="dashboard-hero--node"
                eyebrow="PORTFOLIO NODE"
                title="ПОРТФЕЛЬ"
                actions={(
                    <Card className="dashboard-totals-card portfolio-toolbar">
                        <div className="portfolio-toolbar__account">
                            <Select
                                options={accounts.map(a => ({
                                    value: String(a.id),
                                    label: formatPortfolioAccountLabel(a),
                                    tag: formatPortfolioAccountPlatformTag(a.type),
                                }))}
                                value={selectedAccountId != null ? String(selectedAccountId) : ''}
                                onChange={handleAccountChange}
                                placeholder="Выберите счёт"
                            />
                        </div>
                    </Card>
                )}
            />

            <div className="dashboard-layout">
                <div className="dashboard-currency-grid">
                    {summaryCard}
                    {chartCard}
                </div>

                <PortfolioComposition
                    positions={positions}
                    loading={posLoading}
                    currency={accountCurrency}
                    bybitAccount={bybitAccount}
                    defaultOpen={!isMobile}
                />

                <Card className="dashboard-totals-card portfolio-history-zone">
                    <div className="portfolio-history-zone__toolbar">
                        <div className="portfolio-history-zone__lead">
                            <h3 className="dashboard-panel-title portfolio-history-zone__title">
                                <IconHistory />
                                История
                                <span className="portfolio-history-tab-panel__count mono">
                                    {historyTab === 'snapshots'
                                        ? historyCountText(snapshotsCount)
                                        : historyCountText(operationsCount)}
                                </span>
                            </h3>
                            <SegmentedControl
                                className="portfolio-history-tabs"
                                aria-label="Раздел истории"
                                options={HISTORY_TAB_OPTIONS}
                                value={historyTab}
                                onChange={(v) => setHistoryTab(v as HistoryTab)}
                            />
                        </div>
                        <div className="portfolio-history-period" aria-label="Период истории">
                            <div className="portfolio-history-period__row">
                                <DateRangePicker
                                    variant="fields"
                                    fromValue={historyFrom ? `${historyFrom}T00:00` : ''}
                                    toValue={historyTo ? `${historyTo}T00:00` : ''}
                                    onFromChange={(v) => setHistoryFrom(v ? v.slice(0, 10) : null)}
                                    onToChange={(v) => setHistoryTo(v ? v.slice(0, 10) : null)}
                                    showLabel={false}
                                />
                                {historyTab === 'operations' ? (
                                    <Tooltip text="Синхронизировать операции">
                                        <button
                                            type="button"
                                            className={`portfolio-history-sync-btn${opsSyncing ? ' portfolio-history-sync-btn--loading' : ''}`}
                                            aria-label="Синхронизировать операции"
                                            disabled={opsSyncing}
                                            onClick={() => void handleSyncOperations()}
                                        >
                                            <IconSync />
                                        </button>
                                    </Tooltip>
                                ) : null}
                            </div>
                        </div>
                    </div>

                    <div className="portfolio-history-zone__panels">
                        <div
                            className={`portfolio-history-tab-panel${historyTab === 'snapshots' ? ' portfolio-history-tab-panel--active' : ''}`}
                            hidden={historyTab !== 'snapshots'}
                        >
                            {snapshotsTable}
                        </div>

                        <div
                            className={`portfolio-history-tab-panel${historyTab === 'operations' ? ' portfolio-history-tab-panel--active' : ''}`}
                            hidden={historyTab !== 'operations'}
                        >
                            {operationsTable}
                        </div>
                    </div>
                </Card>
            </div>
        </div>
    )
}

function PortfolioSkeleton({ isMobile }: { isMobile: boolean }) {
    const chartHeight = isMobile ? 240 : 420
    return (
        <div className="dashboard-layout dashboard-skeleton" aria-busy="true" aria-label="Загрузка портфеля">
            <div className="dashboard-currency-grid">
                <Card className="dashboard-totals-card dashboard-skeleton-card">
                    <div className="dashboard-totals-card__head">
                        <Skeleton width="160px" height="18px" borderRadius="4px" />
                    </div>
                    <div className="dashboard-summary-metrics">
                        {[0, 1, 2, 3].map(i => (
                            <div key={i} className="dashboard-summary-metric dashboard-summary-metric--primary">
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
                        <Skeleton width="180px" height="18px" borderRadius="4px" />
                    </div>
                    <Skeleton width="100%" height={`${chartHeight}px`} borderRadius="8px" />
                </Card>
            </div>
            <Card className="dashboard-totals-card portfolio-history-zone dashboard-skeleton-card">
                <div className="portfolio-history-zone__toolbar">
                    <Skeleton width="120px" height="18px" borderRadius="4px" />
                </div>
                <Skeleton width="100%" height="96px" borderRadius="8px" />
            </Card>
        </div>
    )
}

function SummaryBlock({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <section className="portfolio-summary-block">
            <h4 className="portfolio-summary-block__title">{title}</h4>
            {children}
        </section>
    )
}

function SummaryMetric({
    label,
    value,
    valueClassName = '',
    primary = false,
    modifier = '',
}: {
    label: string
    value: React.ReactNode
    valueClassName?: string
    primary?: boolean
    modifier?: string
}) {
    const className = [
        'dashboard-summary-metric',
        modifier,
        primary ? 'dashboard-summary-metric--primary' : '',
    ].filter(Boolean).join(' ')

    return (
        <div className={className}>
            <span className="dashboard-summary-metric__label">{label}</span>
            <span className={`dashboard-summary-metric__value mono ${valueClassName}`.trim()}>
                {value}
            </span>
        </div>
    )
}

function PortfolioSparkline({
    portfolio,
    benchmark,
    unavailable,
}: {
    portfolio: number[]
    benchmark: number[]
    unavailable: boolean
}) {
    const toPoints = (values: number[]) => {
        if (values.length < 2) return ''
        const min = Math.min(...values)
        const span = Math.max(...values) - min || 1
        return values
            .map((value, index) => {
                const x = 2 + (index / (values.length - 1)) * 276
                const y = 42 - ((value - min) / span) * (44 - 4)
                return `${x},${y}`
            })
            .join(' ')
    }

    const portfolioPoints = toPoints(portfolio)
    const benchmarkPoints = benchmark.length >= 2 && !unavailable ? toPoints(benchmark) : ''

    return (
        <div className="portfolio-summary-sparkline" aria-hidden>
            <svg viewBox="0 0 280 44" preserveAspectRatio="none">
                {benchmarkPoints ? (
                    <polyline
                        points={benchmarkPoints}
                        fill="none"
                        stroke="var(--text-muted)"
                        strokeWidth="1.5"
                        strokeDasharray="3 3"
                        vectorEffect="non-scaling-stroke"
                    />
                ) : null}
                <polyline
                    points={portfolioPoints}
                    fill="none"
                    stroke="var(--neon-cyan)"
                    strokeWidth="2"
                    vectorEffect="non-scaling-stroke"
                />
            </svg>
            <div className="portfolio-summary-sparkline__legend">
                <span>
                    <i className="portfolio-summary-sparkline__dot portfolio-summary-sparkline__dot--portfolio" />
                    {' '}
                    Портфель
                </span>
                {!unavailable && benchmarkPoints ? (
                    <span>
                        <i className="portfolio-summary-sparkline__dot portfolio-summary-sparkline__dot--benchmark" />
                        {' '}
                        IMOEX
                    </span>
                ) : null}
            </div>
        </div>
    )
}

function IconChart() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path fill="none" stroke="currentColor" strokeWidth="1.7" d="M12 3.6a8.4 8.4 0 1 1-8.4 8.4" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" d="M12 3.6V12h8.4" />
        </svg>
    )
}

function IconSummary() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <rect x="3.2" y="6.2" width="17.6" height="11.6" rx="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" d="M3.2 9.4h17.6" />
            <circle cx="16.4" cy="13.6" r="1.05" fill="currentColor" />
        </svg>
    )
}

function IconSync() {
    return (
        <svg className="portfolio-history-sync-btn__icon" viewBox="0 0 24 24" aria-hidden>
            <path
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M20 12a8 8 0 1 1-2.34-5.66"
            />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M20 4v5h-5" />
        </svg>
    )
}

function IconHistory() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path fill="none" stroke="currentColor" strokeWidth="1.7" d="M12 3.6a8.4 8.4 0 1 1-8.4 8.4" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M12 7.2v4.8l3.2 2" />
        </svg>
    )
}

function formatAbsWithPercent(abs: number | null, pct: number | null, currency: string): string {
    if (abs == null || Number.isNaN(Number(abs))) return '—'
    const signed = formatPortfolioMoneySigned(abs, currency)
    if (pct == null || Number.isNaN(Number(pct))) return signed
    return `${signed} (${formatPercent(pct)})`
}

function formatPercentWithArrow(val: number | null | undefined, drawdown = false): React.ReactNode {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    const arrow = drawdown
        ? (n > 0 ? '▼' : n < 0 ? '▲' : '•')
        : (n > 0 ? '▲' : n < 0 ? '▼' : '•')
    const text = drawdown
        ? `${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`
        : `${n >= 0 ? '+' : ''}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`
    return (
        <>
            <span className="portfolio-summary-arrow" aria-hidden>{arrow}</span>
            {text}
        </>
    )
}

function deltaClass(val: number | null | undefined): string {
    if (val == null || Number.isNaN(Number(val))) return 'dashboard-delta--flat'
    const n = Number(val)
    if (Math.abs(n) <= 1e-9) return 'dashboard-delta--flat'
    return n > 0 ? 'color-up' : 'color-down'
}

function computeFreeCash(positions: any[]): number | null {
    let total = 0
    let found = false
    for (const row of positions) {
        const haystack = `${row.instrument_type || ''} ${row.type_name || ''} ${row.ticker || ''} ${row.ticker_name || ''}`.toLowerCase()
        if (/currency|cash|money|валют|деньг|руб|rub|usd|usdt|eur/.test(haystack)) {
            total += Number(row.total_value || 0)
            found = true
        }
    }
    return found ? total : null
}

function buildPortfolioReturnSparkline(series?: Array<{ value?: number | null }>): number[] {
    const values = (series || [])
        .map(point => Number(point.value))
        .filter(value => Number.isFinite(value))
    if (values.length < 2) return []
    const window = values.slice(-36)
    const base = window[0]
    if (Math.abs(base) < 1e-9) return []
    return window.map(value => ((value - base) / base) * 100)
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

function formatLossStreakCount(count: number | undefined): string {
    if (!count) return '—'
    return `${count} подряд`
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
        byTime.set(Number(item.time), item)
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
