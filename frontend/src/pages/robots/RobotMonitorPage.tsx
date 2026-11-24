import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { useToast } from '@/components/ui/Toast'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAuthStore } from '@/stores/authStore'
import { MonitorEquityChart } from '@/pages/robots/components/MonitorEquityChart'
import { MonitorLiveOrdersCard } from '@/pages/robots/components/MonitorLiveOrdersCard'
import { MonitorOrdersCard } from '@/pages/robots/components/MonitorOrdersCard'
import { MonitorPositionsCard } from '@/pages/robots/components/MonitorPositionsCard'
import { MonitorSummaryCard } from '@/pages/robots/components/MonitorSummaryCard'
import { MonitorUniverseCard } from '@/pages/robots/components/MonitorUniverseCard'
import {
    useQuietChromeActions,
    useQuietChromeLive,
    useQuietChromePhaseNote,
} from '@/pages/robots/RobotQuietShell'
import { fmtErr, fmtRubSmart, readCssColor } from '@/pages/robots/formatters'
import {
    appendEquityPoint,
    balanceFootnoteText,
    collectAuditTradeTickers,
    computeDayTradeStats,
    filterScanCooldownRows,
    formatBalanceAsOfLabel,
    fmtNetPnl,
    fmtOrderClock,
    isFiniteBalance,
    buildPoolDecisionRows,
    mergeDecisionFeed,
    mergeLiveRoundTrips,
    mergeUniverseTickers,
    normalizeEquityPoints,
    isMoscowToday,
    parseBalanceSource,
    pick,
    pickOpenPositions,
    pickRoundTripField,
    posPrice,
    positionBlotterSubtitle,
    positionTicker,
    positionTickerWarning,
    positionUnrealizedPnl,
    positionsStampMs,
    readPosNumber,
    scanStampMs,
    sortByTickerName,
    toDecisionFeedRow,
    tripOnLiveDay,
    toOrderDisplayRow,
} from '@/pages/robots/monitorUtils'
import { robotService } from '@/services/robotService'
import type { TradingRobot, TradingRobotRoundTrip, TradingRobotStatus, TradingRobotTickerScan } from '@/types/robots'
import type { IChartApi, ISeriesApi, Time } from '@/components/ui/Chart'
import { formatLocalChartTime } from '@/components/ui/Chart'
import { LineSeries } from 'lightweight-charts'
import type { MonitorChartHover } from '@/pages/robots/components/MonitorEquityChart'

