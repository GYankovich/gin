import { buildStrategyParamsPayload, type TradingRobotFormSnapshot } from '@/pages/testing/buildTradingRobotConfigV2'
import { CRYPTO_UNIVERSE_DEFAULTS } from '@/modules/robots/config/cryptoUniverseDefaults'
import { normalizeFundingMode, type FundingSimulationMode } from '@/pages/testing/executionRiskDefaults'



export function isCryptoBroker(brokerType: string | undefined | null): boolean {

    return String(brokerType || '').trim().toLowerCase() === 'bybit'

}



/** v3 type2_bybit config for history backtest / robot patch. */

export function buildCryptoTradingRobotConfig(snapshot: TradingRobotFormSnapshot): Record<string, unknown> {

    const symbols = (snapshot.fixedTickers ?? [])

        .map(s => String(s).trim().toUpperCase())

        .filter(Boolean)

    const cryptoMode =

        snapshot.cryptoUniverseMode ?? (symbols.length > 0 ? 'fixed' : 'auto')

    const strategyParams = buildStrategyParamsPayload(
        snapshot.strategy,

        snapshot.strategyParams,

        snapshot.interval,

        snapshot.capital,

        snapshot.mergeStrategyParamsFrom,

        snapshot.brokerType ?? 'bybit',

    )

    const fundingMode = normalizeFundingMode(snapshot.fundingMode)

    return {

        config_version: 3,

        schema_profile: 'type2_bybit',

        broker_type: 'bybit',

        market_profile: 'crypto',

        instrument_id_type: 'symbol',

        strategy: snapshot.strategy || 'reversion_to_ma',

        strategy_params: strategyParams,

        bybit: {

            testnet: snapshot.bybitTestnet ?? false,

            instrument_category: snapshot.instrumentCategory ?? 'linear',

            position_mode: 'one_way',

            leverage: Math.max(1, Number(snapshot.leverage ?? 1)),

            maintenance_margin_rate: Number(
                ((snapshot.maintenanceMarginPct ?? 0.5) / 100).toFixed(6),
            ),

        },

        signal_generation: {

            strategy: snapshot.strategy || 'reversion_to_ma',

            params: strategyParams,

            data_source: 'bybit',

            update_interval_seconds: 10,

        },

        instruments: symbols,

        allowed_symbols: symbols,

        allowed_figis: symbols,

        fixed_tickers: symbols,

        universe_mode: cryptoMode,

        costs: {

            maker_fee_rate: Number((Number(snapshot.makerFeePct ?? 0.01) / 100).toFixed(6)),

            taker_fee_rate: Number((Number(snapshot.takerFeePct ?? 0.06) / 100).toFixed(6)),

            funding_rate_enabled: fundingMode !== 'off',
            funding_mode: fundingMode,

            backtest_execution: snapshot.backtestExecution ?? 'market_taker',

            backtest_fee_model: snapshot.backtestFeeModel ?? 'maker_taker',

            ndfl_rate: 0,

        },

        risk: {

            stop_loss_percent: Number(snapshot.stopLossPct || 0),

            take_profit_percent: Number(snapshot.takeProfitPct || 0),

            max_position_percent: Number(snapshot.maxPositionPct || 0),

            max_position_rub: Number(snapshot.maxPositionRub || 0),

            max_daily_loss: Number(snapshot.maxDailyLoss || 0),
            min_trade_amount_rub: Number(snapshot.minTradeAmountRub ?? 5),
            max_drawdown_percent: Number(snapshot.maxDrawdownPct ?? 20),

            allow_short: true,

            max_leverage: Math.max(1, Number(snapshot.leverage ?? 5)),

            trading_hours_start: '00:00 MSK',

            trading_hours_end: '23:59 MSK',

            allowed_weekdays: 127,

        },

        execution_model: {
            model: 'NEXT_BAR_OPEN',
            slippage_pct: Number(snapshot.slippagePct ?? 0),
            latency_sec: Math.max(0, Number(snapshot.executionLatencySec ?? 0)),
        },

        crypto_universe: {

            enabled: cryptoMode === 'auto',

            min_volume_24h_usd: Number(snapshot.cryptoMinVolume24hUsd ?? CRYPTO_UNIVERSE_DEFAULTS.minVolume24hUsd),

            min_last_price: Number(snapshot.cryptoMinLastPrice ?? CRYPTO_UNIVERSE_DEFAULTS.minLastPrice),

            max_spread_bps: Number(snapshot.cryptoMaxSpreadBps ?? CRYPTO_UNIVERSE_DEFAULTS.maxSpreadBps),

            min_funding_rate: Number(
                ((snapshot.cryptoMinFundingRatePct ?? CRYPTO_UNIVERSE_DEFAULTS.minFundingRatePct) / 100).toFixed(8),
            ),

            max_funding_rate: Number(
                ((snapshot.cryptoMaxFundingRatePct ?? CRYPTO_UNIVERSE_DEFAULTS.maxFundingRatePct) / 100).toFixed(8),
            ),

            min_open_interest_usd: Number(
                snapshot.cryptoMinOpenInterestUsd ?? CRYPTO_UNIVERSE_DEFAULTS.minOpenInterestUsd,
            ),

            min_lsr: Number(snapshot.cryptoMinLsr ?? CRYPTO_UNIVERSE_DEFAULTS.minLsr),

            max_lsr: Number(snapshot.cryptoMaxLsr ?? CRYPTO_UNIVERSE_DEFAULTS.maxLsr),

            min_rvol: Number(snapshot.cryptoMinRvol ?? CRYPTO_UNIVERSE_DEFAULTS.minRvol),

            min_atr_percent: Number(snapshot.cryptoMinAtrPercent ?? CRYPTO_UNIVERSE_DEFAULTS.minAtrPercent),

            max_atr_percent: Number(snapshot.cryptoMaxAtrPercent ?? CRYPTO_UNIVERSE_DEFAULTS.maxAtrPercent),

            lookback_days: Number(snapshot.cryptoLookbackDays ?? CRYPTO_UNIVERSE_DEFAULTS.lookbackDays),

            funding_lookback_hours: Math.max(
                1,
                Number(snapshot.cryptoFundingLookbackHours ?? 8),
            ),

            refresh: {
                every_minutes: Math.max(0, Number(snapshot.cryptoRefreshEveryMinutes ?? 60)),
            },

        },

        update_interval_seconds: 10,

    }

}



