/** Backtest progress unit labels (moved out of deprecated /testing pages). */

/** OsEngine prefetch encodes units as tickers*100 + download%. */
export function formatBacktestPhaseUnits(
    runPhase: string | null | undefined,
    done: number | null | undefined,
    total: number | null | undefined,
): string | null {
    if (total == null || total <= 0 || done == null) return null
    const phase = String(runPhase || '').toLowerCase()
    if (phase === 'prefetching_osengine_candles' && total >= 100 && total % 100 === 0) {
        const tickers = total / 100
        const completed = Math.floor(done / 100)
        const pct = done % 100
        if (pct > 0 && completed < tickers) {
            return `${completed + 1}/${tickers} · ${pct}%`
        }
        return `${Math.min(completed, tickers)}/${tickers}`
    }
    return `${done} / ${total}`
}
