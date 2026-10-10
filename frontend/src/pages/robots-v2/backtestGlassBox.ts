import type {
    BacktestDecisionPacket,
    BacktestExecutionEvent,
    BacktestFeeSummary,
    BacktestHoldingPosition,
    BacktestObservability,
    BacktestPortfolioSnapshot,
    BacktestRejectReasonCount,
    BacktestUniverseMembershipItem,
} from '@/types/robot'

const DEFAULT_SIGNAL_CAP = 25_000
const EXECUTION_NOTE_RU = 'Исполнение на открытии следующего бара · без look-ahead'

export function asRecord(v: unknown): Record<string, unknown> {
    return v && typeof v === 'object' ? (v as Record<string, unknown>) : {}
}

export function pickStr(...vals: unknown[]): string | null {
    for (const v of vals) {
        if (v == null) continue
        const s = String(v).trim()
        if (s) return s
    }
    return null
}

export function pickNum(...vals: unknown[]): number | null {
    for (const v of vals) {
        if (v == null) continue
        const n = Number(v)
        if (Number.isFinite(n)) return n
    }
    return null
}

export function signalPayload(row: Record<string, unknown>): Record<string, unknown> {
    return asRecord(row.payload)
}

export function rowCycleId(row: Record<string, unknown>): string | null {
    const p = signalPayload(row)
    return pickStr(row.cycle_id, row.cycleId, p.cycle_id, p.cycleId)
}

export function rowRejectReason(row: Record<string, unknown>): string | null {
    const p = signalPayload(row)
    return pickStr(row.reject_reason, row.rejectReason, p.reject_reason, p.rejectReason)
}

export function rowStatus(row: Record<string, unknown>): string | null {
    const p = signalPayload(row)
    const raw = pickStr(row.status, p.status)
    if (raw) return raw.toLowerCase()
    if (row.was_executed === 1 || row.was_executed === true) return 'filled'
    return null
}

export function rowKind(row: Record<string, unknown>): string | null {
    const p = signalPayload(row)
    return pickStr(row.kind, p.kind)
}

export function rowReason(row: Record<string, unknown>): string | null {
    const p = signalPayload(row)
    return pickStr(row.reason, p.reason, row.kind, p.kind)
}

export function resolveObservability(args: {
    topLevel?: BacktestObservability | null
    fromPayload?: BacktestObservability | null
    signals: Array<Record<string, unknown>>
    historyStats?: Record<string, unknown> | null
    executionModel?: unknown
}): BacktestObservability {
    const base: BacktestObservability = {
        ...(args.fromPayload || {}),
        ...(args.topLevel || {}),
    }

    const histTrunc = args.historyStats?.signals_truncated
    const truncated =
        Boolean(base.signals_truncated)
        || histTrunc === true
        || histTrunc === 1
        || Number(histTrunc) > 0

    const execRaw = base.execution_model
        ?? asRecord(args.executionModel)
        ?? null
    const execObj = asRecord(execRaw)
    const code = pickStr(
        execObj.code,
        execObj.fill_on,
        execObj.fillOn,
        execObj.model,
    )
    const lookAhead = execObj.look_ahead ?? execObj.lookAhead
    const honestCode =
        !code || code.toUpperCase() === 'BAR_CLOSE'
            ? 'NEXT_BAR_OPEN'
            : code.toUpperCase()
    // Backend default label is English; UX-05 honesty banner must stay RU for NEXT_BAR_OPEN.
    const rawLabel = pickStr(execObj.label)
    const honestLabel =
        honestCode === 'NEXT_BAR_OPEN'
            ? EXECUTION_NOTE_RU
            : (rawLabel || EXECUTION_NOTE_RU)

    const rejectCounts =
        Array.isArray(base.reject_reason_counts) && base.reject_reason_counts.length > 0
            ? base.reject_reason_counts
            : deriveRejectCounts(args.signals)

    const statusCounts =
        base.status_counts && Object.keys(base.status_counts).length > 0
            ? base.status_counts
            : deriveStatusCounts(args.signals)

    return {
        ...base,
        execution_model: {
            code: honestCode,
            label: honestLabel,
            look_ahead: lookAhead === true ? true : false,
            signal_on: pickStr(execObj.signal_on, execObj.signalOn),
            fill_on: pickStr(execObj.fill_on, execObj.fillOn) || 'NEXT_BAR_OPEN',
            model: pickStr(execObj.model),
        },
        signals_logged:
            base.signals_logged
            ?? pickNum(args.historyStats?.signals, args.signals.length)
            ?? args.signals.length,
        signals_truncated: truncated,
        signal_log_cap: base.signal_log_cap ?? DEFAULT_SIGNAL_CAP,
        reject_reason_counts: rejectCounts,
        status_counts: statusCounts,
    }
}

