import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { LineSeries, createSeriesMarkers } from 'lightweight-charts'
import type { ISeriesMarkersPluginApi, SeriesMarker } from 'lightweight-charts'
import { Card } from '@/components/ui/Card'
import { Chart } from '@/components/ui/Chart'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { StatTile } from '@/components/ui/StatTile'
import { BacktestCostsStrip } from '@/pages/robots-v2/components/BacktestCostsStrip'
import { BacktestHoldingsSection } from '@/pages/robots-v2/components/BacktestHoldingsSection'
import { BacktestNarrativeSection } from '@/pages/robots-v2/components/BacktestNarrativeSection'
import { BacktestPriceScrubber, type PriceBarsPreset } from '@/pages/robots-v2/components/BacktestPriceScrubber'
import { BacktestUniverseSection } from '@/pages/robots-v2/components/BacktestUniverseSection'
import { DecisionInspectorDrawer } from '@/pages/robots-v2/components/DecisionInspectorDrawer'
import { fmtMoney, fmtPct } from '@/pages/robots-v2/formatters'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'
import {
    GLASS_BOX_EXECUTION_COPY,
    SIGNAL_PAGE_SIZE,
    SIGNAL_PAGINATE_THRESHOLD,
    anatomyCaption,
    aroundFromPacket,
    asRecord,
    feeSummaryVisible,
    mergeCycleBundle,
    packetFromSignal,
    packetFromTrade,
    resolveFeeSummary,
    resolveObservability,
    rowCycleId,
    rowRejectReason,
    rowStatus,
    tickerFromPacket,
    type HoldingsSampleMode,
} from '@/pages/robots-v2/backtestGlassBox'
import { robotV2Service } from '@/services/robotV2Service'
import type {
    BacktestDecisionPacket,
    BacktestExecutionEvent,
    BacktestFeeSummary,
    BacktestNarrativeStep,
    BacktestObservability,
    BacktestPortfolioSnapshot,
} from '@/types/robot'
import type { IChartApi, ISeriesApi, Time } from '@/components/ui/Chart'

type TradeRow = Record<string, unknown> & {
    id?: string | number
    bar_time?: string
    figi?: string
    side?: string
    reason?: string
    kind?: string
    price?: number
    quantity?: number
    commission?: number
    pnl_net?: number | null
    cycle_id?: string | null
}

type SignalRow = Record<string, unknown>
type OrderRow = Record<string, unknown>
type DailyRow = Record<string, unknown>

function fmtRatio(v: number | null | undefined): string {
    if (v == null || !Number.isFinite(v)) return '—'
    return v.toFixed(2)
}

function fmtTs(raw: unknown): string {
    if (raw == null) return '—'
    const d = new Date(String(raw))
    if (!Number.isFinite(d.getTime())) return '—'
    return d.toLocaleString('ru-RU')
}

function tradeTimeSec(t: TradeRow): number | null {
    const raw = t.bar_time ?? t.signal_time
    if (raw == null) return null
    const sec = Math.floor(new Date(String(raw)).getTime() / 1000)
    return Number.isFinite(sec) ? sec : null
}

type BacktestResultsPanelProps = {
    runId: number | null
    runStatus?: string | null
    partialResult?: boolean | null
    capital: number
    initialCapital: number
    finalEquity: number | null
    totalReturnPercent: number | null
    maxDrawdownPercent: number | null
    winRatePercent?: number | null
    sharpeRatio?: number | null
    sortinoRatio?: number | null
    calmarRatio?: number | null
    stages?: string[]
    historyStats?: Record<string, unknown> | null
    fundingChargesTotal?: number | null
    observability?: BacktestObservability | null
    executionModel?: unknown
    feeSummary?: BacktestFeeSummary | null
    portfolioSnapshots?: BacktestPortfolioSnapshot[]
    narrative?: BacktestNarrativeStep[] | null
    requestedFrom?: string | null
    requestedTo?: string | null
    signalsTotal?: number | null
    trades: TradeRow[]
    chartPoints: Array<{ time: Time; value: number }>
    signals: SignalRow[]
    orders: OrderRow[]
    dailySummary: DailyRow[]
    chartRef: React.MutableRefObject<IChartApi | null>
    seriesRef: React.MutableRefObject<ISeriesApi<'Line'> | null>
}

type PriceSelection = {
    ticker: string
    around: string
}

