import type { Dispatch, SetStateAction } from 'react'
import type { RecommendationItem, SuggestedChange } from '@/types/recommendations'
import {
    type CryptoScreeningFilter,
    type CryptoScreeningFilterType,
    upsertCryptoFilterValue,
} from '@/pages/testing/cryptoScreeningPipeline'
import {
    normalizeFundingMode,
    type FundingSimulationMode,
} from '@/pages/testing/executionRiskDefaults'
import { stripTradingHoursMsk } from '@/pages/testing/strategyPresets'

const CRYPTO_UNIVERSE_PATH: Record<string, CryptoScreeningFilterType> = {
    'crypto_universe.min_volume_24h_usd': 'min_volume_24h_usd',
    'crypto_universe.min_last_price': 'min_last_price',
    'crypto_universe.max_spread_bps': 'max_spread_bps',
    'crypto_universe.min_funding_rate': 'min_funding_rate_pct',
    'crypto_universe.max_funding_rate': 'max_funding_rate_pct',
    'crypto_universe.min_open_interest_usd': 'min_open_interest_usd',
    'crypto_universe.min_lsr': 'min_lsr',
    'crypto_universe.max_lsr': 'max_lsr',
    'crypto_universe.min_rvol': 'min_rvol',
    'crypto_universe.min_atr_percent': 'min_atr_percent',
    'crypto_universe.max_atr_percent': 'max_atr_percent',
    'crypto_universe.lookback_days': 'lookback_days',
}

export type RecommendationFormActions = {
    setStopLossPct: (v: number) => void
    setTakeProfitPct: (v: number) => void
    setMaxPositionPct: (v: number) => void
    setMaxDailyLoss: (v: number) => void
    setSlippagePct: (v: number) => void
    setTradingHoursStart: (v: string) => void
    setTradingHoursEnd: (v: string) => void
    setAllowedWeekdays: (v: number) => void
    setStrategyParam: (key: string, value: unknown) => void
    setInterval: (v: string) => void
    setFundingMode: (v: FundingSimulationMode) => void
    setBacktestExecution: (v: 'limit_maker' | 'market_taker') => void
    setBacktestFeeModel: (v: 'maker_taker' | 'taker_only' | 'maker_only') => void
    setLeverage: (v: number) => void
    setInstrumentCategory: (v: 'spot' | 'linear' | 'inverse') => void
    cryptoFilters: CryptoScreeningFilter[]
    setCryptoFilters: Dispatch<SetStateAction<CryptoScreeningFilter[]>>
}

export type ApplyRecommendationResult = {
    applied: number
    skipped: string[]
}

function isAutoApplicableValue(value: unknown): boolean {
    if (value == null) return false
    if (typeof value === 'number' && Number.isFinite(value)) return true
    if (typeof value === 'boolean') return true
    if (typeof value !== 'string') return false
    const s = value.trim().toLowerCase()
    if (!s) return false
    const manualPrefixes = [
        'suggest',
        'soften',
        'tighten',
        'review',
        'exclude_',
        'focus_',
        'expand_',
        'reduce_',
    ]
    return !manualPrefixes.some(p => s.includes(p))
}

function toNumber(value: unknown): number | null {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
}

function fundingRateForForm(path: string, value: number): number {
    if (!path.includes('funding_rate')) return value
    if (Math.abs(value) <= 1) return value * 100
    return value
}

function applyCryptoUniversePath(
    actions: RecommendationFormActions,
    path: string,
    rawValue: unknown,
): boolean {
    const type = CRYPTO_UNIVERSE_PATH[path]
    if (!type) return false
    const num = toNumber(rawValue)
    if (num == null) return false
    const value = fundingRateForForm(path, num)
    actions.setCryptoFilters(prev => upsertCryptoFilterValue(prev, type, value))
    return true
}

function collectCryptoUniverseUpdate(
    path: string,
    rawValue: unknown,
): { type: CryptoScreeningFilterType; value: number } | null {
    const type = CRYPTO_UNIVERSE_PATH[path]
    if (!type || !isAutoApplicableValue(rawValue)) return null
    const num = toNumber(rawValue)
    if (num == null) return null
    return { type, value: fundingRateForForm(path, num) }
}

