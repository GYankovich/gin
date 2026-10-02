import type { AccountSummary } from '@/types/api'

export function isBybitPortfolioAccount(
    account: Pick<AccountSummary, 'account_id' | 'type'> | null | undefined,
): boolean {
    if (!account) return false
    const ext = String(account.account_id || '').toUpperCase()
    if (ext.startsWith('BYBIT_')) return true
    return String(account.type || '').toUpperCase() === 'UNIFIED'
}

export function formatPortfolioMoney(val: unknown, currency = 'RUB', maxFractionDigits = 2): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val ?? 0)
    const sym = currency === 'RUB' ? '₽' : currency
    return `${n.toLocaleString('ru-RU', { maximumFractionDigits: maxFractionDigits })} ${sym}`
}

/** Compact money for narrow UI (price scale / last-value badge): 800000 → «800 т. ₽». */
export function formatPortfolioMoneyCompact(val: unknown, currency = 'RUB'): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    const sym = currency === 'RUB' ? '₽' : currency
    const abs = Math.abs(n)
    const sign = n < 0 ? '−' : ''
    const fmt = (v: number, maxFractionDigits: number) =>
        v.toLocaleString('ru-RU', { maximumFractionDigits: maxFractionDigits, minimumFractionDigits: 0 })

    if (abs >= 1_000_000_000) return `${sign}${fmt(abs / 1_000_000_000, 1)} млрд ${sym}`
    if (abs >= 1_000_000) return `${sign}${fmt(abs / 1_000_000, 1)} млн ${sym}`
    if (abs >= 1_000) return `${sign}${fmt(abs / 1_000, abs >= 10_000 ? 0 : 1)} т. ${sym}`
    return `${sign}${fmt(abs, 0)} ${sym}`
}

export function formatPortfolioMoneySigned(val: unknown, currency = 'RUB'): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    const sym = currency === 'RUB' ? '₽' : currency
    return `${n >= 0 ? '+' : ''}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${sym}`
}

export function formatPortfolioAccountLabel(account: AccountSummary): string {
    return account.name?.trim() || account.account_id
}

/** Short platform tag for account type (matches dashboard settings row). */
export function formatPortfolioAccountPlatformTag(type: string | null | undefined): string {
    const raw = String(type || '').trim()
    const t = raw.toLowerCase().replace(/^account_type_/, '')
    if (/tinkoff|t-bank|tbank|broker/.test(t)) return 'T-BANK'
    if (/bybit|unified|contract|spot/.test(t)) return 'BYBIT'
    if (/sber/.test(t)) return 'SBER'
    if (/binance/.test(t)) return 'BINANCE'
    if (!raw) return 'ACC'
    return raw.replace(/_/g, ' ').slice(0, 12).toUpperCase()
}

/** Match Live/broker account_id to portfolio_accounts row from analytics summary. */
export function matchPortfolioAccountByBrokerId(
    accounts: AccountSummary[],
    brokerAccountId: string | null | undefined,
): AccountSummary | null {
    const aid = String(brokerAccountId || '').trim()
    if (!aid || !accounts.length) return null
    const exact = accounts.find(a => a.account_id === aid)
    if (exact) return exact
    const upper = aid.toUpperCase()
    const caseInsensitive = accounts.find(a => String(a.account_id || '').toUpperCase() === upper)
    if (caseInsensitive) return caseInsensitive
    if (upper === 'BYBIT_UNIFIED' || upper.endsWith(':UNIFIED')) {
        return accounts.find(a => isBybitPortfolioAccount(a)) ?? null
    }
    return null
}
