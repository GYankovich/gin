import type { Time } from '@/components/ui/Chart'
import type {
    RobotV2BalanceSource,
    RobotV2RoundTrip,
    RobotV2Status,
    RobotV2TickerScan,
} from '@/types/robotV2'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'

/** Finite numeric balance from status — never treat missing as 0. */
export function isFiniteBalance(v: unknown): v is number {
    if (v == null || v === '') return false
    return Number.isFinite(Number(v))
}

export function parseBalanceSource(raw: unknown): RobotV2BalanceSource | null {
    const s = String(raw || '').toLowerCase()
    if (s === 'session' || s === 'broker' || s === 'paper_last') return s
    return null
}

/** UX-06 Zone B tile labels from balanceSource (+ mode for session). */
export function balanceTileLabels(
    source: RobotV2BalanceSource | null,
    mode: string | null | undefined,
): { equity: string; cash: string } {
    const isPaper = String(mode || '').toLowerCase() === 'paper'
    if (source === 'broker') return { equity: 'Equity · Счёт', cash: 'Cash · Счёт' }
    if (source === 'paper_last') return { equity: 'Equity · Paper', cash: 'Cash · Paper' }
    if (source === 'session') {
        return isPaper
            ? { equity: 'Equity · Paper', cash: 'Cash · Paper' }
            : { equity: 'Equity · Счёт', cash: 'Cash · Счёт' }
    }
    return { equity: 'Equity', cash: 'Cash' }
}

/** UX-06 Zone Bƒ footnote; null when no honesty line needed. */
export function balanceFootnoteText(
    source: RobotV2BalanceSource | null,
    mode: string | null | undefined,
): string | null {
    const isPaper = String(mode || '').toLowerCase() === 'paper'
    if (source === 'broker') return 'Счёт брокера · робот не выделяет отдельный баланс'
    if (source === 'paper_last') return 'Последний бумажный капитал · не живой счёт'
    if (source === 'session') {
        return isPaper ? 'Бумажный капитал сессии' : 'Средства брокерского счёта'
    }
    return null
}

/** Local time for «обновлено …» freshness suffix. */
export function formatBalanceAsOfLabel(iso: string | null | undefined): string | null {
    if (!iso) return null
    const d = new Date(iso)
    if (!Number.isFinite(d.getTime())) return null
    const time = d.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    })
    return `обновлено ${time}`
}

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

/** Same order as backend CYCLE_STAGES. Bootstrap and skip sit outside the track. */
export const CYCLE_STAGE_ORDER = [
    'idle',
    'prices',
    'reconcile',
    'schedule',
    'exits',
    'strategy',
    'risk',
    'execution',
    'metrics',
    'done',
] as const

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
    /** Closed day trades with net PnL > 0. */
    wins: number
    /** Closed day trades with net PnL < 0. */
    losses: number
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

/** True when an instant falls on the current Moscow calendar day. Unix seconds or ms. */
export function isMoscowToday(isoOrMs: string | number | null | undefined, dayKey = todayMoscowDayKey()): boolean {
    if (isoOrMs == null || isoOrMs === '') return false
    const raw = typeof isoOrMs === 'number' ? isoOrMs : Date.parse(String(isoOrMs))
    if (!Number.isFinite(raw)) return false
    const ms = raw < 1e12 ? raw * 1000 : raw
    return moscowDayKey(ms) === dayKey
}

/** Live orders table: open work stays; closed trips only if they settled today. */
export function tripOnLiveDay(trip: RobotV2RoundTrip, dayKey = todayMoscowDayKey()): boolean {
    const status = String(trip.status || '').toLowerCase()
    if (status === 'open' || status === 'resting' || status === 'submitted' || status === 'new') {
        return true
    }
    const sellAt = pickRoundTripField<string | null>(trip, 'sellAt', 'sell_at')
    const buyAt = pickRoundTripField<string | null>(trip, 'buyAt', 'buy_at')
    const stamp = sellAt || buyAt
    if (!stamp) return true
    return isMoscowToday(stamp, dayKey)
}

