import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { useToast } from '@/components/ui/Toast'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAuthStore } from '@/stores/authStore'
import { MonitorDecisionsCard } from '@/pages/robots-v2/components/MonitorDecisionsCard'
import { MonitorEquityChart } from '@/pages/robots-v2/components/MonitorEquityChart'
import { MonitorEventsCard } from '@/pages/robots-v2/components/MonitorEventsCard'
import { MonitorOrdersCard } from '@/pages/robots-v2/components/MonitorOrdersCard'
import { MonitorPositionsCard } from '@/pages/robots-v2/components/MonitorPositionsCard'
import { MonitorSummaryCard } from '@/pages/robots-v2/components/MonitorSummaryCard'
import { MonitorUniverseCard } from '@/pages/robots-v2/components/MonitorUniverseCard'
import { RobotConfirmModal } from '@/pages/robots-v2/components/RobotConfirmModal'
import { RobotPageChrome } from '@/pages/robots-v2/components/RobotPageChrome'
import { RobotStageCard } from '@/pages/robots-v2/components/RobotStageCard'
import { fmtErr, fmtNum, sessionStateLabel } from '@/pages/robots-v2/formatters'
import {
    appendEquityPoint,
    balanceFootnoteText,
    balanceTileLabels,
    collectAuditTradeTickers,
    computeDayTradeStats,
    filterScanCooldownRows,
    formatBalanceAsOfLabel,
    fmtNetPnl,
    isFiniteBalance,
    mergeLiveRoundTrips,
    mergeUniverseTickers,
    normalizeEquityPoints,
    parseBalanceSource,
    pick,
    pickOpenPositions,
    posPrice,
    positionTicker,
    positionTickerWarning,
    positionsStampMs,
    scanStampMs,
    sortByTickerName,
    stageDetailLabel,
    stageLabel,
    toOrderDisplayRow,
    SKIP_LABELS,
} from '@/pages/robots-v2/monitorUtils'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2, RobotV2RoundTrip, RobotV2Status, RobotV2TickerScan } from '@/types/robotV2'
import type { IChartApi, ISeriesApi, Time } from '@/components/ui/Chart'
import { LineSeries } from 'lightweight-charts'

