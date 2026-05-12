import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'
import { useToast } from '@/components/ui/Toast'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { api } from '@/services/api'
import { useSearchParams } from 'react-router-dom'
import { RobotIllustration } from '@/components/ui/RobotIllustration'

///@EPIC Frontend.ITEM RobotsUI.TOPIC Trading Robot Configuration [1]
///@ Главная форма настройки торгового робота: pipeline-фильтры, риск/costs, расписание,
///@ пресеты и интеграция с robots API для create/update/preview сценариев.
type PipelineFilterType =
    | 'security_status'
    | 'trading_status'
    | 'volume'
    | 'num_trades'
    | 'gap'
    | 'spread'
    | 'atr'
    | 'capitalization'
    | 'allowed_tickers'
    | 'min_step_ratio'
    | 'excluded_tickers'
    | 'turnover'
    | 'gap_retention'
    | 'price_vs_open'
    | 'opening_range'
type PipelineFilter = {
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

type DraftSnapshot = {
    name: string
    tokenId: number
    robotType: 1 | 2
    pollValue: number
    pollUnit: 'minutes' | 'hours'
    brokerCommissionRate: number
    ndflRate: number
    hoursFrom: string
    hoursTo: string
    weekdaysMask: number
    pipelineMode: 'ALL' | 'ANY'
    filters: Array<{
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
    }>
}

function parseTickers(v: string): string[] {
    return v
        .split(',')
        .map(x => x.trim().toUpperCase())
        .filter(Boolean)
}

const FILTER_META: Record<PipelineFilterType, { label: string }> = {
    security_status: { label: 'Статус' },
    trading_status: { label: 'Торги' },
    volume: { label: 'Объем' },
    num_trades: { label: 'Сделки' },
    gap: { label: 'Утренний гэп (%)' },
    spread: { label: 'Спред (%)' },
    atr: { label: 'ATR (%)' },
    capitalization: { label: 'Капитализация' },
    allowed_tickers: { label: 'Одобренные бумаги' },
    excluded_tickers: { label: 'Исключенные бумаги' },
    min_step_ratio: { label: 'Мин. шаг / комиссия' },
    turnover: { label: 'Оборачиваемость (%)' },
    gap_retention: { label: 'Удержание гэпа (ratio)' },
    price_vs_open: { label: 'Цена vs открытие (%)' },
    opening_range: { label: 'Диапазон открытия (%)' },
}

const DEFAULT_PIPELINE_FILTERS: Array<Omit<PipelineFilter, 'id'>> = [
    { type: 'security_status', eq: 'A' },
    { type: 'trading_status', eq: 'T' },
    { type: 'volume', min: 50_000_000 },
    { type: 'num_trades', min: 100 },
    { type: 'gap', max_percent: 2.5, direction: 'BOTH' },
    { type: 'spread', max_percent: 0.15 },
    { type: 'atr', min_percent: 1.5, period: 14 },
    { type: 'turnover', min_percent: 0.1 },
    { type: 'gap_retention', min_ratio: 0.5 },
]

const FILTER_TOOLTIP: Record<PipelineFilterType, string[]> = {
    security_status: ["SECURITIES.STATUS == 'A'", 'Бумага активна и допущена к торгам.'],
    trading_status: ["MARKETDATA.TRADINGSTATUS == 'T'", 'Инструмент в режиме торгов.'],
    volume: ['VALTODAY >= 50M RUB', 'Дневной объем в рублях. Фильтр ликвидности.'],
    num_trades: ['NUMTRADES >= 100', 'Количество сделок за сессию.'],
    gap: ['ABS(OPEN - PREVPRICE) / PREVPRICE <= 2.5%', 'Утренний разрыв цены. BOTH / UP_ONLY / DOWN_ONLY.'],
    spread: ['(ASK - BID) / BID <= 0.15%', 'Разница между покупкой и продажей.'],
    atr: ['ATR(14) / LAST >= 1.5%', 'Средняя волатильность. Гарантирует движение.'],
    capitalization: ['ISSUESIZE * LAST >= 10B RUB', 'Рыночная капитализация.'],
    allowed_tickers: ['TICKER IN (SBER, LKOH, ...)', 'Белый список. Пусто = игнорируется.'],
    excluded_tickers: ['TICKER NOT IN (...)', 'Черный список. Пусто = игнорируется.'],
    min_step_ratio: ['MINSTEP ratio filter', 'Технический фильтр шага цены к комиссии.'],
    turnover: ['VOLTODAY / ISSUESIZE >= 0.3%', 'Оборачиваемость выпуска. Фильтр ликвидности.'],
    gap_retention: ['|LAST - OPEN| / |OPEN - CLOSEPRICE| >= 0.7', 'Продолжение движения после гэпа. >0.7 = тренд, <0.3 = откат.'],
    price_vs_open: ['LAST / OPEN >= 0.998', 'Цена не упала более чем на 0.2% от открытия.'],
    opening_range: ['(HIGH - LOW) / CLOSEPRICE >= 1.5%', 'Достаточно широкий диапазон для торговли.'],
}

const PRESETS: Record<'conservative' | 'moderate' | 'aggressive', { mode: 'ALL' | 'ANY'; filters: Array<Omit<PipelineFilter, 'id'>> }> = {
    conservative: {
        mode: 'ALL',
        filters: [
            { type: 'security_status', eq: 'A' },
            { type: 'trading_status', eq: 'T' },
            { type: 'volume', min: 500_000_000 },
            { type: 'num_trades', min: 500 },
            { type: 'gap', max_percent: 1.5, direction: 'UP_ONLY' },
            { type: 'spread', max_percent: 0.05 },
            { type: 'atr', min_percent: 1.0, period: 14 },
            { type: 'min_step_ratio', max_steps: 3 },
            { type: 'turnover', min_percent: 0.3 },
            { type: 'gap_retention', min_ratio: 0.7 },
            { type: 'price_vs_open', min_percent: 0.998 },
        ],
    },
    moderate: {
        mode: 'ALL',
        filters: [
            { type: 'security_status', eq: 'A' },
            { type: 'trading_status', eq: 'T' },
            { type: 'volume', min: 100_000_000 },
            { type: 'num_trades', min: 200 },
            { type: 'gap', max_percent: 2.5, direction: 'BOTH' },
            { type: 'spread', max_percent: 0.1 },
            { type: 'atr', min_percent: 1.2, period: 14 },
            { type: 'turnover', min_percent: 0.2 },
            { type: 'gap_retention', min_ratio: 0.5 },
            { type: 'opening_range', min_percent: 1.0 },
        ],
    },
    aggressive: {
        mode: 'ANY',
        filters: [
            { type: 'security_status', eq: 'A' },
            { type: 'trading_status', eq: 'T' },
            { type: 'volume', min: 30_000_000 },
            { type: 'num_trades', min: 50 },
            { type: 'gap', max_percent: 4.0, direction: 'BOTH' },
            { type: 'spread', max_percent: 0.25 },
            { type: 'atr', min_percent: 1.8, period: 14 },
            { type: 'turnover', min_percent: 0.05 },
            { type: 'price_vs_open', min_percent: 0.99 },
            { type: 'opening_range', min_percent: 0.8 },
        ],
    },
}

export default function TradingRobotSettingsPage() {
    const tradingPollMinuteOptions = [1, 2, 5, 10, 15, 30, 60]
    const [searchParams, setSearchParams] = useSearchParams()
    const toast = useToast()
    const [robots, setRobots] = useState<Robot[]>([])
    const [tokenOptions, setTokenOptions] = useState<Array<{ value: string; label: string }>>([])
    const [selectedRobot, setSelectedRobot] = useState<number | null>(() => {
        const raw = searchParams.get('robotId')
        const parsed = raw ? Number(raw) : null
        return parsed && Number.isFinite(parsed) ? parsed : null
    })
    const [isNewRobot, setIsNewRobot] = useState<boolean>(() => !searchParams.get('robotId'))
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [previewLoading, setPreviewLoading] = useState(false)
    const [preview, setPreview] = useState<{
        total_checked: number
        passed: number
        rejected: number
        sample: any[]
    } | null>(null)
    const [dragFilterId, setDragFilterId] = useState<string | null>(null)
    const [dropIndex, setDropIndex] = useState<number | null>(null)
    const [recentlyMovedFilterId, setRecentlyMovedFilterId] = useState<string | null>(null)

    const [pipelineMode, setPipelineMode] = useState<'ALL' | 'ANY'>('ALL')
    const [filters, setFilters] = useState<PipelineFilter[]>([])
    const [name, setName] = useState('')
    const [tokenId, setTokenId] = useState<number>(0)
    const [robotType, setRobotType] = useState<1 | 2>(2)
    const [pollValue, setPollValue] = useState<number>(5)
    const [pollUnit, setPollUnit] = useState<'minutes' | 'hours'>('minutes')
    const [brokerCommissionRate, setBrokerCommissionRate] = useState<number>(0.05)
    const [ndflRate, setNdflRate] = useState<number>(15)
    const [hoursFrom, setHoursFrom] = useState('10:00')
    const [hoursTo, setHoursTo] = useState('18:45')
    const [weekdaysMask, setWeekdaysMask] = useState(31)
    const [baselineDraft, setBaselineDraft] = useState<string>('')
    const [isEditing, setIsEditing] = useState(false)
    const [robotTypeOptions, setRobotTypeOptions] = useState<Array<{ value: string; label: string }>>([
        { value: '1', label: 'Portfolio updater' },
        { value: '2', label: 'Trading robot' },
    ])
    const [missingFieldsHint, setMissingFieldsHint] = useState<string[]>([])
    const hydratingDraftRef = useRef(false)
    const isEditingRef = useRef(false)

    const selectedRobotEntity = useMemo(
        () => robots.find(r => r.id === selectedRobot) || null,
        [robots, selectedRobot],
    )

    const buildDraftSnapshot = (): DraftSnapshot => ({
        name: name.trim(),
        tokenId: Number(tokenId || 0),
        robotType,
        pollValue: Number(pollValue || 1),
        pollUnit,
        brokerCommissionRate: Number(brokerCommissionRate || 0),
        ndflRate: Number(ndflRate || 0),
        hoursFrom,
        hoursTo,
        weekdaysMask: Math.max(0, Math.min(127, Number(weekdaysMask || 0))),
        pipelineMode,
        filters: filters.map(f => ({
            type: f.type,
            min: f.min != null ? Number(f.min) : undefined,
            max_percent: f.max_percent != null ? Number(f.max_percent) : undefined,
            min_percent: f.min_percent != null ? Number(f.min_percent) : undefined,
            period: f.period != null ? Number(f.period) : undefined,
            eq: f.eq != null ? String(f.eq) : undefined,
            direction: f.direction,
            max_steps: f.max_steps != null ? Number(f.max_steps) : undefined,
            min_ratio: f.min_ratio != null ? Number(f.min_ratio) : undefined,
            list: Array.isArray(f.list) ? f.list.map(x => String(x).toUpperCase()) : (f.list ?? null),
        })),
    })

    const applyDraft = (draft: DraftSnapshot) => {
        hydratingDraftRef.current = true
        setName(draft.name)
        setTokenId(draft.tokenId)
        setRobotType(draft.robotType)
        setPollValue(draft.pollValue)
        setPollUnit(draft.pollUnit)
        setBrokerCommissionRate(draft.brokerCommissionRate)
        setNdflRate(draft.ndflRate)
        setHoursFrom(draft.hoursFrom)
        setHoursTo(draft.hoursTo)
        setWeekdaysMask(draft.weekdaysMask)
        setPipelineMode(draft.pipelineMode)
        setFilters(
            draft.filters.map((f, idx) => ({
                id: `${f.type}-${idx}-${Date.now()}`,
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
            })),
        )
        setPreview(null)
        setBaselineDraft(JSON.stringify(draft))
        setIsEditing(false)
        queueMicrotask(() => {
            hydratingDraftRef.current = false
        })
    }

    const loadReferenceData = async () => {
        try {
            const keysResp = await api.post('/apikey/data', {})
            const keys = (keysResp.data?.keys || []) as Array<{ id: number; name: string | null; token_type?: { typeName?: string } }>
            setTokenOptions(
                keys.map(k => ({
                    value: String(k.id),
                    label: `${k.name || `Токен #${k.id}`} (${k.token_type?.typeName || 'TYPE'})`,
                })),
            )
            const robotTypesResp = await api.post('/dictionary/data', { tableName: 'ROBOT', columnName: 'TYPE' })
            const typeOptions = (Array.isArray(robotTypesResp.data) ? robotTypesResp.data : [])
                .map((x: any) => ({
                    value: String(x.numericValue ?? ''),
                    label: String(x.name ?? x.stringValue ?? ''),
                }))
                .filter((x: { value: string }) => x.value !== '')
            if (typeOptions.length > 0) {
                setRobotTypeOptions(typeOptions)
            }
            try {
                const defaults = await robotService.getTradingDefaults()
                setBrokerCommissionRate(Number(defaults.broker_commission_rate || 0.0005) * 100)
                setNdflRate(Number(defaults.ndfl_rate || 0.15) * 100)
            } catch {
                // Keep local defaults if endpoint unavailable.
            }
        } catch {
            toast.show('Не удалось загрузить справочники', 'error')
        }
    }

    const loadRobots = async (showLoader = true) => {
        if (showLoader) setLoading(true)
        try {
            const res = await robotService.list(200, 0)
            setRobots(res.items)
            if (!selectedRobot && res.items.length > 0 && !isNewRobot) {
                setSelectedRobot(res.items[0].id)
            }
            return res.items
        } catch {
            toast.show('Не удалось загрузить роботов', 'error')
            return []
        } finally {
            if (showLoader) setLoading(false)
        }
    }

    const openRobotForEdit = (robotId: number) => {
        // Always enter pure view mode first on robot switch.
        hydratingDraftRef.current = true
        setIsEditing(false)
        setBaselineDraft('')
        setIsNewRobot(false)
        setSelectedRobot(robotId)
        setSearchParams({ robotId: String(robotId) })
        queueMicrotask(() => {
            hydratingDraftRef.current = false
        })
    }

    const startCreateRobot = () => {
        setIsNewRobot(true)
        setSelectedRobot(null)
        setSearchParams({})
        setMissingFieldsHint([])
        applyDraft({
            name: '',
            tokenId: 0,
            robotType: 2,
            pollValue: 5,
            pollUnit: 'minutes',
            hoursFrom: '10:00',
            hoursTo: '18:45',
            brokerCommissionRate: brokerCommissionRate || 0.05,
            ndflRate: ndflRate || 15,
            weekdaysMask: 31,
            pipelineMode: 'ALL',
            filters: DEFAULT_PIPELINE_FILTERS,
        })
    }

    const toggleRobotStatus = async (robot: Robot) => {
        const nextStatus = robot.status === 1 ? 2 : 1
        try {
            await robotService.changeStatus(robot.id, nextStatus)
            toast.show(nextStatus === 1 ? 'Робот запущен' : 'Робот остановлен', 'success')
            await loadRobots()
        } catch {
            toast.show('Не удалось изменить статус робота', 'error')
        }
    }

    const deleteRobot = async (robot: Robot) => {
        if (!window.confirm(`Удалить робота «${robot.name}»?`)) return
        try {
            await robotService.deleteRobot(robot.id)
            if (selectedRobot === robot.id) {
                startCreateRobot()
            }
            toast.show('Робот удален', 'success')
            await loadRobots()
        } catch {
            toast.show('Не удалось удалить робота', 'error')
        }
    }

    useEffect(() => {
        const boot = async () => {
            await Promise.all([
                loadReferenceData(),
                loadRobots(true),
            ])
        }
        boot()
    }, [])

    useEffect(() => {
        const loadOne = async () => {
            if (!selectedRobot || isNewRobot) return
            try {
                const r = await robotService.getById(selectedRobot)
                const cfg = (r.config || {}) as any
                const pipeline = (cfg.pipeline || {}) as any
                const filters: any[] = Array.isArray(pipeline.filters) ? pipeline.filters : []
                const schedule = (r as any).schedule || null
                const missing: string[] = []
                const pollFromCfgHours = cfg.poll_interval_hours != null ? Number(cfg.poll_interval_hours) : null
                const pollFromCfgMinutes = pollFromCfgHours != null ? Math.max(1, Math.round(pollFromCfgHours * 60)) : null
                const pollFromScheduleMinutes = schedule?.interval_seconds != null
                    ? Math.max(1, Math.round(Number(schedule.interval_seconds) / 60))
                    : null
                const isTradingRobot = Number(r.type) === 2
                const resolvedPoll = isTradingRobot
                    ? (pollFromScheduleMinutes ?? pollFromCfgMinutes ?? 5)
                    : (pollFromCfgHours ?? (pollFromScheduleMinutes ? Math.max(1, Math.round(pollFromScheduleMinutes / 60)) : null) ?? 1)
                if (pollFromCfgHours == null && pollFromScheduleMinutes == null) missing.push('Частота опроса')
                const startCfg = toTime(String(cfg?.risk?.trading_hours_start || '').replace(' MSK', ''))
                const endCfg = toTime(String(cfg?.risk?.trading_hours_end || '').replace(' MSK', ''))
                const startSch = toTime(schedule?.start_time)
                const endSch = toTime(schedule?.end_time)
                const resolvedStart = startCfg ?? startSch ?? '10:00'
                const resolvedEnd = endCfg ?? endSch ?? '18:45'
                if (!startCfg && !startSch) missing.push('Часы работы (от)')
                if (!endCfg && !endSch) missing.push('Часы работы (до)')
                const weekdaysCfg = cfg?.risk?.allowed_weekdays != null ? Number(cfg.risk.allowed_weekdays) : null
                const weekdaysSch = schedule?.weekdays != null ? Number(schedule.weekdays) : null
                const resolvedWeekdays = weekdaysCfg ?? weekdaysSch ?? 31
                if (weekdaysCfg == null && weekdaysSch == null) missing.push('Дни недели')
                if (r.token?.id == null) missing.push('Токен')
                if (r.type == null) missing.push('Тип робота')
                const normalized: Array<DraftSnapshot['filters'][number]> = filters
                    .filter(f => ['security_status', 'trading_status', 'allowed_tickers', 'volume', 'num_trades', 'gap', 'spread', 'atr', 'capitalization', 'min_step_ratio', 'excluded_tickers', 'exclude_tickers', 'turnover', 'gap_retention', 'price_vs_open', 'opening_range'].includes(String(f?.type)))
                    .map((f) => ({
                        type: (f.type === 'exclude_tickers' ? 'excluded_tickers' : f.type) as PipelineFilterType,
                        min: f.min != null ? Number(f.min) : undefined,
                        max_percent: f.max_percent != null ? Number(f.max_percent) : undefined,
                        min_percent: f.min_percent != null ? Number(f.min_percent) : undefined,
                        period: f.period != null ? Number(f.period) : undefined,
                        eq: f.eq != null ? String(f.eq) : undefined,
                        direction: f.direction === 'UP_ONLY' || f.direction === 'DOWN_ONLY' ? f.direction : 'BOTH',
                        max_steps: f.max_steps != null ? Number(f.max_steps) : undefined,
                        min_ratio: f.min_ratio != null ? Number(f.min_ratio) : undefined,
                        list: Array.isArray(f.list) ? f.list.map((x: any) => String(x).toUpperCase()) : f.list ?? null,
                    }))
                if (isEditingRef.current) {
                    return
                }
                applyDraft({
                    name: r.name || '',
                    tokenId: Number(r.token?.id || 0),
                    robotType: (Number(r.type) === 1 ? 1 : 2) as 1 | 2,
                    pollValue: isTradingRobot
                        ? (tradingPollMinuteOptions.includes(Number(resolvedPoll)) ? Number(resolvedPoll) : 5)
                        : Math.max(1, Math.min(12, Number(resolvedPoll || 1))),
                    pollUnit: isTradingRobot ? 'minutes' : 'hours',
                    brokerCommissionRate: Number(cfg?.costs?.broker_commission_rate ?? (brokerCommissionRate / 100) ?? 0.0005) * 100,
                    ndflRate: Number(cfg?.costs?.ndfl_rate ?? (ndflRate / 100) ?? 0.15) * 100,
                    hoursFrom: resolvedStart,
                    hoursTo: resolvedEnd,
                    weekdaysMask: resolvedWeekdays,
                    pipelineMode: pipeline.mode === 'ANY' ? 'ANY' : 'ALL',
                    filters: normalized.length > 0 ? normalized : DEFAULT_PIPELINE_FILTERS,
                })
                setMissingFieldsHint(missing)
            } catch {
                toast.show('Не удалось загрузить настройки выбранного робота', 'error')
            }
        }
        loadOne()
    }, [selectedRobot, isNewRobot])

    useEffect(() => {
        if (hydratingDraftRef.current) return
        if (!baselineDraft) return
        const current = JSON.stringify(buildDraftSnapshot())
        setIsEditing(current !== baselineDraft)
    }, [name, tokenId, robotType, pollValue, pollUnit, brokerCommissionRate, ndflRate, hoursFrom, hoursTo, weekdaysMask, pipelineMode, filters, baselineDraft])

    useEffect(() => {
        isEditingRef.current = isEditing
    }, [isEditing])

    const exitEditing = async () => {
        if (isNewRobot) {
            setIsEditing(false)
            return
        }
        if (!selectedRobot) return
        setIsEditing(false)
        const r = await robotService.getById(selectedRobot)
        const cfg = (r.config || {}) as any
        const pipeline = (cfg.pipeline || {}) as any
        const schedule = (r as any).schedule || null
        const loadedFilters: any[] = Array.isArray(pipeline.filters) ? pipeline.filters : []
        const missing: string[] = []
        const pollFromCfgHours = cfg.poll_interval_hours != null ? Number(cfg.poll_interval_hours) : null
        const pollFromCfgMinutes = pollFromCfgHours != null ? Math.max(1, Math.round(pollFromCfgHours * 60)) : null
        const pollFromScheduleMinutes = schedule?.interval_seconds != null
            ? Math.max(1, Math.round(Number(schedule.interval_seconds) / 60))
            : null
        const isTradingRobot = Number(r.type) === 2
        const resolvedPoll = isTradingRobot
            ? (pollFromScheduleMinutes ?? pollFromCfgMinutes ?? 5)
            : (pollFromCfgHours ?? (pollFromScheduleMinutes ? Math.max(1, Math.round(pollFromScheduleMinutes / 60)) : null) ?? 1)
        if (pollFromCfgHours == null && pollFromScheduleMinutes == null) missing.push('Частота опроса')
        const startCfg = toTime(String(cfg?.risk?.trading_hours_start || '').replace(' MSK', ''))
        const endCfg = toTime(String(cfg?.risk?.trading_hours_end || '').replace(' MSK', ''))
        const startSch = toTime(schedule?.start_time)
        const endSch = toTime(schedule?.end_time)
        const resolvedStart = startCfg ?? startSch ?? '10:00'
        const resolvedEnd = endCfg ?? endSch ?? '18:45'
        if (!startCfg && !startSch) missing.push('Часы работы (от)')
        if (!endCfg && !endSch) missing.push('Часы работы (до)')
        const weekdaysCfg = cfg?.risk?.allowed_weekdays != null ? Number(cfg.risk.allowed_weekdays) : null
        const weekdaysSch = schedule?.weekdays != null ? Number(schedule.weekdays) : null
        const resolvedWeekdays = weekdaysCfg ?? weekdaysSch ?? 31
        if (weekdaysCfg == null && weekdaysSch == null) missing.push('Дни недели')
        if (r.token?.id == null) missing.push('Токен')
        if (r.type == null) missing.push('Тип робота')
        const normalized = loadedFilters
            .filter(f => ['security_status', 'trading_status', 'allowed_tickers', 'volume', 'num_trades', 'gap', 'spread', 'atr', 'capitalization', 'min_step_ratio', 'excluded_tickers', 'exclude_tickers', 'turnover', 'gap_retention', 'price_vs_open', 'opening_range'].includes(String(f?.type)))
            .map(f => ({
                type: (f.type === 'exclude_tickers' ? 'excluded_tickers' : f.type) as PipelineFilterType,
                min: f.min != null ? Number(f.min) : undefined,
                max_percent: f.max_percent != null ? Number(f.max_percent) : undefined,
                min_percent: f.min_percent != null ? Number(f.min_percent) : undefined,
                period: f.period != null ? Number(f.period) : undefined,
                eq: f.eq != null ? String(f.eq) : undefined,
                direction: f.direction === 'UP_ONLY' || f.direction === 'DOWN_ONLY' ? f.direction : 'BOTH',
                max_steps: f.max_steps != null ? Number(f.max_steps) : undefined,
                min_ratio: f.min_ratio != null ? Number(f.min_ratio) : undefined,
                list: Array.isArray(f.list) ? f.list.map((x: any) => String(x).toUpperCase()) : f.list ?? null,
            }))
        applyDraft({
            name: r.name || '',
            tokenId: Number(r.token?.id || 0),
            robotType: (Number(r.type) === 1 ? 1 : 2) as 1 | 2,
            pollValue: isTradingRobot
                ? (tradingPollMinuteOptions.includes(Number(resolvedPoll)) ? Number(resolvedPoll) : 5)
                : Math.max(1, Math.min(12, Number(resolvedPoll || 1))),
            pollUnit: isTradingRobot ? 'minutes' : 'hours',
            brokerCommissionRate: Number(cfg?.costs?.broker_commission_rate ?? (brokerCommissionRate / 100) ?? 0.0005) * 100,
            ndflRate: Number(cfg?.costs?.ndfl_rate ?? (ndflRate / 100) ?? 0.15) * 100,
            hoursFrom: resolvedStart,
            hoursTo: resolvedEnd,
            weekdaysMask: resolvedWeekdays,
            pipelineMode: pipeline.mode === 'ANY' ? 'ANY' : 'ALL',
            filters: normalized.length > 0 ? normalized : DEFAULT_PIPELINE_FILTERS,
        })
        setMissingFieldsHint(missing)
    }

    const toTime = (raw: any): string | null => {
        if (!raw) return null
        const s = String(raw)
        const hhmm = s.match(/(\d{2}):(\d{2})/)
        return hhmm ? `${hhmm[1]}:${hhmm[2]}` : null
    }

    const save = async () => {
        if (!name.trim()) {
            toast.show('Укажите название робота', 'error')
            return
        }
        if (!tokenId) {
            toast.show('Выберите токен', 'error')
            return
        }
        setSaving(true)
        try {
            let robotId = selectedRobot
            if (isNewRobot) {
                const created = await robotService.create({ name: name.trim(), token_id: tokenId, type: robotType })
                robotId = created.id
                setSelectedRobot(robotId)
                setIsNewRobot(false)
                setSearchParams({ robotId: String(robotId) })
            }
            if (!robotId) {
                throw new Error('robot id missing')
            }
            const patch: Record<string, any> = {
                name: name.trim(),
                token_id: tokenId,
                type: robotType,
                poll_interval_hours: pollUnit === 'minutes'
                    ? Number((Number(pollValue || 5) / 60).toFixed(4))
                    : Number(Number(pollValue || 1).toFixed(4)),
                trading_hours_start: hoursFrom,
                trading_hours_end: hoursTo,
                allowed_weekdays: weekdaysMask,
            }
            if (robotType === 2) {
                const toApiFilters = filters.map(f => {
                    if (f.type === 'security_status') return { type: 'security_status', eq: String(f.eq || 'A') }
                    if (f.type === 'trading_status') return { type: 'trading_status', eq: String(f.eq || 'T') }
                    if (f.type === 'allowed_tickers') return { type: 'allowed_tickers', list: Array.isArray(f.list) ? f.list : [] }
                    if (f.type === 'volume') return { type: 'volume', min: Number(f.min || 0) }
                    if (f.type === 'num_trades') return { type: 'num_trades', min: Number(f.min || 0) }
                    if (f.type === 'gap') return { type: 'gap', max_percent: Number(f.max_percent || 0), direction: f.direction || 'BOTH' }
                    if (f.type === 'spread') return { type: 'spread', max_percent: Number(f.max_percent || 0) }
                    if (f.type === 'atr') return { type: 'atr', min_percent: Number(f.min_percent || 0), period: Number(f.period || 14) }
                    if (f.type === 'capitalization') return { type: 'capitalization', min: Number(f.min || 0) }
                    if (f.type === 'min_step_ratio') return { type: 'min_step_ratio', max_steps: Number(f.max_steps || 5) }
                    if (f.type === 'turnover') return { type: 'turnover', min_percent: Number(f.min_percent || 0) }
                    if (f.type === 'gap_retention') return { type: 'gap_retention', min_ratio: Number(f.min_ratio || 0) }
                    if (f.type === 'price_vs_open') return { type: 'price_vs_open', min_percent: Number(f.min_percent || 0.998) }
                    if (f.type === 'opening_range') return { type: 'opening_range', min_percent: Number(f.min_percent || 0) }
                    return { type: 'excluded_tickers', list: Array.isArray(f.list) ? f.list : [] }
                })
                patch.config = {
                    pipeline: {
                        filters: toApiFilters,
                        mode: pipelineMode,
                    },
                    costs: {
                        broker_commission_rate: Number((Number(brokerCommissionRate || 0) / 100).toFixed(6)),
                        ndfl_rate: Number((Number(ndflRate || 0) / 100).toFixed(6)),
                    },
                }
            }
            await robotService.updateRobot(robotId, patch)
            toast.show(isNewRobot ? 'Робот создан и настроен' : 'Настройки робота сохранены', 'success')
            setBaselineDraft(JSON.stringify(buildDraftSnapshot()))
            setIsEditing(false)
            await loadRobots(false)
        } catch {
            toast.show('Не удалось сохранить настройки робота', 'error')
        } finally {
            setSaving(false)
        }
    }

    const removeFilter = (id: string) => setFilters(prev => prev.filter(f => f.id !== id))
    const addFilter = (t: PipelineFilterType) => {
        if (filters.some(f => f.type === t)) return
        const base: PipelineFilter = { id: `${t}-${Date.now()}`, type: t }
        if (t === 'security_status') base.eq = 'A'
        if (t === 'trading_status') base.eq = 'T'
        if (t === 'allowed_tickers') base.list = []
        if (t === 'volume') base.min = 50_000_000
        if (t === 'num_trades') base.min = 100
        if (t === 'gap') {
            base.max_percent = 2.5
            base.direction = 'BOTH'
        }
        if (t === 'spread') base.max_percent = 0.15
        if (t === 'atr') {
            base.min_percent = 1.5
            base.period = 14
        }
        if (t === 'capitalization') base.min = 10_000_000_000
        if (t === 'min_step_ratio') base.max_steps = 5
        if (t === 'excluded_tickers') base.list = []
        if (t === 'turnover') base.min_percent = 0.3
        if (t === 'gap_retention') base.min_ratio = 0.7
        if (t === 'price_vs_open') base.min_percent = 0.998
        if (t === 'opening_range') base.min_percent = 1.5
        setFilters(prev => [...prev, base])
    }

    const previewPipeline = async () => {
        if (!selectedRobot || isNewRobot || robotType !== 2) return
        setPreviewLoading(true)
        try {
            const payloadFilters = filters.map(f => ({
                type: f.type,
                min: f.min,
                max_percent: f.max_percent,
                min_percent: f.min_percent,
                period: f.period,
                eq: f.eq,
                direction: f.direction,
                max_steps: f.max_steps,
                min_ratio: f.min_ratio,
                list: f.list,
            }))
            const res = await robotService.previewDmsPipeline({
                robot_id: selectedRobot,
                board: 'TQBR',
                filters: payloadFilters,
                mode: pipelineMode,
            })
            setPreview(res)
            toast.show('Preview готов', 'success')
        } catch {
            toast.show('Не удалось выполнить preview пайплайна', 'error')
        } finally {
            setPreviewLoading(false)
        }
    }

    const resetPipelineFilters = () => {
        setFilters(
            DEFAULT_PIPELINE_FILTERS.map((f, idx) => ({
                id: `${f.type}-${idx}-${Date.now()}`,
                ...f,
            })),
        )
    }

    const applyPreset = (preset: 'conservative' | 'moderate' | 'aggressive') => {
        const config = PRESETS[preset]
        setPipelineMode(config.mode)
        setFilters(
            config.filters.map((f, idx) => ({
                id: `${f.type}-${idx}-${Date.now()}`,
                ...f,
            })),
        )
    }

    const reorderFilters = (fromId: string, toId: string) => {
        if (fromId === toId) return
        setFilters(prev => {
            const fromIdx = prev.findIndex(f => f.id === fromId)
            const toIdx = prev.findIndex(f => f.id === toId)
            if (fromIdx < 0 || toIdx < 0) return prev
            const next = [...prev]
            const [moved] = next.splice(fromIdx, 1)
            next.splice(toIdx, 0, moved)
            setRecentlyMovedFilterId(moved.id)
            return next
        })
    }

    const insertFilterAt = (fromId: string, targetIndex: number) => {
        setFilters(prev => {
            const fromIdx = prev.findIndex(f => f.id === fromId)
            if (fromIdx < 0) return prev
            const next = [...prev]
            const [moved] = next.splice(fromIdx, 1)
            const normalizedIndex = Math.max(0, Math.min(targetIndex, next.length))
            next.splice(normalizedIndex, 0, moved)
            setRecentlyMovedFilterId(moved.id)
            return next
        })
    }

    useEffect(() => {
        if (!recentlyMovedFilterId) return
        const t = window.setTimeout(() => setRecentlyMovedFilterId(null), 260)
        return () => window.clearTimeout(t)
    }, [recentlyMovedFilterId])

    if (loading) {
        return (
            <div className="page">
                <h1 className="page__title">Настройка торгового робота</h1>
                <div className="ops-loader"><div className="soft-loading-bar" /></div>
            </div>
        )
    }

    const isEditMode = isEditing

    return (
        <div className="page">
            <h1 className="page__title">Роботы</h1>

            <div className="robots-unified-layout">
                <aside className="robots-unified-layout__sidebar">
            <Card className="mb-6 robots-list-card">
                <div className="card__header">
                    <h3>Список роботов</h3>
                    <Button variant="primary" size="sm" className="robot-create-btn" onClick={startCreateRobot}>+ Создать робота</Button>
                </div>
                {robots.length === 0 ? (
                    <div className="empty-state" style={{ minHeight: 140 }}>
                        <RobotIllustration size={96} />
                        <p style={{ marginTop: 8, color: 'var(--text-secondary)' }}>Роботов пока нет</p>
                    </div>
                ) : (
                    <div className="robots-list-cards">
                        {robots.map(r => (
                            <div
                                key={r.id}
                                role="button"
                                tabIndex={0}
                                className={`robots-list-item ${!isNewRobot && selectedRobot === r.id ? (isEditMode ? 'robots-list-item--selected-edit' : 'robots-list-item--selected') : ''}`}
                                onClick={() => openRobotForEdit(r.id)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                        e.preventDefault()
                                        openRobotForEdit(r.id)
                                    }
                                }}
                            >
                                <div className="robots-list-item__head">
                                    <strong>{r.name}</strong>
                                    {!isNewRobot && selectedRobot === r.id && isEditMode && (
                                        <span className="badge badge--warn">Редактируется</span>
                                    )}
                                </div>
                                <div className="robots-list-item__meta">{r.typeName} · {r.statusName}</div>
                                <div className="robots-list-item__actions">
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        className="robot-status-toggle-btn"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            toggleRobotStatus(r)
                                        }}
                                    >
                                        {r.status === 1 ? 'Стоп' : 'Старт'}
                                    </Button>
                                    <Button
                                        size="sm"
                                        variant="danger"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            deleteRobot(r)
                                        }}
                                    >
                                        Удалить
                                    </Button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Card>
                </aside>

                <section className="robots-unified-layout__editor">

            <Card className="mb-6 cyber-form-card">
                <h3 className="card__section-title pipeline-title">
                    <span className="cyber-bracket">[</span>
                    ОСНОВНЫЕ НАСТРОЙКИ
                    <span className="cyber-bracket">]</span>
                </h3>
                <div className="form-group">
                    <label className="form-label">Название робота</label>
                    <input className="form-input cyber-input" value={name} onChange={e => setName(e.target.value)} />
                </div>
                <div className="form-row">
                    <div className="form-group">
                        <label className="form-label">Токен</label>
                        <div className="cyber-select-wrap">
                        <Select
                            options={[{ value: '0', label: 'Выберите токен' }, ...tokenOptions]}
                            value={String(tokenId || 0)}
                            onChange={v => setTokenId(Number(v || 0))}
                        />
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Тип робота</label>
                        <div className="cyber-select-wrap">
                        <Select
                            options={robotTypeOptions}
                            value={String(robotType)}
                            onChange={v => setRobotType((Number(v) === 1 ? 1 : 2) as 1 | 2)}
                        />
                        </div>
                    </div>
                </div>
                {robotType === 2 && (
                    <div className="form-row">
                        <div className="form-group">
                            <label className="form-label">Комиссия брокера (%)</label>
                            <input
                                className="form-input cyber-input"
                                type="number"
                                step="0.01"
                                min={0}
                                max={100}
                                value={brokerCommissionRate}
                                onChange={e => setBrokerCommissionRate(Math.max(0, Math.min(100, Number(e.target.value || 0))))}
                            />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Налог НДФЛ (%)</label>
                            <input
                                className="form-input cyber-input"
                                type="number"
                                step="0.01"
                                min={0}
                                max={100}
                                value={ndflRate}
                                onChange={e => setNdflRate(Math.max(0, Math.min(100, Number(e.target.value || 0))))}
                            />
                        </div>
                    </div>
                )}
            </Card>

            <Card className="mb-6 cyber-form-card">
                <h3 className="card__section-title pipeline-title">
                    <span className="cyber-bracket">[</span>
                    РАСПИСАНИЕ
                    <span className="cyber-bracket">]</span>
                </h3>
                <div className="form-row">
                    <div className="form-group">
                        <label className="form-label">Частота опроса</label>
                        <div className="form-row">
                            <div className="form-group">
                                {pollUnit === 'minutes' ? (
                                    <div className="cyber-select-wrap">
                                        <Select
                                            options={tradingPollMinuteOptions.map(v => ({ value: String(v), label: `${v}` }))}
                                            value={String(pollValue)}
                                            onChange={v => setPollValue(Number(v || 5))}
                                        />
                                    </div>
                                ) : (
                                    <input
                                        className="form-input cyber-input"
                                        type="number"
                                        min={1 / 60}
                                        max={12}
                                        step={0.1}
                                        value={pollValue}
                                        onChange={e => setPollValue(Math.max(1 / 60, Math.min(12, Number(e.target.value || 1))))}
                                    />
                                )}
                            </div>
                            <div className="form-group">
                                <div className="cyber-select-wrap">
                                    <Select
                                        options={[
                                            { value: 'minutes', label: 'минуты' },
                                            { value: 'hours', label: 'часы' },
                                        ]}
                                        value={pollUnit}
                                        onChange={v => setPollUnit(v === 'hours' ? 'hours' : 'minutes')}
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Дни недели (mask)</label>
                        <input className="form-input cyber-input" type="number" min={0} max={127} value={weekdaysMask} onChange={e => setWeekdaysMask(Math.max(0, Math.min(127, Number(e.target.value || 0))))} />
                    </div>
                </div>
                <div className="form-row">
                    <div className="form-group">
                        <label className="form-label">Часы работы (от)</label>
                        <input className="form-input cyber-input" type="time" value={hoursFrom} onChange={e => setHoursFrom(e.target.value)} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Часы работы (до)</label>
                        <input className="form-input cyber-input" type="time" value={hoursTo} onChange={e => setHoursTo(e.target.value)} />
                    </div>
                </div>
            </Card>

            {robotType === 2 && (
            <Card className="mb-6 pipeline-card">
                <div className="pipeline-header">
                    <h3 className="card__section-title pipeline-title">
                        <span className="cyber-bracket">[</span>
                        УПРАВЛЕНИЕ ПАЙПЛАЙНОМ
                        <span className="cyber-bracket">]</span>
                    </h3>
                    <div className="pipeline-mode">
                        <Select
                            options={[{ value: 'ALL', label: '[ALL] - ВСЕ ФИЛЬТРЫ' }, { value: 'ANY', label: '[ANY] - ЛЮБОЙ ФИЛЬТР' }]}
                            value={pipelineMode}
                            onChange={v => setPipelineMode((v as 'ALL' | 'ANY') || 'ALL')}
                        />
                    </div>
                </div>
                <div className="preset-buttons">
                    <Button size="sm" variant="ghost" onClick={() => applyPreset('conservative')}>Консервативная</Button>
                    <Button size="sm" variant="ghost" onClick={() => applyPreset('moderate')}>Умеренная</Button>
                    <Button size="sm" variant="ghost" onClick={() => applyPreset('aggressive')}>Агрессивная</Button>
                </div>
                {filters.map((f, idx) => (
                    <React.Fragment key={f.id}>
                        <div
                            onDragOver={(e) => {
                                e.preventDefault()
                                setDropIndex(idx)
                            }}
                            onDrop={(e) => {
                                e.preventDefault()
                                if (dragFilterId) insertFilterAt(dragFilterId, idx)
                                setDropIndex(null)
                            }}
                            className={`pipeline-dropzone ${dropIndex === idx ? 'pipeline-dropzone--active' : ''}`}
                        />
                        <div
                            onDragOver={(e) => {
                                e.preventDefault()
                                e.dataTransfer.dropEffect = 'move'
                            }}
                            onDrop={(e) => {
                                e.preventDefault()
                                if (dragFilterId) reorderFilters(dragFilterId, f.id)
                                setDropIndex(null)
                            }}
                            className={`form-group pipeline-filter-card ${dragFilterId === f.id ? 'pipeline-filter-card--dragging' : ''} ${recentlyMovedFilterId === f.id ? 'pipeline-filter-card--moved' : ''}`}
                        >
                        {(() => {
                            const isLockedStatus = f.type === 'security_status' || f.type === 'trading_status'
                            return (
                        <div className="pipeline-filter-row">
                            <span
                                className={`pipeline-drag-handle ${isLockedStatus ? 'pipeline-drag-handle--locked' : ''}`}
                                draggable={!isLockedStatus}
                                onDragStart={() => {
                                    if (isLockedStatus) return
                                    setDragFilterId(f.id)
                                }}
                                onDragEnd={() => {
                                    setDragFilterId(null)
                                    setDropIndex(null)
                                }}
                            >
                                ⋮
                            </span>
                            <strong className="pipeline-filter-label">{FILTER_META[f.type].label}:</strong>
                            <span className="pipeline-filter-info" data-tooltip={FILTER_TOOLTIP[f.type].map(line => `>_ ${line}`).join('\n')}>[ i ]</span>
                            <div className="pipeline-filter-inputs">
                                {f.type === 'volume' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input className="form-input" type="number" value={Number(f.min || 0)} onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, min: Number(e.target.value || 0) } : x))} />
                                        <span className="cyber-unit">RUB</span>
                                    </div>
                                )}
                                {f.type === 'num_trades' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input className="form-input" type="number" value={Number(f.min || 0)} onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, min: Number(e.target.value || 0) } : x))} />
                                    </div>
                                )}
                                {f.type === 'gap' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input className="form-input" type="number" step="0.1" value={Number(f.max_percent || 0)} onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, max_percent: Number(e.target.value || 0) } : x))} />
                                        <span className="cyber-unit">%</span>
                                        <Select
                                            options={[{ value: 'BOTH', label: 'BOTH' }, { value: 'UP_ONLY', label: 'UP_ONLY' }, { value: 'DOWN_ONLY', label: 'DOWN_ONLY' }]}
                                            value={f.direction || 'BOTH'}
                                            onChange={v => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, direction: (v as 'BOTH' | 'UP_ONLY' | 'DOWN_ONLY') || 'BOTH' } : x))}
                                        />
                                    </div>
                                )}
                                {f.type === 'min_step_ratio' && (
                                    <input className="form-input" type="number" step="0.5" value={Number(f.max_steps || 5)} onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, max_steps: Number(e.target.value || 5) } : x))} />
                                )}
                                {f.type === 'spread' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input className="form-input" type="number" step="0.01" value={Number(f.max_percent || 0)} onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, max_percent: Number(e.target.value || 0) } : x))} />
                                        <span className="cyber-unit">%</span>
                                    </div>
                                )}
                                {f.type === 'atr' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input className="form-input" type="number" step="0.1" value={Number(f.min_percent || 0)} onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, min_percent: Number(e.target.value || 0) } : x))} />
                                        <span className="cyber-unit">%</span>
                                        <input className="form-input" type="number" min={5} max={60} value={Number(f.period || 14)} onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, period: Number(e.target.value || 14) } : x))} />
                                        <span className="cyber-unit">DAYS</span>
                                    </div>
                                )}
                                {f.type === 'capitalization' && (
                                    <input className="form-input" type="number" value={Number(f.min || 0)} onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, min: Number(e.target.value || 0) } : x))} />
                                )}
                                {f.type === 'turnover' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input
                                            className="form-input"
                                            type="number"
                                            step="0.01"
                                            value={Number(f.min_percent || 0)}
                                            onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, min_percent: Number(e.target.value || 0) } : x))}
                                        />
                                        <span className="cyber-unit">% от выпуска</span>
                                    </div>
                                )}
                                {f.type === 'gap_retention' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input
                                            className="form-input"
                                            type="number"
                                            step="0.1"
                                            min={0}
                                            max={5}
                                            value={Number(f.min_ratio || 0)}
                                            onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, min_ratio: Number(e.target.value || 0) } : x))}
                                        />
                                        <span className="cyber-unit">ratio</span>
                                    </div>
                                )}
                                {f.type === 'price_vs_open' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input
                                            className="form-input"
                                            type="number"
                                            step="0.001"
                                            min={0.9}
                                            max={1.1}
                                            value={Number(f.min_percent || 0.998)}
                                            onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, min_percent: Number(e.target.value || 0.998) } : x))}
                                        />
                                        <span className="cyber-unit">доля от OPEN</span>
                                    </div>
                                )}
                                {f.type === 'opening_range' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input
                                            className="form-input"
                                            type="number"
                                            step="0.1"
                                            min={0}
                                            max={100}
                                            value={Number(f.min_percent || 0)}
                                            onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, min_percent: Number(e.target.value || 0) } : x))}
                                        />
                                        <span className="cyber-unit">%</span>
                                    </div>
                                )}
                                {(f.type === 'security_status' || f.type === 'trading_status') && (
                                    <div className="form-row pipeline-inline-row">
                                        <input className="form-input" value={String(f.eq || '')} readOnly />
                                        <span className="form-hint">
                                            {f.type === 'security_status' ? 'Бумага должна быть активна' : 'Бумага должна торговаться'}
                                        </span>
                                    </div>
                                )}
                                {(f.type === 'excluded_tickers' || f.type === 'allowed_tickers') && (
                                    <input
                                        className="form-input"
                                        placeholder="SBER, LKOH"
                                        value={Array.isArray(f.list) ? f.list.join(', ') : ''}
                                        onChange={e => setFilters(prev => prev.map(x => x.id === f.id ? { ...x, list: parseTickers(e.target.value) } : x))}
                                    />
                                )}
                            </div>
                            {!isLockedStatus && <Button size="sm" variant="ghost" className="pipeline-delete-btn" onClick={() => removeFilter(f.id)}>×</Button>}
                        </div>
                            )
                        })()}
                        </div>
                    </React.Fragment>
                ))}
                <div
                    onDragOver={(e) => {
                        e.preventDefault()
                        setDropIndex(filters.length)
                    }}
                    onDrop={(e) => {
                        e.preventDefault()
                        if (dragFilterId) insertFilterAt(dragFilterId, filters.length)
                        setDropIndex(null)
                    }}
                    className={`pipeline-dropzone pipeline-dropzone--tail ${dropIndex === filters.length ? 'pipeline-dropzone--active' : ''}`}
                />
                <div className="pipeline-chip-list">
                    {(Object.keys(FILTER_META) as PipelineFilterType[])
                        .filter(t => !filters.some(f => f.type === t))
                        .map(t => (
                            <Button key={t} size="sm" variant="ghost" onClick={() => addFilter(t)}>
                                + {FILTER_META[t].label}
                            </Button>
                        ))}
                </div>
                <div className="form-actions">
                    <Button className="pipeline-action-btn pipeline-action-btn--reset" variant="ghost" onClick={resetPipelineFilters}>СБРОС</Button>
                    <Button className="pipeline-action-btn pipeline-action-btn--test" variant="secondary" loading={previewLoading} onClick={previewPipeline} disabled={!selectedRobot || isNewRobot}>ТЕСТИРОВАТЬ</Button>
                </div>
                {preview && (
                    <div style={{ marginTop: 12 }}>
                        <div className="form-hint" style={{ marginBottom: 8 }}>
                            Проверено: {preview.total_checked} · Прошли: {preview.passed} · Отклонено: {preview.rejected}
                        </div>
                        <DataTable
                            columns={[
                                { key: 'ticker', header: 'Тикер', sortable: true } as Column<any>,
                                { key: 'result', header: 'Результат', sortable: true } as Column<any>,
                                { key: 'reason', header: 'Причина', sortable: true, render: (r: any) => r.reason || '—' } as Column<any>,
                                { key: 'value_today', header: 'Объем (руб)', align: 'right', render: (r: any) => Number(r.value_today || 0).toLocaleString('ru-RU') } as Column<any>,
                                { key: 'gap_percent', header: 'Гэп %', align: 'right', render: (r: any) => r.gap_percent != null ? Number(r.gap_percent).toFixed(2) : '—' } as Column<any>,
                                { key: 'spread_percent', header: 'Спред %', align: 'right', render: (r: any) => r.spread_percent != null ? Number(r.spread_percent).toFixed(3) : '—' } as Column<any>,
                                { key: 'atr_percent', header: 'ATR %', align: 'right', render: (r: any) => r.atr_percent != null ? Number(r.atr_percent).toFixed(2) : '—' } as Column<any>,
                            ]}
                            data={preview.sample || []}
                            keyField="ticker"
                            emptyText="Нет данных preview"
                            maxHeight={260}
                        />
                    </div>
                )}
            </Card>
            )}

            {isEditMode && (
                <div className="form-actions">
                    <Button variant="ghost" onClick={exitEditing}>Выйти из редактирования</Button>
                    <Button variant="primary" glow loading={saving} onClick={save}>Сохранить</Button>
                </div>
            )}
                </section>
            </div>
        </div>
    )
}