/** Closed round-trips for the Moscow calendar day (by sell time). */
export function computeDayTradeStats(trips: RobotV2RoundTrip[], dayKey = todayMoscowDayKey()): DayTradeStats {
    let trades = 0
    let wins = 0
    let losses = 0
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
        if (pnl > 0) {
            wins += 1
            sumPlus += pnl
        } else if (pnl < 0) {
            losses += 1
            sumMinus += pnl
        }
    }
    return { dayKey, trades, wins, losses, sumPlus, sumMinus, delta: sumPlus + sumMinus }
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
    timeLabel: string
    /** When the EXIT order was submitted (LIMIT/MARKET) — not the buy fill. */
    placedAtLabel: string
    /** When the position was opened (buy fill). */
    boughtAtLabel: string
    /** Broker fill clock for the exit leg. */
    filledAtLabel: string
    qtyLabel: string
    priceLabel: string
    /** Entry unit price only (no qty). */
    buyPxLabel: string
    /** Exit fill unit price only (no qty). */
    sellPxLabel: string
    detailLabel: string
    isOpen: boolean
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
    outcomeText: string
    outcomeTone: 'up' | 'down' | 'neutral'
    outcomeTitle?: string
    /** Round-trip commission label (entry+exit). */
    commissionText: string
    /** Exit / sell reason (SL, TP, flatten…). Shown as «Причина продажи». */
    reasonLabel: string
    /** Entry / buy reason that opened the position. Shown as «Причина покупки». */
    signalLabel: string
}

const OPEN_ORDER_STATUSES = new Set(['open', 'resting', 'submitted', 'new'])

/**
 * Blotter clock: always `дд.мм, чч:мм`.
 * Resting limits can span days — omitting “today” makes fill look like the same morning as placement.
 */
export function fmtOrderClock(ts: string | null | undefined): string {
    if (!ts) return '—'
    const d = new Date(ts)
    if (!Number.isFinite(d.getTime())) return '—'
    return d.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    })
}

