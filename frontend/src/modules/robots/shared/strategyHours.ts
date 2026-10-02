/** Small time helpers used by robot config builders (ex-testing strategyPresets). */

export function stripTradingHoursMsk(s: string): string {
    return String(s || '')
        .replace(/\s*MSK\s*$/i, '')
        .trim()
}

export function toRiskMskTime(display: string, fallbackMsk: string): string {
    const d = String(display || '').trim()
    if (!d) return fallbackMsk
    if (/msk/i.test(d)) return d
    return `${d} MSK`
}
