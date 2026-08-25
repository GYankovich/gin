import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { Chart } from '@/components/ui/Chart'
import { PageHero } from '@/components/ui/PageHero'
import { StatTile } from '@/components/ui/StatTile'
import { useToast } from '@/components/ui/Toast'
import { Tooltip } from '@/components/ui/Tooltip'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAuthStore } from '@/stores/authStore'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2, RobotV2RoundTrip, RobotV2Status, RobotV2TickerScan } from '@/types/robotV2'
import type { IChartApi, ISeriesApi, Time } from '@/components/ui/Chart'
import { LineSeries } from 'lightweight-charts'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'

function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    return err?.message || 'Ошибка'
}

function pick<T>(obj: RobotV2Status, camel: keyof RobotV2Status, snake: string): T | undefined {
    const anyObj = obj as Record<string, unknown>
    return (obj[camel] ?? anyObj[snake]) as T | undefined
}

function fmtNum(v: number): string {
    return v.toLocaleString('ru-RU', { maximumFractionDigits: 0 })
}

/** Lightweight Charts requires strictly ascending unique unix seconds. */
function normalizeEquityPoints(
    points: Array<{ time: Time; value: number }>,
    max = 200,
): Array<{ time: Time; value: number }> {
    const byTime = new Map<number, number>()
    for (const p of points) {
        const t = typeof p.time === 'number' ? p.time : Number(p.time)
        if (!Number.isFinite(t) || !Number.isFinite(p.value)) continue
        byTime.set(Math.floor(t), p.value)
    }
    return [...byTime.entries()]
        .sort((a, b) => a[0] - b[0])
        .slice(-max)
        .map(([time, value]) => ({ time: time as Time, value }))
}

function appendEquityPoint(
    prev: Array<{ time: Time; value: number }>,
    value: number,
    timeSec?: number,
): Array<{ time: Time; value: number }> {
    const t = Math.floor(timeSec ?? Date.now() / 1000)
    return normalizeEquityPoints([...prev, { time: t as Time, value }])
}

const STAGE_LABELS: Record<string, string> = {
    idle: 'Ожидание',
    prices: 'Цены',
    reconcile: 'Сверка',
    schedule: 'Расписание',
    exits: 'Выходы SL/TP',
    strategy: 'Стратегия',
    risk: 'Риск',
    execution: 'Исполнение',
    metrics: 'Метрики',
    done: 'Цикл завершён',
    skipped: 'Пропуск',
    bootstrap: 'Bootstrap',
    bootstrap_sync: 'Синхронизация',
}

const SKIP_LABELS: Record<string, string> = {
    OUTSIDE_SESSION: 'Вне торговой сессии',
    EOD_HOLD: 'EOD hold',
    RECONCILE_FAILED: 'Сверка с брокером не удалась',
    NO_PRICES: 'Нет цен',
    BOOTSTRAP_SYNC: 'Синхронизация при старте',
}

const SCAN_CODE_VARIANT: Record<string, 'up' | 'down' | 'warn' | 'cyan' | 'neutral'> = {
    SIGNAL: 'up',
    EXIT_SIGNAL: 'warn',
    EXIT_BLOCKED: 'warn',
    IN_POSITION: 'cyan',
    WARMUP: 'neutral',
    NO_DATA: 'down',
    NO_PRICE: 'down',
    NO_INDICATORS: 'down',
    WRONG_TRIGGER: 'neutral',
    BELOW_MA: 'neutral',
    BELOW_BREAKOUT: 'neutral',
    LOW_VOLUME: 'neutral',
    NO_ENTRY: 'neutral',
    DELTA_BELOW_THRESHOLD: 'neutral',
    LOW_LIQUIDITY: 'neutral',
    NO_ORDER_FLOW: 'down',
    COOLDOWN: 'neutral',
    SL_COOLDOWN: 'warn',
    OUTSIDE_SESSION: 'down',
    EOD_HOLD: 'down',
    UNIVERSE_REFRESH: 'cyan',
    RECONCILE_FAILED: 'down',
    NO_PRICES: 'down',
}

function stageLabel(stage: string | null | undefined): string {
    if (!stage) return '—'
    return STAGE_LABELS[stage] || stage
}

