import { normalizeStrategyInterval } from '@/pages/testing/strategyIntervals'
import {
    buildPipelineFiltersPayload,
    createDefaultTestingPipelineFilters,
    type PipelineFilter,
} from '@/pages/testing/testingPipeline'
import {
    getStrategyParamsPreset,
    stripTradingHoursMsk,
    toRiskMskTime,
} from '@/pages/testing/strategyPresets'
import { normalizeUniverseMode, type UniverseMode } from '@/utils/universeMode'
import { HISTORICAL_FILTER_TYPES, splitFiltersByRole } from '@/utils/robotConfigV2'
import type { CryptoUniverseFormFields } from '@/modules/robots/config/cryptoUniverseDefaults'
import type { FundingSimulationMode } from '@/pages/testing/executionRiskDefaults'

export type TradingRobotFormSnapshot = {
    strategy: string
    strategyParams: Record<string, unknown>
    interval: string
    capital: number
    brokerType: string
    stopLossPct: number
    takeProfitPct: number
    maxPositionPct: number
    maxPositionRub: number
    maxDailyLoss: number
    /** Мин. нотионал сделки (₽ / USDT) — Stage6 MIN_TRADE_AMOUNT. */
    minTradeAmountRub?: number
    slippagePct?: number
    executionLatencySec?: number
    maxDrawdownPct?: number
    tradingHoursStart: string
    tradingHoursEnd: string
    allowedWeekdays: number
    brokerCommissionPct: number
    ndflPct: number
    pipelineMode: 'ALL' | 'ANY'
    filters: PipelineFilter[]
    universeMode?: UniverseMode
    fixedTickers?: string[]
    universeRefreshMinutes?: number
    cryptoUniverseMode?: 'fixed' | 'auto'
} & Partial<CryptoUniverseFormFields> & {
    historicalEnabled?: boolean
    historicalInterval?: string
    historicalLookbackDays?: number
    historicalDailyAtMsk?: string
    mergeStrategyParamsFrom?: Record<string, unknown>
    preserveAllowedFigis?: string[]
    bybitTestnet?: boolean
    instrumentCategory?: 'spot' | 'linear' | 'inverse'
    leverage?: number
    makerFeePct?: number
    takerFeePct?: number
    fundingMode?: FundingSimulationMode
    backtestExecution?: 'limit_maker' | 'market_taker'
    backtestFeeModel?: 'maker_taker' | 'taker_only' | 'maker_only'
    maintenanceMarginPct?: number
}

export type TradingRobotSchedulePatch = {
    poll_interval_hours: number
    trading_hours_start: string
    trading_hours_end: string
    allowed_weekdays: number
}

export function pollValueToHours(pollValue: number, pollUnit: 'minutes' | 'hours'): number {
    const raw = pollUnit === 'minutes' ? Number(pollValue) / 60 : Number(pollValue)
    return Number(Math.max(1 / 60, raw).toFixed(4))
}

export function buildStrategyParamsPayload(
    strategy: string,
    strategyParams: Record<string, unknown>,
    interval: string,
    capital: number,
    mergeBase?: Record<string, unknown>,
    brokerType: string = 'tinvest',
): Record<string, unknown> {
    const preset = getStrategyParamsPreset(strategy)
    const merged: Record<string, unknown> = {
        ...preset,
        ...(mergeBase ?? {}),
        ...strategyParams,
        interval: normalizeStrategyInterval(
            interval || String(strategyParams.interval ?? preset.interval ?? ''),
            brokerType,
        ),
        initial_capital: Number(capital || 1_000_000),
    }
    if (strategy !== 'grain_seed') {
        delete merged.signal_profile
    }
    return merged
}

function splitPipelineFilters(filters: PipelineFilter[]): {
    historical: PipelineFilter[]
    paper: PipelineFilter[]
} {
    return splitFiltersByRole(filters)
}