export function deriveRejectCounts(signals: Array<Record<string, unknown>>): BacktestRejectReasonCount[] {
    const map = new Map<string, number>()
    for (const s of signals) {
        const code = rowRejectReason(s)
        if (!code) continue
        const status = rowStatus(s)
        if (status && status !== 'rejected' && status !== 'deferred') {
            // still count explicit reject_reason
        }
        map.set(code, (map.get(code) || 0) + 1)
    }
    return [...map.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([code, count]) => ({ code, count }))
}

export function deriveStatusCounts(signals: Array<Record<string, unknown>>): {
    filled: number
    rejected: number
    deferred: number
    ignored: number
} {
    let filled = 0
    let rejected = 0
    let deferred = 0
    let ignored = 0
    for (const s of signals) {
        const st = rowStatus(s)
        if (st === 'filled' || st === 'executed') filled += 1
        else if (st === 'deferred') deferred += 1
        else if (st === 'ignored') ignored += 1
        else if (st === 'rejected' || rowRejectReason(s)) rejected += 1
    }
    return { filled, rejected, deferred, ignored }
}

export function packetFromTrade(t: Record<string, unknown>): BacktestDecisionPacket {
    const p = signalPayload(t)
    return {
        id: (t.id as string | number | undefined) ?? null,
        source: 'trade',
        cycle_id: rowCycleId(t),
        signal_time: pickStr(t.signal_time, p.signal_time),
        bar_time: pickStr(t.bar_time, t.time, p.bar_time),
        ticker: pickStr(t.ticker, t.figi, p.ticker, p.figi),
        figi: pickStr(t.figi, t.ticker, p.figi),
        kind: rowKind(t),
        side: pickStr(t.side, p.side)?.toUpperCase() ?? null,
        status: rowStatus(t) || 'filled',
        strategy_reason: rowReason(t),
        reject_reason: rowRejectReason(t),
        quantity: pickNum(t.quantity, p.quantity),
        price: pickNum(t.price, t.executed_price, p.price),
        pnl_net: pickNum(t.pnl_net, p.pnl_net),
        linked_trade_ids: t.id != null ? [t.id as string | number] : null,
        execution_note: EXECUTION_NOTE_RU,
    }
}

