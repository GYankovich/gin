/** Отображение инструмента: тикер в UI, FIGI — во внутренних ключах и tooltip. */

export function buildTickerByFigiMap(
    ...sources: Array<Record<string, unknown> | Map<string, string> | null | undefined>
): Map<string, string> {
    const out = new Map<string, string>()
    for (const src of sources) {
        if (!src) continue
        if (src instanceof Map) {
            for (const [figi, ticker] of src.entries()) {
                const fg = String(figi).trim().toUpperCase()
                const tk = String(ticker).trim().toUpperCase()
                if (fg && tk) out.set(fg, tk)
            }
            continue
        }
        for (const [figi, ticker] of Object.entries(src)) {
            const fg = String(figi).trim().toUpperCase()
            const tk = String(ticker ?? '').trim().toUpperCase()
            if (fg && tk) out.set(fg, tk)
        }
    }
    return out
}

export function tickerFromFigi(figi: string, tickerByFigi: Map<string, string>): string {
    const raw = String(figi || '').trim()
    if (!raw) return '—'
    const fg = raw.toUpperCase()
    const mapped = tickerByFigi.get(fg) ?? tickerByFigi.get(raw)
    if (mapped) return mapped
    if (!fg.startsWith('BBG') && fg.length <= 16) return fg
    return fg.length > 10 ? fg.slice(-8) : fg
}

export function instrumentTitle(figi: string, tickerByFigi: Map<string, string>): string {
    const label = tickerFromFigi(figi, tickerByFigi)
    const fg = String(figi || '').trim()
    if (!fg || label === fg || label === fg.toUpperCase()) return fg
    return `${label} · ${fg}`
}
