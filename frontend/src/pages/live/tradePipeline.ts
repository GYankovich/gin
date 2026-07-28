/** Unified live feed: Signal ? Order ? Result */

export type PipelineSide = 'buy' | 'sell' | 'info'

export type PipelineResultKind =
    | 'pending'
    | 'working'
    | 'partial'
    | 'filled'
    | 'open'
    | 'failed'
    | 'skipped'
    | 'rejected'
    | 'cancelled'
    | 'error'

export interface TradePipelineItem {
    id: string
    figi: string
    ticker: string
    side: PipelineSide
    time: string
    signal?: {
        id?: number
        price?: number
        time: string
        label: string
    }
    order?: {
        tradeId?: number
        orderId?: string
        quantity?: number
        price?: number
        status?: string
        time: string
        label: string
    }
    result?: {
        kind: PipelineResultKind
        time: string
        label: string
        reason?: string
    }
}

function parseTs(value: unknown): number {
    if (value == null) return 0
    if (typeof value === 'number' && Number.isFinite(value)) return value
    const t = Date.parse(String(value))
    return Number.isFinite(t) ? t : 0
}

export function normalizeSide(raw: unknown): PipelineSide {
    const s = String(raw || '').toLowerCase()
    if (s === 'buy') return 'buy'
    if (s === 'sell') return 'sell'
    return 'info'
}

export function resultKindFromStatus(status: unknown, reason?: unknown): PipelineResultKind {
    const s = String(status || '').toLowerCase()
    if (s === 'skipped') return 'skipped'
    if (s === 'failed' || s === 'error') return 'failed'
    if (s === 'rejected') return 'rejected'
    if (s === 'cancelled' || s === 'canceled') return 'cancelled'
    if (s === 'partial') return 'partial'
    if (s === 'closed' || s === 'filled') return 'filled'
    if (s === 'open') return 'open'
    if (s === 'pending' || s === 'new') return 'working'
    if (reason) return 'error'
    return 'pending'
}

export function resultLabel(kind: PipelineResultKind, reason?: string): string {
    switch (kind) {
        case 'pending':
            return '????????'
        case 'working':
            return '? ??????'
        case 'partial':
            return '????????'
        case 'filled':
            return '?????????'
        case 'open':
            return '???????'
        case 'failed':
            return reason ? `??????` : '??????'
        case 'skipped':
            return reason ? '???????' : '???????'
        case 'rejected':
            return '?????'
        case 'cancelled':
            return '??????'
        case 'error':
            return '??????'
        default:
            return String(kind)
    }
}

function fmtQty(q: unknown): string {
    const n = Number(q)
    if (!Number.isFinite(n)) return '?'
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 4 })
}

function fmtPrice(p: unknown): string {
    const n = Number(p)
    if (!Number.isFinite(n)) return '?'
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 4 })
}

