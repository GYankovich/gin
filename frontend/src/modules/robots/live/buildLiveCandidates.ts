import type { PipelineResultKind, PipelineSide, SignalSummaryRow } from '@/pages/live/tradePipeline'

export type LiveCandidateRow = {
    key: string
    figi: string
    ticker: string
    inScreening: boolean
    inPortfolio: boolean
    sourceLabel: string
    side: PipelineSide | null
    signalAtRaw: string | null
    signalAtLabel: string
    lastSignalLabel: string
    lastReason: string
    lastKind: PipelineResultKind | 'none'
    hasOpenOrder: boolean
    _sortTs: number
}

function normId(value: unknown): string {
    return String(value || '').trim().toUpperCase()
}

/** dd.mm HH:mm for candidate table */
export function formatCandidateStamp(value?: string | Date | null): string {
    if (value == null || value === '') return '—'
    const d = value instanceof Date ? value : new Date(value)
    if (Number.isNaN(d.getTime())) {
        const raw = String(value).trim()
        return raw || '—'
    }
    const dd = String(d.getDate()).padStart(2, '0')
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    return `${dd}.${mm} ${hh}:${mi}`
}

function sourceLabel(inScreening: boolean, inPortfolio: boolean): string {
    if (inScreening && inPortfolio) return 'портфель + screening'
    if (inPortfolio) return 'портфель'
    if (inScreening) return 'screening'
    return '—'
}

function parseTs(value: unknown): number {
    if (value == null || value === '') return 0
    if (typeof value === 'number' && Number.isFinite(value)) return value
    const t = Date.parse(String(value))
    return Number.isFinite(t) ? t : 0
}

type UniverseLike = { figi?: string; ticker?: string; symbol?: string }
type PortfolioLike = { figi?: string; ticker?: string }
type OrderLike = { figi?: string; symbol?: string; ticker?: string }

type Acc = {
    figi: string
    ticker: string
    inScreening: boolean
    inPortfolio: boolean
}

/**
 * Watchlist for Live: accepted screening ∪ portfolio positions,
 * joined with last signal / pipeline outcome.
 */