function universeToV2(
    universeMode: UniverseMode | undefined,
    fixedTickers: string[],
    snapshot: TradingRobotFormSnapshot,
): { hist: Record<string, unknown>; paperInput: string } {
    const mode = normalizeUniverseMode(universeMode)
    const fixed = fixedTickers.map(t => String(t).trim().toUpperCase()).filter(Boolean)
    if (mode === 'fixed') {
        return {
            hist: { enabled: false, universe: 'fixed', fixed_tickers: fixed, filters: [] },
            paperInput: 'fixed',
        }
    }
    if (mode === 'tqbr_scan') {
        return {
            hist: { enabled: true, universe: 'tqbr_all', fixed_tickers: fixed },
            paperInput: 'candidate_pool',
        }
    }
    const histEnabled = historicalWillEnable(snapshot)
    return {
        hist: { enabled: histEnabled, universe: 'tqbr_all', fixed_tickers: fixed },
        paperInput: histEnabled ? 'candidate_pool' : 'tqbr_all',
    }
}

function historicalWillEnable(snapshot: TradingRobotFormSnapshot): boolean {
    if (snapshot.historicalEnabled != null) return snapshot.historicalEnabled
    const { historical } = splitPipelineFilters(snapshot.filters)
    return historical.length > 0
}

/**
 * Конфиг робота v2: historical_screening → paper_selection → signal_generation
 * + legacy-поля для обратной совместимости API.
 */
/** @deprecated Используйте buildMoexConfig / buildTradingRobotConfig (v3). Внутренний builder для legacy sandbox. */
export function buildTradingRobotConfigV2(snapshot: TradingRobotFormSnapshot): Record<string, unknown> {
    const legacy = buildTradingRobotConfigLegacy(snapshot)
    const { historical, paper } = splitPipelineFilters(snapshot.filters)
    const { hist, paperInput } = universeToV2(
        snapshot.universeMode,
        snapshot.fixedTickers ?? [],
        snapshot,
    )
    const histEnabled = snapshot.historicalEnabled ?? Boolean(hist.enabled)
    const moexInterval = normalizeStrategyInterval(
        String(snapshot.historicalInterval ?? snapshot.strategyParams.moex_analysis_interval ?? 'CANDLE_INTERVAL_10_MIN'),
        'moex',
    )
    const lookbackDays = Math.max(
        1,
        Number(snapshot.historicalLookbackDays ?? snapshot.strategyParams.candle_days ?? 14),
    )
    const dailyAt = String(snapshot.historicalDailyAtMsk ?? '07:00').slice(0, 5)
    const paperRefreshMin = Math.max(0, Number(snapshot.universeRefreshMinutes ?? 30))
    const histFilters =
        historical.length > 0
            ? buildPipelineFiltersPayload(historical)
            : histEnabled
              ? [{ type: 'atr', min_percent: 1.5, period: 14, direction: 'BOTH' }]
              : []

    return {
        ...legacy,
        config_version: 2,
        historical_screening: {
            enabled: histEnabled,
            source: 'moex',
            board: 'TQBR',
            universe: hist.universe ?? 'tqbr_all',
            fixed_tickers: snapshot.fixedTickers ?? [],
            interval: moexInterval,
            lookback_days: lookbackDays,
            filters: histFilters,
            refresh: { every_minutes: 0, only_trading_hours: false, daily_at_msk: dailyAt },
        },
        paper_selection: {
            enabled: true,
            input: paperInput,
            fixed_tickers: snapshot.fixedTickers ?? [],
            mode: snapshot.pipelineMode,
            filters: buildPipelineFiltersPayload(paper.length ? paper : snapshot.filters),
            refresh: {
                every_minutes: paperRefreshMin,
                only_trading_hours: true,
                daily_at_msk: null,
            },
        },
        signal_generation: {
            strategy: snapshot.strategy || 'grain_seed',
            params: legacy.strategy_params,
            data_source: snapshot.brokerType || 'tinvest',
            update_interval_seconds: 10,
            indicator_update_schedule: legacy.indicator_update_schedule,
        },
    }
}