export default function RobotMonitorPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const toast = useToast()

    const [robot, setRobot] = useState<TradingRobot | null>(null)
    const [status, setStatus] = useState<TradingRobotStatus | null>(null)
    const [statusLoaded, setStatusLoaded] = useState(false)
    const [equityPoints, setEquityPoints] = useState<Array<{ time: Time; value: number }>>([])
    const [chartHover, setChartHover] = useState<MonitorChartHover | null>(null)
    const equityPointsRef = useRef(equityPoints)
    equityPointsRef.current = equityPoints
    const [liveStage, setLiveStage] = useState<{
        stage: string
        label?: string
        progress?: number
        skipReason?: string | null
        triggeredBy?: string | null
        detail?: string | null
    } | null>(null)
    const [tickerScan, setTickerScan] = useState<TradingRobotTickerScan[]>([])
    const [tickerScanAt, setTickerScanAt] = useState<string | null>(null)
    const [roundTrips, setRoundTrips] = useState<TradingRobotRoundTrip[]>([])
    const [decisionFeed, setDecisionFeed] = useState<Array<Record<string, unknown>>>([])
    const [busy, setBusy] = useState(false)
    const [universeBusy, setUniverseBusy] = useState(false)
    const positionsFreshAtRef = useRef(0)
    const scanFreshAtRef = useRef(0)

    const chartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)

    const applyOpenPositions = useCallback((
        rows: Array<Record<string, unknown>>,
        updatedAt: string,
        incomingMs: number,
    ) => {
        if (incomingMs < positionsFreshAtRef.current) return
        positionsFreshAtRef.current = incomingMs
        setStatus(prev => prev ? {
            ...prev,
            openPositions: rows,
            positionsUpdatedAt: updatedAt,
        } : prev)
    }, [])

    const applyTickerScan = useCallback((
        rows: TradingRobotTickerScan[],
        at: string,
        incomingMs: number,
    ) => {
        if (!rows.length) return
        if (incomingMs > 0 && incomingMs < scanFreshAtRef.current) return
        if (incomingMs > 0) scanFreshAtRef.current = incomingMs
        setTickerScan(rows)
        setTickerScanAt(at)
    }, [])

    const refresh = useCallback(async () => {
        if (!Number.isFinite(robotId)) return
        try {
            const [r, s, auditRes] = await Promise.all([
                robotService.getById(robotId),
                robotService.getStatus(robotId),
                robotService.fetchAudit({
                    robotId,
                    limit: 200,
                    types: ['roundTrips', 'decisions'],
                }).catch(() => ({
                    robotId,
                    roundTrips: { items: [] as TradingRobotRoundTrip[], total: 0 },
                    decisions: { items: [], total: 0 },
                })),
            ])
            setRobot(r)
            setStatus(prev => {
                const restAt = positionsStampMs(
                    pick<string>(s, 'positionsUpdatedAt', 'positions_updated_at'),
                )
                if (prev && restAt < positionsFreshAtRef.current) {
                    return {
                        ...s,
                        openPositions: prev.openPositions,
                        positionsUpdatedAt: prev.positionsUpdatedAt,
                    }
                }
                if (restAt >= positionsFreshAtRef.current) {
                    positionsFreshAtRef.current = restAt
                }
                return s
            })
            setStatusLoaded(true)
            setRoundTrips(auditRes.roundTrips?.items || [])
            const liveDecisions = pick<Array<Record<string, unknown>>>(s, 'decisions', 'decisions')
            const auditDecisions = (auditRes.decisions?.items || []) as Array<Record<string, unknown>>
            setDecisionFeed(mergeDecisionFeed(liveDecisions, auditDecisions))
            const scan = pick<TradingRobotTickerScan[]>(s, 'tickerScan', 'ticker_scan')
            const scanAt = pick<string>(s, 'tickerScanAt', 'ticker_scan_at')
            if (Array.isArray(scan) && scan.length > 0) {
                const scanMs = scanStampMs(scanAt)
                applyTickerScan(scan, scanAt || new Date().toISOString(), scanMs || Date.now())
            }
            const curve = pick<Array<{ time?: string; equity?: number }>>(s, 'equityCurve', 'equity_curve')
            if (Array.isArray(curve) && curve.length > 0) {
                const points = curve
                    .map(p => {
                        const eq = Number(p.equity)
                        if (!Number.isFinite(eq)) return null
                        let tSec: number
                        if (p.time) {
                            const ms = Date.parse(String(p.time))
                            tSec = Number.isFinite(ms) ? Math.floor(ms / 1000) : Math.floor(Date.now() / 1000)
                        } else {
                            tSec = Math.floor(Date.now() / 1000)
                        }
                        return { time: tSec as Time, value: eq }
                    })
                    .filter((x): x is { time: Time; value: number } => x != null)
                if (points.length) {
                    setEquityPoints(normalizeEquityPoints(points).filter(p => isMoscowToday(p.time as number)))
                }
            } else {
                const eq = pick<number>(s, 'equity', 'equity')
                if (eq != null && Number.isFinite(eq)) {
                    setEquityPoints(prev => appendEquityPoint(prev, Number(eq)))
                }
            }
        } catch (e) {
            setStatusLoaded(true)
            toast.show(fmtErr(e), 'error')
        }
    }, [robotId, toast, applyTickerScan])

    useEffect(() => {
        setStatusLoaded(false)
        setStatus(null)
        setDecisionFeed([])
        positionsFreshAtRef.current = 0
        scanFreshAtRef.current = 0
        void refresh()
    }, [robotId, refresh])

    const token = useAuthStore(s => s.token)
    const wsUrl = useMemo(() => {
        if (!Number.isFinite(robotId) || !token) return ''
        return robotService.buildStreamUrl(robotId, token)
    }, [robotId, token])
    const { connected: streamConnected } = useWebSocket({
        url: wsUrl,
        enabled: Boolean(wsUrl),
        onMessage: (msg: { type?: string; robotId?: number; ts?: string; [k: string]: unknown }) => {
            if (!msg || typeof msg !== 'object') return
            const type = String(msg.type || 'event')
            if (type === 'ping') return
            const posRows = (type === 'cycle' || type === 'positions')
                ? pickOpenPositions(msg as Record<string, unknown>)
                : null
            if (posRows) {
                const updatedAt = msg.positionsUpdatedAt != null
                    ? String(msg.positionsUpdatedAt)
                    : (msg.positions_updated_at != null
                        ? String(msg.positions_updated_at)
                        : (msg.ts ? String(msg.ts) : new Date().toISOString()))
                applyOpenPositions(posRows, updatedAt, positionsStampMs(updatedAt, msg.ts) || Date.now())
            }
            if (type === 'equity_snapshot' && Array.isArray(msg.points)) {
                const points = (msg.points as Array<{ time?: string; equity?: number }>)
                    .map(p => {
                        const eq = Number(p.equity)
                        if (!Number.isFinite(eq)) return null
                        const ms = p.time ? Date.parse(String(p.time)) : NaN
                        const tSec = Number.isFinite(ms) ? Math.floor(ms / 1000) : Math.floor(Date.now() / 1000)
                        return { time: tSec as Time, value: eq }
                    })
                    .filter((x): x is { time: Time; value: number } => x != null)
                if (points.length) {
                    setEquityPoints(normalizeEquityPoints(points).filter(p => isMoscowToday(p.time as number)))
                }
                return
            }
            if (type === 'cycle' && typeof msg.equity === 'number' && isMoscowToday(msg.ts ? String(msg.ts) : Date.now())) {
                setEquityPoints(prev => appendEquityPoint(prev, Number(msg.equity)))
            }
            if (type === 'cycle' && Array.isArray(msg.tickerScan)) {
                const at = msg.ts ? String(msg.ts) : new Date().toISOString()
                applyTickerScan(
                    msg.tickerScan as TradingRobotTickerScan[],
                    at,
                    scanStampMs(at, msg.ts) || Date.now(),
                )
            }
            if (type === 'cycle' && Array.isArray(msg.decisions) && msg.decisions.length > 0) {
                setDecisionFeed(mergeDecisionFeed(
                    msg.decisions as Array<Record<string, unknown>>,
                    null,
                ))
            }
            if (type === 'decision') {
                const row = toDecisionFeedRow(msg as Record<string, unknown>)
                if (row) {
                    if (row.createdAt == null) {
                        row.createdAt = msg.ts != null ? String(msg.ts) : new Date().toISOString()
                    }
                    setDecisionFeed(prev => mergeDecisionFeed([row, ...prev], null))
                }
            }
            if (type === 'universe') {
                const uni = Array.isArray(msg.universe) ? (msg.universe as string[]) : null
                if (uni) {
                    setStatus(prev => prev ? { ...prev, universe: uni } : prev)
                }
                if (Array.isArray(msg.tickerScan) && msg.tickerScan.length > 0) {
                    const at = msg.refreshedAt != null
                        ? String(msg.refreshedAt)
                        : (msg.ts ? String(msg.ts) : new Date().toISOString())
                    applyTickerScan(
                        msg.tickerScan as TradingRobotTickerScan[],
                        at,
                        scanStampMs(at, msg.refreshedAt ?? msg.ts) || Date.now(),
                    )
                }
            }
            if (type === 'stage') {
                setLiveStage({
                    stage: String(msg.stage || 'idle'),
                    label: msg.label ? String(msg.label) : undefined,
                    progress: typeof msg.progress === 'number' ? Number(msg.progress) : undefined,
                    skipReason: msg.skipReason != null ? String(msg.skipReason) : null,
                    triggeredBy: msg.triggeredBy != null ? String(msg.triggeredBy) : null,
                    detail: msg.detail != null ? String(msg.detail) : null,
                })
            }
            if (type === 'health') {
                const state = String(msg.state || '').toUpperCase()
                if (state === 'RUNNING' || state === 'BOOTSTRAP' || state === 'STOPPING'
                    || state === 'TERMINATED' || state === 'ERROR') {
                    void refresh()
                }
            }
        },
    })

    useEffect(() => {
        const pollMs = streamConnected ? 8_000 : 5_000
        const timer = window.setInterval(() => void refresh(), pollMs)
        return () => window.clearInterval(timer)
    }, [refresh, streamConnected])

    useEffect(() => {
        const series = seriesRef.current
        if (!series || equityPoints.length === 0) return
        series.setData(equityPoints)
    }, [equityPoints])

    const onStart = useCallback(async () => {
        setBusy(true)
        try {
            const mode = String((robot?.config?.core as Record<string, unknown> | undefined)?.mode || 'paper')
            if (mode === 'live') {
                await robotService.start(robotId, {})
            } else {
                const risk = (robot?.config?.risk || {}) as Record<string, unknown>
                await robotService.start(robotId, { virtualCapital: Number(risk.capital || 100_000) })
            }
            toast.show('Запущен', 'success')
            await refresh()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusy(false)
        }
    }, [robot, robotId, toast, refresh])

    const onPause = useCallback(async () => {
        setBusy(true)
        try {
            await robotService.stop(robotId, 'soft')
            toast.show('Пауза', 'info')
            await refresh()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusy(false)
        }
    }, [robotId, toast, refresh])

    const onRefreshUniverse = async () => {
        setUniverseBusy(true)
        try {
            const res = await robotService.refreshUniverse(robotId)
            if (res.keptPrevious) {
                toast.show('Скринер вернул пустой список — оставлен прежний пул', 'info')
            } else {
                const added = res.added?.length ?? 0
                const removed = res.removed?.length ?? 0
                toast.show(
                    added || removed
                        ? `Пул обновлён: +${added} −${removed}`
                        : 'Пул обновлён, состав тот же',
                    'success',
                )
            }
            if (Array.isArray(res.universe)) {
                setStatus(prev => prev ? { ...prev, universe: res.universe } : prev)
            }
            if (Array.isArray(res.tickerScan) && res.tickerScan.length > 0) {
                const at = res.refreshedAt || new Date().toISOString()
                applyTickerScan(
                    res.tickerScan,
                    at,
                    scanStampMs(at) || Date.now(),
                )
            }
            await refresh()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setUniverseBusy(false)
        }
    }

    const sessionStateRaw = pick(status || ({} as TradingRobotStatus), 'sessionState', 'session_state')
    const sessionUpper = String(sessionStateRaw || '').toUpperCase()
    const equityRaw = pick<number>(status || ({} as TradingRobotStatus), 'equity', 'equity')
    const cashRaw = pick<number>(status || ({} as TradingRobotStatus), 'cash', 'cash')
    const equity = isFiniteBalance(equityRaw) ? Number(equityRaw) : null
    const cash = isFiniteBalance(cashRaw) ? Number(cashRaw) : null
    const chartLastEquity = (() => {
        if (!equityPoints.length) return null
        const last = Number(equityPoints[equityPoints.length - 1]?.value)
        return Number.isFinite(last) ? last : null
    })()
    /** Live equity for hero — not chart crosshair (hover stays on the chart overlay only). */
    const displayEquity = chartLastEquity ?? equity
    const balanceSource = parseBalanceSource(
        pick(status || ({} as TradingRobotStatus), 'balanceSource', 'balance_source'),
    )
    const balanceAsOf = pick<string>(status || ({} as TradingRobotStatus), 'balanceAsOf', 'balance_as_of')
    const statusMode = pick<string>(status || ({} as TradingRobotStatus), 'mode', 'mode')
        || String((robot?.config?.core as Record<string, unknown> | undefined)?.mode || '')
    const bootstrapReady = Boolean(
        pick<boolean>(status || ({} as TradingRobotStatus), 'bootstrapReady', 'bootstrap_ready'),
    )
    const isRunning = sessionUpper === 'RUNNING' || sessionUpper === 'BOOTSTRAP'
    const isStopping = sessionUpper === 'STOPPING'
    const isActive = isRunning || isStopping
    const statusStage = pick<string>(status || ({} as TradingRobotStatus), 'cycleStage', 'cycle_stage')
    const stageLower = String(liveStage?.stage || statusStage || '').toLowerCase()
    const isSyncing =
        statusLoaded
        && (
            sessionUpper === 'BOOTSTRAP'
            || (sessionUpper === 'RUNNING' && !bootstrapReady)
            || (isActive && (stageLower === 'bootstrap' || stageLower === 'bootstrap_sync'))
        )
    const showSessionOps = statusLoaded && isActive && !isSyncing
    const showBalance = statusLoaded && (displayEquity != null || equity != null || cash != null)
    const balanceFootnote = showBalance ? balanceFootnoteText(balanceSource, statusMode) : null
    const balanceAsOfLabel = showBalance ? formatBalanceAsOfLabel(balanceAsOf) : null
    const isLiveMode = String(statusMode || '').toLowerCase() === 'live'
    /** Live idle/fail with null balances → honesty line; paper never-capitalized → omit strip */
    const showBalanceUnavailable = statusLoaded && !showBalance && isLiveMode
    const universeCfg = (robot?.config?.universe || {}) as Record<string, unknown>
    const universeMode = String(universeCfg.mode || '')
    const canRefreshUniverse = isActive && !isSyncing && (universeMode === 'screener' || universeMode === 'index')
    const positionsRaw = pick<Array<Record<string, unknown>>>(status || ({} as TradingRobotStatus), 'openPositions', 'open_positions') || []
    const positions = useMemo(
        () => sortByTickerName(positionsRaw, positionTicker),
        [positionsRaw],
    )
    const liveOrders = pick<Array<Record<string, unknown>>>(status || ({} as TradingRobotStatus), 'openOrders', 'open_orders') || []
    const orderRows = useMemo(
        () => mergeLiveRoundTrips(roundTrips, liveOrders),
        [roundTrips, liveOrders],
    )
    const dayOrderRows = useMemo(
        () => orderRows.filter(trip => tripOnLiveDay(trip)),
        [orderRows],
    )
    const dayStats = useMemo(() => computeDayTradeStats(roundTrips), [roundTrips])
    const dayDelta = fmtNetPnl(dayStats.delta)
    const dayMtm = useMemo(() => {
        if (equityPoints.length < 2) return null
        const first = Number(equityPoints[0]?.value)
        const last = Number(equityPoints[equityPoints.length - 1]?.value)
        if (!Number.isFinite(first) || !Number.isFinite(last)) return null
        return fmtNetPnl(last - first)
    }, [equityPoints])
    const sessionHint = useMemo(() => {
        if (!statusLoaded || showSessionOps) return null
        if (isSyncing) return 'Робот синхронизируется'
        if (!isActive) return 'Робот не работает'
        return null
    }, [statusLoaded, showSessionOps, isSyncing, isActive])
    const orderDisplayRows = useMemo(
        () => dayOrderRows.map(toOrderDisplayRow),
        [dayOrderRows],
    )
    const universeRaw = pick<string[]>(status || ({} as TradingRobotStatus), 'universe', 'universe') || []
    const universe = useMemo(
        () => mergeUniverseTickers(universeRaw, positionsRaw),
        [universeRaw, positionsRaw],
    )
    const auditTradeTickers = useMemo(
        () => collectAuditTradeTickers(roundTrips, positions, liveOrders),
        [roundTrips, positions, liveOrders],
    )
    const displayTickerScan = useMemo(
        () => sortByTickerName(
            filterScanCooldownRows(tickerScan, auditTradeTickers),
            row => row.ticker,
        ),
        [tickerScan, auditTradeTickers],
    )
    const positionTableRows = useMemo(
        () => positions.map((p, i) => {
            const row = p as Record<string, unknown>
            const ticker = positionTicker(row)
            const entryN = readPosNumber(row, 'entry_price', 'entryPrice', 'avg_entry_price', 'avgEntryPrice')
            const currentN = readPosNumber(row, 'current_price', 'currentPrice')
            const currentTone: 'up' | 'down' | 'neutral' = entryN != null && currentN != null
                ? (currentN > entryN ? 'up' : currentN < entryN ? 'down' : 'neutral')
                : 'neutral'
            const pnlAbs = positionUnrealizedPnl(row)
            const pnl = fmtNetPnl(pnlAbs)
            const qty = readPosNumber(row, 'quantity', 'qty')
            const entry = posPrice(row, 'entry_price', 'entryPrice', 'avg_entry_price', 'avgEntryPrice')
            const current = posPrice(row, 'current_price', 'currentPrice')
            const sl = posPrice(row, 'stop_loss_price', 'stopLossPrice')
            const tp = posPrice(row, 'take_profit_price', 'takeProfitPrice')
            const openedRaw = row.opened_at ?? row.openedAt
            const openTrip = roundTrips.find(t => {
                const st = String(t.status || '').toLowerCase()
                return String(t.ticker || '').toUpperCase() === ticker
                    && (st === 'open' || st === 'resting' || st === 'submitted' || st === 'new')
            })
            const tripBuyAt = openTrip
                ? pickRoundTripField<string | null>(openTrip, 'buyAt', 'buy_at')
                : null
            const boughtAtLabel = fmtOrderClock(
                (typeof openedRaw === 'string' || typeof openedRaw === 'number'
                    ? String(openedRaw)
                    : null)
                || tripBuyAt,
            )
            return {
                id: String(row.ticker ?? row.secid ?? row.figi ?? i),
                tickerLabel: String(row.ticker ?? row.figi ?? '—'),
                tickerWarning: positionTickerWarning(row),
                side: String(row.side ?? '—'),
                quantity: qty != null ? String(qty) : '—',
                boughtAtLabel,
                entry,
                current,
                currentTone,
                entryToNow: `${entry} → ${current}`,
                sl,
                tp,
                slTp: `${sl} / ${tp}`,
                subtitle: positionBlotterSubtitle(row, liveOrders),
                pnlText: pnl.text,
                pnlTone: pnl.tone,
                pnlAbs: pnlAbs ?? 0,
            }
        }),
        [positions, liveOrders, roundTrips],
    )
    const positionsPnlTotal = useMemo(() => {
        let sum = 0
        let any = false
        for (const row of positionTableRows) {
            if (!Number.isFinite(row.pnlAbs)) continue
            sum += row.pnlAbs
            any = true
        }
        if (!any) return null
        const fmt = fmtNetPnl(sum)
        return { ...fmt, abs: sum }
    }, [positionTableRows])
    const displayUniverse = useMemo(
        () => sortByTickerName(universe, t => t),
        [universe],
    )
    const cycle = pick<number>(status || ({} as TradingRobotStatus), 'cycleNumber', 'cycle_number')
    const balanceNote = [balanceFootnote, balanceAsOfLabel].filter(Boolean).join(' · ') || null
    const poolTickers = displayUniverse.length > 0
        ? displayUniverse
        : displayTickerScan.map(row => row.ticker)
    const poolDecisionRows = useMemo(
        () => buildPoolDecisionRows(poolTickers, displayTickerScan, decisionFeed, tickerScanAt),
        [poolTickers, displayTickerScan, decisionFeed, tickerScanAt],
    )
    const totalPnlLabel = positionsPnlTotal
        ? `${positionsPnlTotal.text}${equity != null && equity !== 0
            ? ` (${((positionsPnlTotal.abs / Math.abs(equity)) * 100).toLocaleString('ru-RU', {
                maximumFractionDigits: 1,
                signDisplay: 'exceptZero',
            })}%)`
            : ''}`
        : null

    useQuietChromeLive(liveStage, streamConnected)
    useQuietChromePhaseNote(balanceNote)
    useQuietChromeActions(() => (
        !statusLoaded ? (
            <Button type="button" size="sm" loading disabled>
                Статус…
            </Button>
        ) : isActive ? (
            <Button
                type="button"
                variant="ghost"
                size="sm"
                loading={busy}
                disabled={isStopping}
                onClick={() => void onPause()}
            >
                Пауза
            </Button>
        ) : (
            <Button type="button" size="sm" loading={busy} onClick={() => void onStart()}>
                Запуск
            </Button>
        )
    ), [statusLoaded, isActive, busy, isStopping, onPause, onStart])

    return (
            <div className="dashboard-layout">
                <Card className="dashboard-totals-card robots-monitor-cockpit">
                    <div className="robots-monitor-cockpit__grid">
                    <MonitorSummaryCard
                        statusLoaded={statusLoaded}
                        dayDelta={dayDelta}
                        dayMtm={dayMtm}
                        showBalance={showBalance}
                        equityLabel={displayEquity != null ? fmtRubSmart(displayEquity) : null}
                        cashLabel={cash != null ? fmtRubSmart(cash) : null}
                        showBalanceUnavailable={showBalanceUnavailable}
                        positionsCount={positions.length}
                        cycle={cycle}
                        dayWins={dayStats.wins}
                        dayLosses={dayStats.losses}
                        sessionHint={sessionHint}
                    />
                    <MonitorEquityChart
                        hover={chartHover}
                        onReady={chart => {
                            if (!chart) {
                                chartRef.current = null
                                seriesRef.current = null
                                setChartHover(null)
                                return
                            }
                            chartRef.current = chart
                            const series = chart.addSeries(LineSeries, {
                                color: readCssColor('--color-up', '#3dbe7a'),
                                lineWidth: 2,
                                priceLineVisible: false,
                                lastValueVisible: true,
                            })
                            seriesRef.current = series
                            if (equityPointsRef.current.length) series.setData(equityPointsRef.current)
                            chart.subscribeCrosshairMove(param => {
                                const points = equityPointsRef.current
                                const point = param.seriesData?.get(series) as { value?: number } | undefined
                                if (!param.time || point?.value == null) {
                                    setChartHover(null)
                                    return
                                }
                                const key = String(param.time)
                                const idx = points.findIndex(item => String(item.time) === key)
                                const prev = idx > 0 ? points[idx - 1]?.value : null
                                const delta = prev != null ? point.value - prev : null
                                const deltaPct = prev != null && prev !== 0 && delta != null
                                    ? (delta / prev) * 100
                                    : null
                                setChartHover({
                                    time: formatLocalChartTime(param.time),
                                    value: point.value,
                                    delta: delta != null ? Number(delta.toFixed(2)) : null,
                                    deltaPct: deltaPct != null ? Number(deltaPct.toFixed(2)) : null,
                                })
                            })
                        }}
                    />
                    </div>
                </Card>

                <div className="robots-monitor-panels">
                    <MonitorLiveOrdersCard orders={liveOrders} />
                    <MonitorPositionsCard
                        rows={positionTableRows}
                        totalPnlLabel={totalPnlLabel}
                        totalPnlTone={positionsPnlTotal?.tone ?? 'neutral'}
                        brokerSoftStopHint={
                            !isRunning
                            && pick<string>(status || ({} as TradingRobotStatus), 'positionsSource', 'positions_source') === 'broker'
                            && positions.length > 0
                        }
                        isRunning={isRunning}
                    />
                    <MonitorOrdersCard
                        rows={orderDisplayRows}
                        dayTotalLabel={dayStats.trades > 0 ? dayDelta.text : null}
                        dayTotalTone={dayDelta.tone}
                    />
                    <MonitorUniverseCard
                        rows={poolDecisionRows}
                        canRefreshUniverse={canRefreshUniverse}
                        universeBusy={universeBusy}
                        onRefreshUniverse={() => void onRefreshUniverse()}
                    />
                </div>
            </div>
    )
}