/** Exit placement / fill clock with seconds — so LIMIT lag is visible. */
export function fmtOrderClockSeconds(ts: string | null | undefined): string {
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
    const sellSubmittedAt = pickRoundTripField<string | null>(row, 'sellSubmittedAt', 'sell_submitted_at')
    const reason = pickRoundTripField<string | null>(row, 'reason', 'reason')
    const entryReason = pickRoundTripField<string | null>(row, 'entryReason', 'entry_reason')
    const netPnl = pickRoundTripField<number | null>(row, 'netPnl', 'net_pnl')
    const realizedPnl = pickRoundTripField<number | null>(row, 'realizedPnl', 'realized_pnl')
    const commissionRaw = pickRoundTripField<number | null>(row, 'commission', 'commission')
    const commissionN = Number(commissionRaw)
    const commissionText = Number.isFinite(commissionN) && commissionN > 0
        ? `−${commissionN.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽`
        : Number.isFinite(commissionN) && commissionN === 0
            ? '0 ₽'
            : '—'
    const pocket = fmtNetPnl(netPnl)
    const statusKey = String(row.status || '').toLowerCase()
    const isOpen = OPEN_ORDER_STATUSES.has(statusKey)
    const listedOk = sellListed != null && Number(sellListed) > 0
    const fillOk = sellFill != null && Number(sellFill) > 0
    const listedLabel = listedOk
        ? fmtPrice(sellListed)
        : statusKey === 'resting'
            ? '—'
            : fillOk
                ? 'рынок'
                : '—'
    const listedText = listedOk ? fmtPrice(sellListed) : null
    const fillText = fillOk ? fmtPrice(sellFill) : null
    const buyText = buyPrice != null && Number(buyPrice) > 0 ? fmtPriceQty(buyPrice, buyQty) : null
    const detailLabel = isOpen && listedText
        ? `лимит · выст. ${listedText} · факт —`
        : listedText && fillText
            ? `продажа · выст. ${listedText} · факт ${fillText}`
            : fillText
                ? `продажа · факт ${fillText}`
                : buyText
                    ? `покупка · ${buyText}`
                    : orderStatusLabel(row.status)
    const qtyN = Number(sellQty || buyQty)
    const qtyLabel = Number.isFinite(qtyN) && qtyN > 0
        ? qtyN.toLocaleString('ru-RU', { maximumFractionDigits: 4 })
        : '—'
    const priceLabel = fillOk
        ? fmtPrice(sellFill)
        : listedOk
            ? fmtPrice(sellListed)
            : (buyPrice != null && Number(buyPrice) > 0 ? fmtPrice(buyPrice) : '—')
    const buyN = Number(buyPrice)
    const listedN = Number(sellListed)
    const planned = isOpen && buyN > 0 && listedN > 0 && qtyN > 0
        ? (listedN - buyN) * qtyN
        : null
    const outcome = !isOpen && tripPocketValue(row) != null
        ? fmtNetPnl(tripPocketValue(row))
        : planned != null
            ? fmtNetPnl(planned)
            : fmtNetPnl(null)
    const outcomeTitle = !isOpen && tripPocketValue(row) != null
        ? (realizedPnl != null && Number.isFinite(Number(realizedPnl))
            ? `В кармане. До НДФЛ: ${Number(realizedPnl).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽`
            : 'В кармане, после комиссии и налога')
        : planned != null
            ? 'Если лимит исполнится, до комиссии и налога'
            : undefined
    // «Выставление» = when the EXIT order was submitted to the broker — never buyAt.
    const placedAt = sellSubmittedAt
    return {
        id: String(row.id),
        ticker: String(row.ticker || ''),
        dateMs: tripDateMs(row) ?? 0,
        timeLabel: fmtOrderClock((isOpen ? buyAt : sellAt) || buyAt || sellAt),
        placedAtLabel: fmtOrderClockSeconds(placedAt),
        filledAtLabel: fmtOrderClockSeconds(sellAt),
        boughtAtLabel: fmtOrderClock(buyAt),
        qtyLabel,
        priceLabel,
        buyPxLabel: buyPrice != null && Number(buyPrice) > 0 ? fmtPrice(buyPrice) : '—',
        sellPxLabel: fillOk ? fmtPrice(sellFill) : (listedOk ? fmtPrice(sellListed) : '—'),
        detailLabel,
        isOpen,
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
        outcomeText: outcome.text,
        outcomeTone: outcome.tone,
        outcomeTitle,
        commissionText,
        reasonLabel: tradeReasonLabel(reason),
        signalLabel: tradeReasonLabel(entryReason),
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

export function readPosNumber(row: Record<string, unknown>, ...keys: string[]): number | null {
    for (const key of keys) {
        const n = Number(row[key])
        if (Number.isFinite(n) && n !== 0) return n
    }
    for (const key of keys) {
        const n = Number(row[key])
        if (Number.isFinite(n)) return n
    }
    return null
}

/** Unrealized PnL for a long/short row (qty × (mark − entry), sign by side). */
export function positionUnrealizedPnl(row: Record<string, unknown>): number | null {
    const entry = readPosNumber(row, 'entry_price', 'entryPrice', 'avg_entry_price', 'avgEntryPrice')
    const current = readPosNumber(row, 'current_price', 'currentPrice')
    const qty = readPosNumber(row, 'quantity', 'qty')
    if (entry == null || current == null || qty == null || qty === 0) return null
    const side = String(row.side || 'long').toLowerCase()
    const signedQty = side === 'short' || side === 'sell' ? -Math.abs(qty) : Math.abs(qty)
    return (current - entry) * signedQty
}

export type RestingLimitHint = {
    kind: 'sl' | 'tp' | 'limit'
    label: string
}

export function restingLimitForTicker(
    ticker: string,
    liveOrders: Array<Record<string, unknown>>,
): RestingLimitHint | null {
    const key = ticker.toUpperCase()
    for (const o of liveOrders) {
        if (String(o.ticker || '').toUpperCase() !== key) continue
        const status = String(o.status || '').toLowerCase()
        if (!['resting', 'submitted', 'new'].includes(status)) continue
        const side = String(o.side || '').toUpperCase()
        if (side !== 'SELL' && side !== 'BUY') continue
        const raw = String(o.kind || o.reason || o.orderType || o.order_type || '').toLowerCase()
        if (raw.includes('stop') || raw.includes('sl')) {
            return { kind: 'sl', label: 'лимит SL выставлен' }
        }
        if (raw.includes('take') || raw.includes('tp')) {
            return { kind: 'tp', label: 'лимит TP выставлен' }
        }
        return { kind: 'limit', label: 'лимит выставлен' }
    }
    return null
}

export function positionBlotterSubtitle(
    row: Record<string, unknown>,
    liveOrders: Array<Record<string, unknown>>,
): string {
    const ticker = positionTicker(row)
    const limit = ticker ? restingLimitForTicker(ticker, liveOrders) : null
    const current = readPosNumber(row, 'current_price', 'currentPrice')
    const sl = readPosNumber(row, 'stop_loss_price', 'stopLossPrice')
    const parts: string[] = []
    if (current != null && sl != null && current > 0 && sl > 0) {
        const dist = Math.abs(current - sl)
        parts.push(`до SL ${fmtPrice(dist)}`)
    }
    if (limit) parts.push(limit.label)
    else parts.push('без лимита')
    return parts.join(' · ')
}

const DECISION_CODE_RU: Record<string, string> = {
    NO_SIGNAL: 'Тихо',
    HOLD: 'Держим',
    BLOCK: 'Блок',
    BLOCKED: 'Блок',
    SKIP: 'Пропуск',
    ENTER: 'Вход',
    EXIT: 'Выход',
    RISK: 'Риск',
}

export function decisionCodeLabel(code: unknown): string {
    const raw = String(code || '').trim()
    if (!raw) return '—'
    return DECISION_CODE_RU[raw.toUpperCase()] || raw
}

/** Normalize status / audit / WS decision rows for the monitor feed. */
export function toDecisionFeedRow(raw: Record<string, unknown>): Record<string, unknown> | null {
    const code = String(raw.code ?? raw.decision_code ?? '').trim()
    const message = raw.message ?? raw.decision_message ?? null
    const ticker = raw.ticker ?? null
    if (!code && (message == null || String(message).trim() === '')) return null
    const row: Record<string, unknown> = {
        code: code || '—',
        message,
        ticker,
    }
    if (raw.id != null) row.id = raw.id
    if (raw.allow != null) row.allow = raw.allow
    if (raw.createdAt != null || raw.created_at != null) {
        row.createdAt = raw.createdAt ?? raw.created_at
    }
    return row
}

/** Prefer live session decisions; fall back to audit; drop consecutive duplicates. */
export function mergeDecisionFeed(
    live: Array<Record<string, unknown>> | null | undefined,
    audit: Array<Record<string, unknown>> | null | undefined,
    max = 40,
): Array<Record<string, unknown>> {
    const source = (Array.isArray(live) && live.length > 0) ? live : (audit || [])
    const out: Array<Record<string, unknown>> = []
    for (const raw of source) {
        const row = toDecisionFeedRow(raw)
        if (!row) continue
        const prev = out[out.length - 1]
        if (
            prev
            && String(prev.code) === String(row.code)
            && String(prev.message ?? '') === String(row.message ?? '')
            && String(prev.ticker ?? '') === String(row.ticker ?? '')
        ) {
            continue
        }
        out.push(row)
        if (out.length >= max) break
    }
    return out
}

/** Per-ticker strategy scan → decision-feed rows (pool monitoring). */
export function tickerScanToDecisionRows(
    scan: Array<{ ticker?: string; code?: string; message?: string } | RobotV2TickerScan>,
): Array<Record<string, unknown>> {
    const out: Array<Record<string, unknown>> = []
    for (const s of scan || []) {
        const ticker = String(s.ticker || '').toUpperCase()
        const code = String(s.code || '').trim()
        const message = s.message != null ? String(s.message) : ''
        if (!ticker && !code && !message) continue
        out.push({
            code: code || 'SCAN',
            message,
            ticker: ticker || null,
        })
    }
    return out
}

/**
 * Monitor «Решения»: risk/audit rows + per-ticker scan.
 * Pool monitoring lives in tickerScan — without it the panel looks empty while the universe is scanned.
 */
export function buildMonitorDecisionFeed(
    riskOrAudit: Array<Record<string, unknown>> | null | undefined,
    scan: Array<{ ticker?: string; code?: string; message?: string } | RobotV2TickerScan>,
    max = 40,
): Array<Record<string, unknown>> {
    const risk = mergeDecisionFeed(riskOrAudit, null, max)
    const interesting = risk.filter(d => String(d.code || '').toUpperCase() !== 'NO_SIGNAL')
    const scanRows = tickerScanToDecisionRows(scan)
    if (interesting.length > 0) {
        return mergeDecisionFeed([...interesting, ...scanRows], null, max)
    }
    if (scanRows.length > 0) {
        return mergeDecisionFeed(scanRows, null, max)
    }
    return risk
}

export type PoolDecisionRow = {
    id: string
    ticker: string
    code: string
    /** Human decision code (Вход / Тихо / Риск…). */
    decision: string
    /** Detail / message for the decision. */
    reason: string
    /** Epoch ms for sorting; null/NaN → bottom. */
    updatedMs: number | null
    updatedLabel: string
}

function poolUpdatedMs(raw: unknown): number | null {
    if (raw == null || raw === '') return null
    if (typeof raw === 'number' && Number.isFinite(raw)) return raw
    const d = new Date(String(raw))
    const ms = d.getTime()
    return Number.isFinite(ms) ? ms : null
}

function poolUpdatedLabel(ms: number | null): string {
    if (ms == null) return '—'
    return new Date(ms).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    })
}

