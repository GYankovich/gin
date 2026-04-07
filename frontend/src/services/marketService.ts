import { api } from './api'
import type { RobotHistoryBacktestResult } from '@/types/robot'

export interface MarketInstrumentRow {
    figi: string
    ticker: string | null
    name: string | null
    instrument_type: string | null
    candle_interval: string
    first_candle_at: string | null
    last_candle_at: string | null
    candle_count: number
}

export interface SavedBacktestItem {
    id: number
    user_id: number
    name: string | null
    figi: string
    candle_interval: string
    strategy: string
    from_date: string
    to_date: string
    initial_capital: number
    request_payload: Record<string, unknown>
    result_payload: Record<string, unknown>
    created_at: string
}

export interface EnsureCandlesResponse {
    figi: string
    ticker: string | null
    candle_interval: string
    from_date: string
    to_date: string
    was_full_in_db: boolean
    rows_loaded: number
    candle_count: number
    stages: string[]
    candles: Record<string, unknown>[]
}

export const marketService = {
    async listInstruments(): Promise<MarketInstrumentRow[]> {
        const { data } = await api.get<{ items: MarketInstrumentRow[] }>('/market/instruments')
        return data.items ?? []
    },

    async sync(payload: {
        figi: string
        candle_interval?: string
        years?: number
        from_date?: string
        to_date?: string
        data_source?: 'tinvest' | 'moex'
        token_id?: number | null
        ticker?: string
        name?: string
    }) {
        const { data } = await api.post('/market/sync', payload)
        return data as { figi: string; interval: string; years: number; rows_upserted: number }
    },

    async runBacktest(payload: Record<string, unknown>): Promise<RobotHistoryBacktestResult> {
        const { data } = await api.post<RobotHistoryBacktestResult>('/market/backtest', payload)
        return data
    },

    async ensureCandles(payload: {
        figi: string
        ticker?: string
        candle_interval: string
        from_date: string
        to_date: string
        data_source?: 'tinvest' | 'moex'
        token_id?: number | null
        name?: string
    }): Promise<EnsureCandlesResponse> {
        const { data } = await api.post<EnsureCandlesResponse>('/market/ensure-candles', payload)
        return data
    },

    async saveBacktest(payload: {
        name?: string
        request_payload: Record<string, unknown>
        result_payload: Record<string, unknown>
    }): Promise<{ id: number }> {
        const { data } = await api.post<{ id: number }>('/market/backtests', payload)
        return data
    },

    async listBacktests(limit = 30): Promise<SavedBacktestItem[]> {
        const { data } = await api.get<{ items: SavedBacktestItem[] }>('/market/backtests', { params: { limit } })
        return data.items ?? []
    },
}
