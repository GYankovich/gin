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

export function formatPortfolioMoneySigned(val: unknown, currency = 'RUB'): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    const sym = currency === 'RUB' ? '₽' : currency
    return `${n >= 0 ? '+' : ''}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${sym}`
}

export function formatPortfolioAccountLabel(account: AccountSummary): string {
    const name = account.name?.trim() || account.account_id
    const type = account.type?.trim()
    // const idPart = `#${account.id}`
    // const meta = [account.type, account.status].filter(Boolean).join(' · ')
    // const value =
    //     account.total_value != null && Number(account.total_value) > 0
    //         ? formatPortfolioMoney(account.total_value, account.currency)
    //         : account.last_snapshot_date
    //           ? null
    //           : 'нет снимков'
    // return [idPart, name, meta, value].filter(Boolean).join(' — ')
    return [name, type].filter(Boolean).join(' — ')
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