/**
 * One row per pool ticker: ticker · decision · updated (risk feed, else scan).
 */
export function buildPoolDecisionRows(
    tickers: string[],
    scan: Array<{ ticker?: string; code?: string; message?: string } | RobotV2TickerScan>,
    decisions: Array<Record<string, unknown>> | null | undefined,
    scanAt?: string | null,
): PoolDecisionRow[] {
    const scanMs = poolUpdatedMs(scanAt)
    const scanByTicker = new Map<string, { code: string; message: string; updatedMs: number | null }>()
    for (const s of scan || []) {
        const ticker = String(s.ticker || '').toUpperCase()
        if (!ticker || scanByTicker.has(ticker)) continue
        scanByTicker.set(ticker, {
            code: String(s.code || '').trim(),
            message: s.message != null ? String(s.message) : '',
            updatedMs: scanMs,
        })
    }

    const decisionByTicker = new Map<string, { code: string; message: string; updatedMs: number | null }>()
    for (const raw of decisions || []) {
        const row = toDecisionFeedRow(raw)
        if (!row) continue
        const ticker = String(row.ticker || '').toUpperCase()
        if (!ticker || decisionByTicker.has(ticker)) continue
        decisionByTicker.set(ticker, {
            code: String(row.code || '').trim(),
            message: row.message != null ? String(row.message) : '',
            updatedMs: poolUpdatedMs(row.createdAt),
        })
    }

    const ordered: string[] = []
    const seen = new Set<string>()
    for (const t of tickers) {
        const ticker = String(t || '').toUpperCase()
        if (!ticker || seen.has(ticker)) continue
        seen.add(ticker)
        ordered.push(ticker)
    }
    for (const ticker of scanByTicker.keys()) {
        if (seen.has(ticker)) continue
        seen.add(ticker)
        ordered.push(ticker)
    }

    return ordered.map(ticker => {
        const hit = decisionByTicker.get(ticker) || scanByTicker.get(ticker)
        if (!hit) {
            return {
                id: ticker,
                ticker,
                code: '',
                decision: '—',
                reason: '—',
                updatedMs: null,
                updatedLabel: '—',
            }
        }
        const decision = decisionCodeLabel(hit.code) || '—'
        const msg = decisionMessageRu(hit.message, ticker)
        // decisionMessageRu may prefix ticker — strip for the reason column
        const reason = (msg.startsWith(`${ticker} · `) ? msg.slice(ticker.length + 3) : msg) || '—'
        const updatedMs = hit.updatedMs ?? scanMs
        return {
            id: ticker,
            ticker,
            code: hit.code,
            decision,
            reason,
            updatedMs,
            updatedLabel: poolUpdatedLabel(updatedMs),
        }
    })
}

/** Soft RU rewrite for common English decision messages. */
export function decisionMessageRu(message: unknown, ticker?: unknown): string {
    let msg = String(message || '').trim()
    if (!msg) return ticker ? String(ticker) : ''
    msg = msg
        .replace(/Strategy quiet[^.)]*/gi, 'стратегия без сигнала')
        .replace(/triggered_by=/gi, 'триггер ')
        .replace(/minCandles=/gi, 'свечей ≥')
        .replace(/universe=/gi, 'пул ')
        .replace(/tick_count/gi, 'тиков')
        .replace(/no signal/gi, 'нет сигнала')
        .replace(/liquidity/gi, 'ликвидность')
    const tk = ticker != null ? String(ticker) : ''
    if (tk && !msg.includes(tk)) return `${tk} · ${msg}`
    return msg
}

export function countRestingLimits(liveOrders: Array<Record<string, unknown>>): number {
    return liveOrders.filter(o => {
        const status = String(o.status || '').toLowerCase()
        return ['resting', 'submitted', 'new'].includes(status)
    }).length
}
