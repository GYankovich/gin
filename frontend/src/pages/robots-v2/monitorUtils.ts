import type { Time } from '@/components/ui/Chart'
import type { RobotV2RoundTrip, RobotV2Status, RobotV2TickerScan } from '@/types/robotV2'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'

export function pick<T>(obj: RobotV2Status, camel: keyof RobotV2Status, snake: string): T | undefined {
    const anyObj = obj as Record<string, unknown>
    return (obj[camel] ?? anyObj[snake]) as T | undefined
}

/** Lightweight Charts requires strictly ascending unique unix seconds. */
export function normalizeEquityPoints(
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

export function appendEquityPoint(
    prev: Array<{ time: Time; value: number }>,
    value: number,
    timeSec?: number,
): Array<{ time: Time; value: number }> {
    const t = Math.floor(timeSec ?? Date.now() / 1000)
    return normalizeEquityPoints([...prev, { time: t as Time, value }])
}

export const STAGE_LABELS: Record<string, string> = {
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

export const SKIP_LABELS: Record<string, string> = {
    OUTSIDE_SESSION: 'Вне торговой сессии',
    EOD_HOLD: 'EOD hold',
    RECONCILE_FAILED: 'Сверка с брокером не удалась',
    NO_PRICES: 'Нет цен',
    BOOTSTRAP_SYNC: 'Синхронизация при старте',
}

export const SCAN_CODE_VARIANT: Record<string, 'up' | 'down' | 'warn' | 'cyan' | 'neutral'> = {
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

export function stageLabel(stage: string | null | undefined): string {
    if (!stage) return '—'
    return STAGE_LABELS[stage] || stage
}

export function stageDetailLabel(detail: string | null | undefined): string | null {
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

export function fmtPrice(v: unknown): string {
    const n = Number(v)
    if (!Number.isFinite(n) || n <= 0) return '—'
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}

export function orderStatusLabel(status: string): string {
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

export function posPrice(p: Record<string, unknown>, ...keys: string[]): string {
    for (const k of keys) {
        const v = p[k]
        if (v != null && Number.isFinite(Number(v))) return fmtPrice(v)
    }
    return '—'
}

export function positionTickerWarning(row: Record<string, unknown>): string {
    const raw = row.tickerWarning ?? row.ticker_warning
    return typeof raw === 'string' && raw.trim() ? raw.trim() : ''
}

export function positionsStampMs(updatedAt: unknown, fallbackTs?: unknown): number {
    const raw = updatedAt != null ? String(updatedAt) : (fallbackTs != null ? String(fallbackTs) : '')
    const ms = raw ? Date.parse(raw) : NaN
    return Number.isFinite(ms) ? ms : 0
}

export function pickOpenPositions(msg: Record<string, unknown>): Array<Record<string, unknown>> | null {
    const rows = msg.openPositions ?? msg.open_positions
    if (!Array.isArray(rows)) return null
    return rows as Array<Record<string, unknown>>
}

export function fmtPriceQty(price: unknown, qty: unknown): string {
    const px = fmtPrice(price)
    const q = Number(qty)
    if (px === '—') return '—'
    if (!Number.isFinite(q) || q <= 0) return px
    return `${px} (${q % 1 === 0 ? q.toLocaleString('ru-RU') : q.toLocaleString('ru-RU', { maximumFractionDigits: 4 })})`
}

export function fmtTime(ts: string | null | undefined): string {
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

export function fmtNetPnl(value: unknown): { text: string; tone: 'up' | 'down' | 'neutral' } {
    const n = Number(value)
    if (!Number.isFinite(n)) return { text: '—', tone: 'neutral' }
    const text = `${n.toLocaleString('ru-RU', { maximumFractionDigits: 2, signDisplay: 'exceptZero' })} ₽`
    if (n > 0) return { text, tone: 'up' }
    if (n < 0) return { text, tone: 'down' }
    return { text: '0 ₽', tone: 'neutral' }
}

/** Calendar day in Europe/Moscow (MOEX session day). */
export function moscowDayKey(ms: number): string {
    return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Europe/Moscow',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).format(new Date(ms))
}

export function todayMoscowDayKey(): string {
    return moscowDayKey(Date.now())
}

export type DayTradeStats = {
    dayKey: string
    trades: number
    sumPlus: number
    sumMinus: number
    delta: number
}

export function pickRoundTripField<T>(
    row: RobotV2RoundTrip,
    camel: keyof RobotV2RoundTrip,
    snake: string,
): T | undefined {
    const anyRow = row as Record<string, unknown>
    return (row[camel] ?? anyRow[snake]) as T | undefined
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

/** Closed round-trips for the Moscow calendar day (by sell time). */
export function computeDayTradeStats(trips: RobotV2RoundTrip[], dayKey = todayMoscowDayKey()): DayTradeStats {
    let trades = 0
    let sumPlus = 0
    let sumMinus = 0
    for (const trip of trips) {
        const status = String(trip.status || '').toLowerCase()
        if (status !== 'closed' && status !== 'filled') continue
        const sellAt = pickRoundTripField<string | null>(trip, 'sellAt', 'sell_at')
        if (!sellAt) continue
        const ms = Date.parse(String(sellAt))
        if (!Number.isFinite(ms) || moscowDayKey(ms) !== dayKey) continue
        const pnl = tripPocketValue(trip)
        if (pnl == null) continue
        trades += 1
        if (pnl > 0) sumPlus += pnl
        else if (pnl < 0) sumMinus += pnl
    }
    return { dayKey, trades, sumPlus, sumMinus, delta: sumPlus + sumMinus }
}

export function mergeLiveRoundTrips(
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

export type OrderDisplayRow = {
    id: string
    ticker: string
    dateMs: number
    buyAtLabel: string
    buyPriceLabel: string
    sellAtLabel: string
    sellListedLabel: string
    sellFillLabel: string
    status: string
    statusLabel: string
    statusRank: number
    pocket: number | null
    pocketText: string
    pocketTone: 'up' | 'down' | 'neutral'
    pocketTitle?: string
    reasonLabel: string
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

export function toOrderDisplayRow(row: RobotV2RoundTrip): OrderDisplayRow {
    const buyAt = pickRoundTripField<string | null>(row, 'buyAt', 'buy_at')
    const buyPrice = pickRoundTripField<number | null>(row, 'buyPrice', 'buy_price')
    const buyQty = pickRoundTripField<number | null>(row, 'buyQty', 'buy_qty')
    const sellAt = pickRoundTripField<string | null>(row, 'sellAt', 'sell_at')
    const sellListed = pickRoundTripField<number | null>(row, 'sellListedPrice', 'sell_listed_price')
    const sellFill = pickRoundTripField<number | null>(row, 'sellFillPrice', 'sell_fill_price')
    const sellQty = pickRoundTripField<number | null>(row, 'sellQty', 'sell_qty')
    const reason = pickRoundTripField<string | null>(row, 'reason', 'reason')
    const netPnl = pickRoundTripField<number | null>(row, 'netPnl', 'net_pnl')
    const realizedPnl = pickRoundTripField<number | null>(row, 'realizedPnl', 'realized_pnl')
    const pocket = fmtNetPnl(netPnl)
    const listedLabel = sellListed != null && Number(sellListed) > 0
        ? fmtPrice(sellListed)
        : String(row.status).toLowerCase() === 'resting'
            ? '—'
            : sellFill != null
                ? 'рынок'
                : '—'
    return {
        id: String(row.id),
        ticker: String(row.ticker || ''),
        dateMs: tripDateMs(row) ?? 0,
        buyAtLabel: fmtTime(buyAt),
        buyPriceLabel: fmtPriceQty(buyPrice, buyQty),
        sellAtLabel: fmtTime(sellAt),
        sellListedLabel: listedLabel,
        sellFillLabel: fmtPriceQty(sellFill, sellQty),
        status: String(row.status || ''),
        statusLabel: orderStatusLabel(row.status),
        statusRank: ORDERS_STATUS_RANK[String(row.status || '').toLowerCase()] ?? 99,
        pocket: tripPocketValue(row),
        pocketText: pocket.text,
        pocketTone: pocket.tone,
        pocketTitle:
            realizedPnl != null && Number.isFinite(Number(realizedPnl))
                ? `До НДФЛ: ${Number(realizedPnl).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽`
                : undefined,
        reasonLabel: tradeReasonLabel(reason),
    }
}

const COOLDOWN_SCAN_CODES = new Set(['COOLDOWN', 'SL_COOLDOWN'])

export function positionTicker(p: Record<string, unknown>): string {
    return String(p.secid || p.ticker || p.figi || '').toUpperCase()
}

/** Tickers with a recent trade in audit, open position, or live order. */
export function collectAuditTradeTickers(
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
export function filterScanCooldownRows(
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

export function scanStampMs(at: unknown, fallbackTs?: unknown): number {
    const raw = at != null ? String(at) : (fallbackTs != null ? String(fallbackTs) : '')
    const ms = raw ? Date.parse(raw) : NaN
    return Number.isFinite(ms) ? ms : 0
}

/** Stable alphabetical order — avoids rows jumping when a position opens/closes. */
export function sortByTickerName<T>(items: T[], getTicker: (item: T) => string): T[] {
    return [...items].sort((a, b) => {
        const ta = String(getTicker(a) || '').toUpperCase()
        const tb = String(getTicker(b) || '').toUpperCase()
        return ta.localeCompare(tb, 'en')
    })
}

export function mergeUniverseTickers(universe: string[], positions: Array<Record<string, unknown>>): string[] {
    const seen = new Set<string>()
    const out: string[] = []
    for (const raw of universe) {
        const t = String(raw || '').toUpperCase()
        if (!t || seen.has(t)) continue
        seen.add(t)
        out.push(t)
    }
    for (const p of positions) {
        const t = positionTicker(p)
        if (!t || seen.has(t)) continue
        seen.add(t)
        out.push(t)
    }
    out.sort((a, b) => a.localeCompare(b, 'en'))
    return out
}
