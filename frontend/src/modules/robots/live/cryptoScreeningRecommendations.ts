/**
 * Live crypto-screening recommendations: concrete crypto_universe field changes.
 * Module is UI-agnostic — LivePage only renders the tip list.
 */

export type CryptoScreeningTip = {
    id: string
    /** Short label, e.g. «Объём 24h» */
    title: string
    /** Config path shown to user */
    field: string
    /** Human-readable current → suggested */
    change: string
    /** Why this helps */
    why: string
    rejectCount?: number
}

type TipRule = {
    title: string
    /** Key inside crypto_universe */
    key: string
    fieldLabel: string
    /** 'min' = lower threshold to accept more; 'max' = raise ceiling */
    direction: 'min' | 'max'
    /** Display unit for values */
    unit: 'usd' | 'price' | 'bps' | 'funding_pct' | 'ratio' | 'atr_pct' | 'none'
    why: string
}

const RULES: Record<string, TipRule> = {
    volume_below_min: {
        title: 'Объём 24h',
        key: 'min_volume_24h_usd',
        fieldLabel: 'crypto_universe.min_volume_24h_usd',
        direction: 'min',
        unit: 'usd',
        why: 'пропускать пары с меньшим суточным оборотом в отбор universe',
    },
    price_below_min: {
        title: 'Мин. цена',
        key: 'min_last_price',
        fieldLabel: 'crypto_universe.min_last_price',
        direction: 'min',
        unit: 'price',
        why: 'не отсекать дешёвые монеты на этапе screening',
    },
    spread_above_max: {
        title: 'Спред',
        key: 'max_spread_bps',
        fieldLabel: 'crypto_universe.max_spread_bps',
        direction: 'max',
        unit: 'bps',
        why: 'допускать более широкий bid/ask при отборе в пул',
    },
    spread_missing: {
        title: 'Спред (нет данных)',
        key: 'max_spread_bps',
        fieldLabel: 'crypto_universe.max_spread_bps',
        direction: 'max',
        unit: 'bps',
        why: 'ослабить фильтр, пока часть символов без котировки спреда; проверьте testnet/mainnet',
    },
    funding_below_min: {
        title: 'Funding (мин)',
        key: 'min_funding_rate',
        fieldLabel: 'crypto_universe.min_funding_rate',
        direction: 'min',
        unit: 'funding_pct',
        why: 'расширить нижнюю границу funding (в настройках UI — %, в конфиге — доля)',
    },
    funding_above_max: {
        title: 'Funding (макс)',
        key: 'max_funding_rate',
        fieldLabel: 'crypto_universe.max_funding_rate',
        direction: 'max',
        unit: 'funding_pct',
        why: 'не отсекать пары с более высоким funding',
    },
    oi_below_min: {
        title: 'Open Interest',
        key: 'min_open_interest_usd',
        fieldLabel: 'crypto_universe.min_open_interest_usd',
        direction: 'min',
        unit: 'usd',
        why: 'набрать больше контрактов с меньшим OI',
    },
    lsr_below_min: {
        title: 'LSR (мин)',
        key: 'min_lsr',
        fieldLabel: 'crypto_universe.min_lsr',
        direction: 'min',
        unit: 'ratio',
        why: 'расширить коридор Long/Short Ratio снизу',
    },
    lsr_above_max: {
        title: 'LSR (макс)',
        key: 'max_lsr',
        fieldLabel: 'crypto_universe.max_lsr',
        direction: 'max',
        unit: 'ratio',
        why: 'расширить коридор Long/Short Ratio сверху',
    },
    rvol_below_min: {
        title: 'RVOL',
        key: 'min_rvol',
        fieldLabel: 'crypto_universe.min_rvol',
        direction: 'min',
        unit: 'ratio',
        why: 'ослабить требование к всплеску относительного объёма',
    },
    atr_below_min: {
        title: 'ATR (мин)',
        key: 'min_atr_percent',
        fieldLabel: 'crypto_universe.min_atr_percent',
        direction: 'min',
        unit: 'atr_pct',
        why: 'пускать менее волатильные инструменты в universe',
    },
    atr_above_max: {
        title: 'ATR (макс)',
        key: 'max_atr_percent',
        fieldLabel: 'crypto_universe.max_atr_percent',
        direction: 'max',
        unit: 'atr_pct',
        why: 'не резать слишком волатильные пары на screening',
    },
}

