import { normalizeUniverseMode, type UniverseMode } from '@/utils/universeMode'
import type { PipelineFilter } from '@/pages/testing/testingPipeline'

/** Фильтры П1 — по историческим свечам (MOEX lookback). */
export const HISTORICAL_FILTER_TYPES = new Set([
    'atr',
    'atr_percent',
    'volatility',
    'realized_volatility',
    'min_avg_volume',
    'volume_avg',
])

export type HistoricalScreeningState = {
    enabled: boolean
    source: 'moex' | 'tinvest'
    interval: string
    lookbackDays: number
    dailyAtMsk: string
    filters: PipelineFilter[]
}

export type PaperSelectionState = {
    enabled: boolean
    input: string
    mode: 'ALL' | 'ANY'
    refreshMinutes: number
    onlyTradingHours: boolean
    filters: PipelineFilter[]
    universeMode: UniverseMode
    fixedTickers: string[]
}

export type SignalGenerationState = {
    strategy: string
    params: Record<string, unknown>
    dataSource: string
    updateIntervalSeconds: number
}

export function splitFiltersByRole(filters: PipelineFilter[]): {
    historical: PipelineFilter[]
    paper: PipelineFilter[]
} {
    const historical: PipelineFilter[] = []
    const paper: PipelineFilter[] = []
    for (const f of filters) {
        const t = String(f.type || '').toLowerCase()
        if (HISTORICAL_FILTER_TYPES.has(t)) historical.push(f)
        else paper.push(f)
    }
    return { historical, paper }
}

export function hydrateHistoricalScreening(cfg: Record<string, unknown>): HistoricalScreeningState {
    const hs = (cfg.historical_screening || {}) as Record<string, unknown>
    const refresh = (hs.refresh || {}) as Record<string, unknown>
    const rawFilters = Array.isArray(hs.filters) ? (hs.filters as PipelineFilter[]) : []
    const pipelineFilters = Array.isArray((cfg.pipeline as any)?.filters)
        ? ((cfg.pipeline as any).filters as PipelineFilter[])
        : []
    const { historical } = splitFiltersByRole(
        rawFilters.length ? rawFilters : pipelineFilters,
    )
    return {
        enabled: hs.enabled !== false,
        source: (hs.source === 'tinvest' ? 'tinvest' : 'moex') as 'moex' | 'tinvest',
        interval: String(hs.interval || 'CANDLE_INTERVAL_10_MIN'),
        lookbackDays: Math.max(
            1,
            Number(
                hs.lookback_days
                    ?? (cfg.strategy_params as Record<string, unknown> | undefined)?.candle_days
                    ?? 14,
            ),
        ),
        dailyAtMsk: String(refresh.daily_at_msk || '07:00').replace(/\s*MSK/i, '').slice(0, 5),
        filters: historical,
    }
}

export function hydratePaperSelection(cfg: Record<string, unknown>): PaperSelectionState {
    const ps = (cfg.paper_selection || {}) as Record<string, unknown>
    const refresh = (ps.refresh || {}) as Record<string, unknown>
    const rawFilters = Array.isArray(ps.filters) ? (ps.filters as PipelineFilter[]) : []
    const pipeline = (cfg.pipeline || {}) as Record<string, unknown>
    const pipelineFilters = Array.isArray(pipeline.filters) ? (pipeline.filters as PipelineFilter[]) : []
    const { paper } = splitFiltersByRole(rawFilters.length ? rawFilters : pipelineFilters)
    const input = String(ps.input || '')
    let universeMode = normalizeUniverseMode(cfg.universe_mode)
    if (input === 'fixed') universeMode = 'fixed'
    else if (input === 'tqbr_all' && !ps.enabled) universeMode = 'tqbr_scan'
    return {
        enabled: ps.enabled !== false,
        input: input || 'candidate_pool',
        mode: ps.mode === 'ANY' ? 'ANY' : 'ALL',
        refreshMinutes: Math.max(
            0,
            Number(refresh.every_minutes ?? cfg.universe_refresh_minutes ?? 30),
        ),
        onlyTradingHours: refresh.only_trading_hours !== false,
        filters: paper,
        universeMode,
        fixedTickers: Array.isArray(ps.fixed_tickers)
            ? (ps.fixed_tickers as string[])
            : Array.isArray(cfg.fixed_tickers)
              ? (cfg.fixed_tickers as string[])
              : [],
    }
}

export function hydrateSignalGeneration(cfg: Record<string, unknown>): SignalGenerationState {
    const sg = (cfg.signal_generation || {}) as Record<string, unknown>
    return {
        strategy: String(sg.strategy || cfg.strategy || 'grain_seed'),
        params: (sg.params as Record<string, unknown>) || (cfg.strategy_params as Record<string, unknown>) || {},
        dataSource: String(sg.data_source || cfg.broker_type || 'tinvest'),
        updateIntervalSeconds: Math.max(1, Number(sg.update_interval_seconds ?? cfg.update_interval_seconds ?? 10)),
    }
}

export type CandidatePoolState = {
    tickers: string[]
    asOf: string | null
}

export type UniverseJobsState = {
    lastHistoricalScreeningAt: string | null
    lastPaperSelectionAt: string | null
}

export function hydrateCandidatePool(cfg: Record<string, unknown>): CandidatePoolState {
    const pool = cfg.candidate_pool
    if (!pool || typeof pool !== 'object') {
        return { tickers: [], asOf: null }
    }
    const p = pool as Record<string, unknown>
    return {
        tickers: Array.isArray(p.tickers) ? p.tickers.map(t => String(t).toUpperCase()) : [],
        asOf: p.as_of != null ? String(p.as_of) : null,
    }
}

export function hydrateUniverseJobsState(cfg: Record<string, unknown>): UniverseJobsState {
    const st = cfg.universe_jobs_state
    if (!st || typeof st !== 'object') {
        return { lastHistoricalScreeningAt: null, lastPaperSelectionAt: null }
    }
    const raw = st as Record<string, unknown>
    return {
        lastHistoricalScreeningAt:
            raw.last_historical_screening_at != null ? String(raw.last_historical_screening_at) : null,
        lastPaperSelectionAt:
            raw.last_paper_selection_at != null ? String(raw.last_paper_selection_at) : null,
    }
}

export function formatUniverseJobTime(iso: string | null | undefined): string {
    if (!iso) return '—'
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
}
