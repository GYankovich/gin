import type { TestingMarket } from '@/pages/testing/refactored/types/forms'

export type FundingSimulationMode = 'off' | 'historical' | 'forecast' | 'average'

export const FUNDING_MODE_OPTIONS: Array<{ value: FundingSimulationMode; label: string }> = [
    { value: 'off', label: 'Не учитывать' },
    { value: 'historical', label: 'По историческому значению' },
    { value: 'forecast', label: 'По прогнозному (следующий rate)' },
    { value: 'average', label: 'Усреднённый за период удержания' },
]

export const DEFAULT_EXECUTION_LATENCY_SEC = 0
export const DEFAULT_MAX_DRAWDOWN_PCT = 20

export function defaultSlippagePct(market: TestingMarket): number {
    return market === 'crypto' ? 0.05 : 0.1
}

export function normalizeFundingMode(
    value: string | null | undefined,
    legacyEnabled?: boolean,
): FundingSimulationMode {
    const raw = String(value || '').trim().toLowerCase()
    if (raw === 'off' || raw === 'historical' || raw === 'forecast' || raw === 'average') {
        return raw
    }
    if (legacyEnabled === false) return 'off'
    return 'historical'
}
