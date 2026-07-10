import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'
import {
    type PipelineFilterType,
    createDefaultTestingPipelineFilters,
    type PipelineFilter,
} from '@/pages/testing/testingPipeline'
import {
    defaultIntervalForMarket,
    normalizeStrategyInterval,
} from '@/pages/testing/strategyIntervals'
import {
    getGrainSeedRiskPreset,
    getStrategyParamsPreset,
    listStrategyMeta,
    stripTradingHoursMsk,
} from '@/pages/testing/strategyPresets'
import {
    formatFixedTickers,
    normalizeUniverseMode,
    type UniverseMode,
} from '@/utils/universeMode'
import {
    cryptoDefaultsFromConfig,
    isCryptoBroker,
} from '@/modules/robots/config/builders/buildCryptoConfig'
import {
    createDefaultCryptoScreeningFilters,
    cryptoFieldsFromFilters,
    cryptoFiltersFromFields,
    cryptoScreeningFiltersFromPreset,
    defaultValueForCryptoFilterType,
    type CryptoScreeningFilter,
    type CryptoScreeningFilterType,
} from '@/pages/testing/cryptoScreeningPipeline'
import type { UniverseFilterPresetId } from '@/modules/robots/config/universeFilterPresets'
import {
    applyTestingMarketPresets,
    marketFromBroker,
    robotMatchesMarket,
    type TestingMarket,
} from '@/pages/testing/refactored/market'
import { defaultBacktestPeriod, defaultTestName } from '@/pages/testing/testingUtils'
import {
    DEFAULT_EXECUTION_LATENCY_SEC,
    DEFAULT_MAX_DRAWDOWN_PCT,
    defaultSlippagePct,
    normalizeFundingMode,
    type FundingSimulationMode,
} from '@/pages/testing/executionRiskDefaults'

type RobotSchedule = { interval_seconds?: number }

const DEFAULT_STRATEGY = 'grain_seed'