export function buildPipelineFromSnapshot(
    signals: any[] | undefined,
    orders: any[] | undefined,
    tickerOf: (figi: string) => string,
    formatTime: (v: unknown) => string,
    limit: number,
): TradePipelineItem[] {
    const sigs = [...(signals || [])]
    const ords = [...(orders || [])]
    const usedTradeIds = new Set<number>()
    const items: TradePipelineItem[] = []

    const ordersById = new Map<number, any>()
    for (const o of ords) {
        const id = Number(o?.id)
        if (Number.isFinite(id)) ordersById.set(id, o)
    }

    const takeOrder = (o: any, signalId?: number): TradePipelineItem => {
        const figi = String(o?.figi || '').toUpperCase()
        const side = normalizeSide(o?.side)
        const status = String(o?.status || 'pending')
        const reason = o?.error || o?.reason ? String(o.error || o.reason) : undefined
        const kind = resultKindFromStatus(status, reason)
        const ts = formatTime(o?.created_at || o?.time)
        const tradeId = Number(o?.id)
        if (Number.isFinite(tradeId)) usedTradeIds.add(tradeId)
        return {
            id: Number.isFinite(tradeId)
                ? `trade:${tradeId}`
                : signalId != null
                    ? `signal:${signalId}`
                    : `order:${figi}:${o?.created_at || ts}`,
            figi,
            ticker: tickerOf(figi),
            side,
            time: ts,
            order: {
                tradeId: Number.isFinite(tradeId) ? tradeId : undefined,
                orderId: o?.order_id != null ? String(o.order_id) : undefined,
                quantity: o?.quantity != null ? Number(o.quantity) : undefined,
                price: o?.price != null ? Number(o.price) : undefined,
                status,
                time: ts,
                label: `x${fmtQty(o?.quantity)} ? ${status}`,
            },
            result: {
                kind,
                time: ts,
                label: resultLabel(kind, reason),
                reason,
            },
        }
    }

    // 1) Signals with executed_trade_id
    for (const s of sigs) {
        const signalId = Number(s?.id)
        const tradeId = s?.executed_trade_id != null ? Number(s.executed_trade_id) : NaN
        if (!Number.isFinite(tradeId) || !ordersById.has(tradeId)) continue
        const o = ordersById.get(tradeId)
        const row = takeOrder(o, Number.isFinite(signalId) ? signalId : undefined)
        const figi = String(s?.figi || row.figi).toUpperCase()
        const side = normalizeSide(s?.signal_type || row.side)
        const sts = formatTime(s?.created_at || s?.time)
        row.id = Number.isFinite(signalId) ? `signal:${signalId}` : row.id
        row.figi = figi
        row.ticker = tickerOf(figi)
        row.side = side
        row.time = sts
        row.signal = {
            id: Number.isFinite(signalId) ? signalId : undefined,
            price: s?.price_at_signal != null ? Number(s.price_at_signal) : undefined,
            time: sts,
            label: `@ ${fmtPrice(s?.price_at_signal)}`,
        }
        items.push(row)
    }

    // 2) Remaining signals ? nearest unused order by figi/side within 8s
    const unusedOrders = ords.filter(o => {
        const id = Number(o?.id)
        return !Number.isFinite(id) || !usedTradeIds.has(id)
    })

    for (const s of sigs) {
        const signalId = Number(s?.id)
        if (items.some(it => it.signal?.id === signalId)) continue
        const figi = String(s?.figi || '').toUpperCase()
        const side = normalizeSide(s?.signal_type)
        const sts = formatTime(s?.created_at || s?.time)
        const sigMs = parseTs(s?.created_at || s?.time)

        let best: any = null
        let bestDt = Infinity
        for (const o of unusedOrders) {
            const oid = Number(o?.id)
            if (Number.isFinite(oid) && usedTradeIds.has(oid)) continue
            if (String(o?.figi || '').toUpperCase() !== figi) continue
            if (normalizeSide(o?.side) !== side && side !== 'info') continue
            const dt = Math.abs(parseTs(o?.created_at || o?.time) - sigMs)
            if (dt < bestDt && dt <= 8000) {
                bestDt = dt
                best = o
            }
        }

        if (best) {
            const row = takeOrder(best, Number.isFinite(signalId) ? signalId : undefined)
            row.id = Number.isFinite(signalId) ? `signal:${signalId}` : row.id
            row.figi = figi
            row.ticker = tickerOf(figi)
            row.side = side
            row.time = sts
            row.signal = {
                id: Number.isFinite(signalId) ? signalId : undefined,
                price: s?.price_at_signal != null ? Number(s.price_at_signal) : undefined,
                time: sts,
                label: `@ ${fmtPrice(s?.price_at_signal)}`,
            }
            items.push(row)
        } else {
            items.push({
                id: Number.isFinite(signalId) ? `signal:${signalId}` : `signal:${figi}:${s?.created_at || sts}`,
                figi,
                ticker: tickerOf(figi),
                side,
                time: sts,
                signal: {
                    id: Number.isFinite(signalId) ? signalId : undefined,
                    price: s?.price_at_signal != null ? Number(s.price_at_signal) : undefined,
                    time: sts,
                    label: `@ ${fmtPrice(s?.price_at_signal)}`,
                },
                result: {
                    kind: 'pending',
                    time: sts,
                    label: resultLabel('pending'),
                },
            })
        }
    }

    // 3) Orders without signal
    for (const o of ords) {
        const tradeId = Number(o?.id)
        if (Number.isFinite(tradeId) && usedTradeIds.has(tradeId)) continue
        if (items.some(it => it.order?.tradeId === tradeId)) continue
        items.push(takeOrder(o))
    }

    items.sort((a, b) => parseTs(b.time) - parseTs(a.time) || String(b.id).localeCompare(String(a.id)))
    return items.slice(0, limit)
}

export function upsertPipelineFromSignal(
    prev: TradePipelineItem[],
    data: any,
    tickerOf: (figi: string) => string,
    formatTime: (v: unknown) => string,
    limit: number,
): TradePipelineItem[] {
    const figi = String(data?.figi || '').toUpperCase()
    const side = normalizeSide(data?.signal_type || data?.side)
    const ts = formatTime(data?.time)
    const signalId = data?.id != null && Number.isFinite(Number(data.id)) ? Number(data.id) : undefined
    const id = signalId != null ? `signal:${signalId}` : `signal:${figi}:${data?.time || Date.now()}`
    const signal = {
        id: signalId,
        price: data?.price != null ? Number(data.price) : undefined,
        time: ts,
        label: `@ ${fmtPrice(data?.price)}`,
    }
    const next = [...prev]
    const idx = signalId != null
        ? next.findIndex(x => x.signal?.id === signalId || x.id === id)
        : -1
    if (idx >= 0) {
        next[idx] = {
            ...next[idx],
            figi: figi || next[idx].figi,
            ticker: tickerOf(figi || next[idx].figi),
            side,
            time: ts,
            signal,
        }
    } else {
        next.unshift({
            id,
            figi,
            ticker: tickerOf(figi),
            side,
            time: ts,
            signal,
            result: { kind: 'pending', time: ts, label: resultLabel('pending') },
        })
    }
    return next.slice(0, limit)
}