function stageDetailLabel(detail: string | null | undefined): string | null {
    if (!detail) return null
    const d = detail.trim()
    const atr = /^atr_warmup\s+(\d+)\/(\d+)(?:\s+(\S+))?/i.exec(d)
    if (atr) {
        const [, cur, tot, ticker] = atr
        const tail = ticker ? ` · ${ticker}` : ''
        return `ATR-кэш ${cur}/${tot}${tail}`
    }
    if (d === 'moex_snapshot') return 'Снимок MOEX'
    if (d === 'screener_filters') return 'Фильтры screener'
    if (d.startsWith('universe_retry_')) return `Повтор universe (${d.replace('universe_retry_', '')})`
    if (d === 'universe_ok') return 'Universe готов'
    if (d.includes('seed') || d.includes('candle')) return 'Загрузка свечей'
    if (d.includes('reconcil')) return 'Сверка с брокером'
    if (d.startsWith('attempt=')) return `Синхронизация (${d.replace('attempt=', 'попытка ')})`
    return d
}

function fmtPrice(v: unknown): string {
    const n = Number(v)
    if (!Number.isFinite(n) || n <= 0) return '—'
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}

function orderStatusLabel(status: string): string {
    switch (String(status || '').toLowerCase()) {
        case 'closed':
            return 'Закрыта'
        case 'open':
            return 'Открыта'
        case 'resting':
            return 'В рынке'
        case 'filled':
            return 'Исполнено'
        case 'cancelled':
        case 'canceled':
            return 'Отменена'
        case 'rejected':
            return 'Отклонена'
        default:
            return status || '—'
    }
}

function posPrice(p: Record<string, unknown>, ...keys: string[]): string {
    for (const k of keys) {
        const v = p[k]
        if (v != null && Number.isFinite(Number(v))) return fmtPrice(v)
    }
    return '—'
}

function positionTickerWarning(row: Record<string, unknown>): string {
    const raw = row.tickerWarning ?? row.ticker_warning
    return typeof raw === 'string' && raw.trim() ? raw.trim() : ''
}

function TickerWarningMark({ text }: { text: string }) {
    return (
        <Tooltip text={text} className="robots-v2-ticker-warn">
            <svg
                className="robots-v2-ticker-warn__icon"
                viewBox="0 0 16 16"
                width="14"
                height="14"
                aria-hidden
            >
                <path
                    d="M8 1.4 15 14.2H1L8 1.4Z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.4"
                    strokeLinejoin="round"
                />
                <path d="M8 6.2v3.4" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                <circle cx="8" cy="11.6" r="0.7" fill="currentColor" />
            </svg>
        </Tooltip>
    )
}

function positionsStampMs(updatedAt: unknown, fallbackTs?: unknown): number {
    const raw = updatedAt != null ? String(updatedAt) : (fallbackTs != null ? String(fallbackTs) : '')
    const ms = raw ? Date.parse(raw) : NaN
    return Number.isFinite(ms) ? ms : 0
}

function pickOpenPositions(msg: Record<string, unknown>): Array<Record<string, unknown>> | null {
    const rows = msg.openPositions ?? msg.open_positions
    if (!Array.isArray(rows)) return null
    return rows as Array<Record<string, unknown>>
}

function fmtPriceQty(price: unknown, qty: unknown): string {
    const px = fmtPrice(price)
    const q = Number(qty)
    if (px === '—') return '—'
    if (!Number.isFinite(q) || q <= 0) return px
    return `${px} (${q % 1 === 0 ? q.toLocaleString('ru-RU') : q.toLocaleString('ru-RU', { maximumFractionDigits: 4 })})`
}

function fmtTime(ts: string | null | undefined): string {
    if (!ts) return '—'
    const d = new Date(ts)
    if (!Number.isFinite(d.getTime())) return '—'
    return d.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    })
}

function fmtNetPnl(value: unknown): { text: string; tone: 'up' | 'down' | 'neutral' } {
    const n = Number(value)
    if (!Number.isFinite(n)) return { text: '—', tone: 'neutral' }
    const text = `${n.toLocaleString('ru-RU', { maximumFractionDigits: 2, signDisplay: 'exceptZero' })} ₽`
    if (n > 0) return { text, tone: 'up' }
    if (n < 0) return { text, tone: 'down' }
    return { text: '0 ₽', tone: 'neutral' }
}

function pickRoundTripField<T>(
    row: RobotV2RoundTrip,
    camel: keyof RobotV2RoundTrip,
    snake: string,
): T | undefined {
    const anyRow = row as Record<string, unknown>
    return (row[camel] ?? anyRow[snake]) as T | undefined
}