export function packetFromSignal(s: Record<string, unknown>): BacktestDecisionPacket {
    const p = signalPayload(s)
    const linked = s.linked_trade_ids ?? p.linked_trade_ids ?? p.linkedTradeIds
    const rawMetrics = s.decision_metrics ?? p.decision_metrics
    return {
        id: (s.id as string | number | undefined) ?? null,
        source: 'signal',
        cycle_id: rowCycleId(s),
        signal_time: pickStr(s.signal_time, s.created_at, p.signal_time),
        bar_time: pickStr(s.bar_time, p.bar_time),
        ticker: pickStr(s.ticker, s.figi, p.ticker, p.figi),
        figi: pickStr(s.figi, s.ticker, p.figi),
        kind: rowKind(s),
        side: pickStr(s.signal_type, s.side, p.side)?.toUpperCase() ?? null,
        status: rowStatus(s),
        strategy_reason: rowReason(s),
        reject_reason: rowRejectReason(s),
        decision_code: pickStr(s.decision_code, p.decision_code),
        decision_message: pickStr(s.decision_message, p.decision_message),
        decision_metrics:
            rawMetrics && typeof rawMetrics === 'object' && !Array.isArray(rawMetrics)
                ? rawMetrics as Record<string, unknown>
                : null,
        quantity: pickNum(s.quantity, p.quantity),
        price: pickNum(s.price, p.price),
        pnl_net: pickNum(s.pnl_net, p.pnl_net),
        linked_trade_ids: Array.isArray(linked) ? linked as Array<string | number> : null,
        execution_note: EXECUTION_NOTE_RU,
    }
}

export function mergeCycleBundle(
    base: BacktestDecisionPacket,
    bundle: {
        cycle_id?: string
        signals?: Array<Record<string, unknown>>
        trades?: Array<Record<string, unknown>>
        orders?: Array<Record<string, unknown>>
        execution_events?: BacktestExecutionEvent[]
        config_risk_excerpt?: Record<string, unknown>
    } | null,
): BacktestDecisionPacket & {
    config_risk_excerpt?: Record<string, unknown>
    execution_events?: BacktestExecutionEvent[]
} {
    if (!bundle) return base
    const sig = bundle.signals?.[0]
    const tr = bundle.trades?.[0]
    const fromSig = sig ? packetFromSignal(sig) : null
    const fromTr = tr ? packetFromTrade(tr) : null
    const linked = (bundle.trades || [])
        .map(t => t.id)
        .filter((x): x is string | number => x != null) as Array<string | number>
    return {
        ...base,
        ...(fromTr || {}),
        ...(fromSig || {}),
        ...base,
        cycle_id: base.cycle_id || bundle.cycle_id || fromSig?.cycle_id || fromTr?.cycle_id,
        strategy_reason: base.strategy_reason || fromSig?.strategy_reason || fromTr?.strategy_reason,
        reject_reason: base.reject_reason || fromSig?.reject_reason,
        decision_code: base.decision_code || fromSig?.decision_code,
        decision_message: base.decision_message || fromSig?.decision_message,
        decision_metrics: base.decision_metrics || fromSig?.decision_metrics,
        status: base.status || fromSig?.status || fromTr?.status,
        linked_trade_ids: linked.length ? linked : base.linked_trade_ids,
        execution_note: EXECUTION_NOTE_RU,
        config_risk_excerpt: bundle.config_risk_excerpt,
        execution_events: bundle.execution_events,
    }
}

/** Prefer fill bar_time when filled; else signal_time (UX-05 P2). */
export function aroundFromPacket(packet: BacktestDecisionPacket | null | undefined): string | null {
    if (!packet) return null
    const status = String(packet.status || '').toLowerCase()
    if ((status === 'filled' || status === 'executed') && packet.bar_time) {
        return packet.bar_time
    }
    return pickStr(packet.signal_time, packet.bar_time)
}

export function tickerFromPacket(packet: BacktestDecisionPacket | null | undefined): string | null {
    if (!packet) return null
    return pickStr(packet.ticker, packet.figi)?.toUpperCase() ?? null
}

const EXEC_STATUS_LABELS: Record<string, string> = {
    deferred: 'Отложено',
    filled: 'Исполнено',
    executed: 'Исполнено',
    rejected: 'Отказ',
    dropped: 'Сброшено',
    dropped_deferred: 'Сброшено',
    resting: 'В рынке',
}

export function executionStatusLabel(status: string | null | undefined): string {
    if (!status) return '—'
    const key = String(status).trim().toLowerCase()
    return EXEC_STATUS_LABELS[key] || String(status)
}

