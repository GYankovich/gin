export interface PortfolioAccount {
    id: number
    account_id: string
    type: string
    name: string
    status: string
    opened_date: string | null
    last_sync_at: string | null
    created_at: string
}

export interface PortfolioPosition {
    figi: string
    instrument_type: string
    quantity: number
    average_position_price: number
    current_price: number
    expected_yield: number
    name?: string
    ticker?: string
}

export interface TokenResponse {
    id: number
    token_type: string
    token_name: string
    is_active: boolean
    created_at: string
    last_used_at: string | null
    expires_at: string | null
    token_preview: string
}

export interface ApiKeyResponse {
    id: number
    name: string
    token_type: { type: number; typeName: string; typeDesc: string }
    is_active: boolean
    created_at: string
    masked_token: string
}