function mergeLiveRoundTrips(
    trips: RobotV2RoundTrip[],
    liveOrders: Array<Record<string, unknown>>,
): RobotV2RoundTrip[] {
    const out = trips.map(t => ({ ...t }))
    for (const o of liveOrders) {
        const side = String(o.side || '').toUpperCase()
        if (side !== 'SELL') continue
        const status = String(o.status || '').toLowerCase()
        if (status !== 'resting' && status !== 'submitted' && status !== 'new') continue
        const ticker = String(o.ticker || '').toUpperCase()
        if (!ticker) continue
        const listed = o.price != null ? Number(o.price) : null
        const qty = Number(o.quantity || 0)
        const openIdx = out.findIndex(
            t => String(t.ticker).toUpperCase() === ticker && String(t.status).toLowerCase() === 'open',
        )
        if (openIdx >= 0) {
            out[openIdx] = {
                ...out[openIdx],
                status: 'resting',
                sellListedPrice: listed,
                sellQty: qty > 0 ? qty : out[openIdx].sellQty,
            }
            continue
        }
        out.unshift({
            id: `live-${String(o.brokerOrderId || o.broker_order_id || ticker)}`,
            ticker,
            buyAt: null,
            buyPrice: (o.entryPrice ?? o.entry_price ?? null) as number | null,
            buyQty: qty > 0 ? qty : null,
            sellAt: null,
            sellListedPrice: listed,
            sellFillPrice: null,
            sellQty: qty > 0 ? qty : null,
            status: 'resting',
            reason: String(o.kind || o.reason || 'exit_sl_tp'),
        })
    }
    return out
}

type OrdersSortKey = 'ticker' | 'date' | 'status' | 'pocket'

const ORDERS_SORT_DEFAULT_DIR: Record<OrdersSortKey, 'asc' | 'desc'> = {
    ticker: 'asc',
    date: 'desc',
    status: 'asc',
    pocket: 'desc',
}

const ORDERS_STATUS_RANK: Record<string, number> = {
    resting: 0,
    open: 1,
    filled: 2,
    closed: 3,
    cancelled: 4,
    canceled: 4,
    rejected: 5,
}

function tripDateMs(row: RobotV2RoundTrip): number | null {
    const buyAt = pickRoundTripField<string | null>(row, 'buyAt', 'buy_at')
    const sellAt = pickRoundTripField<string | null>(row, 'sellAt', 'sell_at')
    const raw = buyAt || sellAt
    if (!raw) {
        return String(row.id).startsWith('live-') ? Date.now() : null
    }
    const ms = Date.parse(String(raw))
    return Number.isFinite(ms) ? ms : null
}

function tripPocketValue(row: RobotV2RoundTrip): number | null {
    const n = Number(pickRoundTripField<number | null>(row, 'netPnl', 'net_pnl'))
    return Number.isFinite(n) ? n : null
}

function compareNullableNumber(a: number | null, b: number | null, dir: 'asc' | 'desc' = 'asc'): number {
    if (a == null && b == null) return 0
    if (a == null) return 1
    if (b == null) return -1
    const cmp = a < b ? -1 : a > b ? 1 : 0
    return dir === 'asc' ? cmp : -cmp
}

function compareOrderRows(a: RobotV2RoundTrip, b: RobotV2RoundTrip, key: OrdersSortKey): number {
    if (key === 'ticker') {
        return String(a.ticker || '').localeCompare(String(b.ticker || ''), 'en', { sensitivity: 'base' })
    }
    if (key === 'date') {
        return compareNullableNumber(tripDateMs(a), tripDateMs(b))
    }
    if (key === 'status') {
        const ra = ORDERS_STATUS_RANK[String(a.status || '').toLowerCase()] ?? 99
        const rb = ORDERS_STATUS_RANK[String(b.status || '').toLowerCase()] ?? 99
        if (ra !== rb) return ra - rb
        return orderStatusLabel(a.status).localeCompare(orderStatusLabel(b.status), 'ru')
    }
    return compareNullableNumber(tripPocketValue(a), tripPocketValue(b))
}

function OrdersSortTh({
    label,
    col,
    sortKey,
    sortDir,
    onSort,
}: {
    label: string
    col: OrdersSortKey
    sortKey: OrdersSortKey
    sortDir: 'asc' | 'desc'
    onSort: (col: OrdersSortKey) => void
}) {
    const active = sortKey === col
    return (
        <th
            className="robots-v2-table__th--sortable"
            aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
            onClick={() => onSort(col)}
        >
            <button type="button" className="robots-v2-table__sort-btn">
                {label}
                {active ? (
                    <span className="robots-v2-table__sort-arrow" aria-hidden="true">
                        {sortDir === 'asc' ? ' ↑' : ' ↓'}
                    </span>
                ) : null}
            </button>
        </th>
    )
}

const COOLDOWN_SCAN_CODES = new Set(['COOLDOWN', 'SL_COOLDOWN'])

function positionTicker(p: Record<string, unknown>): string {
    return String(p.secid || p.ticker || p.figi || '').toUpperCase()
}