export function BacktestResultsPanel({
    runId,
    runStatus,
    partialResult,
    capital,
    initialCapital,
    finalEquity,
    totalReturnPercent,
    maxDrawdownPercent,
    winRatePercent,
    sharpeRatio,
    sortinoRatio,
    calmarRatio,
    stages,
    historyStats,
    fundingChargesTotal,
    observability: observabilityProp,
    executionModel,
    feeSummary: feeSummaryProp,
    portfolioSnapshots = [],
    narrative: narrativeProp,
    requestedFrom,
    requestedTo,
    signalsTotal: signalsTotalProp,
    trades,
    chartPoints,
    signals: signalsProp,
    orders,
    dailySummary,
    chartRef,
    seriesRef,
}: BacktestResultsPanelProps) {
    const [inspectorOpen, setInspectorOpen] = useState(false)
    const [inspectorPacket, setInspectorPacket] = useState<BacktestDecisionPacket | null>(null)
    const [inspectorLoading, setInspectorLoading] = useState(false)
    const [selectedTradeKey, setSelectedTradeKey] = useState<string | null>(null)
    const [holdingsSampleMode, setHoldingsSampleMode] = useState<HoldingsSampleMode>('end')
    const [markerPinSec, setMarkerPinSec] = useState<number | null>(null)
    const [priceSel, setPriceSel] = useState<PriceSelection | null>(null)
    const [priceBars, setPriceBars] = useState<PriceBarsPreset>(50)
    const [playheadTs, setPlayheadTs] = useState<string | null>(null)
    const chartCardRef = useRef<HTMLDivElement | null>(null)

    const [rejectFilter, setRejectFilter] = useState<string | null>(null)
    const [signalsOpen, setSignalsOpen] = useState(false)
    const [pagedSignals, setPagedSignals] = useState<SignalRow[] | null>(null)
    const [signalsPage, setSignalsPage] = useState(0)
    const [signalsFetchTotal, setSignalsFetchTotal] = useState<number | null>(null)
    const [signalsLoading, setSignalsLoading] = useState(false)
    const [signalsEndpointOk, setSignalsEndpointOk] = useState(true)

    const markersApiRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
    const clickUnsubRef = useRef<(() => void) | null>(null)
    const inspectReqRef = useRef(0)
    const pointsRef = useRef(chartPoints)
    pointsRef.current = chartPoints
    const tradesRef = useRef(trades)
    tradesRef.current = trades
    const openTradeAtRef = useRef<(index: number) => void>(() => {})

    const [chartHeight, setChartHeight] = useState(() =>
        typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches ? 240 : 320,
    )

    useEffect(() => {
        const mq = window.matchMedia('(max-width: 767px)')
        const apply = () => setChartHeight(mq.matches ? 240 : 320)
        apply()
        mq.addEventListener('change', apply)
        return () => mq.removeEventListener('change', apply)
    }, [])

    const baseSignals = pagedSignals ?? signalsProp

    const observability = useMemo(
        () => resolveObservability({
            topLevel: observabilityProp,
            fromPayload: null,
            signals: signalsProp,
            historyStats: historyStats ?? null,
            executionModel,
        }),
        [observabilityProp, signalsProp, historyStats, executionModel],
    )

    const signalsTotal =
        signalsFetchTotal
        ?? signalsTotalProp
        ?? Number(observability.signals_logged ?? signalsProp.length)
        ?? signalsProp.length

    const needServerPagination = signalsTotal > SIGNAL_PAGINATE_THRESHOLD && signalsEndpointOk

    const filteredSignals = useMemo(() => {
        if (!rejectFilter) return baseSignals
        return baseSignals.filter(s => rowRejectReason(s) === rejectFilter)
    }, [baseSignals, rejectFilter])

    const rejectTop = useMemo(
        () => (observability.reject_reason_counts || []).slice(0, 8),
        [observability.reject_reason_counts],
    )

    const statusCounts = observability.status_counts || {}
    const feeSummary = useMemo(
        () => resolveFeeSummary(feeSummaryProp, null),
        [feeSummaryProp],
    )
    const showCosts = feeSummaryVisible(feeSummary)
    const anatomy = useMemo(
        () => anatomyCaption(stages, historyStats ?? null, fundingChargesTotal),
        [stages, historyStats, fundingChargesTotal],
    )
    // When M shows funding, drop duplicate P0 funding hint in C.
    const anatomyFundingHint = showCosts ? null : anatomy.fundingHint

    const statusUpper = String(runStatus || '').toUpperCase()
    const isPartial = Boolean(partialResult) || statusUpper === 'CANCELLED'
    const truncated = Boolean(observability.signals_truncated)
    const signalCap = Number(observability.signal_log_cap ?? 25_000)

    const tradeRows = useMemo(
        () => trades.map((t, i) => ({ ...t, id: t.id ?? i })),
        [trades],
    )

    const activatePriceForPacket = useCallback((packet: BacktestDecisionPacket) => {
        const ticker = tickerFromPacket(packet)
        const around = aroundFromPacket(packet)
        if (!ticker || !around) {
            setPriceSel(null)
            return
        }
        setPriceSel({ ticker, around })
        setPlayheadTs(around)
        const sec = Math.floor(new Date(around).getTime() / 1000)
        if (Number.isFinite(sec)) {
            setMarkerPinSec(sec)
            setHoldingsSampleMode('marker')
        }
    }, [])

    const closeInspector = useCallback(() => {
        setInspectorOpen(false)
        setPriceSel(null)
        setPlayheadTs(null)
    }, [])

    const onPricePlayhead = useCallback((iso: string, sec: number) => {
        setPlayheadTs(iso)
        setMarkerPinSec(sec)
        setHoldingsSampleMode('marker')
    }, [])

    const openPacket = useCallback(async (packet: BacktestDecisionPacket) => {
        const req = ++inspectReqRef.current
        setInspectorPacket(packet)
        setInspectorOpen(true)
        activatePriceForPacket(packet)
        const cid = packet.cycle_id
        if (!cid || runId == null) return
        setInspectorLoading(true)
        try {
            const bundle = await robotV2Service.getBacktestCycle(runId, cid)
            if (req !== inspectReqRef.current) return
            if (bundle) {
                setInspectorPacket(prev => {
                    if (!prev || (prev.cycle_id && prev.cycle_id !== cid)) return prev
                    return mergeCycleBundle(prev, bundle)
                })
            }
        } finally {
            if (req === inspectReqRef.current) setInspectorLoading(false)
        }
    }, [runId, activatePriceForPacket])

    const onLifecycleStep = useCallback((ev: BacktestExecutionEvent) => {
        const ts = ev.ts || ev.signal_time
        const ticker = (ev.ticker || priceSel?.ticker || '').toUpperCase()
        if (ts && ticker) {
            setPriceSel({ ticker, around: String(ts) })
            setPlayheadTs(String(ts))
            const sec = Math.floor(new Date(String(ts)).getTime() / 1000)
            if (Number.isFinite(sec)) {
                setMarkerPinSec(sec)
                setHoldingsSampleMode('marker')
            }
        }
    }, [priceSel?.ticker])

    const onNarrativeStep = useCallback((step: BacktestNarrativeStep) => {
        if (step.cycle_id) {
            void openPacket({
                cycle_id: step.cycle_id,
                ticker: step.ticker || null,
                figi: step.ticker || null,
                signal_time: step.ts || null,
                bar_time: step.ts || null,
                source: 'cycle',
            })
            return
        }
        if (step.ts && priceSel) {
            setPriceSel(prev => (prev ? { ...prev, around: String(step.ts) } : prev))
            setPlayheadTs(String(step.ts))
            const sec = Math.floor(new Date(String(step.ts)).getTime() / 1000)
            if (Number.isFinite(sec)) {
                setMarkerPinSec(sec)
                setHoldingsSampleMode('marker')
            }
        } else if (step.ts) {
            setPlayheadTs(String(step.ts))
        }
    }, [openPacket, priceSel])

    const openTradeAt = useCallback((index: number) => {
        const t = tradeRows[index]
        if (!t) return
        setSelectedTradeKey(String(t.id))
        const sec = tradeTimeSec(t)
        if (sec != null) {
            setMarkerPinSec(sec)
            setHoldingsSampleMode('marker')
        }
        void openPacket(packetFromTrade(t))
    }, [tradeRows, openPacket])
    openTradeAtRef.current = openTradeAt

    const selectedTradeIndex = useMemo(() => {
        if (selectedTradeKey == null) return -1
        return tradeRows.findIndex(t => String(t.id) === selectedTradeKey)
    }, [tradeRows, selectedTradeKey])

    const bindChartClick = useCallback((chart: IChartApi) => {
        clickUnsubRef.current?.()
        const handler = (param: { hoveredObjectId?: unknown }) => {
            const hid = param?.hoveredObjectId
            if (hid == null) return
            const id = String(hid)
            if (!id.startsWith('trade-')) return
            const key = id.slice('trade-'.length)
            const idx = tradesRef.current.findIndex((t, i) => String(t.id ?? i) === key)
            if (idx >= 0) openTradeAtRef.current(idx)
        }
        chart.subscribeClick(handler)
        clickUnsubRef.current = () => {
            try {
                chart.unsubscribeClick(handler)
            } catch {
                /* disposed */
            }
        }
    }, [])

    const loadSignalsPage = useCallback(async (page: number, reject: string | null) => {
        if (runId == null || !needServerPagination) return
        setSignalsLoading(true)
        try {
            const res = await robotV2Service.listBacktestSignals(runId, {
                limit: SIGNAL_PAGE_SIZE,
                offset: page * SIGNAL_PAGE_SIZE,
                rejectReason: reject ?? undefined,
            })
            if (!res) {
                setSignalsEndpointOk(false)
                setPagedSignals(null)
                setSignalsFetchTotal(null)
                return
            }
            setSignalsEndpointOk(true)
            setPagedSignals(res.items || [])
            setSignalsFetchTotal(res.total)
            setSignalsPage(page)
        } finally {
            setSignalsLoading(false)
        }
    }, [runId, needServerPagination])

    useEffect(() => {
        if (!needServerPagination) {
            setPagedSignals(null)
            return
        }
        void loadSignalsPage(0, rejectFilter)
    }, [needServerPagination, rejectFilter, loadSignalsPage])

    const onRejectChip = (code: string | null) => {
        setRejectFilter(prev => (prev === code ? null : code))
        setSignalsOpen(true)
        if (!needServerPagination) setSignalsPage(0)
    }

    const buildMarkers = useCallback((): SeriesMarker<Time>[] => {
        const equityTimes: number[] = []
        for (const p of pointsRef.current) {
            if (typeof p.time === 'number') equityTimes.push(p.time)
        }
        const equitySet = new Set(equityTimes)
        const markers: SeriesMarker<Time>[] = []
        tradesRef.current.forEach((t, i) => {
            const sec = tradeTimeSec(t)
            if (sec == null) return
            // Snap to nearest equity point if exact bar missing
            let time: Time = sec as Time
            if (equitySet.size && !equitySet.has(sec)) {
                let best: number | null = null
                let bestDist = Infinity
                for (const et of equityTimes) {
                    const d = Math.abs(et - sec)
                    if (d < bestDist) {
                        bestDist = d
                        best = et
                    }
                }
                if (best != null && bestDist <= 86_400) time = best as Time
            }
            const side = String(t.side || '').toUpperCase()
            const isBuy = side === 'BUY' || side === 'LONG'
            const pnl = t.pnl_net
            let color = isBuy ? '#3dd68c' : '#f07178'
            if (pnl != null && Number.isFinite(pnl)) {
                color = pnl >= 0 ? '#3dd68c' : '#f07178'
            }
            markers.push({
                time,
                position: isBuy ? 'belowBar' : 'aboveBar',
                color,
                shape: isBuy ? 'arrowUp' : 'arrowDown',
                id: `trade-${t.id ?? i}`,
                size: 1,
            })
        })
        return markers
    }, [])

    const applyMarkers = useCallback(() => {
        const series = seriesRef.current
        if (!series) return
        const markers = buildMarkers()
        if (!markersApiRef.current) {
            markersApiRef.current = createSeriesMarkers(series, markers)
        } else {
            markersApiRef.current.setMarkers(markers)
        }
    }, [buildMarkers, seriesRef])

    useEffect(() => {
        applyMarkers()
    }, [trades, chartPoints, applyMarkers])

    useEffect(() => () => {
        clickUnsubRef.current?.()
        clickUnsubRef.current = null
    }, [])

    const tradeColumns = useMemo<Column<TradeRow>[]>(() => [
        {
            key: 'bar_time',
            header: 'Время',
            sortable: true,
            render: t => (
                <span className="mono">
                    {t.bar_time ? String(t.bar_time).replace('T', ' ').slice(0, 19) : '—'}
                </span>
            ),
        },
        { key: 'figi', header: 'Тикер', sortable: true },
        { key: 'side', header: 'Сторона' },
        {
            key: 'reason',
            header: 'Причина',
            render: t => (
                <span className="robots-v2-scan-reason">
                    {tradeReasonLabel(t.reason || t.kind)}
                </span>
            ),
        },
        {
            key: 'price',
            header: 'Цена',
            render: t => <span className="mono">{fmtMoney(Number(t.price ?? 0))}</span>,
        },
        {
            key: 'quantity',
            header: 'Кол-во',
            render: t => <span className="mono">{t.quantity}</span>,
        },
        {
            key: 'commission',
            header: 'Комиссия',
            render: t => <span className="mono">{fmtMoney(Number(t.commission ?? 0))}</span>,
        },
        {
            key: 'pnl_net',
            header: 'PnL',
            sortable: true,
            render: t => {
                const pnl = t.pnl_net
                const tone = pnl == null ? 'neutral' : pnl >= 0 ? 'up' : 'down'
                return (
                    <span className={`mono robots-v2-pnl--${tone}`}>
                        {pnl == null ? '—' : fmtMoney(pnl)}
                    </span>
                )
            },
        },
    ], [])

    const signalRows = useMemo(
        () => filteredSignals.map((s, i) => ({ ...s, id: String(s.id ?? `${signalsPage}-${i}`) })),
        [filteredSignals, signalsPage],
    )

    const signalColumns = useMemo<Column<SignalRow>[]>(() => [
        {
            key: 'signal_time',
            header: 'Время',
            sortable: true,
            render: s => (
                <span className="mono">
                    {s.signal_time
                        ? fmtTs(s.signal_time)
                        : s.created_at
                            ? fmtTs(s.created_at)
                            : '—'}
                </span>
            ),
        },
        {
            key: 'figi',
            header: 'Тикер',
            sortable: true,
            render: s => String(s.figi ?? s.ticker ?? '—'),
        },
        {
            key: 'signal_type',
            header: 'Сигнал',
            render: s => String(s.signal_type ?? s.side ?? '—'),
        },
        {
            key: 'reason',
            header: 'Причина',
            render: s => (
                <span className="robots-v2-scan-reason">
                    {tradeReasonLabel(packetFromSignal(s).strategy_reason)}
                </span>
            ),
        },
        {
            key: 'status',
            header: 'Статус',
            render: s => rowStatus(s) || '—',
        },
        {
            key: 'reject_reason',
            header: 'Отказ',
            render: s => {
                const reject = rowRejectReason(s)
                return reject ? (
                    <span className="robots-v2-scan-reason">{tradeReasonLabel(reject)}</span>
                ) : '—'
            },
        },
        {
            key: 'price',
            header: 'Цена',
            render: s => (
                <span className="mono">
                    {s.price != null ? fmtMoney(Number(s.price)) : '—'}
                </span>
            ),
        },
        {
            key: 'cycle_id',
            header: 'cycle',
            render: s => {
                const cid = rowCycleId(s)
                return cid ? <span className="mono">{cid.slice(0, 8)}…</span> : '—'
            },
        },
    ], [])

    const orderRows = useMemo(
        () => orders.map((o, i) => ({ ...o, id: String(o.id ?? i) })),
        [orders],
    )
    const orderColumns = useMemo<Column<OrderRow>[]>(() => [
        {
            key: 'signal_time',
            header: 'Время',
            sortable: true,
            render: o => (
                <span className="mono">
                    {o.signal_time
                        ? fmtTs(o.signal_time)
                        : o.submitted_at
                            ? fmtTs(o.submitted_at)
                            : '—'}
                </span>
            ),
        },
        {
            key: 'figi',
            header: 'Тикер',
            sortable: true,
            render: o => String(o.figi ?? o.ticker ?? '—'),
        },
        {
            key: 'side',
            header: 'Сторона',
            render: o => String(o.side ?? '—').toUpperCase(),
        },
        {
            key: 'status',
            header: 'Статус',
            render: o => String(o.status ?? '—'),
        },
        {
            key: 'quantity',
            header: 'Кол-во',
            render: o => <span className="mono">{Number(o.quantity ?? 0).toFixed(2)}</span>,
        },
        {
            key: 'price',
            header: 'Цена',
            render: o => (
                <span className="mono">
                    {o.executed_price != null
                        ? fmtMoney(Number(o.executed_price))
                        : o.price != null
                            ? fmtMoney(Number(o.price))
                            : '—'}
                </span>
            ),
        },
        {
            key: 'pnl_net',
            header: 'PnL',
            sortable: true,
            render: o => (
                <span className="mono">
                    {o.pnl_net != null ? fmtMoney(Number(o.pnl_net)) : '—'}
                </span>
            ),
        },
    ], [])

    const dailyRows = useMemo(
        () => dailySummary.map((row, i) => ({ ...row, id: String(row.date ?? i) })),
        [dailySummary],
    )
    const dailyColumns = useMemo<Column<DailyRow>[]>(() => [
        {
            key: 'date',
            header: 'Дата',
            sortable: true,
            render: row => <span className="mono">{String(row.date ?? '—')}</span>,
        },
        {
            key: 'signals_total',
            header: 'Сигналы',
            render: row => <span className="mono">{String(row.signals_total ?? '—')}</span>,
        },
        {
            key: 'candidates_accept',
            header: 'Accept',
            render: row => <span className="mono">{String(row.candidates_accept ?? '—')}</span>,
        },
        {
            key: 'candidates_reject',
            header: 'Reject',
            render: row => <span className="mono">{String(row.candidates_reject ?? '—')}</span>,
        },
        {
            key: 'signals_deferred',
            header: 'Deferred',
            render: row => <span className="mono">{String(row.signals_deferred ?? '—')}</span>,
        },
        {
            key: 'trades_total',
            header: 'Сделки',
            render: row => <span className="mono">{String(row.trades_total ?? '—')}</span>,
        },
    ], [])

    const clientPageCount = Math.max(1, Math.ceil(filteredSignals.length / SIGNAL_PAGE_SIZE))
    const showPagination = needServerPagination || filteredSignals.length > SIGNAL_PAGE_SIZE
    const pageCount = needServerPagination
        ? Math.max(1, Math.ceil(signalsTotal / SIGNAL_PAGE_SIZE))
        : clientPageCount
    const clientPagedRows = needServerPagination
        ? signalRows
        : signalRows.slice(signalsPage * SIGNAL_PAGE_SIZE, (signalsPage + 1) * SIGNAL_PAGE_SIZE)

    const execLabel =
        observability.execution_model?.label
        || GLASS_BOX_EXECUTION_COPY

    return (
        <>
            {/* Zone A — honesty banner (never collapsed) */}
            <div className="robots-v2-glass-honesty" role="region" aria-label="Честность исполнения">
                <div className="robots-v2-banner robots-v2-banner--warn">
                    <strong>#{runId ?? '—'}</strong>
                    <span>{execLabel}</span>
                </div>
                {truncated && (
                    <div className="robots-v2-banner robots-v2-banner--warn">
                        Журнал сигналов обрезан (лимит {signalCap.toLocaleString('ru-RU')}).
                        Статистика отказов — по залогированному окну.
                    </div>
                )}
                {isPartial && (
                    <div className="robots-v2-banner robots-v2-banner--warn">
                        Прогон частичный / отменён — метрики и решения только по доступному интервалу.
                    </div>
                )}
            </div>

            {/* Zone B — KPI */}
            <Card className="dashboard-totals-card">
                <div className="dashboard-totals-card__head">
                    <h3 className="dashboard-panel-title">Результат #{runId}</h3>
                </div>
                <div className="portfolio-stats-grid dashboard-summary-grid">
                    <StatTile label="Капитал" value={fmtMoney(initialCapital || capital)} />
                    <StatTile
                        label="Equity"
                        value={fmtMoney(finalEquity ?? 0)}
                        valueClassName={
                            (finalEquity ?? 0) >= (initialCapital || capital) ? 'color-up' : 'color-down'
                        }
                    />
                    <StatTile
                        label="Доходность"
                        value={fmtPct(totalReturnPercent)}
                        valueClassName={(totalReturnPercent ?? 0) >= 0 ? 'color-up' : 'color-down'}
                    />
                    <StatTile
                        label="Max DD"
                        value={maxDrawdownPercent == null ? '—' : `${maxDrawdownPercent.toFixed(2)}%`}
                        valueClassName="color-down"
                    />
                    <StatTile
                        label="Win rate"
                        value={
                            winRatePercent == null ? '—' : `${winRatePercent.toFixed(1)}%`
                        }
                    />
                    <StatTile label="Sharpe" value={fmtRatio(sharpeRatio)} />
                    <StatTile label="Sortino" value={fmtRatio(sortinoRatio)} />
                    <StatTile label="Calmar" value={fmtRatio(calmarRatio)} />
                    <StatTile label="Сделки" value={trades.length} />
                </div>

                {/* Zone C — run anatomy */}
                {(anatomy.chips.length > 0 || anatomyFundingHint) && (
                    <div className="robots-v2-glass-anatomy">
                        {anatomy.chips.length > 0 && (
                            <p className="robots-v2-hint robots-v2-universe-caption">
                                {anatomy.chips.join(' · ')}
                            </p>
                        )}
                        {anatomyFundingHint && (
                            <p className="robots-v2-hint robots-v2-glass-funding">{anatomyFundingHint}</p>
                        )}
                    </div>
                )}
            </Card>

            {/* Zone M — costs / funding (P1) */}
            {showCosts && feeSummary ? <BacktestCostsStrip fee={feeSummary} /> : null}

            {/* Zone D — equity + markers (+ N price submode) */}
            <div ref={chartCardRef}>
            <Card className="dashboard-assets-card robots-v2-monitor-chart">
                <div className="dashboard-assets-card__head">
                    <h3 className="dashboard-panel-title">График equity</h3>
                    <span className="robots-v2-hint">маркеры сделок кликабельны</span>
                </div>
                {chartPoints.length === 0 ? (
                    <p className="robots-v2-hint">Нет точек equity за выбранный период</p>
                ) : (
                    <Chart
                        height={chartHeight}
                        onReady={(chart) => {
                            if (!chart) {
                                clickUnsubRef.current?.()
                                clickUnsubRef.current = null
                                chartRef.current = null
                                seriesRef.current = null
                                markersApiRef.current = null
                                return
                            }
                            chartRef.current = chart
                            const series = chart.addSeries(LineSeries, {
                                color: '#3dd68c',
                                lineWidth: 2,
                            })
                            seriesRef.current = series
                            const pts = pointsRef.current
                            if (pts.length) series.setData(pts)
                            markersApiRef.current = createSeriesMarkers(series, buildMarkers())
                            bindChartClick(chart)
                        }}
                    />
                )}
                {priceSel && runId != null ? (
                    <BacktestPriceScrubber
                        runId={runId}
                        ticker={priceSel.ticker}
                        around={priceSel.around}
                        bars={priceBars}
                        onBarsChange={setPriceBars}
                        onPlayheadChange={onPricePlayhead}
                        chartHeight={chartHeight > 280 ? 200 : 180}
                    />
                ) : null}
            </Card>
            </div>

            {/* Zone E — reject lens (always visible) */}
            <Card className="dashboard-assets-card robots-v2-glass-reject">
                <div className="dashboard-assets-card__head">
                    <h3 className="dashboard-panel-title">Отказы (топ-8)</h3>
                    <div className="robots-v2-glass-status-counts">
                        <span className="robots-v2-chip robots-v2-chip--static">
                            Исполнено {statusCounts.filled ?? 0}
                        </span>
                        <span className="robots-v2-chip robots-v2-chip--static">
                            Отказ {statusCounts.rejected ?? 0}
                        </span>
                        <span className="robots-v2-chip robots-v2-chip--static">
                            Отложено {statusCounts.deferred ?? 0}
                        </span>
                    </div>
                </div>
                {truncated && (
                    <p className="robots-v2-hint robots-v2-universe-caption">
                        По залогированному окну
                    </p>
                )}
                {rejectTop.length === 0 ? (
                    <p className="robots-v2-hint">Отказов по риску не зафиксировано</p>
                ) : (
                    <div className="robots-v2-chip-row robots-v2-glass-reject__chips">
                        <button
                            type="button"
                            className={`robots-v2-chip ${rejectFilter == null ? 'robots-v2-chip--on' : ''}`}
                            onClick={() => onRejectChip(null)}
                        >
                            Все
                        </button>
                        {rejectTop.map(r => (
                            <button
                                key={r.code}
                                type="button"
                                className={`robots-v2-chip ${rejectFilter === r.code ? 'robots-v2-chip--on' : ''}`}
                                onClick={() => onRejectChip(r.code)}
                                title={r.code}
                            >
                                {tradeReasonLabel(r.code)}
                                <span className="mono robots-v2-glass-reject__count">{r.count}</span>
                            </button>
                        ))}
                    </div>
                )}
                <p className="robots-v2-hint robots-v2-glass-reject__caption">
                    Выберите маркер на графике или строку в таблице — откроется решение движка.
                </p>
            </Card>

            {/* Zone L — holdings at sample (P1) */}
            <BacktestHoldingsSection
                snapshots={portfolioSnapshots}
                sampleMode={holdingsSampleMode}
                onSampleModeChange={setHoldingsSampleMode}
                markerTimeSec={markerPinSec}
            />

            {/* Zone H — trades (open) */}
            <Card className="dashboard-assets-card">
                <div className="dashboard-assets-card__head">
                    <h3 className="dashboard-panel-title">Сделки</h3>
                    <span className="robots-v2-hint">{trades.length}</span>
                </div>
                <DataTable
                    columns={tradeColumns}
                    data={tradeRows as Array<TradeRow & Record<string, unknown>>}
                    keyField="id"
                    emptyText="Сделок не было — проверьте период, расписание и сигналы стратегии"
                    maxHeight={360}
                    onRowClick={(t) => {
                        const idx = tradeRows.findIndex(x => String(x.id) === String(t.id))
                        if (idx >= 0) openTradeAt(idx)
                    }}
                    rowClassName={t =>
                        selectedTradeKey != null && String(t.id) === selectedTradeKey
                            ? 'robots-v2-glass-row--selected'
                            : ''
                    }
                    mobilePrimary={t => (
                        <div className="portfolio-mobile-split">
                            <strong>{String(t.figi ?? '—')}</strong>
                            <span className="mono">
                                {t.pnl_net == null ? '—' : fmtMoney(t.pnl_net)}
                            </span>
                        </div>
                    )}
                    mobileDetails={t =>
                        `${t.side} · ${t.bar_time ? String(t.bar_time).slice(0, 16) : '—'}`
                    }
                />
            </Card>

            {/* Zone G — signals */}
            <CollapsibleSection
                title={(
                    <span className="dashboard-collapse__label">
                        <IconSignal />
                        Сигналы
                    </span>
                )}
                badge={
                    <span className="robots-v2-hint">
                        {rejectFilter
                            ? (needServerPagination ? signalsTotal : filteredSignals.length)
                            : signalsTotal}
                        {rejectFilter ? ` · ${tradeReasonLabel(rejectFilter)}` : ''}
                    </span>
                }
                className="dashboard-assets-card"
                open={signalsOpen}
                onOpenChange={setSignalsOpen}
            >
                {signalsLoading ? (
                    <p className="robots-v2-hint">Загрузка сигналов…</p>
                ) : (
                    <DataTable
                        columns={signalColumns}
                        data={clientPagedRows}
                        keyField="id"
                        emptyText={
                            rejectFilter
                                ? 'Нет сигналов с этим кодом отказа'
                                : 'Нет сигналов за период'
                        }
                        maxHeight={320}
                        onRowClick={(s) => {
                            setSelectedTradeKey(null)
                            void openPacket(packetFromSignal(s))
                        }}
                    />
                )}
                {showPagination && (
                    <div className="robots-v2-glass-pager">
                        <button
                            type="button"
                            className="robots-v2-chip"
                            disabled={signalsPage <= 0 || signalsLoading}
                            onClick={() => {
                                const next = signalsPage - 1
                                if (needServerPagination) void loadSignalsPage(next, rejectFilter)
                                else setSignalsPage(next)
                            }}
                        >
                            ←
                        </button>
                        <span className="robots-v2-hint mono">
                            {signalsPage + 1} / {pageCount}
                        </span>
                        <button
                            type="button"
                            className="robots-v2-chip"
                            disabled={signalsPage + 1 >= pageCount || signalsLoading}
                            onClick={() => {
                                const next = signalsPage + 1
                                if (needServerPagination) void loadSignalsPage(next, rejectFilter)
                                else setSignalsPage(next)
                            }}
                        >
                            →
                        </button>
                    </div>
                )}
            </CollapsibleSection>

            {/* Zone I — daily */}
            <CollapsibleSection
                title={(
                    <span className="dashboard-collapse__label">
                        <IconDaily />
                        Дневная сводка
                    </span>
                )}
                badge={
                    dailySummary.length > 0 ? (
                        <span className="robots-v2-hint">{dailySummary.length}</span>
                    ) : undefined
                }
                className="dashboard-assets-card"
            >
                <DataTable
                    columns={dailyColumns}
                    data={dailyRows}
                    keyField="id"
                    emptyText="Нет дневной разбивки"
                    maxHeight={320}
                />
            </CollapsibleSection>

            {/* Zone K — universe membership (P1) */}
            <BacktestUniverseSection
                runId={runId}
                fromDate={requestedFrom}
                toDate={requestedTo}
            />

            {/* Zone P — narrative stream (P2) */}
            <BacktestNarrativeSection
                runId={runId}
                seedSteps={narrativeProp}
                highlightedTs={playheadTs}
                onStepClick={onNarrativeStep}
            />

            {/* Orders — de-emphasized */}
            <CollapsibleSection
                title={(
                    <span className="dashboard-collapse__label">
                        <IconOrders />
                        Ордера
                    </span>
                )}
                badge={
                    orders.length > 0 ? (
                        <span className="robots-v2-hint">{orders.length}</span>
                    ) : undefined
                }
                className="dashboard-assets-card robots-v2-glass-orders"
                hint="Вторичный журнал — glass-box смотрите в сделках и сигналах"
            >
                <DataTable
                    columns={orderColumns}
                    data={orderRows}
                    keyField="id"
                    emptyText="Нет ордеров за период"
                    maxHeight={320}
                    onRowClick={(o) => {
                        const row = asRecord(o)
                        const cid = rowCycleId(row)
                        if (!cid && !row.figi && !row.ticker) return
                        setSelectedTradeKey(null)
                        void openPacket({
                            ...packetFromTrade(row),
                            source: 'order',
                            status: String(row.status ?? '') || null,
                        })
                    }}
                />
            </CollapsibleSection>

            {/* Zone F — inspector (+ O lifecycle) */}
            <DecisionInspectorDrawer
                open={inspectorOpen}
                onClose={closeInspector}
                packet={inspectorPacket}
                loading={inspectorLoading}
                runId={runId}
                seedExecutionEvents={
                    (() => {
                        const ev = (inspectorPacket as BacktestDecisionPacket & {
                            execution_events?: BacktestExecutionEvent[]
                        } | null)?.execution_events
                        return ev && ev.length ? ev : null
                    })()
                }
                onLifecycleStepClick={onLifecycleStep}
                onJumpToPriceChart={
                    priceSel
                        ? () => {
                            chartCardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                        }
                        : undefined
                }
                onPrevTrade={
                    selectedTradeIndex > 0
                        ? () => openTradeAt(selectedTradeIndex - 1)
                        : undefined
                }
                onNextTrade={
                    selectedTradeIndex >= 0 && selectedTradeIndex < tradeRows.length - 1
                        ? () => openTradeAt(selectedTradeIndex + 1)
                        : undefined
                }
            />
        </>
    )
}

function IconSignal() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M4 18V12M9 18V8M14 18V10M19 18V6" />
        </svg>
    )
}

function IconOrders() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" d="M5 5h14v14H5z" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M8 9h8M8 12h8M8 15h5" />
        </svg>
    )
}

function IconDaily() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <rect x="4" y="5" width="16" height="15" rx="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M8 3.5v3M16 3.5v3M4 9.5h16" />
        </svg>
    )
}