export function useTestingRobotForm() {
    const [robots, setRobots] = useState<Robot[]>([])
    const [robotId, setRobotId] = useState<number | null>(null)
    const [capital, setCapital] = useState(1_000_000)
    const [strategy, setStrategyRaw] = useState(DEFAULT_STRATEGY)
    /**
     * Универсальный набор параметров выбранной стратегии.
     * Ключи зависят от `strategy` — см. `strategyPresets.ts` и формы
     * `TestingStrategyParamsCard`.
     */
    const [strategyParams, setStrategyParams] = useState<Record<string, unknown>>(() =>
        getStrategyParamsPreset(DEFAULT_STRATEGY),
    )
    const [interval, setIntervalState] = useState<string>(() =>
        defaultIntervalForMarket('moex'),
    )
    const [stopLossPct, setStopLossPct] = useState(2)
    const [takeProfitPct, setTakeProfitPct] = useState(3)
    const [maxPositionPct, setMaxPositionPct] = useState(10)
    const [maxPositionRub, setMaxPositionRub] = useState(50_000)
    const [maxDailyLoss, setMaxDailyLoss] = useState(5)
    const [slippagePct, setSlippagePct] = useState(() => defaultSlippagePct('moex'))
    const [executionLatencySec, setExecutionLatencySec] = useState(DEFAULT_EXECUTION_LATENCY_SEC)
    const [maxDrawdownPct, setMaxDrawdownPct] = useState(DEFAULT_MAX_DRAWDOWN_PCT)
    const [tradingHoursStart, setTradingHoursStart] = useState('10:00')
    const [tradingHoursEnd, setTradingHoursEnd] = useState('18:45')
    const [allowedWeekdays, setAllowedWeekdays] = useState(31)
    const [brokerCommissionPct, setBrokerCommissionPct] = useState(0.05)
    const [ndflPct, setNdflPct] = useState(15)
    const [brokerType, setBrokerType] = useState('tinvest')
    const [bybitTestnet, setBybitTestnet] = useState(false)
    const [instrumentCategory, setInstrumentCategory] = useState<'spot' | 'linear' | 'inverse'>('linear')
    const [leverage, setLeverage] = useState(1)
    const [makerFeePct, setMakerFeePct] = useState(0.01)
    const [takerFeePct, setTakerFeePct] = useState(0.06)
    const [fundingMode, setFundingMode] = useState<FundingSimulationMode>('historical')
    const [backtestExecution, setBacktestExecution] = useState<'limit_maker' | 'market_taker'>('market_taker')
    const [backtestFeeModel, setBacktestFeeModel] = useState<'maker_taker' | 'taker_only' | 'maker_only'>(
        'maker_taker',
    )
    const [maintenanceMarginPct, setMaintenanceMarginPct] = useState(0.5)
    const [pollValue, setPollValue] = useState<number>(5)
    const [pollUnit, setPollUnit] = useState<'minutes' | 'hours'>('minutes')
    const [pipelineMode, setPipelineMode] = useState<'ALL' | 'ANY'>('ALL')
    const [universeRefreshMinutes, setUniverseRefreshMinutes] = useState(0)
    const [universeMode, setUniverseMode] = useState<UniverseMode>('dms_pipeline')
    const [cryptoUniverseMode, setCryptoUniverseMode] = useState<'fixed' | 'auto'>('auto')
    const [cryptoFilters, setCryptoFilters] = useState<CryptoScreeningFilter[]>(() => createDefaultCryptoScreeningFilters())
    const cryptoUniverseFields = useMemo(() => cryptoFieldsFromFilters(cryptoFilters), [cryptoFilters])
    const [fixedTickersText, setFixedTickersText] = useState('')
    const [filters, setFilters] = useState<PipelineFilter[]>(() => createDefaultTestingPipelineFilters())
    const defaultPeriod = defaultBacktestPeriod()
    const [fromDate, setFromDate] = useState(defaultPeriod.fromDate)
    const [toDate, setToDate] = useState(defaultPeriod.toDate)
    const [testName, setTestName] = useState(() => defaultTestName('moex'))

    const [loading, setLoading] = useState(true)
    const [invalid, setInvalid] = useState<Record<string, boolean>>({})
    const [configDirty, setConfigDirty] = useState(false)
    const [strategyOptions, setStrategyOptions] = useState<Array<{ value: string; label: string }>>(() =>
        listStrategyMeta().map(s => ({ value: s.name, label: s.title })),
    )

    /** Подстановка пресета при ручной смене стратегии (без перетирания при гидратации робота). */
    const hydratingRef = useRef(false)

    const setStrategy = useCallback(
        (next: string) => {
            setStrategyRaw(prev => {
                if (prev === next) return prev
                if (!hydratingRef.current) {
                    const preset = getStrategyParamsPreset(next)
                    const iv = defaultIntervalForMarket(marketFromBroker(brokerType))
                    setStrategyParams({ ...preset, interval: iv })
                    setIntervalState(iv)
                }
                return next
            })
        },
        [brokerType],
    )

    const setInterval = useCallback(
        (next: string) => {
            const normalized = normalizeStrategyInterval(next, brokerType)
            setIntervalState(normalized)
            setStrategyParams(prev => ({ ...prev, interval: normalized }))
        },
        [brokerType],
    )

    const setStrategyParam = useCallback(
        (key: string, value: unknown) => {
            setStrategyParams(prev => ({ ...prev, [key]: value }))
            if (key === 'interval' && typeof value === 'string') {
                setIntervalState(normalizeStrategyInterval(value, brokerType))
            }
        },
        [brokerType],
    )

    useEffect(() => {
        robotService
            .getStrategies()
            .then(r => {
                const opts = (r.items || []).map(x => ({ value: x.name, label: x.title || x.name }))
                if (opts.length) setStrategyOptions(opts)
            })
            .catch(() => {})
    }, [])

    useEffect(() => {
        Promise.all([robotService.list(100, 0)])
            .then(([r]) => {
                setRobots(r.items)
            })
            .finally(() => setLoading(false))
    }, [])

    const selectedRobot = useMemo(() => robots.find(r => r.id === robotId) ?? null, [robots, robotId])

    const applyGrainSeedRiskPresetToForm = useCallback(() => {
        const p = getGrainSeedRiskPreset()
        setStopLossPct(p.stop_loss_percent)
        setTakeProfitPct(p.take_profit_percent)
        setMaxPositionPct(p.max_position_percent)
        setMaxPositionRub(p.max_position_rub)
        setMaxDailyLoss(p.max_daily_loss)
        setTradingHoursStart(stripTradingHoursMsk(p.trading_hours_start))
        setTradingHoursEnd(stripTradingHoursMsk(p.trading_hours_end))
        setAllowedWeekdays(p.allowed_weekdays)
    }, [])

    useEffect(() => {
        if (robotId != null) return
        if (isCryptoBroker(brokerType)) return
        applyGrainSeedRiskPresetToForm()
        setFilters(createDefaultTestingPipelineFilters())
    }, [robotId, brokerType, applyGrainSeedRiskPresetToForm])

    useEffect(() => {
        if (!selectedRobot) return
        const cfg = (selectedRobot.config ?? {}) as Record<string, unknown>
        const robotStrategy = String(cfg.strategy ?? DEFAULT_STRATEGY)
        const rawParams = (cfg.strategy_params as Record<string, unknown> | undefined) ?? {}
        const risk = cfg.risk as Record<string, unknown> | undefined
        const costs = cfg.costs as Record<string, unknown> | undefined
        const execModel = cfg.execution_model as Record<string, unknown> | undefined
        const pipeline = cfg.pipeline as Record<string, unknown> | undefined
        const loadedFilters: unknown[] = Array.isArray(pipeline?.filters) ? (pipeline.filters as unknown[]) : []
        const scheduleSeconds = Number((selectedRobot as Robot & { schedule?: RobotSchedule }).schedule?.interval_seconds ?? 0)
        if (scheduleSeconds > 0 && scheduleSeconds < 3600) {
            setPollUnit('minutes')
            setPollValue(Math.max(1, Math.round(scheduleSeconds / 60)))
        } else if (scheduleSeconds >= 3600) {
            setPollUnit('hours')
            setPollValue(Math.max(1 / 60, Number((scheduleSeconds / 3600).toFixed(2))))
        } else {
            setPollUnit('minutes')
            setPollValue(5)
        }
        setCapital(Number(rawParams?.initial_capital ?? 1_000_000))

        hydratingRef.current = true
        setStrategyRaw(robotStrategy)
        const preset = getStrategyParamsPreset(robotStrategy)
        const merged: Record<string, unknown> = { ...preset, ...rawParams }
        const broker = String(cfg.broker_type ?? 'tinvest')
        setBrokerType(broker)
        if (merged.interval) {
            merged.interval = normalizeStrategyInterval(String(merged.interval), broker)
            setIntervalState(String(merged.interval))
        }
        setStrategyParams(merged)
        hydratingRef.current = false

        setStopLossPct(Number(risk?.stop_loss_percent ?? 2))
        setTakeProfitPct(Number(risk?.take_profit_percent ?? 3))
        setMaxPositionPct(Number(risk?.max_position_percent ?? 10))
        setMaxPositionRub(Number(risk?.max_position_rub ?? 50_000))
        setMaxDailyLoss(Number(risk?.max_daily_loss ?? 5))
        setSlippagePct(
            Number(
                execModel?.slippage_pct ??
                    defaultSlippagePct(isCryptoBroker(broker) ? 'crypto' : 'moex'),
            ),
        )
        setExecutionLatencySec(Number(execModel?.latency_sec ?? 0))
        setMaxDrawdownPct(Number(risk?.max_drawdown_percent ?? DEFAULT_MAX_DRAWDOWN_PCT))
        setTradingHoursStart(stripTradingHoursMsk(String(risk?.trading_hours_start ?? '10:00 MSK')) || '10:00')
        setTradingHoursEnd(stripTradingHoursMsk(String(risk?.trading_hours_end ?? '18:45 MSK')) || '18:45')
        setAllowedWeekdays(Number(risk?.allowed_weekdays ?? 31))
        setBrokerCommissionPct(Number((Number(costs?.broker_commission_rate ?? 0.0005) * 100).toFixed(4)))
        setNdflPct(Number((Number(costs?.ndfl_rate ?? 0.15) * 100).toFixed(2)))
        if (isCryptoBroker(broker)) {
            const crypto = cryptoDefaultsFromConfig(cfg)
            setBybitTestnet(crypto.bybitTestnet)
            setInstrumentCategory(crypto.instrumentCategory)
            setLeverage(crypto.leverage)
            setMakerFeePct(crypto.makerFeePct)
            setTakerFeePct(crypto.takerFeePct)
            setFundingMode(
                normalizeFundingMode(
                    costs?.funding_mode as string | undefined,
                    costs?.funding_rate_enabled !== false,
                ),
            )
            setBacktestExecution(crypto.backtestExecution ?? 'market_taker')
            setBacktestFeeModel(crypto.backtestFeeModel ?? 'maker_taker')
            setMaintenanceMarginPct(crypto.maintenanceMarginPct ?? 0.5)
            setCryptoUniverseMode(crypto.cryptoUniverseMode)
            setCryptoFilters(
                cryptoFiltersFromFields({
                    cryptoMinVolume24hUsd: crypto.cryptoMinVolume24hUsd,
                    cryptoMinLastPrice: crypto.cryptoMinLastPrice,
                    cryptoMaxSpreadBps: crypto.cryptoMaxSpreadBps,
                    cryptoMaxFundingRatePct: crypto.cryptoMaxFundingRatePct,
                    cryptoMinFundingRatePct: crypto.cryptoMinFundingRatePct,
                    cryptoMinOpenInterestUsd: crypto.cryptoMinOpenInterestUsd,
                    cryptoMinLsr: crypto.cryptoMinLsr,
                    cryptoMaxLsr: crypto.cryptoMaxLsr,
                    cryptoMinRvol: crypto.cryptoMinRvol,
                    cryptoMinAtrPercent: crypto.cryptoMinAtrPercent,
                    cryptoMaxAtrPercent: crypto.cryptoMaxAtrPercent,
                    cryptoLookbackDays: crypto.cryptoLookbackDays,
                    cryptoFundingLookbackHours: crypto.cryptoFundingLookbackHours,
                    cryptoRefreshEveryMinutes: crypto.cryptoRefreshEveryMinutes,
                }),
            )
            setNdflPct(0)
            const symbols = Array.isArray(cfg.allowed_symbols)
                ? (cfg.allowed_symbols as string[])
                : Array.isArray(cfg.instruments)
                  ? (cfg.instruments as string[])
                  : Array.isArray(cfg.fixed_tickers)
                    ? (cfg.fixed_tickers as string[])
                    : []
            if (symbols.length) {
                setFixedTickersText(formatFixedTickers(symbols))
            }
        }
        setPipelineMode(pipeline?.mode === 'ANY' ? 'ANY' : 'ALL')
        setUniverseRefreshMinutes(Math.max(0, Number(cfg.universe_refresh_minutes ?? 0)))
        setUniverseMode(normalizeUniverseMode(cfg.universe_mode))
        setFixedTickersText(
            formatFixedTickers(Array.isArray(cfg.fixed_tickers) ? (cfg.fixed_tickers as string[]) : []),
        )
        setFilters(
            loadedFilters.length
                ? loadedFilters.map((raw, idx) => {
                      const f = raw as Record<string, unknown>
                      return {
                          id: `${f.type || 'filter'}-${idx}-${Date.now()}`,
                          type: (f.type || 'volume') as PipelineFilterType,
                          min: f.min != null ? Number(f.min) : undefined,
                          max_percent: f.max_percent != null ? Number(f.max_percent) : undefined,
                          min_percent: f.min_percent != null ? Number(f.min_percent) : undefined,
                          period: f.period != null ? Number(f.period) : undefined,
                          eq: f.eq != null ? String(f.eq) : undefined,
                          direction: f.direction as PipelineFilter['direction'] | undefined,
                          max_steps: f.max_steps != null ? Number(f.max_steps) : undefined,
                          min_ratio: f.min_ratio != null ? Number(f.min_ratio) : undefined,
                          list: Array.isArray(f.list)
                              ? f.list.map((x: unknown) => String(x).toUpperCase())
                              : (f.list as string[] | null | undefined) ?? null,
                      }
                  })
                : createDefaultTestingPipelineFilters(),
        )
        setConfigDirty(false)
    }, [selectedRobot])

    useEffect(() => {
        if (robotId != null) return
        if (!isCryptoBroker(brokerType)) return
        setCryptoUniverseMode('auto')
        setNdflPct(0)
    }, [brokerType, robotId])

    const addFilter = useCallback((t: PipelineFilterType) => {
        let added = false
        setFilters(prev => {
            if (prev.some(f => f.type === t)) return prev
            added = true
            return [...prev, { id: `${t}-${Date.now()}`, type: t }]
        })
        if (added) setConfigDirty(true)
    }, [])

    const removeFilter = useCallback((id: string) => {
        setFilters(prev => prev.filter(f => f.id !== id))
        setConfigDirty(true)
    }, [])

    const addCryptoFilter = useCallback((t: CryptoScreeningFilterType) => {
        let added = false
        setCryptoFilters(prev => {
            if (prev.some(f => f.type === t)) return prev
            added = true
            return [...prev, { id: `${t}-${Date.now()}`, type: t, value: defaultValueForCryptoFilterType(t) }]
        })
        if (added) setConfigDirty(true)
    }, [])

    const removeCryptoFilter = useCallback((id: string) => {
        setCryptoFilters(prev => prev.filter(f => f.id !== id))
        setConfigDirty(true)
    }, [])

    // Backward-compat: `signalProfile` теперь хранится в `strategyParams.signal_profile`,
    // но эта пара пробрасывается отдельно для существующих компонентов и хуков.
    const signalProfile = useMemo<'legacy' | 'tz_signals_v1'>(() => {
        const raw = String(strategyParams.signal_profile ?? 'legacy').toLowerCase()
        return raw === 'tz_signals_v1' ? 'tz_signals_v1' : 'legacy'
    }, [strategyParams.signal_profile])

    const setSignalProfile = useCallback((next: 'legacy' | 'tz_signals_v1') => {
        setStrategyParams(prev => ({ ...prev, signal_profile: next }))
    }, [])

    const applyCryptoUniversePreset = useCallback((presetId: UniverseFilterPresetId) => {
        setCryptoFilters(cryptoScreeningFiltersFromPreset(presetId))
        setConfigDirty(true)
    }, [])

    const market = useMemo(() => marketFromBroker(brokerType), [brokerType])

    const setMarket = useCallback(
        (next: TestingMarket): { robotCleared: boolean } => {
            if (marketFromBroker(brokerType) === next) {
                return { robotCleared: false }
            }
            let robotCleared = false
            if (selectedRobot && !robotMatchesMarket(selectedRobot, next)) {
                setRobotId(null)
                robotCleared = true
            }
            hydratingRef.current = true
            applyTestingMarketPresets(next, {
                setBrokerType,
                setCapital,
                setStrategy,
                setStrategyParams,
                setIntervalState: setIntervalState,
                setStopLossPct,
                setTakeProfitPct,
                setMaxPositionPct,
                setMaxPositionRub,
                setMaxDailyLoss,
                setTradingHoursStart,
                setTradingHoursEnd,
                setAllowedWeekdays,
                setBrokerCommissionPct,
                setNdflPct,
                setPipelineMode,
                setFilters,
                setUniverseMode,
                setUniverseRefreshMinutes,
                setFixedTickersText,
                setCryptoUniverseMode,
                setCryptoFilters,
                setBybitTestnet,
                setInstrumentCategory,
                setLeverage,
                setMakerFeePct,
                setTakerFeePct,
                setFundingMode,
                setSlippagePct,
                setExecutionLatencySec,
                setMaxDrawdownPct,
                setBacktestExecution,
                setBacktestFeeModel,
                setMaintenanceMarginPct,
            })
            setTestName(defaultTestName(next))
            hydratingRef.current = false
            setConfigDirty(true)
            return { robotCleared }
        },
        [brokerType, selectedRobot],
    )

    return {
        robots,
        setRobots,
        robotId,
        setRobotId,
        capital,
        setCapital,
        strategy,
        setStrategy,
        strategyParams,
        setStrategyParams,
        setStrategyParam,
        interval,
        setInterval,
        stopLossPct,
        setStopLossPct,
        takeProfitPct,
        setTakeProfitPct,
        maxPositionPct,
        setMaxPositionPct,
        maxPositionRub,
        setMaxPositionRub,
        maxDailyLoss,
        setMaxDailyLoss,
        slippagePct,
        setSlippagePct,
        executionLatencySec,
        setExecutionLatencySec,
        maxDrawdownPct,
        setMaxDrawdownPct,
        tradingHoursStart,
        setTradingHoursStart,
        tradingHoursEnd,
        setTradingHoursEnd,
        allowedWeekdays,
        setAllowedWeekdays,
        brokerCommissionPct,
        setBrokerCommissionPct,
        ndflPct,
        setNdflPct,
        brokerType,
        setBrokerType,
        bybitTestnet,
        setBybitTestnet,
        instrumentCategory,
        setInstrumentCategory,
        leverage,
        setLeverage,
        makerFeePct,
        setMakerFeePct,
        takerFeePct,
        setTakerFeePct,
        fundingMode,
        setFundingMode,
        backtestExecution,
        setBacktestExecution,
        backtestFeeModel,
        setBacktestFeeModel,
        maintenanceMarginPct,
        setMaintenanceMarginPct,
        pollValue,
        setPollValue,
        pollUnit,
        setPollUnit,
        pipelineMode,
        setPipelineMode,
        universeRefreshMinutes,
        setUniverseRefreshMinutes,
        universeMode,
        setUniverseMode,
        cryptoUniverseMode,
        setCryptoUniverseMode,
        cryptoFilters,
        setCryptoFilters,
        ...cryptoUniverseFields,
        fixedTickersText,
        setFixedTickersText,
        filters,
        setFilters,
        signalProfile,
        setSignalProfile,
        fromDate,
        setFromDate,
        toDate,
        setToDate,
        loading,
        invalid,
        setInvalid,
        configDirty,
        setConfigDirty,
        strategyOptions,
        selectedRobot,
        addFilter,
        removeFilter,
        addCryptoFilter,
        removeCryptoFilter,
        market,
        setMarket,
        testName,
        setTestName,
        applyCryptoUniversePreset,
    }
}