function normalizeReason(raw: string): { reason: string; observed: number | null } {
    const s = String(raw || '').trim().toLowerCase()
    if (!s) return { reason: '', observed: null }
    const [head, tail] = s.split(':')
    const base = head.trim().replace(/\s+/g, '_')
    let observed: number | null = null
    if (tail != null && tail !== '') {
        const n = Number(tail)
        if (Number.isFinite(n)) observed = n
    }
    if (RULES[base]) return { reason: base, observed }

    if (s.includes('volume') && (s.includes('below') || s.includes('min'))) {
        return { reason: 'volume_below_min', observed }
    }
    if (s.includes('price') && (s.includes('below') || s.includes('min'))) {
        return { reason: 'price_below_min', observed }
    }
    if (s.includes('spread') && s.includes('missing')) return { reason: 'spread_missing', observed }
    if (s.includes('spread') && (s.includes('above') || s.includes('max'))) {
        return { reason: 'spread_above_max', observed }
    }
    if (s.includes('funding') && (s.includes('below') || s.includes('min'))) {
        return { reason: 'funding_below_min', observed }
    }
    if (s.includes('funding') && (s.includes('above') || s.includes('max'))) {
        return { reason: 'funding_above_max', observed }
    }
    if (s.includes('open_interest') || base.startsWith('oi_')) {
        return { reason: 'oi_below_min', observed }
    }
    if (s.includes('lsr') && (s.includes('below') || s.includes('min'))) {
        return { reason: 'lsr_below_min', observed }
    }
    if (s.includes('lsr') && (s.includes('above') || s.includes('max'))) {
        return { reason: 'lsr_above_max', observed }
    }
    if (s.includes('rvol')) return { reason: 'rvol_below_min', observed }
    if (s.includes('atr') && (s.includes('below') || s.includes('min'))) {
        return { reason: 'atr_below_min', observed }
    }
    if (s.includes('atr') && (s.includes('above') || s.includes('max'))) {
        return { reason: 'atr_above_max', observed }
    }
    return { reason: base, observed }
}

function readConfigNumber(cu: Record<string, unknown>, key: string): number | null {
    const v = cu[key]
    if (v == null || v === '') return null
    const n = Number(v)
    return Number.isFinite(n) ? n : null
}

/** Format stored config value for display (funding stored as fraction → %). */
function formatStored(value: number, unit: TipRule['unit']): string {
    if (unit === 'funding_pct') {
        return `${(value * 100).toFixed(4)}%`
    }
    if (unit === 'usd') return Math.round(value).toLocaleString('ru-RU')
    if (unit === 'bps') return String(Math.round(value))
    if (unit === 'price') return value.toPrecision(4)
    if (unit === 'atr_pct') return `${Number(value.toFixed(2))}%`
    if (unit === 'ratio') return String(Number(value.toFixed(4)))
    return String(value)
}

/** Suggest a looser threshold from current config (+ optional observed reject metric). */
function suggestValue(
    current: number,
    direction: 'min' | 'max',
    unit: TipRule['unit'],
    observed: number | null,
): number {
    if (direction === 'min') {
        // Aim below typical rejected metric, or cut threshold in half.
        let next = current * 0.5
        if (observed != null && Number.isFinite(observed)) {
            // observed for funding/oi is raw; for funding it's rate fraction
            const obs = unit === 'funding_pct' ? observed : observed
            next = Math.min(next, obs * 0.9)
        }
        if (unit === 'bps') return Math.max(1, Math.round(next))
        if (unit === 'usd') return Math.max(0, Math.round(next))
        if (unit === 'funding_pct') return Number(next.toFixed(8))
        if (unit === 'atr_pct') return Math.max(0.1, Number(next.toFixed(2)))
        if (unit === 'ratio') return Math.max(0, Number(next.toFixed(4)))
        if (unit === 'price') return Math.max(0, Number(next.toPrecision(4)))
        return next
    }
    // max: raise ceiling
    let next = current * 1.5
    if (observed != null && Number.isFinite(observed)) {
        const obs = observed
        next = Math.max(next, obs * 1.1)
    }
    if (unit === 'bps') return Math.max(current + 5, Math.round(next))
    if (unit === 'usd') return Math.round(next)
    if (unit === 'funding_pct') return Number(next.toFixed(8))
    if (unit === 'atr_pct') return Number(next.toFixed(2))
    if (unit === 'ratio') return Number(next.toFixed(4))
    return next
}

