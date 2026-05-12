import { useCallback, useEffect, useMemo, useState } from 'react'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'
import {
    type PipelineFilter,
    type PipelineFilterType,
    normalizeSignalInterval,
} from '@/pages/testing/testingPipeline'

type RobotSchedule = { interval_seconds?: number }

export function useTestingRobotForm() {
    const [robots, setRobots] = useState<Robot[]>([])
    const [robotId, setRobotId] = useState<number | null>(null)
    const [capital, setCapital] = useState(1_000_000)
    const [strategy, setStrategy] = useState('grain_seed')
    const [interval, setInterval] = useState('CANDLE_INTERVAL_10_MIN')
    const [stopLossPct, setStopLossPct] = useState(2)
    const [takeProfitPct, setTakeProfitPct] = useState(3)
    const [maxPositionPct, setMaxPositionPct] = useState(10)
    const [maxPositionRub, setMaxPositionRub] = useState(50_000)
    const [brokerCommissionPct, setBrokerCommissionPct] = useState(0.05)
    const [ndflPct, setNdflPct] = useState(15)
    const [brokerType, setBrokerType] = useState('tinvest')
    const [pollValue, setPollValue] = useState<number>(5)
    const [pollUnit, setPollUnit] = useState<'minutes' | 'hours'>('minutes')
    const [pipelineMode, setPipelineMode] = useState<'ALL' | 'ANY'>('ALL')
    const [filters, setFilters] = useState<PipelineFilter[]>([])
    const [fromDate, setFromDate] = useState('')
    const [toDate, setToDate] = useState('')

    const [loading, setLoading] = useState(true)
    const [invalid, setInvalid] = useState<Record<string, boolean>>({})
    const [configDirty, setConfigDirty] = useState(false)

    const [strategyOptions, setStrategyOptions] = useState<Array<{ value: string; label: string }>>([
        { value: 'grain_seed', label: 'grain_seed' },
    ])

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
                const firstTradeRobot = r.items.find(x => x.type === 2)
                if (firstTradeRobot) setRobotId(firstTradeRobot.id)
                else if (r.items.length > 0) setRobotId(r.items[0].id)
            })
            .finally(() => setLoading(false))
    }, [])

    const selectedRobot = useMemo(() => robots.find(r => r.id === robotId) ?? null, [robots, robotId])

    useEffect(() => {
        if (!selectedRobot) return
        const cfg = (selectedRobot.config ?? {}) as Record<string, unknown>
        const strategyParams = cfg.strategy_params as Record<string, unknown> | undefined
        const risk = cfg.risk as Record<string, unknown> | undefined
        const costs = cfg.costs as Record<string, unknown> | undefined
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
        setCapital(Number(strategyParams?.initial_capital ?? 1_000_000))
        setStrategy(String(cfg.strategy ?? 'grain_seed'))
        setInterval(normalizeSignalInterval(String(strategyParams?.interval ?? 'CANDLE_INTERVAL_10_MIN')))
        setStopLossPct(Number(risk?.stop_loss_percent ?? 2))
        setTakeProfitPct(Number(risk?.take_profit_percent ?? 3))
        setMaxPositionPct(Number(risk?.max_position_percent ?? 10))
        setMaxPositionRub(Number(risk?.max_position_rub ?? 50_000))
        setBrokerCommissionPct(Number((Number(costs?.broker_commission_rate ?? 0.0005) * 100).toFixed(4)))
        setNdflPct(Number((Number(costs?.ndfl_rate ?? 0.15) * 100).toFixed(2)))
        setBrokerType(String(cfg.broker_type ?? 'tinvest'))
        setPipelineMode(pipeline?.mode === 'ANY' ? 'ANY' : 'ALL')
        setFilters(
            loadedFilters.map((raw, idx) => {
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
                    list: Array.isArray(f.list) ? f.list.map((x: unknown) => String(x).toUpperCase()) : (f.list as string[] | null | undefined) ?? null,
                }
            }),
        )
        setConfigDirty(false)
    }, [selectedRobot])

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

    return {
        robots,
        setRobots,
        robotId,
        setRobotId,
        capital,
        setCapital,
        strategy,
        setStrategy,
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
        brokerCommissionPct,
        setBrokerCommissionPct,
        ndflPct,
        setNdflPct,
        brokerType,
        setBrokerType,
        pollValue,
        setPollValue,
        pollUnit,
        setPollUnit,
        pipelineMode,
        setPipelineMode,
        filters,
        setFilters,
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
    }
}
