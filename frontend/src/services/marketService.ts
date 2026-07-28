///@EPIC Frontend.ITEM APIClient.TOPIC FrontendSrcServicesMarketservice [1]
///@ Исходный модуль `frontend/src/services/marketService.ts` — автоматическая разметка для Obsidian Source Scanner.

import { api } from './api'
import type { RobotHistoryBacktestResult } from '@/types/robot'

/** Канонические интервалы общего кеша MOEX (ARCH-01), см. `market_data_v1.intervals`. */
export const MOEX_CACHE_INTERVALS = ['1m', '10m', '1h', '1d', '1w', '1M'] as const
export type MoexCacheInterval = (typeof MOEX_CACHE_INTERVALS)[number]

/** §9.5 GET /v1/market-data/candles/coverage-summary */
export interface CandleCoverageTickerSummary {
    ticker: string
    bucket_count: number
    min_bucket_start: string | null
    max_bucket_start: string | null
}

export interface CandleCoverageSummaryResponse {
    board: string
    interval: string
    items: CandleCoverageTickerSummary[]
}

/** §9.5 GET /v1/market-data/tqbr-securities */
export interface TqbrSecurityRow {
    secid: string
    shortname?: string | null
    isin?: string | null
}

export interface TqbrSearchResponse {
    items: TqbrSecurityRow[]
}

export interface CandleLoadJobCreateResponse {
    job_id: string
    status: string
}

export interface CandleLoadJobStatus {
    job_id: string
    status: string
    progress_percent: number
    tickers_total: number
    tickers_done: number
    bars_written: number
    message?: string | null
    started_at?: string | null
    updated_at?: string | null
    eta_seconds?: number | null
    error?: string | null
}

export interface SharedCandleRow {
    ticker: string
    board: string
    interval: string
    bucket_start: string
    open: number
    high: number
    low: number
    close: number
    volume?: number | null
    source?: string | null
}

export interface CandleGap {
    ticker: string
    from: string
    to: string
}

export interface CandlesQueryResponse {
    candles: SharedCandleRow[]
    gaps: CandleGap[]
}

function serializeCandlesQuery(params: {
    tickers: string[]
    board: string
    interval: string
    from: string
    to: string
}): string {
    const sp = new URLSearchParams()
    for (const t of params.tickers) {
        const u = String(t).trim().toUpperCase()
        if (u) sp.append('tickers', u)
    }
    sp.set('board', params.board.trim().toUpperCase() || 'TQBR')
    sp.set('interval', params.interval)
    sp.set('from', params.from)
    sp.set('to', params.to)
    return sp.toString()
}

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
    /**
     * ARCH-01: фоновая дозагрузка свечей MOEX в общий кеш.
     * Тело: `from` / `to` в ISO 8601 (UTC).
     */
    async createCandleLoadJob(
        body: {
            tickers: string[]
            board?: string
            interval: MoexCacheInterval | string
            from: string
            to: string
        },
        opts?: { idempotencyKey?: string },
    ): Promise<CandleLoadJobCreateResponse> {
        const { data } = await api.post<CandleLoadJobCreateResponse>(
            '/v1/market-data/candle-load-jobs',
            {
                tickers: body.tickers,
                board: body.board ?? 'TQBR',
                interval: body.interval,
                from: body.from,
                to: body.to,
            },
            opts?.idempotencyKey
                ? { headers: { 'Idempotency-Key': opts.idempotencyKey } }
                : undefined,
        )
        return data
    },

    async getCandleLoadJob(jobId: string): Promise<CandleLoadJobStatus> {
        const { data } = await api.get<CandleLoadJobStatus>(`/v1/market-data/candle-load-jobs/${jobId}`)
        return data
    },

    /** Чтение только из общей таблицы; при неполном покрытии смотрите `gaps`. */
    async getSharedCandles(params: {
        tickers: string[]
        board?: string
        interval: MoexCacheInterval | string
        from: string
        to: string
    }): Promise<CandlesQueryResponse> {
        const qs = serializeCandlesQuery({
            tickers: params.tickers,
            board: params.board ?? 'TQBR',
            interval: params.interval,
            from: params.from,
            to: params.to,
        })
        const { data } = await api.get<CandlesQueryResponse>(`/v1/market-data/candles?${qs}`)
        return data
    },

    /** §9.5: сводка покрытия shared_market_candles без дозагрузки MOEX. */
    async getCandlesCoverageSummary(params: {
        tickers: string[]
        board?: string
        interval: MoexCacheInterval | string
        from: string
        to: string
    }): Promise<CandleCoverageSummaryResponse> {
        const qs = serializeCandlesQuery({
            tickers: params.tickers,
            board: params.board ?? 'TQBR',
            interval: params.interval,
            from: params.from,
            to: params.to,
        })
        const { data } = await api.get<CandleCoverageSummaryResponse>(
            `/v1/market-data/candles/coverage-summary?${qs}`,
        )
        return data
    },

    /** §9.5: поиск SECID TQBR по префиксу (справочник в БД). */
    async searchTqbrSecurities(q: string, limit = 50): Promise<TqbrSearchResponse> {
        const { data } = await api.get<TqbrSearchResponse>('/v1/market-data/tqbr-securities', {
            params: { q, limit },
        })
        return data
    },

    /** Полный срез справочника TQBR одним запросом (до limit строк). Раньше UI делал 36× prefix-поиск. */
    async listTqbrSecuritiesBulk(limit = 12_000): Promise<TqbrSearchResponse> {
        const { data } = await api.get<TqbrSearchResponse>('/v1/market-data/tqbr-securities/bulk', {
            params: { limit },
        })
        return data
    },

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
