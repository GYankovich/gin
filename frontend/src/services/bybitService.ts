import { api } from './api'

export type BybitFundingRateResponse = {
    symbol: string
    instrument_category: 'spot' | 'linear' | 'inverse'
    funding_rate: number
    next_funding_time: string | null
    testnet: boolean
    source: string
}

export type BybitInstrumentItem = {
    symbol: string
    base_coin: string
    quote_coin: string
    status?: string | null
    category: 'spot' | 'linear' | 'inverse'
}

export type BybitInstrumentsResponse = {
    items: BybitInstrumentItem[]
    total: number
    category: 'spot' | 'linear' | 'inverse'
    testnet: boolean
}

export const bybitService = {
    async getFundingRate(params: {
        symbol: string
        instrument_category?: 'spot' | 'linear' | 'inverse'
        testnet?: boolean
    }): Promise<BybitFundingRateResponse> {
        const { data } = await api.get<BybitFundingRateResponse>('/bybit/funding-rate', {
            params: {
                symbol: params.symbol,
                instrument_category: params.instrument_category ?? 'linear',
                testnet: params.testnet ?? false,
            },
        })
        return data
    },

    async getInstruments(params: {
        category?: 'spot' | 'linear' | 'inverse'
        quote_coin?: string
        testnet?: boolean
    }): Promise<BybitInstrumentsResponse> {
        const { data } = await api.get<BybitInstrumentsResponse>('/bybit/instruments', {
            params: {
                category: params.category ?? 'linear',
                quote_coin: params.quote_coin,
                testnet: params.testnet ?? false,
            },
        })
        return data
    },

    async previewUniverseScreening(body: {
        testnet?: boolean
        instrument_category?: 'spot' | 'linear' | 'inverse'
        min_volume_24h_usd: number
        max_spread_bps: number
        min_funding_rate_pct?: number
        max_funding_rate_pct?: number
        min_open_interest_usd?: number
        min_lsr?: number
        max_lsr?: number
        min_rvol?: number
        min_atr_percent?: number
        max_atr_percent?: number
        lookback_days?: number
    }): Promise<{ accepted: number; scanned: number; message?: string | null; skipped?: boolean }> {
        const { data } = await api.post('/bybit/universe/screening-preview', body)
        return data
    },
}