/** Tickers with a recent trade in audit, open position, or live order. */
function collectAuditTradeTickers(
    roundTrips: RobotV2RoundTrip[],
    positions: Array<Record<string, unknown>>,
    liveOrders: Array<Record<string, unknown>>,
): Set<string> {
    const tickers = new Set<string>()
    for (const trip of roundTrips) {
        const t = String(trip.ticker || '').toUpperCase()
        if (!t) continue
        const buyAt = pickRoundTripField<string | null>(trip, 'buyAt', 'buy_at')
        const sellAt = pickRoundTripField<string | null>(trip, 'sellAt', 'sell_at')
        if (buyAt || sellAt) tickers.add(t)
    }
    for (const p of positions) {
        const t = positionTicker(p)
        if (t) tickers.add(t)
    }
    for (const o of liveOrders) {
        const t = String(o.ticker || '').toUpperCase()
        if (t) tickers.add(t)
    }
    return tickers
}

/** Hide strategy cooldown in scan unless the ticker has audit-backed activity. */
function filterScanCooldownRows(
    scan: RobotV2TickerScan[],
    auditTickers: Set<string>,
): RobotV2TickerScan[] {
    return scan.map(row => {
        const code = String(row.code || '')
        const ticker = String(row.ticker || '').toUpperCase()
        if (!COOLDOWN_SCAN_CODES.has(code) || auditTickers.has(ticker)) {
            return row
        }
        return {
            ...row,
            code: 'NO_ENTRY',
            message: 'Ожидание сигнала',
        }
    })
}

function heldTickersFromPositions(positions: Array<Record<string, unknown>>): Set<string> {
    const held = new Set<string>()
    for (const p of positions) {
        const t = positionTicker(p)
        if (t) held.add(t)
    }
    return held
}

/** Open positions first, then alphabetically by ticker name. */
function sortHeldThenName<T>(
    items: T[],
    getTicker: (item: T) => string,
    held: Set<string>,
): T[] {
    return [...items].sort((a, b) => {
        const ta = String(getTicker(a) || '').toUpperCase()
        const tb = String(getTicker(b) || '').toUpperCase()
        const ha = held.has(ta) ? 0 : 1
        const hb = held.has(tb) ? 0 : 1
        if (ha !== hb) return ha - hb
        return ta.localeCompare(tb, 'en')
    })
}