export function upsertPipelineFromOrder(
    prev: TradePipelineItem[],
    data: any,
    tickerOf: (figi: string) => string,
    formatTime: (v: unknown) => string,
    limit: number,
    skipped = false,
): TradePipelineItem[] {
    const figi = String(data?.figi || '').toUpperCase()
    const side = normalizeSide(data?.side)
    const ts = formatTime(data?.time)
    const status = skipped ? 'skipped' : String(data?.status || 'pending')
    const reason = data?.reason || data?.error ? String(data.reason || data.error) : undefined
    const kind = resultKindFromStatus(status, reason)
    const signalId = data?.signal_id != null && Number.isFinite(Number(data.signal_id))
        ? Number(data.signal_id)
        : undefined
    const tradeId = data?.trade_id != null && Number.isFinite(Number(data.trade_id))
        ? Number(data.trade_id)
        : undefined
    const orderId = data?.order_id != null ? String(data.order_id) : undefined

    const order = {
        tradeId,
        orderId,
        quantity: data?.quantity != null ? Number(data.quantity) : undefined,
        price: data?.price != null ? Number(data.price) : undefined,
        status,
        time: ts,
        label: `x${fmtQty(data?.quantity)} ? ${status}`,
    }
    const result = {
        kind,
        time: ts,
        label: resultLabel(kind, reason),
        reason,
    }

    const next = [...prev]
    let idx = -1
    if (signalId != null) idx = next.findIndex(x => x.signal?.id === signalId || x.id === `signal:${signalId}`)
    if (idx < 0 && tradeId != null) idx = next.findIndex(x => x.order?.tradeId === tradeId || x.id === `trade:${tradeId}`)
    if (idx < 0 && orderId) idx = next.findIndex(x => x.order?.orderId === orderId)
    if (idx < 0 && figi) {
        idx = next.findIndex(x =>
            x.figi === figi
            && x.side === side
            && (!x.result || x.result.kind === 'pending' || x.result.kind === 'working' || x.result.kind === 'partial' || x.result.kind === 'open'),
        )
    }

    if (idx >= 0) {
        const cur = next[idx]
        next[idx] = {
            ...cur,
            figi: figi || cur.figi,
            ticker: tickerOf(figi || cur.figi),
            side: side !== 'info' ? side : cur.side,
            time: ts,
            order: { ...cur.order, ...order },
            result,
        }
    } else {
        next.unshift({
            id: tradeId != null
                ? `trade:${tradeId}`
                : signalId != null
                    ? `signal:${signalId}`
                    : `order:${orderId || figi}:${data?.time || Date.now()}`,
            figi,
            ticker: tickerOf(figi),
            side,
            time: ts,
            order,
            result,
        })
    }
    return next.slice(0, limit)
}

export interface SignalSummaryRow {
    figi: string
    ticker: string
    side: PipelineSide
    lastResult: string
    lastReason?: string
    lastKind: PipelineResultKind | 'none'
    lastTime: string
    ok: number
    skip: number
    fail: number
    /** Sort key: newest first */
    _sortTs: number
}

function classifyResultBucket(kind: PipelineResultKind | undefined): 'ok' | 'skip' | 'fail' | null {
    if (!kind) return null
    if (kind === 'filled' || kind === 'open' || kind === 'partial') return 'ok'
    if (kind === 'skipped' || kind === 'cancelled') return 'skip'
    if (kind === 'failed' || kind === 'rejected' || kind === 'error') return 'fail'
    return null
}

/** Aggregate pipeline events per symbol for Live signals summary table. */
export function buildSignalSummaryRows(items: TradePipelineItem[]): SignalSummaryRow[] {
    const byFigi = new Map<string, SignalSummaryRow>()

    for (const item of items) {
        const figi = String(item.figi || '').trim().toUpperCase()
        if (!figi) continue
        const kind = item.result?.kind
        const bucket = classifyResultBucket(kind)
        const itemTs = Math.max(
            parseTs(item.result?.time),
            parseTs(item.order?.time),
            parseTs(item.signal?.time),
            parseTs(item.time),
        )

        let row = byFigi.get(figi)
        if (!row) {
            row = {
                figi,
                ticker: item.ticker || figi,
                side: item.side,
                lastResult: item.result?.label || item.signal?.label || '-',
                lastReason: item.result?.reason,
                lastKind: kind || 'none',
                lastTime: item.result?.time || item.time || '-',
                ok: 0,
                skip: 0,
                fail: 0,
                _sortTs: itemTs,
            }
            byFigi.set(figi, row)
        }

        if (bucket === 'ok') row.ok += 1
        else if (bucket === 'skip') row.skip += 1
        else if (bucket === 'fail') row.fail += 1

        if (itemTs >= row._sortTs) {
            row._sortTs = itemTs
            row.ticker = item.ticker || row.ticker
            row.side = item.side !== 'info' ? item.side : row.side
            row.lastResult = item.result?.label || item.signal?.label || row.lastResult
            row.lastReason = item.result?.reason
            row.lastKind = kind || row.lastKind
            row.lastTime = item.result?.time || item.time || row.lastTime
        }
    }

    return [...byFigi.values()].sort((a, b) => b._sortTs - a._sortTs)
}