function buildExecutionModelPayload(snapshot: TradingRobotFormSnapshot): Record<string, unknown> {
    return {
        model: 'NEXT_BAR_OPEN',
        slippage_pct: Number(snapshot.slippagePct ?? 0),
        latency_sec: Math.max(0, Number(snapshot.executionLatencySec ?? 0)),
    }
}

/** Прежний flat-конфиг (pipeline / universe_mode) — для совместимости. */
function buildTradingRobotConfigLegacy(snapshot: TradingRobotFormSnapshot): Record<string, unknown> {
    const thStart = stripTradingHoursMsk(snapshot.tradingHoursStart) || '10:00'
    const thEnd = stripTradingHoursMsk(snapshot.tradingHoursEnd) || '18:45'
    return {
        strategy: snapshot.strategy || 'grain_seed',
        broker_type: snapshot.brokerType || 'tinvest',
        strategy_params: buildStrategyParamsPayload(
            snapshot.strategy,
            snapshot.strategyParams,
            snapshot.interval,
            snapshot.capital,
            snapshot.mergeStrategyParamsFrom,
            snapshot.brokerType,
        ),
        pipeline: {
            mode: snapshot.pipelineMode,
            filters: buildPipelineFiltersPayload(snapshot.filters),
        },
        costs: {
            broker_commission_rate: Number((Number(snapshot.brokerCommissionPct || 0) / 100).toFixed(6)),
            ndfl_rate: Number((Number(snapshot.ndflPct || 0) / 100).toFixed(6)),
        },
        risk: {
            stop_loss_percent: Number(snapshot.stopLossPct || 0),
            take_profit_percent: Number(snapshot.takeProfitPct || 0),
            max_position_percent: Number(snapshot.maxPositionPct || 0),
            max_position_rub: Number(snapshot.maxPositionRub || 0),
            max_daily_loss: Number(snapshot.maxDailyLoss || 0),
            min_trade_amount_rub: Number(snapshot.minTradeAmountRub ?? 500),
            max_drawdown_percent: Number(snapshot.maxDrawdownPct ?? 20),
            trading_hours_start: toRiskMskTime(thStart, '10:00 MSK'),
            trading_hours_end: toRiskMskTime(thEnd, '18:45 MSK'),
            allowed_weekdays: Number(snapshot.allowedWeekdays ?? 31),
        },
        execution_model: buildExecutionModelPayload(snapshot),
        allowed_figis: (snapshot.preserveAllowedFigis ?? []) as string[],
        universe_mode: normalizeUniverseMode(snapshot.universeMode),
        fixed_tickers: Array.isArray(snapshot.fixedTickers)
            ? snapshot.fixedTickers.map(t => String(t).trim().toUpperCase()).filter(Boolean)
            : [],
        universe_refresh_minutes: Math.max(0, Number(snapshot.universeRefreshMinutes ?? 0)),
        update_interval_seconds: 10,
        indicator_update_schedule: {
            CANDLE_INTERVAL_DAY: '10:00 MSK',
            CANDLE_INTERVAL_HOUR: 'every hour at :05',
        },
    }
}

export function buildTradingRobotSchedulePatch(
    snapshot: {
        tradingHoursStart: string
        tradingHoursEnd: string
        allowedWeekdays: number
        pollValue: number
        pollUnit: 'minutes' | 'hours'
        [k: string]: unknown
    },
): TradingRobotSchedulePatch {
    const thStart = stripTradingHoursMsk(snapshot.tradingHoursStart) || '10:00'
    const thEnd = stripTradingHoursMsk(snapshot.tradingHoursEnd) || '18:45'
    return {
        poll_interval_hours: pollValueToHours(snapshot.pollValue, snapshot.pollUnit),
        trading_hours_start: thStart,
        trading_hours_end: thEnd,
        allowed_weekdays: Number(snapshot.allowedWeekdays ?? 31),
    }
}

export function defaultTestingFilters(): PipelineFilter[] {
    return createDefaultTestingPipelineFilters()
}