export function executionStatusTone(status: string | null | undefined): 'warn' | 'up' | 'down' | 'neutral' {
    const key = String(status || '').toLowerCase()
    if (key === 'deferred' || key === 'resting') return 'warn'
    if (key === 'filled' || key === 'executed') return 'up'
    if (key === 'rejected' || key === 'dropped' || key === 'dropped_deferred') return 'down'
    return 'neutral'
}

export function anatomyCaption(
    stages: string[] | undefined,
    historyStats: Record<string, unknown> | null | undefined,
    fundingChargesTotal: number | null | undefined,
): { chips: string[]; fundingHint: string | null } {
    const chips: string[] = []
    if (stages && stages.length > 0) {
        chips.push(...stages)
    } else if (historyStats) {
        const warm = historyStats.warmup_bars
        const traded = historyStats.traded_bars
        const skipped = historyStats.skipped_schedule
        const bars = historyStats.bars
        const tickers = historyStats.tickers
        if (bars != null) chips.push(`Баров: ${bars}`)
        if (tickers != null) chips.push(`Тикеров: ${tickers}`)
        if (warm != null) chips.push(`Warmup: ${warm}`)
        if (traded != null) chips.push(`Торговых баров: ${traded}`)
        if (skipped != null) chips.push(`Пропуск расписания: ${skipped}`)
    }

    const fundingEvents = Number(historyStats?.funding_events ?? 0)
    const fundingTotal = Number(fundingChargesTotal ?? 0)
    let fundingHint: string | null = null
    if ((Number.isFinite(fundingTotal) && fundingTotal !== 0) || fundingEvents > 0) {
        const amt = Number.isFinite(fundingTotal)
            ? fundingTotal.toLocaleString('ru-RU', { maximumFractionDigits: 4 })
            : String(fundingEvents)
        fundingHint = `Funding: ${amt}`
    }
    return { chips, fundingHint }
}

export const GLASS_BOX_EXECUTION_COPY = EXECUTION_NOTE_RU
export const SIGNAL_PAGE_SIZE = 200
export const SIGNAL_PAGINATE_THRESHOLD = 5_000

export type HoldingsSampleMode = 'marker' | 'start' | 'mid' | 'end'

export function resolveFeeSummary(
    topLevel?: BacktestFeeSummary | null,
    fromPayload?: BacktestFeeSummary | null,
): BacktestFeeSummary | null {
    const raw = topLevel || fromPayload
    if (!raw || typeof raw !== 'object') return null
    const makerTakerSum = (raw.maker_commission != null || raw.taker_commission != null)
        ? Number(raw.maker_commission || 0) + Number(raw.taker_commission || 0)
        : null
    const commission = pickNum(
        raw.commission_total,
        raw.total_commission,
        makerTakerSum,
    )
    const funding = pickNum(raw.funding_total, raw.total_funding)
    const events = pickNum(raw.funding_events)
    const tax = pickNum(raw.tax_total)
    return {
        commission_total: commission,
        funding_total: funding,
        funding_events: events,
        tax_total: tax,
    }
}

/** Hide zone M when fee_summary absent / all-zero. */
export function feeSummaryVisible(fee: BacktestFeeSummary | null | undefined): boolean {
    if (!fee) return false
    const c = Number(fee.commission_total ?? 0)
    const f = Number(fee.funding_total ?? 0)
    const e = Number(fee.funding_events ?? 0)
    const tax = fee.tax_total
    return (Number.isFinite(c) && c !== 0)
        || (Number.isFinite(f) && f !== 0)
        || (Number.isFinite(e) && e > 0)
        || (tax != null && Number.isFinite(Number(tax)) && Number(tax) !== 0)
}

export function snapshotTimeIso(snap: BacktestPortfolioSnapshot): string | null {
    return pickStr(snap.snapshot_time, snap.time)
}

export function snapshotTimeSec(snap: BacktestPortfolioSnapshot): number | null {
    const iso = snapshotTimeIso(snap)
    if (!iso) return null
    const sec = Math.floor(new Date(iso).getTime() / 1000)
    return Number.isFinite(sec) ? sec : null
}

