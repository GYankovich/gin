/** T4.7 — currency label for KPI / tables. */
export function resolveResultCurrencyLabel(isCrypto: boolean): string {
    return isCrypto ? 'USDT' : '₽'
}

export function resolveHistoryRunCurrencyLabel(run: {
    market_profile?: string | null
    broker_type?: string | null
}): string {
    const mp = String(run.market_profile ?? '').toLowerCase()
    if (mp === 'crypto') return 'USDT'
    if (mp === 'moex') return '₽'
    const bt = String(run.broker_type ?? '').toLowerCase()
    return bt === 'bybit' ? 'USDT' : '₽'
}
