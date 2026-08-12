import { normalizeUniverseMode, type UniverseMode } from '@/utils/universeMode'
import { buildPipelineFiltersPayload } from '@/pages/testing/testingPipeline'
import { stripTradingHoursMsk } from '@/pages/testing/strategyPresets'
import type { TradingRobotFormSnapshot } from '@/pages/testing/buildTradingRobotConfigV2'

const INTERVAL_TO_V4: Record<string, string> = {
    CANDLE_INTERVAL_1_MIN: '1m',
    CANDLE_INTERVAL_5_MIN: '5m',
    CANDLE_INTERVAL_10_MIN: '10m',
    CANDLE_INTERVAL_15_MIN: '15m',
    CANDLE_INTERVAL_30_MIN: '30m',
    CANDLE_INTERVAL_HOUR: '1h',
    CANDLE_INTERVAL_4_HOUR: '4h',
    CANDLE_INTERVAL_DAY: '1d',
}

const STRATEGY_TO_ARCHETYPE: Record<string, string> = {
    momentum_breakout: 'momentum',
    reversion_to_ma: 'reversion',
}

function intervalToV4Timeframe(interval: string): string {
    const key = String(interval || 'CANDLE_INTERVAL_5_MIN').trim()
    return INTERVAL_TO_V4[key] ?? '5m'
}

function bitmaskToWeekdays(mask: number): boolean[] {
    return Array.from({ length: 7 }, (_, i) => (mask & (1 << i)) !== 0)
}

function buildUniverse(snapshot: TradingRobotFormSnapshot) {
    const mode = normalizeUniverseMode(snapshot.universeMode) as UniverseMode
    const tickers = Array.isArray(snapshot.fixedTickers)
        ? snapshot.fixedTickers.map(t => String(t).trim().toUpperCase()).filter(Boolean)
        : []

    if (mode === 'fixed' || tickers.length > 0) {
        return {
            mode: 'fixed' as const,
            fixedList: tickers,
            excluded: [],
            maxAssets: Math.max(1, tickers.length || 20),
            exitOnDrop: false,
        }
    }

    return {
        mode: 'screener' as const,
        screener: {
            preset: mode === 'tqbr_scan' ? 'high_liquidity' : 'custom',
            filters: buildPipelineFiltersPayload(snapshot.filters),
            filterMode: String(snapshot.pipelineMode || 'ALL').toLowerCase() === 'any' ? 'any' : 'all',
            refreshPolicy: 'on_session',
        },
        excluded: [],
        maxAssets: 20,
        exitOnDrop: false,
    }
}

function buildStrategy(snapshot: TradingRobotFormSnapshot) {
    const strategy = String(snapshot.strategy || '').trim()
    const archetype = STRATEGY_TO_ARCHETYPE[strategy]
    if (!archetype) {
        throw new Error(`Strategy "${strategy}" is not supported by robots v2 backtest`)
    }
    const sp = snapshot.strategyParams || {}
    const timeframe = intervalToV4Timeframe(String(sp.interval || snapshot.interval || 'CANDLE_INTERVAL_5_MIN'))

    if (archetype === 'momentum') {
        return {
            archetype,
            timeframe,
            params: {
                maPeriod: Number(sp.ma_period ?? sp.maPeriod ?? 50),
                volumeMultiplier: Number(sp.volume_multiplier ?? sp.volumeMultiplier ?? 1.5),
                breakoutLookback: Number(sp.lookback_days ?? sp.breakoutLookback ?? 20),
            },
        }
    }

    return {
        archetype,
        timeframe,
        params: {
            indicator: 'rsi',
            overboughtThreshold: Number(sp.rsi_overbought ?? sp.overboughtThreshold ?? 80),
            oversoldThreshold: Number(sp.rsi_oversold ?? sp.oversoldThreshold ?? 20),
            rsiPeriod: Number(sp.rsi_period ?? sp.rsiPeriod ?? 14),
        },
    }
}

/** Build TradingRobotConfigV4 from /testing form snapshot. */
export function buildTradingRobotConfigV4(snapshot: TradingRobotFormSnapshot): Record<string, unknown> {
    const thStart = stripTradingHoursMsk(snapshot.tradingHoursStart) || '10:00'
    const thEnd = stripTradingHoursMsk(snapshot.tradingHoursEnd) || '18:45'
    const instrumentType =
        String(snapshot.brokerType || 'tinvest').toLowerCase() === 'bybit' ? 'perpetual' : 'stock'

    return {
        configVersion: 4,
        core: {
            goal: 'moderate',
            instrumentType,
            mode: 'paper',
            advancedMode: false,
            schedule: {
                weekdays: bitmaskToWeekdays(Number(snapshot.allowedWeekdays ?? 31)),
                timeFrom: thStart,
                timeTo: thEnd,
                pollInterval: '5m',
            },
        },
        strategy: buildStrategy(snapshot),
        universe: buildUniverse(snapshot),
        risk: {
            capital: Number(snapshot.capital || 100_000),
            maxPositionSharePct: Number(snapshot.maxPositionPct || 10),
            stopLossPct: Number(snapshot.stopLossPct || 2),
            takeProfitPct: Number(snapshot.takeProfitPct || 4),
            maxDailyLoss: Number(snapshot.maxDailyLoss || 5000),
            maxDrawdownPct: Number(snapshot.maxDrawdownPct ?? 50),
            maxConcurrentPositions: 3,
            brokerCommissionPct: Number(snapshot.brokerCommissionPct || 0.05),
            taxPct: Number(snapshot.ndflPct || 13),
            slippagePct: Number(snapshot.slippagePct ?? 0.5),
            stopMode: 'soft',
        },
    }
}