export function normalizeHoldings(snap: BacktestPortfolioSnapshot | null | undefined): {
    holdings: BacktestHoldingPosition[]
    count: number
    legacyCountOnly: boolean
} {
    if (!snap) return { holdings: [], count: 0, legacyCountOnly: false }
    const positions = snap.positions
    if (Array.isArray(positions)) {
        const holdings = positions.filter(p => p && typeof p === 'object') as BacktestHoldingPosition[]
        const count = Number(snap.positions_count ?? holdings.length) || holdings.length
        return { holdings, count, legacyCountOnly: false }
    }
    if (typeof positions === 'number' && Number.isFinite(positions)) {
        return { holdings: [], count: positions, legacyCountOnly: positions > 0 }
    }
    const count = Number(snap.positions_count ?? 0)
    if (Number.isFinite(count) && count > 0) {
        return { holdings: [], count, legacyCountOnly: true }
    }
    return { holdings: [], count: 0, legacyCountOnly: false }
}

/** True when run only has count-style positions (pre-P1). */
export function snapshotsAreLegacyCountOnly(snaps: BacktestPortfolioSnapshot[]): boolean {
    if (!snaps.length) return false
    let sawCount = false
    for (const s of snaps) {
        const n = normalizeHoldings(s)
        if (n.holdings.length > 0) return false
        if (n.legacyCountOnly || n.count > 0) sawCount = true
    }
    return sawCount
}

export function pickSnapshotByMode(
    snaps: BacktestPortfolioSnapshot[],
    mode: HoldingsSampleMode,
    markerTimeSec: number | null,
): BacktestPortfolioSnapshot | null {
    if (!snaps.length) return null
    const sorted = [...snaps].sort((a, b) => {
        const sa = snapshotTimeSec(a) ?? 0
        const sb = snapshotTimeSec(b) ?? 0
        return sa - sb
    })
    if (mode === 'start') return sorted[0] ?? null
    if (mode === 'end') return sorted[sorted.length - 1] ?? null
    if (mode === 'mid') return sorted[Math.floor((sorted.length - 1) / 2)] ?? null
    // marker — nearest to pin; fall back to end
    if (markerTimeSec == null) return sorted[sorted.length - 1] ?? null
    let best = sorted[0]
    let bestDist = Infinity
    for (const s of sorted) {
        const sec = snapshotTimeSec(s)
        if (sec == null) continue
        const d = Math.abs(sec - markerTimeSec)
        if (d < bestDist) {
            bestDist = d
            best = s
        }
    }
    return best ?? null
}

export type UniverseDayRow = {
    id: string
    trade_date: string
    size: number
    adds: number
    drops: number
    tickers: string[]
    added: string[]
    dropped: string[]
}

export function groupUniverseByDay(items: BacktestUniverseMembershipItem[]): UniverseDayRow[] {
    const byDay = new Map<string, Set<string>>()
    for (const it of items) {
        const d = String(it.trade_date || '').slice(0, 10)
        const t = String(it.ticker || '').trim().toUpperCase()
        if (!d || !t) continue
        if (!byDay.has(d)) byDay.set(d, new Set())
        byDay.get(d)!.add(t)
    }
    const dates = [...byDay.keys()].sort()
    const rows: UniverseDayRow[] = []
    let prev: Set<string> = new Set()
    for (const d of dates) {
        const set = byDay.get(d) || new Set()
        const tickers = [...set].sort()
        const added = tickers.filter(t => !prev.has(t))
        const dropped = [...prev].filter(t => !set.has(t)).sort()
        rows.push({
            id: d,
            trade_date: d,
            size: tickers.length,
            adds: added.length,
            drops: dropped.length,
            tickers,
            added,
            dropped,
        })
        prev = set
    }
    return rows
}