export default function RobotV2MonitorPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const toast = useToast()

    const [robot, setRobot] = useState<RobotV2 | null>(null)
    const [status, setStatus] = useState<RobotV2Status | null>(null)
    const [statusLoaded, setStatusLoaded] = useState(false)
    const [events, setEvents] = useState<Array<{ ts: string; type: string; payload: unknown }>>([])
    const [equityPoints, setEquityPoints] = useState<Array<{ time: Time; value: number }>>([])
    const [liveStage, setLiveStage] = useState<{
        stage: string
        label?: string
        progress?: number
        skipReason?: string | null
        triggeredBy?: string | null
        detail?: string | null
    } | null>(null)
    const [tickerScan, setTickerScan] = useState<RobotV2TickerScan[]>([])
    const [tickerScanAt, setTickerScanAt] = useState<string | null>(null)
    const [roundTrips, setRoundTrips] = useState<RobotV2RoundTrip[]>([])
    const [busy, setBusy] = useState(false)
    const [hardStopOpen, setHardStopOpen] = useState(false)
    const [universeBusy, setUniverseBusy] = useState(false)
    const seenEventKeys = useRef(new Set<string>())
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
        rows: RobotV2TickerScan[],
        at: string,
        incomingMs: number,
    ) => {
        if (!rows.length) return
        if (incomingMs > 0 && incomingMs < scanFreshAtRef.current) return
        if (incomingMs > 0) scanFreshAtRef.current = incomingMs
        setTickerScan(rows)
        setTickerScanAt(at)
    }, [])

    const pushEvent = useCallback((type: string, payload: unknown, ts?: string) => {
        const stamp = ts || new Date().toISOString()
        const key = `${stamp}|${type}|${JSON.stringify(payload).slice(0, 120)}`
        if (seenEventKeys.current.has(key)) return
        seenEventKeys.current.add(key)
        if (seenEventKeys.current.size > 400) {
            seenEventKeys.current = new Set([...seenEventKeys.current].slice(-200))
        }
        setEvents(prev => [{ ts: stamp, type, payload }, ...prev].slice(0, 80))
    }, [])

    const refresh = useCallback(async () => {
        if (!Number.isFinite(robotId)) return
        try {
            const [r, s, logs, auditRes] = await Promise.all([
                robotV2Service.getById(robotId),
                robotV2Service.getStatus(robotId),
                robotV2Service.getLogs(robotId, { limit: 40 }).catch(() => ({ items: [] as Array<Record<string, unknown>> })),
                robotV2Service.fetchAudit({ robotId, limit: 200, types: ['roundTrips'] }).catch(() => ({
                    robotId,
                    roundTrips: { items: [] as RobotV2RoundTrip[], total: 0 },
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
            const scan = pick<RobotV2TickerScan[]>(s, 'tickerScan', 'ticker_scan')
            const scanAt = pick<string>(s, 'tickerScanAt', 'ticker_scan_at')
            if (Array.isArray(scan) && scan.length > 0) {
                const scanMs = scanStampMs(scanAt)
                applyTickerScan(scan, scanAt || new Date().toISOString(), scanMs || Date.now())
            }
            for (const raw of [...(logs.items || [])].reverse()) {
                const type = String(raw.type || 'event')
                const ts = String(raw.ts || raw.time || new Date().toISOString())
                pushEvent(type, raw, ts)
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
                    setEquityPoints(normalizeEquityPoints(points))
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
    }, [robotId, toast, pushEvent, applyTickerScan])

    useEffect(() => {
        setStatusLoaded(false)
        setStatus(null)
        positionsFreshAtRef.current = 0
        scanFreshAtRef.current = 0
        void refresh()
    }, [robotId, refresh])

    const token = useAuthStore(s => s.token)
    const wsUrl = useMemo(() => {
        if (!Number.isFinite(robotId) || !token) return ''
        return robotV2Service.buildStreamUrl(robotId, token)
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
            if (type !== 'positions') {
                pushEvent(type, msg, msg.ts ? String(msg.ts) : undefined)
            }
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
                if (points.length) setEquityPoints(normalizeEquityPoints(points))
                return
            }
            if (type === 'cycle' && typeof msg.equity === 'number') {
                setEquityPoints(prev => appendEquityPoint(prev, Number(msg.equity)))
            }
            if (type === 'cycle' && Array.isArray(msg.tickerScan)) {
                const at = msg.ts ? String(msg.ts) : new Date().toISOString()
                applyTickerScan(
                    msg.tickerScan as RobotV2TickerScan[],
                    at,
                    scanStampMs(at, msg.ts) || Date.now(),
                )
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
                        msg.tickerScan as RobotV2TickerScan[],
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

    const onStart = async () => {
        setBusy(true)
        try {
            const mode = String((robot?.config?.core as Record<string, unknown> | undefined)?.mode || 'paper')
            if (mode === 'live') {
                await robotV2Service.start(robotId, {})
            } else {
                const risk = (robot?.config?.risk || {}) as Record<string, unknown>
                await robotV2Service.start(robotId, { virtualCapital: Number(risk.capital || 100_000) })
            }
            toast.show('Запущен', 'success')
            await refresh()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusy(false)
        }
    }

    const onStop = async (mode: 'soft' | 'hard') => {
        if (mode === 'hard') {
            setHardStopOpen(true)
            return
        }
        setBusy(true)
        try {
            await robotV2Service.stop(robotId, mode)
            toast.show('Мягкая остановка', 'info')
            await refresh()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusy(false)
        }
    }

    const onHardStopConfirm = async () => {
        setBusy(true)
        try {
            await robotV2Service.stop(robotId, 'hard')
            toast.show('Жёсткая остановка', 'info')
            setHardStopOpen(false)
            await refresh()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusy(false)
        }
    }

    const onRefreshUniverse = async () => {
        setUniverseBusy(true)
        try {
            const res = await robotV2Service.refreshUniverse(robotId)
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

    const sessionStateRaw = pick(status || ({} as RobotV2Status), 'sessionState', 'session_state')
    const sessionState = statusLoaded
        ? (sessionStateRaw ? String(sessionStateRaw) : 'IDLE')
        : '…'
    const sessionUpper = String(sessionStateRaw || '').toUpperCase()
    const equityRaw = pick<number>(status || ({} as RobotV2Status), 'equity', 'equity')
    const cashRaw = pick<number>(status || ({} as RobotV2Status), 'cash', 'cash')
    const equity = isFiniteBalance(equityRaw) ? Number(equityRaw) : null
    const cash = isFiniteBalance(cashRaw) ? Number(cashRaw) : null
    const balanceSource = parseBalanceSource(
        pick(status || ({} as RobotV2Status), 'balanceSource', 'balance_source'),
    )
    const balanceAsOf = pick<string>(status || ({} as RobotV2Status), 'balanceAsOf', 'balance_as_of')
    const statusMode = pick<string>(status || ({} as RobotV2Status), 'mode', 'mode')
        || String((robot?.config?.core as Record<string, unknown> | undefined)?.mode || '')
    const cycle = pick<number>(status || ({} as RobotV2Status), 'cycleNumber', 'cycle_number') ?? 0
    const statusMessage = pick<string>(status || ({} as RobotV2Status), 'message', 'message')
    const bootstrapReady = Boolean(
        pick<boolean>(status || ({} as RobotV2Status), 'bootstrapReady', 'bootstrap_ready'),
    )
    const isRunning = sessionUpper === 'RUNNING' || sessionUpper === 'BOOTSTRAP'
    const isStopping = sessionUpper === 'STOPPING'
    const isActive = isRunning || isStopping
    const isError = sessionUpper === 'ERROR'
    const statusStage = pick<string>(status || ({} as RobotV2Status), 'cycleStage', 'cycle_stage')
    const stageLower = String(liveStage?.stage || statusStage || '').toLowerCase()
    const isSyncing =
        statusLoaded
        && (
            sessionUpper === 'BOOTSTRAP'
            || (sessionUpper === 'RUNNING' && !bootstrapReady)
            || (isActive && (stageLower === 'bootstrap' || stageLower === 'bootstrap_sync'))
        )
    const showSessionOps = statusLoaded && isActive && !isSyncing
    const showBalance = statusLoaded && (equity != null || cash != null)
    const balanceLabels = balanceTileLabels(balanceSource, statusMode)
    const balanceFootnote = showBalance ? balanceFootnoteText(balanceSource, statusMode) : null
    const balanceAsOfLabel = showBalance ? formatBalanceAsOfLabel(balanceAsOf) : null
    const isLiveMode = String(statusMode || '').toLowerCase() === 'live'
    /** Live idle/fail with null balances → honesty line; paper never-capitalized → omit strip */
    const showBalanceUnavailable = statusLoaded && !showBalance && isLiveMode
    const universeCfg = (robot?.config?.universe || {}) as Record<string, unknown>
    const universeMode = String(universeCfg.mode || '')
    const canRefreshUniverse = isActive && !isSyncing && (universeMode === 'screener' || universeMode === 'index')
    const positionsRaw = pick<Array<Record<string, unknown>>>(status || ({} as RobotV2Status), 'openPositions', 'open_positions') || []
    const positions = useMemo(
        () => sortByTickerName(positionsRaw, positionTicker),
        [positionsRaw],
    )
    const liveOrders = pick<Array<Record<string, unknown>>>(status || ({} as RobotV2Status), 'openOrders', 'open_orders') || []
    const orderRows = useMemo(
        () => mergeLiveRoundTrips(roundTrips, liveOrders),
        [roundTrips, liveOrders],
    )
    const openOrderCount = useMemo(
        () => orderRows.filter(r => ['open', 'resting'].includes(String(r.status).toLowerCase())).length,
        [orderRows],
    )
    const dayStats = useMemo(() => computeDayTradeStats(roundTrips), [roundTrips])
    const dayPlus = fmtNetPnl(dayStats.sumPlus)
    const dayMinus = fmtNetPnl(dayStats.sumMinus)
    const dayDelta = fmtNetPnl(dayStats.delta)
    const dayLabel = useMemo(() => {
        const [, m, d] = dayStats.dayKey.split('-')
        if (!m || !d) return 'сегодня'
        return `${d}.${m}`
    }, [dayStats.dayKey])
    const orderDisplayRows = useMemo(
        () => orderRows.map(toOrderDisplayRow),
        [orderRows],
    )
    const decisions = pick<Array<Record<string, unknown>>>(status || ({} as RobotV2Status), 'decisions', 'decisions') || []
    const universeRaw = pick<string[]>(status || ({} as RobotV2Status), 'universe', 'universe') || []
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
            return {
                id: String(row.ticker ?? row.secid ?? row.figi ?? i),
                tickerLabel: String(row.ticker ?? row.figi ?? '—'),
                tickerWarning: positionTickerWarning(row),
                side: String(row.side ?? '—'),
                quantity: String(row.quantity ?? '—'),
                entry: posPrice(row, 'entry_price', 'entryPrice', 'avg_entry_price', 'avgEntryPrice'),
                breakEven: posPrice(row, 'break_even_price', 'breakEvenPrice'),
                current: posPrice(row, 'current_price', 'currentPrice'),
                sl: posPrice(row, 'stop_loss_price', 'stopLossPrice'),
                tp: posPrice(row, 'take_profit_price', 'takeProfitPrice'),
            }
        }),
        [positions],
    )
    const displayUniverse = useMemo(
        () => sortByTickerName(universe, t => t),
        [universe],
    )
    const positionsUpdatedAt = pick<string>(status || ({} as RobotV2Status), 'positionsUpdatedAt', 'positions_updated_at')
        || pick<string>(status || ({} as RobotV2Status), 'lastCycleAt', 'last_cycle_at')
    const title = (robot?.name || `РОБОТ #${robotId}`).toUpperCase()

    const heroBadge = (() => {
        if (!statusLoaded) return { label: '…', variant: 'neutral' as const }
        if (isError) return { label: 'Ошибка', variant: 'down' as const }
        if (isSyncing) return { label: 'Синхронизация', variant: 'cyan' as const }
        if (sessionUpper === 'BOOTSTRAP') return { label: 'Синхронизация', variant: 'cyan' as const }
        if (sessionUpper === 'RUNNING') return { label: 'В работе', variant: 'up' as const }
        if (isStopping) return { label: 'Остановка', variant: 'neutral' as const }
        return { label: sessionStateLabel(sessionState), variant: 'neutral' as const }
    })()

    const statusProgress = pick<number>(status || ({} as RobotV2Status), 'cycleProgress', 'cycle_progress')
    const statusDetail = pick<string>(status || ({} as RobotV2Status), 'cycleDetail', 'cycle_detail')
    const statusSkip = pick<string>(status || ({} as RobotV2Status), 'cycleSkipReason', 'cycle_skip_reason')
    const statusTriggered = pick<string>(status || ({} as RobotV2Status), 'lastTriggeredBy', 'last_triggered_by')
    const stageKey = liveStage?.stage || statusStage || (isRunning ? 'idle' : '—')
    const stageText = liveStage?.label || stageLabel(stageKey === '—' ? null : stageKey)
    const stageProgress = Math.max(
        0,
        Math.min(1, Number(liveStage?.progress ?? statusProgress ?? (stageKey === 'done' || stageKey === 'skipped' ? 1 : 0))),
    )
    const stageDetailRaw = liveStage?.detail ?? statusDetail ?? null
    const stageDetailText = stageDetailLabel(stageDetailRaw)
    const skipReason = liveStage?.skipReason ?? statusSkip ?? null
    const triggeredBy = liveStage?.triggeredBy ?? statusTriggered ?? null
    const archetype = String((robot?.config?.strategy as Record<string, unknown> | undefined)?.archetype || '')

    return (
        <div className="page" data-page="robots">
            <RobotPageChrome
                eyebrow="LIVE NODE"
                title={title}
                robotId={robotId}
                active="monitor"
                subtitle={
                    <p className="dashboard-hero__sub robots-v2-hero-sub">
                        Монитор · сессия {sessionStateLabel(sessionState)}{' '}
                        <Badge variant={heroBadge.variant}>{heroBadge.label}</Badge>
                        {statusMessage ? ` · ${statusMessage}` : ''}
                        {streamConnected ? ' · online' : ''}
                    </p>
                }
                actions={
                    !statusLoaded ? (
                        <Button type="button" size="sm" loading disabled>
                            Статус…
                        </Button>
                    ) : isActive ? (
                        <>
                            <Button
                                type="button"
                                variant="secondary"
                                size="sm"
                                loading={busy}
                                disabled={isStopping}
                                onClick={() => void onStop('soft')}
                            >
                                Мягкая остановка
                            </Button>
                            <Button
                                type="button"
                                variant="danger"
                                size="sm"
                                loading={busy}
                                disabled={isStopping}
                                onClick={() => void onStop('hard')}
                            >
                                Жёсткая остановка
                            </Button>
                        </>
                    ) : (
                        <Button type="button" size="sm" loading={busy} onClick={() => void onStart()}>
                            Запуск
                        </Button>
                    )
                }
            />

            <div className="dashboard-layout">
                <MonitorSummaryCard
                    dayLabel={dayLabel}
                    statusLoaded={statusLoaded}
                    dayTrades={dayStats.trades}
                    dayPlus={dayPlus}
                    dayMinus={dayMinus}
                    dayDelta={dayDelta}
                    showBalance={showBalance}
                    equityLabel={equity != null ? fmtNum(equity, 0) : null}
                    cashLabel={cash != null ? fmtNum(cash, 0) : null}
                    equityTileLabel={balanceLabels.equity}
                    cashTileLabel={balanceLabels.cash}
                    balanceFootnote={balanceFootnote}
                    balanceAsOfLabel={balanceAsOfLabel}
                    showBalanceUnavailable={showBalanceUnavailable}
                    showSessionOps={showSessionOps}
                    isSyncing={isSyncing}
                    cycle={cycle}
                    positionsCount={positions.length}
                />

                <RobotStageCard
                    title="Текущий этап"
                    progress={stageProgress}
                    badge={stageText}
                    badgeVariant={stageKey === 'skipped' ? 'down' : isRunning ? 'cyan' : 'neutral'}
                    ariaLabel="Прогресс этапа цикла"
                    meta={
                        <>
                            <span>{Math.round(stageProgress * 100)}%</span>
                            {stageDetailText ? (
                                <span className="mono robots-v2-stage-detail">{stageDetailText}</span>
                            ) : null}
                            {triggeredBy ? <span className="mono">wake: {triggeredBy}</span> : null}
                            {archetype ? <span className="mono">{archetype}</span> : null}
                            {skipReason ? (
                                <span className="robots-v2-stage-skip">
                                    {SKIP_LABELS[skipReason] || skipReason}
                                </span>
                            ) : null}
                        </>
                    }
                />

                <div className="robots-v2-monitor-grid">
                    <MonitorEquityChart
                        onReady={chart => {
                            if (!chart) {
                                chartRef.current = null
                                seriesRef.current = null
                                return
                            }
                            chartRef.current = chart
                            const series = chart.addSeries(LineSeries, {
                                color: '#3dd68c',
                                lineWidth: 2,
                            })
                            seriesRef.current = series
                            if (equityPoints.length) series.setData(equityPoints)
                        }}
                    />

                    <MonitorOrdersCard rows={orderDisplayRows} openOrderCount={openOrderCount} />

                    <MonitorPositionsCard
                        rows={positionTableRows}
                        positionsCount={positions.length}
                        positionsUpdatedAt={positionsUpdatedAt}
                        brokerSoftStopHint={
                            !isRunning
                            && pick<string>(status || ({} as RobotV2Status), 'positionsSource', 'positions_source') === 'broker'
                            && positions.length > 0
                        }
                        isRunning={isRunning}
                    />

                    <MonitorUniverseCard
                        displayTickerScan={displayTickerScan}
                        displayUniverse={displayUniverse}
                        tickerScanAt={tickerScanAt}
                        canRefreshUniverse={canRefreshUniverse}
                        universeBusy={universeBusy}
                        onRefreshUniverse={() => void onRefreshUniverse()}
                    />

                    <MonitorDecisionsCard decisions={decisions} />

                    <MonitorEventsCard
                        events={events}
                        streamConnected={streamConnected}
                        isRunning={isRunning}
                        hasToken={Boolean(token)}
                    />
                </div>
            </div>

            <RobotConfirmModal
                open={hardStopOpen}
                onClose={() => setHardStopOpen(false)}
                onConfirm={() => void onHardStopConfirm()}
                title="Жёсткая остановка"
                message={
                    String((robot?.config?.core as Record<string, unknown> | undefined)?.mode || 'paper') === 'live'
                        ? 'Жёсткая остановка закроет все позиции. Продолжить?'
                        : 'Жёсткая остановка сессии. Продолжить?'
                }
                confirmLabel="Остановить"
                loading={busy}
            />
        </div>
    )
}
