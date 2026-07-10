import type { Time } from '@/components/ui/Chart'
import type { MoexCacheInterval } from '@/services/marketService'

export function toChartTime(value: unknown): Time {
    if (typeof value === 'number') return value as Time
    const d = new Date(String(value))
    const ms = d.getTime()
    if (!Number.isFinite(ms)) return 0 as Time
    return Math.floor(ms / 1000) as Time
}

export type PipelineFilterType =
    | 'security_status'
    | 'trading_status'
    | 'volume'
    | 'num_trades'
    | 'gap'
    | 'spread'
    | 'atr'
    | 'capitalization'
    | 'allowed_tickers'
    | 'excluded_tickers'
    | 'min_step_ratio'
    | 'turnover'
    | 'gap_retention'
    | 'price_vs_open'
    | 'opening_range'

export type PipelineFilter = {
    id: string
    type: PipelineFilterType
    min?: number
    max_percent?: number
    min_percent?: number
    period?: number
    eq?: string
    direction?: 'BOTH' | 'UP_ONLY' | 'DOWN_ONLY'
    max_steps?: number
    min_ratio?: number
    list?: string[] | null
}

export const FILTER_META: Record<PipelineFilterType, { label: string }> = {
    security_status: { label: 'Статус бумаги' },
    trading_status: { label: 'Статус торгов' },
    volume: { label: 'Объем в рублях' },
    num_trades: { label: 'Количество сделок' },
    gap: { label: 'Утренний гэп (%)' },
    spread: { label: 'Спред (%)' },
    atr: { label: 'ATR (%)' },
    capitalization: { label: 'Капитализация' },
    allowed_tickers: { label: 'Одобренные бумаги' },
    excluded_tickers: { label: 'Исключенные бумаги' },
    min_step_ratio: { label: 'Мин. шаг / комиссия' },
    turnover: { label: 'Оборачиваемость (%)' },
    gap_retention: { label: 'Удержание гэпа' },
    price_vs_open: { label: 'Цена к открытию (%)' },
    opening_range: { label: 'Диапазон открытия (%)' },
}

export function buildPipelineFiltersPayload(filters: PipelineFilter[]) {
    return filters.map(f => ({
        type: f.type,
        min: f.min,
        max_percent: f.max_percent,
        min_percent: f.min_percent,
        period: f.period,
        eq: f.eq,
        direction: f.direction,
        max_steps: f.max_steps,
        min_ratio: f.min_ratio,
        list: f.list ?? null,
    }))
}

import { normalizeStrategyInterval } from '@/pages/testing/strategyIntervals'
import { moexTestingPipelineFromPreset } from '@/modules/robots/config/universeFilterPresets'

/** Нормализация enum интервала свечей для MOEX (T-Invest). Для crypto — normalizeStrategyInterval(..., 'crypto'). */
export function normalizeSignalInterval(value: string | null | undefined): string {
    return normalizeStrategyInterval(value, 'moex')
}

/**
 * Рекомендуемый интервал общего кеша MOEX (ARCH-01) под выбранный интервал сигналов.
 * 5m нет в shared_market_candles — для дозагрузки используем 10m (ближайший стандартный шаг).
 */
export function suggestedMoexIntervalForSignal(signalInterval: string): MoexCacheInterval {
    const v = String(signalInterval || '').toUpperCase()
    if (v.includes('1_MIN') && !v.includes('10_MIN') && !v.includes('15_MIN') && !v.includes('30_MIN')) {
        return '1m'
    }
    if (v.includes('5_MIN') || v.includes('2_MIN') || v.includes('3_MIN')) return '10m'
    if (v.includes('10_MIN') || v.includes('15_MIN')) return '10m'
    if (v.includes('30_MIN')) return '10m'
    if (v.includes('2_HOUR') || v.includes('4_HOUR')) return '1h'
    if (v.includes('HOUR') || v.includes('60')) return '1h'
    if (v.includes('DAY') || v.includes('24')) return '1d'
    if (v.includes('WEEK')) return '1w'
    if (v.includes('MONTH')) return '1M'
    return '10m'
}

/** Стартовый конвейер для grain_seed на странице «Тестирование» — пресет «Умеренная». */
export function createDefaultTestingPipelineFilters(): PipelineFilter[] {
    return moexTestingPipelineFromPreset('moderate').filters
}