export function buildLiveCandidates(args: {
    acceptedUniverse: UniverseLike[]
    portfolio: PortfolioLike[]
    signalSummary: SignalSummaryRow[]
    recentSignals?: Array<{
        figi?: string
        ticker?: string
        symbol?: string
        signal_type?: string
        created_at?: string
        time?: string
    }>
    openOrders?: OrderLike[]
}): LiveCandidateRow[] {
    const byPrimary = new Map<string, Acc>()
    const aliasToPrimary = new Map<string, string>()

    const resolvePrimary = (figi: string, ticker: string): string => {
        const a = aliasToPrimary.get(figi)
        const b = aliasToPrimary.get(ticker)
        return a || b || figi || ticker
    }

    const upsert = (figiRaw: string, tickerRaw: string, patch: { inScreening?: boolean; inPortfolio?: boolean }) => {
        const ticker = normId(tickerRaw)
        const figi = normId(figiRaw) || ticker
        if (!figi && !ticker) return
        const primary = resolvePrimary(figi, ticker) || figi || ticker
        let row = byPrimary.get(primary)
        if (!row) {
            row = {
                figi: figi || ticker,
                ticker: ticker || figi,
                inScreening: false,
                inPortfolio: false,
            }
            byPrimary.set(primary, row)
        } else {
            if (figi) row.figi = figi
            if (ticker) row.ticker = ticker
        }
        if (patch.inScreening) row.inScreening = true
        if (patch.inPortfolio) row.inPortfolio = true
        aliasToPrimary.set(row.figi, primary)
        if (row.ticker) aliasToPrimary.set(row.ticker, primary)
    }

    for (const u of args.acceptedUniverse || []) {
        upsert(normId(u.figi), normId(u.ticker || u.symbol), { inScreening: true })
    }
    for (const p of args.portfolio || []) {
        upsert(normId(p.figi), normId(p.ticker), { inPortfolio: true })
    }

    const summaryByKey = new Map<string, SignalSummaryRow>()
    for (const s of args.signalSummary || []) {
        const figi = normId(s.figi)
        const ticker = normId(s.ticker)
        if (figi) summaryByKey.set(figi, s)
        if (ticker) summaryByKey.set(ticker, s)
    }

    const latestSignalByKey = new Map<string, { side: string; at: string; ts: number }>()
    for (const s of args.recentSignals || []) {
        const figi = normId(s.figi || s.symbol || s.ticker)
        const ticker = normId(s.ticker || s.symbol)
        const at = String(s.created_at || s.time || '')
        const ts = parseTs(at)
        if (!figi && !ticker) continue
        const side = String(s.signal_type || '').toLowerCase()
        for (const k of [figi, ticker].filter(Boolean)) {
            const prev = latestSignalByKey.get(k)
            if (!prev || ts >= prev.ts) {
                latestSignalByKey.set(k, { side, at, ts })
            }
        }
    }

    const openOrderKeys = new Set<string>()
    for (const o of args.openOrders || []) {
        const figi = normId(o.figi || o.symbol || o.ticker)
        const ticker = normId(o.ticker || o.symbol)
        if (figi) openOrderKeys.add(figi)
        if (ticker) openOrderKeys.add(ticker)
    }

    const rows: LiveCandidateRow[] = []
    for (const acc of byPrimary.values()) {
        const summary =
            summaryByKey.get(acc.figi)
            || summaryByKey.get(acc.ticker)
            || null
        const latestSig =
            latestSignalByKey.get(acc.figi)
            || latestSignalByKey.get(acc.ticker)
            || null

        const signalAtRaw = latestSig?.at
            || (summary && summary.lastTime !== '-' ? summary.lastTime : null)
            || null
        const signalTs = Math.max(latestSig?.ts || 0, summary?._sortTs || 0)

        let lastSignalLabel = 'нет сигнала'
        let lastReason = 'в universe, ждёт бар'
        let lastKind: PipelineResultKind | 'none' = 'none'
        let side: PipelineSide | null = null

        if (summary && (summary._sortTs > 0 || summary.lastResult !== '-')) {
            side = summary.side !== 'info' ? summary.side : null
            const sideTxt = side ? side.toUpperCase() : null
            lastKind = summary.lastKind
            lastSignalLabel = sideTxt
                ? `${sideTxt} · ${summary.lastResult}`
                : summary.lastResult
            lastReason = summary.lastReason || '—'
        } else if (latestSig) {
            side = (latestSig.side === 'buy' || latestSig.side === 'sell')
                ? latestSig.side
                : null
            lastSignalLabel = side ? `${side.toUpperCase()} · сигнал` : 'сигнал'
            lastReason = '—'
        } else if (!acc.inScreening && acc.inPortfolio) {
            lastReason = 'в портфеле, вне screening'
        }

        const hasOpenOrder = openOrderKeys.has(acc.figi) || openOrderKeys.has(acc.ticker)

        rows.push({
            key: acc.figi || acc.ticker,
            figi: acc.figi,
            ticker: acc.ticker,
            inScreening: acc.inScreening,
            inPortfolio: acc.inPortfolio,
            sourceLabel: sourceLabel(acc.inScreening, acc.inPortfolio),
            side,
            signalAtRaw,
            signalAtLabel: signalAtRaw ? formatCandidateStamp(signalAtRaw) : '—',
            lastSignalLabel,
            lastReason,
            lastKind,
            hasOpenOrder,
            _sortTs: signalTs,
        })
    }

    return rows.sort((a, b) => {
        if (a.inPortfolio !== b.inPortfolio) return a.inPortfolio ? -1 : 1
        if (a.hasOpenOrder !== b.hasOpenOrder) return a.hasOpenOrder ? -1 : 1
        if (a._sortTs !== b._sortTs) return b._sortTs - a._sortTs
        return a.ticker.localeCompare(b.ticker)
    })
}
