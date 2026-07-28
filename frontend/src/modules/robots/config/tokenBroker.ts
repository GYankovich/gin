/** Брокер робота определяется типом API-токена (dictionary TOKEN.TYPE). */

export type TokenTypeRef = {
    type?: number
    typeName?: string
}

/** type=1 → T-Invest, type=2 → ByBit (см. migration 0038_dictionary_token_type_bybit). */
export function brokerFromTokenType(tokenType: TokenTypeRef | null | undefined): 'tinvest' | 'bybit' {
    const typeNum = Number(tokenType?.type ?? 0)
    if (typeNum === 2) return 'bybit'
    if (typeNum === 1) return 'tinvest'
    const name = String(tokenType?.typeName ?? '').toLowerCase()
    if (name.includes('bybit')) return 'bybit'
    if (name.includes('t-invest') || name.includes('tinvest') || name.includes('tinkoff')) return 'tinvest'
    return 'tinvest'
}

export function brokerFromTokenId(
    tokenId: number,
    tokens: Array<{ id: number; token_type?: TokenTypeRef; broker_type?: string | null }>,
): 'tinvest' | 'bybit' | null {
    if (!tokenId) return null
    const token = tokens.find(t => t.id === tokenId)
    if (!token) return null
    if (token.token_type) return brokerFromTokenType(token.token_type)
    const name = String(token.broker_type ?? '').toLowerCase()
    if (name.includes('bybit')) return 'bybit'
    if (name.includes('t-invest') || name.includes('tinvest') || name.includes('tinkoff')) return 'tinvest'
    return null
}

/** Подпись брокера из /apikey/data (dictionary TOKEN.TYPE). */
export function brokerLabelFromToken(
    tokenId: number,
    tokens: Array<{ id: number; broker_type?: string | null; token_type?: TokenTypeRef }>,
): string {
    if (!tokenId) return '—'
    const token = tokens.find(t => t.id === tokenId)
    if (!token) return '—'
    return String(token.broker_type || token.token_type?.typeName || '').trim() || '—'
}
