export type ApiKeyItem = {
    id: number
    name: string | null
    token_type: { type: number; typeName: string; typeDesc: string }
    /** Словарный перевод TOKEN.TYPE (ganaly.dictionary.name). */
    broker_type?: string | null
    status: number
    status_name?: string | null
    status_description?: string | null
    created_at: string
    masked_token: string
    last_used_at?: string | null
    extra_data?: Record<string, unknown> | null
}

export type TokenConnectionStatus = 'active' | 'error' | 'inactive' | 'unknown' | 'expired'

export type TokenHealth = {
    status: TokenConnectionStatus
    message?: string
    checkedAt?: string
}

export type BrokerKind = 'tinvest' | 'bybit' | 'binance' | 'other'