function buildChangeLine(
    rule: TipRule,
    current: number | null,
    suggested: number | null,
): string {
    if (current == null && suggested == null) {
        return `${rule.fieldLabel}: задайте более мягкий порог в настройках робота`
    }
    if (current == null && suggested != null) {
        return `${rule.fieldLabel}: установить ${formatStored(suggested, rule.unit)}`
    }
    if (current != null && suggested == null) {
        return `${rule.fieldLabel}: сейчас ${formatStored(current, rule.unit)} — ослабьте порог`
    }
    const a = formatStored(current as number, rule.unit)
    const b = formatStored(suggested as number, rule.unit)
    if (a === b) {
        return `${rule.fieldLabel}: сейчас ${a} — сдвиньте ещё мягче после следующего screening`
    }
    return `${rule.fieldLabel}: ${a} → ${b}`
}

/**
 * Build concrete tips from today's reject rows + robot crypto_universe config.
 */
export function buildCryptoScreeningRecommendations(
    rows: Array<{ filter_result?: string; reject_reason?: string | null }>,
    cryptoUniverse: Record<string, unknown> | null | undefined,
    maxTips = 5,
): CryptoScreeningTip[] {
    const rejected = (rows || []).filter((r) => {
        const v = String(r.filter_result || '').toLowerCase()
        return v === 'reject' || v === 'rejected'
    })

    type Agg = { count: number; observed: number | null }
    const byReason = new Map<string, Agg>()
    for (const row of rejected) {
        const { reason, observed } = normalizeReason(String(row.reject_reason || ''))
        if (!reason || !RULES[reason]) continue
        const prev = byReason.get(reason) || { count: 0, observed: null }
        prev.count += 1
        // keep a representative observed (median-ish: last non-null is fine for tip)
        if (observed != null) prev.observed = observed
        byReason.set(reason, prev)
    }

    const ranked = [...byReason.entries()].sort((a, b) => b[1].count - a[1].count)
    const cu = cryptoUniverse && typeof cryptoUniverse === 'object' ? cryptoUniverse : {}
    const tips: CryptoScreeningTip[] = []

    for (const [reason, agg] of ranked) {
        const rule = RULES[reason]
        if (!rule) continue
        const current = readConfigNumber(cu, rule.key)
        const suggested =
            current != null
                ? suggestValue(current, rule.direction, rule.unit, agg.observed)
                : null
        tips.push({
            id: reason,
            title: rule.title,
            field: rule.fieldLabel,
            change: buildChangeLine(rule, current, suggested),
            why: rule.why,
            rejectCount: agg.count,
        })
        if (tips.length >= maxTips) break
    }

    if (tips.length === 0 && rejected.length > 0) {
        tips.push({
            id: 'generic_filters',
            title: 'Фильтры screening',
            field: 'crypto_universe.*',
            change: 'Ослабьте min_volume_24h_usd и увеличьте max_spread_bps (часто режут сильнее всего)',
            why: 'много reject без распознанного кода — начните с объёма и спреда',
            rejectCount: rejected.length,
        })
    }

    if (tips.length === 0 && (rows || []).length === 0) {
        tips.push({
            id: 'no_data',
            title: 'Нет данных за сегодня',
            field: '—',
            change: 'Запустите «crypto-screening», затем при необходимости ослабьте пороги crypto_universe',
            why: 'без строк screening нечего анализировать',
        })
    }

    const accepted = (rows || []).filter((r) => {
        const v = String(r.filter_result || '').toLowerCase()
        return v === 'accept' || v === 'accepted'
    }).length
    if (accepted === 0 && rejected.length > 0 && tips.length < maxTips
        && !tips.some((t) => t.id === 'zero_accept')) {
        tips.push({
            id: 'zero_accept',
            title: '0 accepted',
            field: 'crypto_universe.min_volume_24h_usd / max_spread_bps',
            change: 'Снизьте объём 24h вдвое и поднимите max_spread_bps на +50%',
            why: 'ни один символ не прошёл отбор — эти два фильтра обычно самые жёсткие',
        })
    }

    return tips.slice(0, maxTips)
}