function applyCryptoUniverseUpdates(
    actions: RecommendationFormActions,
    updates: Array<{ type: CryptoScreeningFilterType; value: number }>,
): number {
    if (!updates.length) return 0
    let changedCount = 0
    actions.setCryptoFilters(prev => {
        let next = prev
        for (const { type, value } of updates) {
            const updated = upsertCryptoFilterValue(next, type, value)
            if (updated !== next) {
                changedCount += 1
                next = updated
            }
        }
        return next
    })
    return changedCount
}

export function applySuggestedChange(
    change: SuggestedChange,
    actions: RecommendationFormActions,
): boolean {
    const path = change.path
    const value = change.suggested_value
    if (!isAutoApplicableValue(value)) return false

    if (path.startsWith('strategy_params.')) {
        const key = path.slice('strategy_params.'.length)
        if (!key || key === 'strategy_params') return false
        actions.setStrategyParam(key, value)
        return true
    }

    if (applyCryptoUniversePath(actions, path, value)) return true

    switch (path) {
        case 'risk.stop_loss_percent':
            actions.setStopLossPct(toNumber(value) ?? 0)
            return true
        case 'risk.take_profit_percent':
            actions.setTakeProfitPct(toNumber(value) ?? 0)
            return true
        case 'risk.max_position_percent':
        case 'risk.max_position_size_pct':
            actions.setMaxPositionPct(toNumber(value) ?? 0)
            return true
        case 'risk.max_daily_loss':
            actions.setMaxDailyLoss(toNumber(value) ?? 0)
            return true
        case 'risk.trading_hours_start':
            actions.setTradingHoursStart(stripTradingHoursMsk(String(value)) || String(value))
            return true
        case 'risk.trading_hours_end':
            actions.setTradingHoursEnd(stripTradingHoursMsk(String(value)) || String(value))
            return true
        case 'risk.allowed_weekdays':
            actions.setAllowedWeekdays(Math.round(toNumber(value) ?? 0))
            return true
        case 'execution_model.slippage_pct':
            actions.setSlippagePct(toNumber(value) ?? 0)
            return true
        case 'costs.funding_mode':
            actions.setFundingMode(normalizeFundingMode(String(value)))
            return true
        case 'costs.backtest_execution':
            if (value === 'limit_maker' || value === 'market_taker') {
                actions.setBacktestExecution(value)
                return true
            }
            return false
        case 'costs.backtest_fee_model':
            if (value === 'maker_taker' || value === 'taker_only' || value === 'maker_only') {
                actions.setBacktestFeeModel(value)
                return true
            }
            return false
        case 'bybit.leverage':
            actions.setLeverage(Math.max(1, Math.round(toNumber(value) ?? 1)))
            return true
        case 'bybit.instrument_category':
            if (value === 'spot' || value === 'linear' || value === 'inverse') {
                actions.setInstrumentCategory(value)
                return true
            }
            return false
        default:
            return false
    }
}

export function applyRecommendationItem(
    item: RecommendationItem,
    actions: RecommendationFormActions,
): ApplyRecommendationResult {
    return applySuggestedChanges(item.suggested_changes, actions)
}

export function countApplicableChanges(item: RecommendationItem): number {
    return item.suggested_changes.filter(ch => isAutoApplicableValue(ch.suggested_value)).length
}

export function applySuggestedChanges(
    changes: Array<{ path: string; suggested_value?: unknown }>,
    actions: RecommendationFormActions,
): ApplyRecommendationResult {
    let applied = 0
    const skipped: string[] = []
    const cryptoUpdates: Array<{ type: CryptoScreeningFilterType; value: number }> = []

    for (const ch of changes) {
        const cryptoUpdate = collectCryptoUniverseUpdate(ch.path, ch.suggested_value)
        if (cryptoUpdate) {
            cryptoUpdates.push(cryptoUpdate)
            continue
        }
        if (applySuggestedChange(ch, actions)) {
            applied += 1
        } else if (ch.path) {
            skipped.push(ch.path)
        }
    }

    applied += applyCryptoUniverseUpdates(actions, cryptoUpdates)
    return { applied, skipped }
}

export function applyParamSummary(
    summary: Record<string, unknown>,
    actions: RecommendationFormActions,
): ApplyRecommendationResult {
    let applied = 0
    const skipped: string[] = []
    for (const [path, value] of Object.entries(summary)) {
        if (!isAutoApplicableValue(value)) {
            skipped.push(path)
            continue
        }
        if (applySuggestedChange({ path, suggested_value: value }, actions)) {
            applied += 1
        } else {
            skipped.push(path)
        }
    }
    return { applied, skipped }
}