export function cryptoDefaultsFromConfig(cfg: Record<string, unknown>): {

    bybitTestnet: boolean

    instrumentCategory: 'spot' | 'linear' | 'inverse'

    leverage: number

    makerFeePct: number

    takerFeePct: number

    fundingMode: FundingSimulationMode

    backtestExecution?: 'limit_maker' | 'market_taker'

    backtestFeeModel?: 'maker_taker' | 'taker_only' | 'maker_only'

    maintenanceMarginPct?: number

    cryptoUniverseMode: 'fixed' | 'auto'

    cryptoMinVolume24hUsd: number

    cryptoMinLastPrice: number

    cryptoMaxSpreadBps: number

    cryptoMaxFundingRatePct: number

    cryptoMinFundingRatePct: number

    cryptoMinOpenInterestUsd: number

    cryptoMinLsr: number

    cryptoMaxLsr: number

    cryptoMinRvol: number

    cryptoMinAtrPercent: number

    cryptoMaxAtrPercent: number

    cryptoLookbackDays: number

    cryptoFundingLookbackHours: number

    cryptoRefreshEveryMinutes: number

} {

    const bybit = (cfg.bybit ?? {}) as Record<string, unknown>

    const costs = (cfg.costs ?? {}) as Record<string, unknown>

    const cu = (cfg.crypto_universe ?? {}) as Record<string, unknown>

    const cat = String(bybit.instrument_category || 'linear').toLowerCase()

    const category =

        cat === 'spot' || cat === 'inverse' || cat === 'linear' ? cat : 'linear'

    const symbols = [

        ...(Array.isArray(cfg.allowed_symbols) ? (cfg.allowed_symbols as string[]) : []),

        ...(Array.isArray(cfg.instruments) ? (cfg.instruments as string[]) : []),

    ]

    const rawMode = String(cfg.universe_mode || '').toLowerCase()

    let cryptoUniverseMode: 'fixed' | 'auto' = 'auto'

    if (rawMode === 'fixed' || rawMode === 'auto') {

        cryptoUniverseMode = rawMode

    } else if (symbols.length > 0) {

        cryptoUniverseMode = 'fixed'

    } else if (cu.enabled === false) {

        cryptoUniverseMode = 'fixed'

    }

    return {

        bybitTestnet: bybit.testnet === true,

        instrumentCategory: category,

        leverage: Math.max(1, Number(bybit.leverage ?? 1)),

        makerFeePct: Number((Number(costs.maker_fee_rate ?? 0.0001) * 100).toFixed(4)),

        takerFeePct: Number((Number(costs.taker_fee_rate ?? 0.0006) * 100).toFixed(4)),

        fundingMode: normalizeFundingMode(
            costs.funding_mode as string | undefined,
            costs.funding_rate_enabled !== false,
        ),

        backtestExecution:
            (costs.backtest_execution as 'limit_maker' | 'market_taker' | undefined) ?? 'market_taker',

        backtestFeeModel:
            (costs.backtest_fee_model as 'maker_taker' | 'taker_only' | 'maker_only' | undefined) ??
            'maker_taker',

        maintenanceMarginPct: Number(
            (Number(bybit.maintenance_margin_rate ?? 0.005) * 100).toFixed(4),
        ),

        cryptoUniverseMode,

        cryptoMinVolume24hUsd: Number(cu.min_volume_24h_usd ?? CRYPTO_UNIVERSE_DEFAULTS.minVolume24hUsd),

        cryptoMinLastPrice: Number(cu.min_last_price ?? CRYPTO_UNIVERSE_DEFAULTS.minLastPrice),

        cryptoMaxSpreadBps: Number(cu.max_spread_bps ?? CRYPTO_UNIVERSE_DEFAULTS.maxSpreadBps),

        cryptoMaxFundingRatePct: Number(
            (Number(cu.max_funding_rate ?? CRYPTO_UNIVERSE_DEFAULTS.maxFundingRatePct / 100) * 100).toFixed(4),
        ),

        cryptoMinFundingRatePct: Number(
            (Number(cu.min_funding_rate ?? CRYPTO_UNIVERSE_DEFAULTS.minFundingRatePct / 100) * 100).toFixed(4),
        ),

        cryptoMinOpenInterestUsd: Number(
            cu.min_open_interest_usd ?? CRYPTO_UNIVERSE_DEFAULTS.minOpenInterestUsd,
        ),

        cryptoMinLsr: Number(cu.min_lsr ?? CRYPTO_UNIVERSE_DEFAULTS.minLsr),

        cryptoMaxLsr: Number(cu.max_lsr ?? CRYPTO_UNIVERSE_DEFAULTS.maxLsr),

        cryptoMinRvol: Number(cu.min_rvol ?? CRYPTO_UNIVERSE_DEFAULTS.minRvol),

        cryptoMinAtrPercent: Number(cu.min_atr_percent ?? CRYPTO_UNIVERSE_DEFAULTS.minAtrPercent),

        cryptoMaxAtrPercent: Number(cu.max_atr_percent ?? CRYPTO_UNIVERSE_DEFAULTS.maxAtrPercent),

        cryptoLookbackDays: Number(cu.lookback_days ?? CRYPTO_UNIVERSE_DEFAULTS.lookbackDays),

        cryptoFundingLookbackHours: Math.max(1, Number(cu.funding_lookback_hours ?? 8)),

        cryptoRefreshEveryMinutes: Math.max(
            0,
            Number((cu.refresh as { every_minutes?: number } | undefined)?.every_minutes ?? 60),
        ),

    }

}