export default function RobotV2MonitorPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const navigate = useNavigate()
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
    const [ordersSortKey, setOrdersSortKey] = useState<OrdersSortKey>('date')
    const [ordersSortDir, setOrdersSortDir] = useState<'asc' | 'desc'>('desc')
    const [busy, setBusy] = useState(false)
    const [universeBusy, setUniverseBusy] = useState(false)
    const seenEventKeys = useRef(new Set<string>())
    const positionsFreshAtRef = useRef(0)

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
                robotV2Service.fetchAudit({ robotId, limit: 50, types: ['roundTrips'] }).catch(() => ({
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
            if (Array.isArray(scan)) {
                setTickerScan(scan)
            }
            const scanAt = pick<string>(s, 'tickerScanAt', 'ticker_scan_at')
            if (scanAt) setTickerScanAt(scanAt)
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
    }, [robotId, toast, pushEvent])

    useEffect(() => {
        setStatusLoaded(false)
        setStatus(null)
        positionsFreshAtRef.current = 0
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
                setTickerScan(msg.tickerScan as RobotV2TickerScan[])
                setTickerScanAt(msg.ts ? String(msg.ts) : new Date().toISOString())
            }
            if (type === 'universe') {
                const uni = Array.isArray(msg.universe) ? (msg.universe as string[]) : null
                if (uni) {
                    setStatus(prev => prev ? { ...prev, universe: uni } : prev)
                }
                if (Array.isArray(msg.tickerScan)) {
                    setTickerScan(msg.tickerScan as RobotV2TickerScan[])
                    const at = msg.refreshedAt != null ? String(msg.refreshedAt) : (msg.ts ? String(msg.ts) : new Date().toISOString())
                    setTickerScanAt(at)
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
        setBusy(true)
        try {
            await robotV2Service.stop(robotId, mode)
            toast.show(mode === 'hard' ? 'Жёсткая остановка' : 'Мягкая остановка', 'info')
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
                setTickerScan(res.tickerScan)
                if (res.refreshedAt) setTickerScanAt(res.refreshedAt)
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
    const equity = pick<number>(status || ({} as RobotV2Status), 'equity', 'equity') ?? 0
    const cash = pick<number>(status || ({} as RobotV2Status), 'cash', 'cash') ?? 0
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
    const showSessionStats = statusLoaded && isActive && !isSyncing
    const universeCfg = (robot?.config?.universe || {}) as Record<string, unknown>
    const universeMode = String(universeCfg.mode || '')
    const canRefreshUniverse = isActive && !isSyncing && (universeMode === 'screener' || universeMode === 'index')
    const positions = pick<Array<Record<string, unknown>>>(status || ({} as RobotV2Status), 'openPositions', 'open_positions') || []
    const liveOrders = pick<Array<Record<string, unknown>>>(status || ({} as RobotV2Status), 'openOrders', 'open_orders') || []
    const orderRows = useMemo(
        () => mergeLiveRoundTrips(roundTrips, liveOrders),
        [roundTrips, liveOrders],
    )
    const openOrderCount = useMemo(
        () => orderRows.filter(r => ['open', 'resting'].includes(String(r.status).toLowerCase())).length,
        [orderRows],
    )
    const sortedOrderRows = useMemo(() => {
        return [...orderRows].sort((a, b) => {
            let cmp = 0
            if (ordersSortKey === 'date') {
                cmp = compareNullableNumber(tripDateMs(a), tripDateMs(b), ordersSortDir)
            } else if (ordersSortKey === 'pocket') {
                cmp = compareNullableNumber(tripPocketValue(a), tripPocketValue(b), ordersSortDir)
            } else {
                const raw = compareOrderRows(a, b, ordersSortKey)
                cmp = ordersSortDir === 'asc' ? raw : -raw
            }
            if (cmp !== 0) return cmp
            const dateCmp = compareNullableNumber(tripDateMs(a), tripDateMs(b), 'desc')
            if (dateCmp !== 0) return dateCmp
            return compareOrderRows(a, b, 'ticker')
        })
    }, [orderRows, ordersSortKey, ordersSortDir])
    const toggleOrdersSort = (key: OrdersSortKey) => {
        if (ordersSortKey === key) {
            setOrdersSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
            return
        }
        setOrdersSortKey(key)
        setOrdersSortDir(ORDERS_SORT_DEFAULT_DIR[key])
    }
    const decisions = pick<Array<Record<string, unknown>>>(status || ({} as RobotV2Status), 'decisions', 'decisions') || []
    const universe = pick<string[]>(status || ({} as RobotV2Status), 'universe', 'universe') || []
    const auditTradeTickers = useMemo(
        () => collectAuditTradeTickers(roundTrips, positions, liveOrders),
        [roundTrips, positions, liveOrders],
    )
    const heldTickers = useMemo(() => heldTickersFromPositions(positions), [positions])
    const displayTickerScan = useMemo(
        () => sortHeldThenName(
            filterScanCooldownRows(tickerScan, auditTradeTickers),
            row => row.ticker,
            heldTickers,
        ),
        [tickerScan, auditTradeTickers, heldTickers],
    )
    const displayUniverse = useMemo(
        () => sortHeldThenName(universe, t => t, heldTickers),
        [universe, heldTickers],
    )
    const positionsUpdatedAt = pick<string>(status || ({} as RobotV2Status), 'positionsUpdatedAt', 'positions_updated_at')
        || pick<string>(status || ({} as RobotV2Status), 'lastCycleAt', 'last_cycle_at')
    const title = (robot?.name || `РОБОТ #${robotId}`).toUpperCase()

    const heroBadge = (() => {
        if (!statusLoaded) return { label: '…', variant: 'neutral' as const }
        if (isError) return { label: 'ERROR', variant: 'down' as const }
        if (isSyncing) return { label: 'SYNC', variant: 'cyan' as const }
        if (sessionUpper === 'BOOTSTRAP') return { label: 'BOOTSTRAP', variant: 'cyan' as const }
        if (sessionUpper === 'RUNNING') return { label: 'RUNNING', variant: 'up' as const }
        if (isStopping) return { label: 'STOPPING', variant: 'neutral' as const }
        return { label: 'IDLE', variant: 'neutral' as const }
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
        <div className="page" data-page="robots-v2">
            <PageHero
                eyebrow="LIVE NODE"
                title={title}
                subtitle={
                    <p className="dashboard-hero__sub robots-v2-hero-sub">
                        Monitor · session {sessionState}{' '}
                        <Badge variant={heroBadge.variant}>{heroBadge.label}</Badge>
                        {statusMessage ? ` · ${statusMessage}` : ''}
                        {streamConnected ? ' · live' : ''}
                    </p>
                }
                actions={
                    <>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate('/robots-v2')}
                        >
                            Флот
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate(`/robots-v2/edit/${robotId}`)}
                        >
                            Правка
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate(`/robots-v2/${robotId}/logs`)}
                        >
                            Логи
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate(`/robots-v2/${robotId}/backtest`)}
                        >
                            Бэктест
                        </Button>
                        {!statusLoaded ? (
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
                        )}
                    </>
                }
            />

            <div className="dashboard-layout">
                <Card className="dashboard-totals-card">
                    <div className="dashboard-totals-card__head">
                        <h3 className="dashboard-panel-title">Сводка сессии</h3>
                    </div>
                    {showSessionStats ? (
                        <div className="portfolio-stats-grid dashboard-summary-grid">
                            <StatTile label="Equity" value={fmtNum(equity)} />
                            <StatTile label="Cash" value={fmtNum(cash)} />
                            <StatTile label="Cycle" value={cycle} />
                            <StatTile label="Позиции" value={positions.length} />
                        </div>
                    ) : (
                        <p className="dashboard-empty robots-v2-session-placeholder">
                            {isSyncing ? 'Робот синхронизируется' : 'Робот не работает'}
                        </p>
                    )}
                </Card>

                <Card className="dashboard-totals-card robots-v2-stage-card">
                    <div className="dashboard-totals-card__head robots-v2-stage-card__head">
                        <h3 className="dashboard-panel-title">Текущий этап</h3>
                        <Badge variant={stageKey === 'skipped' ? 'down' : isRunning ? 'cyan' : 'neutral'}>
                            {stageText}
                        </Badge>
                    </div>
                    <div className="robots-v2-stage-progress" aria-label="Прогресс этапа цикла">
                        <div
                            className="robots-v2-stage-progress__bar"
                            style={{ width: `${Math.round(stageProgress * 100)}%` }}
                        />
                    </div>
                    <div className="robots-v2-stage-meta">
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
                    </div>
                </Card>

                <div className="robots-v2-monitor-grid">
                    <Card className="dashboard-assets-card robots-v2-monitor-chart">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">График equity</h3>
                        </div>
                        <Chart
                            height={280}
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
                    </Card>

                    <Card className="dashboard-assets-card robots-v2-monitor-orders">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Заявки</h3>
                            {orderRows.length > 0 ? (
                                <span className="robots-v2-hint">
                                    {openOrderCount > 0 ? `${openOrderCount} открытых · ` : ''}
                                    {orderRows.length}
                                </span>
                            ) : null}
                        </div>
                        <p className="robots-v2-hint robots-v2-universe-caption">
                            Сделки: покупка → продажа. «Цена продажи выставленная» — лимит TP; «факт» — исполнение.
                        </p>
                        {orderRows.length === 0 ? (
                            <p className="dashboard-empty">Пока нет сделок</p>
                        ) : (
                            <div className="robots-v2-scan-table-wrap robots-v2-orders-table-wrap">
                                <table className="robots-v2-table robots-v2-scan-table">
                                    <thead>
                                        <tr>
                                            <OrdersSortTh
                                                label="Тикер"
                                                col="ticker"
                                                sortKey={ordersSortKey}
                                                sortDir={ordersSortDir}
                                                onSort={toggleOrdersSort}
                                            />
                                            <OrdersSortTh
                                                label="Время покупки"
                                                col="date"
                                                sortKey={ordersSortKey}
                                                sortDir={ordersSortDir}
                                                onSort={toggleOrdersSort}
                                            />
                                            <th>Цена покупки</th>
                                            <th>Время продажи</th>
                                            <th>Цена продажи выст.</th>
                                            <th>Цена продажи факт</th>
                                            <OrdersSortTh
                                                label="Статус"
                                                col="status"
                                                sortKey={ordersSortKey}
                                                sortDir={ordersSortDir}
                                                onSort={toggleOrdersSort}
                                            />
                                            <OrdersSortTh
                                                label="В карман"
                                                col="pocket"
                                                sortKey={ordersSortKey}
                                                sortDir={ordersSortDir}
                                                onSort={toggleOrdersSort}
                                            />
                                            <th>Причина</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {sortedOrderRows.map(row => {
                                                const buyAt = pickRoundTripField<string | null>(row, 'buyAt', 'buy_at')
                                                const buyPrice = pickRoundTripField<number | null>(row, 'buyPrice', 'buy_price')
                                                const buyQty = pickRoundTripField<number | null>(row, 'buyQty', 'buy_qty')
                                                const sellAt = pickRoundTripField<string | null>(row, 'sellAt', 'sell_at')
                                                const sellListed = pickRoundTripField<number | null>(
                                                    row,
                                                    'sellListedPrice',
                                                    'sell_listed_price',
                                                )
                                                const sellFill = pickRoundTripField<number | null>(
                                                    row,
                                                    'sellFillPrice',
                                                    'sell_fill_price',
                                                )
                                                const sellQty = pickRoundTripField<number | null>(row, 'sellQty', 'sell_qty')
                                                const reason = pickRoundTripField<string | null>(row, 'reason', 'reason')
                                                const netPnl = pickRoundTripField<number | null>(row, 'netPnl', 'net_pnl')
                                                const realizedPnl = pickRoundTripField<number | null>(
                                                    row,
                                                    'realizedPnl',
                                                    'realized_pnl',
                                                )
                                                const pocket = fmtNetPnl(netPnl)
                                                const listedLabel = sellListed != null && Number(sellListed) > 0
                                                    ? fmtPrice(sellListed)
                                                    : String(row.status).toLowerCase() === 'resting'
                                                        ? '—'
                                                        : sellFill != null
                                                            ? 'рынок'
                                                            : '—'
                                                return (
                                                    <tr key={row.id}>
                                                        <td><strong>{row.ticker}</strong></td>
                                                        <td className="mono">{fmtTime(buyAt)}</td>
                                                        <td className="mono">{fmtPriceQty(buyPrice, buyQty)}</td>
                                                        <td className="mono">{fmtTime(sellAt)}</td>
                                                        <td className="mono">{listedLabel}</td>
                                                        <td className="mono">{fmtPriceQty(sellFill, sellQty)}</td>
                                                        <td>{orderStatusLabel(row.status)}</td>
                                                        <td
                                                            className={`mono robots-v2-pnl--${pocket.tone}`}
                                                            title={
                                                                realizedPnl != null && Number.isFinite(Number(realizedPnl))
                                                                    ? `До НДФЛ: ${Number(realizedPnl).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽`
                                                                    : undefined
                                                            }
                                                        >
                                                            {pocket.text}
                                                        </td>
                                                        <td>{tradeReasonLabel(reason)}</td>
                                                    </tr>
                                                )
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </Card>

                    <Card className="dashboard-assets-card robots-v2-monitor-positions">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Открытые позиции</h3>
                            {positions.length > 0 ? (
                                <span className="robots-v2-hint">{positions.length}</span>
                            ) : null}
                        </div>
                        {positionsUpdatedAt ? (
                            <p className="robots-v2-hint robots-v2-universe-caption">
                                Данные обновлены
                                <span className="mono">
                                    {' '}
                                    · {new Date(positionsUpdatedAt).toLocaleString('ru-RU', {
                                        day: '2-digit',
                                        month: '2-digit',
                                        hour: '2-digit',
                                        minute: '2-digit',
                                        second: '2-digit',
                                    })}
                                </span>
                            </p>
                        ) : null}
                        {(() => {
                            const src = pick<string>(status || ({} as RobotV2Status), 'positionsSource', 'positions_source')
                            if (!isRunning && src === 'broker' && positions.length > 0) {
                                return (
                                    <p className="robots-v2-hint robots-v2-universe-caption">
                                        Сессия остановлена · позиции с брокера (soft stop их не закрывает).
                                        После Start робот подхватит и продолжит торговать.
                                    </p>
                                )
                            }
                            return null
                        })()}
                        {positions.length === 0 ? (
                            <p className="dashboard-empty">
                                {isRunning
                                    ? 'Нет открытых позиций — робот ещё не вошёл в сделку'
                                    : 'Нет открытых позиций на брокере (в universe / по audit fills)'}
                            </p>
                        ) : (
                            <table className="robots-v2-table">
                                <thead>
                                    <tr>
                                        <th>Тикер</th>
                                        <th>Сторона</th>
                                        <th>Кол-во</th>
                                        <th>Вход</th>
                                        <th title="Цена продажи без убытка после комиссий">Точка безубыточности</th>
                                        <th>Текущая</th>
                                        <th>SL</th>
                                        <th>TP</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {positions.map((p, i) => {
                                        const row = p as Record<string, unknown>
                                        const tickerLabel = String(row.ticker ?? row.figi ?? '—')
                                        const tickerWarning = positionTickerWarning(row)
                                        return (
                                            <tr key={`${row.ticker ?? row.figi}-${i}`}>
                                                <td>
                                                    <span className="robots-v2-ticker-cell">
                                                        {tickerWarning ? <TickerWarningMark text={tickerWarning} /> : null}
                                                        {tickerLabel}
                                                    </span>
                                                </td>
                                                <td>{String(row.side ?? '—')}</td>
                                                <td className="mono">{String(row.quantity ?? '—')}</td>
                                                <td className="mono">
                                                    {posPrice(row, 'entry_price', 'entryPrice', 'avg_entry_price', 'avgEntryPrice')}
                                                </td>
                                                <td className="mono">
                                                    {posPrice(row, 'break_even_price', 'breakEvenPrice')}
                                                </td>
                                                <td className="mono">
                                                    {posPrice(row, 'current_price', 'currentPrice')}
                                                </td>
                                                <td className="mono">
                                                    {posPrice(row, 'stop_loss_price', 'stopLossPrice')}
                                                </td>
                                                <td className="mono">
                                                    {posPrice(row, 'take_profit_price', 'takeProfitPrice')}
                                                </td>
                                            </tr>
                                        )
                                    })}
                                </tbody>
                            </table>
                        )}
                    </Card>

                    <Card className="dashboard-assets-card robots-v2-monitor-scan">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Пул активов</h3>
                            <div className="robots-v2-universe-head-actions">
                                {displayTickerScan.length > 0 ? (
                                    <span className="robots-v2-hint">{displayTickerScan.length}</span>
                                ) : displayUniverse.length > 0 ? (
                                    <span className="robots-v2-hint">{displayUniverse.length}</span>
                                ) : null}
                                {canRefreshUniverse ? (
                                    <Button
                                        type="button"
                                        variant="secondary"
                                        size="sm"
                                        loading={universeBusy}
                                        disabled={universeBusy}
                                        onClick={() => void onRefreshUniverse()}
                                    >
                                        Обновить пул
                                    </Button>
                                ) : null}
                            </div>
                        </div>
                        <p className="robots-v2-hint robots-v2-universe-caption">
                            Кандидаты и результат последней оценки стратегии
                            {tickerScanAt ? (
                                <span className="mono">
                                    {' '}
                                    · {new Date(tickerScanAt).toLocaleTimeString('ru-RU')}
                                </span>
                            ) : null}
                        </p>
                        {displayTickerScan.length === 0 && displayUniverse.length === 0 ? (
                            <p className="dashboard-empty">—</p>
                        ) : displayTickerScan.length === 0 ? (
                            <div className="robots-v2-chip-row">
                                {displayUniverse.map(t => (
                                    <span key={t} className="robots-v2-chip robots-v2-chip--on">{t}</span>
                                ))}
                                <p className="robots-v2-hint">Диагностика появится после первого цикла</p>
                            </div>
                        ) : (
                            <div className="robots-v2-scan-table-wrap">
                                <table className="robots-v2-table robots-v2-scan-table">
                                    <thead>
                                        <tr>
                                            <th>Название</th>
                                            <th>Почему нет сигнала</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {displayTickerScan.map(row => {
                                            const code = String(row.code || '—')
                                            return (
                                                <tr key={row.ticker}>
                                                    <td>
                                                        <div className="robots-v2-scan-ticker">
                                                            <strong>{row.ticker}</strong>
                                                            <Badge variant={SCAN_CODE_VARIANT[code] || 'neutral'}>
                                                                {code}
                                                            </Badge>
                                                        </div>
                                                    </td>
                                                    <td className="robots-v2-scan-reason">
                                                        {String(row.message || '—')}
                                                    </td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </Card>

                    <Card className="dashboard-assets-card">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Decisions</h3>
                        </div>
                        <ul className="robots-v2-event-list">
                            {decisions.slice(0, 12).map((d, i) => (
                                <li key={i}>
                                    <strong>{String(d.code ?? '—')}</strong> {String(d.message ?? '')}{' '}
                                    {d.ticker ? `(${String(d.ticker)})` : ''}
                                </li>
                            ))}
                            {decisions.length === 0 && <li className="robots-v2-hint">Пока нет решений риска</li>}
                        </ul>
                    </Card>

                    <Card className="dashboard-assets-card robots-v2-monitor-events">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Live stream</h3>
                            <Badge variant={streamConnected ? 'up' : 'neutral'}>
                                {streamConnected ? 'WS connected' : 'WS offline'}
                            </Badge>
                        </div>
                        <ul className="robots-v2-event-list">
                            {events.map((ev, i) => (
                                <li key={`${ev.ts}-${i}`}>
                                    <span className="mono">{new Date(ev.ts).toLocaleTimeString('ru-RU')}</span>{' '}
                                    <Badge variant="cyan">{ev.type}</Badge>
                                    {ev.type === 'stage' && ev.payload && typeof ev.payload === 'object' ? (
                                        <span className="robots-v2-hint">
                                            {' '}
                                            {stageLabel(String((ev.payload as { stage?: string }).stage || ''))}
                                        </span>
                                    ) : null}
                                </li>
                            ))}
                            {events.length === 0 && (
                                <li className="robots-v2-hint">
                                    {isRunning
                                        ? (streamConnected
                                            ? 'Стрим подключён, ждём события сессии…'
                                            : !token
                                                ? 'Нужна авторизация для live-стрима. События подтягиваются по REST каждые 5с.'
                                                : 'WS offline — события подтягиваются по REST каждые 5с. Проверьте proxy ws для /api.')
                                        : 'Сессия не запущена — нажмите «Запуск»'}
                                </li>
                            )}
                        </ul>
                    </Card>
                </div>
            </div>
        </div>
    )
}
