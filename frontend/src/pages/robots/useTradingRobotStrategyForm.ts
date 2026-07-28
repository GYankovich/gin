import { useCallback, useEffect, useRef, useState } from 'react'
import { robotService } from '@/services/robotService'
import { normalizeSignalInterval } from '@/pages/testing/testingPipeline'
import {
    getGrainSeedRiskPreset,
    getStrategyParamsPreset,
    listStrategyMeta,
    stripTradingHoursMsk,
} from '@/pages/testing/strategyPresets'
import { calcMaxPositionFromBudget } from '@/pages/testing/riskParamsValidation'

const DEFAULT_STRATEGY = 'grain_seed'

export type TradingRobotStrategyDraft = {
    strategy: string
    brokerType: string
    capital: number
    strategyParams: Record<string, unknown>
    interval: string
    stopLossPct: number
    takeProfitPct: number
    maxPositionPct: number
    maxPositionRub: number
    maxDailyLoss: number
    minTradeAmountRub: number
}

export function useTradingRobotStrategyForm() {
    const [strategy, setStrategyRaw] = useState(DEFAULT_STRATEGY)
    const [strategyParams, setStrategyParams] = useState<Record<string, unknown>>(() =>
        getStrategyParamsPreset(DEFAULT_STRATEGY),
    )
    const [interval, setIntervalState] = useState<string>(
        () => String(getStrategyParamsPreset(DEFAULT_STRATEGY).interval ?? 'CANDLE_INTERVAL_5_MIN'),
    )
    const [capital, setCapital] = useState(1_000_000)
    const [stopLossPct, setStopLossPct] = useState(2)
    const [takeProfitPct, setTakeProfitPct] = useState(3)
    const [maxPositionPct, setMaxPositionPct] = useState(10)
    const [maxPositionRub, setMaxPositionRub] = useState(50_000)
    const [maxDailyLoss, setMaxDailyLoss] = useState(10_000)
    const [minTradeAmountRub, setMinTradeAmountRub] = useState(500)
    const [brokerCommissionPct, setBrokerCommissionPct] = useState(0.05)
    const [ndflPct, setNdflPct] = useState(15)
    const [brokerType, setBrokerType] = useState('tinvest')
    const [strategyOptions, setStrategyOptions] = useState<Array<{ value: string; label: string }>>(() =>
        listStrategyMeta().map(s => ({ value: s.name, label: s.title })),
    )

    const hydratingRef = useRef(false)

    useEffect(() => {
        robotService
            .getStrategies()
            .then(r => {
                const opts = (r.items || []).map(x => ({ value: x.name, label: x.title || x.name }))
                if (opts.length) setStrategyOptions(opts)
            })
            .catch(() => {})
    }, [])

    const setStrategy = useCallback((next: string) => {
        setStrategyRaw(prev => {
            if (prev === next) return prev
            if (!hydratingRef.current) {
                const preset = getStrategyParamsPreset(next)
                setStrategyParams(preset)
                if (preset.interval) setIntervalState(String(preset.interval))
            }
            return next
        })
    }, [])

    const setInterval = useCallback((next: string) => {
        const normalized = normalizeSignalInterval(next)
        setIntervalState(normalized)
        setStrategyParams(prev => ({ ...prev, interval: normalized }))
    }, [])

    const setStrategyParam = useCallback((key: string, value: unknown) => {
        setStrategyParams(prev => ({ ...prev, [key]: value }))
        if (key === 'interval' && typeof value === 'string') {
            setIntervalState(normalizeSignalInterval(value))
        }
    }, [])

    const resetToDefaults = useCallback((strategyName = DEFAULT_STRATEGY) => {
        const risk = getGrainSeedRiskPreset()
        hydratingRef.current = true
        setStrategyRaw(strategyName)
        const preset = getStrategyParamsPreset(strategyName)
        setStrategyParams(preset)
        if (preset.interval) setIntervalState(String(preset.interval))
        setCapital(1_000_000)
        setStopLossPct(risk.stop_loss_percent)
        setTakeProfitPct(risk.take_profit_percent)
        setMaxPositionPct(risk.max_position_percent)
        setMaxPositionRub(calcMaxPositionFromBudget(1_000_000, risk.max_position_percent))
        setMaxDailyLoss(risk.max_daily_loss)
        setMinTradeAmountRub(500)
        setBrokerType('tinvest')
        hydratingRef.current = false
    }, [])

    const hydrateFromConfig = useCallback((cfg: Record<string, unknown>): TradingRobotStrategyDraft => {
        const signalGen = (cfg.signal_generation || {}) as Record<string, unknown>
        const robotStrategy = String(
            cfg.strategy ?? signalGen.strategy ?? DEFAULT_STRATEGY,
        )
        const rawParams =
            (cfg.strategy_params as Record<string, unknown> | undefined) ??
            (signalGen.params as Record<string, unknown> | undefined) ??
            {}
        const risk = cfg.risk as Record<string, unknown> | undefined
        const costs = cfg.costs as Record<string, unknown> | undefined
        const broker = String(cfg.broker_type ?? 'tinvest')
        const isCrypto = broker.toLowerCase() === 'bybit'
        const defaultMinTrade = isCrypto ? 5 : 500

        const preset = getStrategyParamsPreset(robotStrategy)
        const merged: Record<string, unknown> = { ...preset, ...rawParams }
        const nextInterval = normalizeSignalInterval(
            String(merged.interval ?? preset.interval ?? 'CANDLE_INTERVAL_5_MIN'),
        )
        merged.interval = nextInterval

        const nextCapital = Number(rawParams?.initial_capital ?? 1_000_000)
        const nextMaxPct = Number(risk?.max_position_percent ?? 10)
        const nextStop = Number(risk?.stop_loss_percent ?? 2)
        const nextTake = Number(risk?.take_profit_percent ?? 3)
        const nextDailyLoss = Number(risk?.max_daily_loss ?? 10_000)
        const nextMinTrade = Number(risk?.min_trade_amount_rub ?? defaultMinTrade)
        const nextMaxRub = calcMaxPositionFromBudget(nextCapital, nextMaxPct)
        const nextCommission = Number(
            (Number(costs?.broker_commission_rate ?? 0.0005) * 100).toFixed(4),
        )
        const nextNdfl = Number((Number(costs?.ndfl_rate ?? 0.15) * 100).toFixed(2))

        const draft: TradingRobotStrategyDraft = {
            strategy: robotStrategy,
            brokerType: broker,
            capital: nextCapital,
            strategyParams: merged,
            interval: nextInterval,
            stopLossPct: nextStop,
            takeProfitPct: nextTake,
            maxPositionPct: nextMaxPct,
            maxPositionRub: nextMaxRub,
            maxDailyLoss: nextDailyLoss,
            minTradeAmountRub: nextMinTrade,
        }

        hydratingRef.current = true
        setStrategyRaw(draft.strategy)
        setStrategyParams(draft.strategyParams)
        setIntervalState(draft.interval)
        setCapital(draft.capital)
        setStopLossPct(draft.stopLossPct)
        setTakeProfitPct(draft.takeProfitPct)
        setMaxPositionPct(draft.maxPositionPct)
        setMaxPositionRub(draft.maxPositionRub)
        setMaxDailyLoss(draft.maxDailyLoss)
        setMinTradeAmountRub(draft.minTradeAmountRub)
        setBrokerCommissionPct(nextCommission)
        setNdflPct(nextNdfl)
        setBrokerType(draft.brokerType)
        hydratingRef.current = false
        return draft
    }, [])

    const applyCommissionDefaults = useCallback((brokerRatePct: number, ndflRatePct: number) => {
        setBrokerCommissionPct(brokerRatePct)
        setNdflPct(ndflRatePct)
    }, [])

    const getDraft = useCallback(
        (): TradingRobotStrategyDraft => ({
            strategy,
            brokerType,
            capital,
            strategyParams,
            interval,
            stopLossPct,
            takeProfitPct,
            maxPositionPct,
            maxPositionRub: calcMaxPositionFromBudget(capital, maxPositionPct),
            maxDailyLoss,
            minTradeAmountRub,
        }),
        [
            strategy,
            brokerType,
            capital,
            strategyParams,
            interval,
            stopLossPct,
            takeProfitPct,
            maxPositionPct,
            maxDailyLoss,
            minTradeAmountRub,
        ],
    )

    const applyDraft = useCallback((draft: TradingRobotStrategyDraft) => {
        hydratingRef.current = true
        setStrategyRaw(draft.strategy || DEFAULT_STRATEGY)
        const preset = getStrategyParamsPreset(draft.strategy || DEFAULT_STRATEGY)
        const merged = { ...preset, ...draft.strategyParams }
        if (merged.interval) {
            merged.interval = normalizeSignalInterval(String(merged.interval))
            setIntervalState(String(merged.interval))
        }
        setStrategyParams(merged)
        setCapital(draft.capital)
        setStopLossPct(draft.stopLossPct)
        setTakeProfitPct(draft.takeProfitPct)
        setMaxPositionPct(draft.maxPositionPct)
        setMaxPositionRub(draft.maxPositionRub)
        setMaxDailyLoss(draft.maxDailyLoss)
        setMinTradeAmountRub(Number(draft.minTradeAmountRub ?? 500))
        setBrokerType(draft.brokerType || 'tinvest')
        hydratingRef.current = false
    }, [])

    return {
        strategy,
        setStrategy,
        strategyParams,
        setStrategyParams,
        setStrategyParam,
        interval,
        setInterval,
        capital,
        setCapital,
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
        minTradeAmountRub,
        setMinTradeAmountRub,
        brokerCommissionPct,
        setBrokerCommissionPct,
        ndflPct,
        setNdflPct,
        brokerType,
        setBrokerType,
        strategyOptions,
        resetToDefaults,
        hydrateFromConfig,
        applyCommissionDefaults,
        getDraft,
        applyDraft,
    }
}

export function tradingHoursFromSchedule(hoursFrom: string, hoursTo: string, weekdaysMask: number) {
    return {
        tradingHoursStart: stripTradingHoursMsk(hoursFrom) || '10:00',
        tradingHoursEnd: stripTradingHoursMsk(hoursTo) || '18:45',
        allowedWeekdays: weekdaysMask,
    }
}
