import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { PageHero } from '@/components/ui/PageHero'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import {
    BacktestCompareStrip,
    BacktestHistoryCard,
    type BacktestCompareState,
    type BacktestHistoryRow,
} from '@/pages/robots-v2/components/BacktestHistoryCard'
import { BacktestResultsPanel } from '@/pages/robots-v2/components/BacktestResultsPanel'
import { BacktestStartGuide } from '@/pages/robots-v2/components/BacktestStartGuide'
import { BacktestVerdictCard } from '@/pages/robots-v2/components/BacktestVerdictCard'
import { LabConfigForm } from '@/pages/robots-v2/components/LabConfigForm'
import { SaveAsRobotModal } from '@/pages/robots-v2/components/SaveAsRobotModal'
import { RobotStageCard } from '@/pages/robots-v2/components/RobotStageCard'
import {
    collectReasonCodes,
    matchingPreset,
    presetById,
    presetDraftPatch,
    type BacktestPresetId,
} from '@/pages/robots-v2/backtestGuide'
import { fmtErr, sessionStateLabel } from '@/pages/robots-v2/formatters'
import { formatBacktestPhaseUnits } from '@/pages/robots-v2/formatBacktestPhaseUnits'
import {
    configToDraft,
    defaultWizardDraft,
    draftToV4Config,
    parseFixedList,
    type RobotV2WizardDraft,
} from '@/pages/robots-v2/wizardDraft'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2 } from '@/types/robotV2'
import type {
    BacktestFeeSummary,
    BacktestNarrativeStep,
    BacktestObservability,
    BacktestPortfolioSnapshot,
    RobotBacktestRunDetails,
    RobotHistoryBacktestResult,
} from '@/types/robot'
import type { IChartApi, ISeriesApi, Time } from '@/components/ui/Chart'

const LAST_CONFIG_KEY = 'gin.backtestLab.lastConfig'

type ConfigSource = 'visual' | 'robot' | 'history'

function stripLabMeta(config: Record<string, unknown>): Record<string, unknown> {
    const cleaned = { ...config }
    delete cleaned.engine_version
    delete cleaned.v2RobotId
    return cleaned
}

function validateVisualDraft(draft: RobotV2WizardDraft): string | null {
    if (!draft.archetype) return 'Выберите архетип стратегии'
    if (draft.archetype === 'scalper') {
        return 'Scalper нельзя прогнать на свечах — нужны тики и order-flow'
    }
    if (draft.universeMode === 'fixed' && parseFixedList(draft.fixedList).length === 0) {
        return 'Укажите хотя бы один тикер'
    }
    if (draft.universeMode === 'index' && !draft.indexCode.trim()) {
        return 'Укажите код индекса'
    }
    if (!(draft.capital > 0)) return 'Капитал в конфиге должен быть больше 0'
    if (draft.stopLossPct >= draft.takeProfitPct) {
        return 'Stop-loss должен быть меньше take-profit'
    }
    return null
}

type StoredLabConfig = {
    config: Record<string, unknown>
    robotId?: number | null
    capital?: number
    savedAt?: string
}

function isoDateUtc(d: Date): string {
    return d.toISOString().slice(0, 10)
}

function daysAgoUtc(n: number): string {
    const d = new Date()
    d.setUTCDate(d.getUTCDate() - n)
    return isoDateUtc(d)
}

function todayUtc(): string {
    return isoDateUtc(new Date())
}

function riskCapitalFromConfig(config: Record<string, unknown> | null | undefined): number {
    const risk = (config?.risk || {}) as Record<string, unknown>
    const n = Number(risk.capital)
    return Number.isFinite(n) && n > 0 ? n : 100_000
}

function tokenIdOf(robot: RobotV2 | null): number | null {
    if (!robot) return null
    const n = Number(robot.tokenId ?? robot.token_id)
    return Number.isFinite(n) && n > 0 ? n : null
}

function archetypeOfConfig(config: Record<string, unknown> | null | undefined): string {
    const strategy = (config?.strategy || {}) as Record<string, unknown>
    return String(strategy.archetype || '')
}

function statusVariant(status: string): 'up' | 'down' | 'neutral' | 'warn' {
    const s = status.toUpperCase()
    if (s === 'SUCCESS') return 'up'
    if (s === 'FAILED') return 'down'
    if (s === 'CANCELLED') return 'warn'
    if (s === 'RUNNING' || s === 'QUEUED') return 'neutral'
    return 'neutral'
}

function toChartPoints(curve: Array<{ time: string; equity: number }>): Array<{ time: Time; value: number }> {
    const byTime = new Map<number, number>()
    for (const p of curve) {
        const t = Math.floor(new Date(p.time).getTime() / 1000)
        if (!Number.isFinite(t) || !Number.isFinite(p.equity)) continue
        byTime.set(t, p.equity)
    }
    return [...byTime.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([time, value]) => ({ time: time as Time, value }))
}

function readStoredConfig(): StoredLabConfig | null {
    try {
        const raw = sessionStorage.getItem(LAST_CONFIG_KEY)
        if (!raw) return null
        const parsed = JSON.parse(raw) as StoredLabConfig
        if (!parsed?.config || typeof parsed.config !== 'object') return null
        return parsed
    } catch {
        return null
    }
}

function writeStoredConfig(payload: StoredLabConfig) {
    try {
        sessionStorage.setItem(LAST_CONFIG_KEY, JSON.stringify({
            ...payload,
            savedAt: new Date().toISOString(),
        }))
    } catch {
        /* ignore quota */
    }
}

function normalizeHistoryItem(item: Record<string, unknown>): BacktestHistoryRow {
    const robotIdRaw = item.robot_id
    const robotId =
        robotIdRaw == null || robotIdRaw === ''
            ? null
            : Number(robotIdRaw)
    const bound =
        typeof item.bound === 'boolean'
            ? item.bound
            : robotId != null && Number.isFinite(robotId) && robotId > 0
    return {
        run_id: Number(item.run_id),
        status: String(item.status || ''),
        requested_from: String(item.requested_from || ''),
        requested_to: String(item.requested_to || ''),
        started_at: String(item.started_at || ''),
        initial_capital: Number(item.initial_capital) || 0,
        total_return_percent: item.total_return_percent == null ? null : Number(item.total_return_percent),
        max_drawdown_percent: item.max_drawdown_percent == null ? null : Number(item.max_drawdown_percent),
        sharpe_ratio: item.sharpe_ratio == null ? null : Number(item.sharpe_ratio),
        final_equity: item.final_equity == null ? null : Number(item.final_equity),
        trades_total: Number(item.trades_total) || 0,
        robot_id: robotId != null && Number.isFinite(robotId) && robotId > 0 ? robotId : null,
        bound,
        config_label: item.config_label == null ? null : String(item.config_label),
    }
}

function httpStatusOf(e: unknown): number | null {
    const err = e as { response?: { status?: number } }
    const n = Number(err?.response?.status)
    return Number.isFinite(n) ? n : null
}

const PRESETS: Array<{ id: string; label: string; days: number }> = [
    { id: '7d', label: '7 дней', days: 7 },
    { id: '30d', label: '30 дней', days: 30 },
    { id: '90d', label: '90 дней', days: 90 },
    { id: '180d', label: '180 дней', days: 180 },
]

export default function BacktestLabPage() {
    const navigate = useNavigate()
    const isNarrow = useMediaQuery('(max-width: 767px)')
    const [searchParams, setSearchParams] = useSearchParams()
    const toast = useToast()

    const [source, setSource] = useState<ConfigSource>('visual')
    const [robots, setRobots] = useState<RobotV2[]>([])
    const [robotsLoading, setRobotsLoading] = useState(true)
    const [selectedRobotId, setSelectedRobotId] = useState<string>('')
    const [historyRunId, setHistoryRunId] = useState<string>('')
    const [historyHydrating, setHistoryHydrating] = useState(false)
    const [draft, setDraft] = useState<RobotV2WizardDraft>(() => defaultWizardDraft())
    const [config, setConfig] = useState<Record<string, unknown> | null>(() => draftToV4Config(defaultWizardDraft()))
    const [sourceHint, setSourceHint] = useState<string | null>(null)

    const [fromDate, setFromDate] = useState(() => daysAgoUtc(30))
    const [toDate, setToDate] = useState(() => todayUtc())
    const [capital, setCapital] = useState(100_000)
    const [launchError, setLaunchError] = useState<string | null>(null)

    const [running, setRunning] = useState(false)
    const [cancelling, setCancelling] = useState(false)
    const [runId, setRunId] = useState<number | null>(null)
    const [status, setStatus] = useState<RobotBacktestRunDetails | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [openingRun, setOpeningRun] = useState(false)

    const [history, setHistory] = useState<BacktestHistoryRow[]>([])
    const [historyLoading, setHistoryLoading] = useState(false)
    const [historyError, setHistoryError] = useState<string | null>(null)
    const [selectedIds, setSelectedIds] = useState<number[]>([])
    const [compare, setCompare] = useState<BacktestCompareState | null>(null)
    const [saveAsOpen, setSaveAsOpen] = useState(false)

    const chartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
    const resultAnchorRef = useRef<HTMLDivElement | null>(null)
    const launchFocusRef = useRef<HTMLDivElement | null>(null)
    const openedFromQueryRef = useRef<number | null>(null)
    const pollFailStreakRef = useRef(0)

    const selectedRobot = useMemo(
        () => robots.find(r => String(r.id) === selectedRobotId) || null,
        [robots, selectedRobotId],
    )

    const tradingRobots = useMemo(
        () => robots.filter(r => Number(r.type) === 2),
        [robots],
    )

    const loadRobots = useCallback(async () => {
        setRobotsLoading(true)
        try {
            const data = await robotV2Service.list()
            setRobots(data.items || [])
        } catch (e) {
            toast.show(fmtErr(e), 'error')
            setRobots([])
        } finally {
            setRobotsLoading(false)
        }
    }, [toast])

    const loadHistory = useCallback(async () => {
        setHistoryLoading(true)
        try {
            const data = await robotV2Service.listBacktestRuns({ limit: 100 })
            const items = (data.items || []).map(item => normalizeHistoryItem(item as Record<string, unknown>))
            setHistory(items)
            setHistoryError(null)
        } catch (e) {
            const msg = fmtErr(e)
            setHistoryError(msg)
            toast.show(`Не удалось загрузить историю: ${msg}`, 'error')
        } finally {
            setHistoryLoading(false)
        }
    }, [toast])

    useEffect(() => {
        void loadRobots()
        void loadHistory()
    }, [loadRobots, loadHistory])

    const applyConfigSnapshot = useCallback((
        snap: Record<string, unknown>,
        opts?: { capital?: number; robotId?: number | null },
    ) => {
        const cleaned = stripLabMeta(snap)
        setConfig(cleaned)
        setDraft(configToDraft(cleaned, 'Lab', null))
        if (opts?.capital != null && opts.capital > 0) setCapital(opts.capital)
        else setCapital(riskCapitalFromConfig(cleaned))
        if (opts?.robotId != null && opts.robotId > 0) {
            setSelectedRobotId(String(opts.robotId))
        } else if (opts && 'robotId' in opts) {
            setSelectedRobotId('')
        }
        setSourceHint(null)
    }, [])

    const hydrateFromRobot = useCallback((robot: RobotV2 | null) => {
        if (!robot) {
            setConfig(null)
            setSourceHint('Выберите робота')
            return
        }
        applyConfigSnapshot(robot.config as Record<string, unknown>, {
            capital: riskCapitalFromConfig(robot.config),
            robotId: robot.id,
        })
    }, [applyConfigSnapshot])

    const hydrateFromHistoryRun = useCallback(async (runId: number) => {
        setHistoryHydrating(true)
        setSourceHint(null)
        try {
            const details = await robotV2Service.getBacktestRunDetails(runId)
            const raw = details as RobotBacktestRunDetails & {
                config_snapshot?: Record<string, unknown> | null
            }
            const snap = (
                raw.config_snapshot
                || (details.result_payload as { config?: Record<string, unknown> } | undefined)?.config
                || null
            ) as Record<string, unknown> | null
            if (!snap || typeof snap !== 'object') {
                setConfig(null)
                setSourceHint('У этого прогона нет сохранённого конфига')
                return false
            }
            const rid = details.robot_id ?? null
            applyConfigSnapshot(snap, {
                capital: Number(details.initial_capital) || riskCapitalFromConfig(snap),
                robotId: rid != null && Number(rid) > 0 ? Number(rid) : null,
            })
            return true
        } catch {
            setConfig(null)
            setSourceHint('Не удалось загрузить конфиг прогона')
            return false
        } finally {
            setHistoryHydrating(false)
        }
    }, [applyConfigSnapshot])

    const patchDraft = useCallback((patch: Partial<RobotV2WizardDraft>) => {
        setDraft(prev => {
            const next = { ...prev, ...patch }
            const nextConfig = draftToV4Config(next)
            setConfig(nextConfig)
            if (patch.capital != null && Number(patch.capital) > 0) {
                setCapital(Number(patch.capital))
            }
            return next
        })
        setSourceHint(null)
    }, [])

    const applyPreset = useCallback((id: BacktestPresetId) => {
        const preset = presetById(id)
        setSource('visual')
        patchDraft(presetDraftPatch(id))
        setFromDate(daysAgoUtc(preset.days - 1))
        setToDate(todayUtc())
        setLaunchError(null)
    }, [patchDraft])

    useEffect(() => {
        if (source === 'robot') {
            hydrateFromRobot(selectedRobot)
        }
    }, [source, selectedRobot, hydrateFromRobot])

    useEffect(() => {
        if (source !== 'history' || historyRunId) return
        const preferred =
            history.find(h => String(h.status).toUpperCase() === 'SUCCESS')
            || history.find(h => {
                const s = String(h.status).toUpperCase()
                return s === 'CANCELLED' || s === 'FAILED'
            })
        if (preferred) {
            setHistoryRunId(String(preferred.run_id))
            return
        }
        setConfig(null)
        setSourceHint('Выберите прошлый прогон')
    }, [source, historyRunId, history])

    useEffect(() => {
        if (source !== 'history') return
        const rid = Number(historyRunId)
        if (!Number.isFinite(rid) || rid <= 0) return
        void hydrateFromHistoryRun(rid)
    }, [source, historyRunId, hydrateFromHistoryRun])

    useEffect(() => {
        if (source !== 'visual') return
        setConfig(draftToV4Config(draft))
        setSourceHint(null)
        // Only when switching into visual — draft edits go through patchDraft
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [source])

    const payload = (status?.result_payload || {}) as Partial<RobotHistoryBacktestResult>
    const equityCurve = payload.equity_curve || []
    const trades = payload.trades || []
    const runSignals = status?.signals ?? []
    const runOrders = status?.orders ?? []
    const dailySummary =
        status?.daily_summary
        ?? (payload as { daily_summary?: Array<Record<string, unknown>> }).daily_summary
        ?? []
    const feeSummary = (
        status?.fee_summary
        ?? payload.fee_summary
        ?? null
    ) as BacktestFeeSummary | null
    const portfolioSnapshots = (status?.portfolio_snapshots || []) as BacktestPortfolioSnapshot[]
    const narrative = (
        status?.narrative
        ?? (payload as { narrative?: BacktestNarrativeStep[] }).narrative
        ?? null
    ) as BacktestNarrativeStep[] | null
    const chartPoints = useMemo(() => toChartPoints(equityCurve), [equityCurve])

    useEffect(() => {
        const series = seriesRef.current
        if (!series) return
        series.setData(chartPoints)
    }, [chartPoints])

    const runStatus = String(status?.status || '').toUpperCase()
    const isActive = running || runStatus === 'RUNNING' || runStatus === 'QUEUED'
    const activeHistoryRow = useMemo(
        () => (runId != null ? history.find(h => h.run_id === runId) ?? null : null),
        [history, runId],
    )
    const runAlreadyBound = useMemo(() => {
        const rid = Number(status?.robot_id ?? activeHistoryRow?.robot_id ?? 0)
        if (Number.isFinite(rid) && rid > 0) return true
        return Boolean(activeHistoryRow?.bound)
    }, [status?.robot_id, activeHistoryRow])
    const saveAsDefaultName = useMemo(() => {
        if (runId == null) return 'Новый робот'
        const hint =
            activeHistoryRow?.config_label
            || archetypeOfConfig(config)
            || 'стратегия'
        return `Бэктест · ${hint} #${runId}`.slice(0, 50)
    }, [runId, activeHistoryRow, config])
    const saveAsSuggestedTokenId = useMemo(() => {
        const fromRobot = tokenIdOf(selectedRobot)
        if (fromRobot) return fromRobot
        const boundId = Number(status?.robot_id ?? activeHistoryRow?.robot_id ?? 0)
        if (Number.isFinite(boundId) && boundId > 0) {
            return tokenIdOf(robots.find(r => r.id === boundId) ?? null)
        }
        return null
    }, [selectedRobot, status?.robot_id, activeHistoryRow, robots])
    const archetype = archetypeOfConfig(config)
    const scalperBlocked = archetype === 'scalper'
    const spanDays = useMemo(() => {
        const a = Date.parse(`${fromDate}T00:00:00Z`)
        const b = Date.parse(`${toDate}T00:00:00Z`)
        if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return 0
        return Math.round((b - a) / 86_400_000) + 1
    }, [fromDate, toDate])

    const syncRunQuery = useCallback(
        (id: number | null) => {
            const next = new URLSearchParams(searchParams)
            next.delete('runId')
            if (id != null && Number.isFinite(id) && id > 0) {
                next.set('run', String(id))
            } else {
                next.delete('run')
            }
            setSearchParams(next, { replace: true })
        },
        [searchParams, setSearchParams],
    )

    const poll = useCallback(async (idToPoll: number) => {
        const st = await robotV2Service.getBacktestRunStatus(idToPoll)
        setStatus(prev => {
            const merged = { ...(prev || {}), ...st } as RobotBacktestRunDetails
            if (!merged.result_payload) merged.result_payload = prev?.result_payload || ({} as RobotHistoryBacktestResult)
            return merged
        })
        const phase = String(st.status || '').toUpperCase()
        if (phase === 'SUCCESS' || phase === 'FAILED' || phase === 'CANCELLED') {
            const details = await robotV2Service.getBacktestRunDetails(idToPoll)
            setStatus(details)
            setRunning(false)
            pollFailStreakRef.current = 0
            if (phase === 'FAILED') {
                setError(details.error_message || 'Прогон завершился с ошибкой')
                toast.show(details.error_message || 'Прогон завершился с ошибкой', 'error')
            } else if (phase === 'CANCELLED') {
                setError(null)
                toast.show('Прогон отменён', 'info')
            } else {
                setError(null)
            }
            void loadHistory()
        }
        return st
    }, [loadHistory, toast])

    useEffect(() => {
        if (!runId || !isActive) return
        let stopped = false
        const loop = async () => {
            while (!stopped) {
                try {
                    const st = await poll(runId)
                    pollFailStreakRef.current = 0
                    const phase = String(st.status || '').toUpperCase()
                    if (phase === 'SUCCESS' || phase === 'FAILED' || phase === 'CANCELLED') return
                } catch (e) {
                    pollFailStreakRef.current += 1
                    if (pollFailStreakRef.current === 5) {
                        toast.show(
                            `Не удаётся получить статус прогона: ${fmtErr(e)}. Повторяем опрос…`,
                            'error',
                        )
                    }
                }
                await new Promise(r => window.setTimeout(r, 1500))
            }
        }
        void loop()
        return () => {
            stopped = true
        }
    }, [runId, isActive, poll, toast])

    const resolveLaunchConfig = (): {
        config: Record<string, unknown>
        robotId: number | null
        tokenId: number | null
    } | null => {
        if (source === 'visual') {
            const err = validateVisualDraft(draft)
            if (err) {
                setLaunchError(err)
                return null
            }
            const next = draftToV4Config(draft)
            return { config: next, robotId: null, tokenId: null }
        }
        if (source === 'robot') {
            if (selectedRobot) {
                return {
                    config: selectedRobot.config as Record<string, unknown>,
                    robotId: selectedRobot.id,
                    tokenId: tokenIdOf(selectedRobot),
                }
            }
            setLaunchError('Выберите робота')
            return null
        }
        // history
        if (!config) {
            setLaunchError(sourceHint || 'Выберите прошлый прогон')
            return null
        }
        const rid = selectedRobotId ? Number(selectedRobotId) : null
        const robot = rid && rid > 0 ? robots.find(r => r.id === rid) || null : null
        return {
            config,
            robotId: robot?.id ?? (rid && rid > 0 ? rid : null),
            tokenId: tokenIdOf(robot),
        }
    }

    const onRun = async () => {
        const resolved = resolveLaunchConfig()
        if (!resolved) return
        const arch = archetypeOfConfig(resolved.config)
        if (arch === 'scalper') {
            setLaunchError('Scalper нельзя прогнать на свечах — нужны тики и order-flow')
            return
        }
        if (fromDate > toDate) {
            setLaunchError('Дата окончания должна быть позже даты начала')
            return
        }
        if (!(capital > 0)) {
            setLaunchError('Проверьте конфиг и период')
            return
        }
        setLaunchError(null)
        setError(null)
        setStatus(null)
        setRunning(true)
        try {
            writeStoredConfig({
                config: resolved.config,
                robotId: resolved.robotId,
                capital,
            })
            const wrap = await robotV2Service.runBacktest({
                config: resolved.config,
                from_date: `${fromDate}T00:00:00Z`,
                to_date: `${toDate}T23:59:59Z`,
                initial_capital: capital,
                robotId: resolved.robotId,
                tokenId: resolved.tokenId,
                asyncExecution: true,
            })
            if (wrap.status === 202) {
                const rid = wrap.data.run_id
                setRunId(rid)
                syncRunQuery(rid)
                toast.show(`Прогон #${rid} запущен`, 'success')
                void loadHistory()
            } else {
                const rid = wrap.data.run_id ?? null
                setRunId(rid)
                syncRunQuery(rid)
                setStatus(wrap.data)
                setRunning(false)
                void loadHistory()
            }
        } catch (e) {
            setRunning(false)
            const code = httpStatusOf(e)
            const msg = fmtErr(e)
            if (code === 422) {
                setLaunchError(msg || 'Проверьте конфиг и период')
            } else if (code === 503) {
                setLaunchError(msg || 'Очередь занята — повторите позже')
            } else {
                setLaunchError(msg)
            }
            toast.show(msg, 'error')
        }
    }

    const onCancel = async () => {
        if (!runId) return
        setCancelling(true)
        try {
            await robotV2Service.cancelBacktestRun(runId)
            toast.show('Отмена запрошена…', 'info')
            for (let i = 0; i < 45; i++) {
                const st = await poll(runId)
                const phase = String(st.status || '').toUpperCase()
                if (phase === 'CANCELLED' || phase === 'FAILED' || phase === 'SUCCESS') return
                await new Promise(r => window.setTimeout(r, 1000))
            }
            toast.show('Отмена отправлена — статус обновится при следующем опросе', 'info')
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setCancelling(false)
        }
    }

    const toggleSelect = (id: number) => {
        setSelectedIds(prev => {
            if (prev.includes(id)) return prev.filter(x => x !== id)
            if (prev.length >= 2) return [prev[1], id]
            return [...prev, id]
        })
        setCompare(null)
    }

    const onCompare = async () => {
        if (selectedIds.length !== 2) return
        try {
            const data = await robotV2Service.compareBacktestRuns(selectedIds[0], selectedIds[1])
            setCompare(data)
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        }
    }

    const openHistoryRun = useCallback(
        async (id: number, opts?: { scroll?: boolean }) => {
            setOpeningRun(true)
            try {
                const details = await robotV2Service.getBacktestRunDetails(id)
                setRunId(id)
                setStatus(details)
                syncRunQuery(id)
                const fromIso = String(details.requested_from || '').slice(0, 10)
                const toIso = String(details.requested_to || '').slice(0, 10)
                if (fromIso) setFromDate(fromIso)
                if (toIso) setToDate(toIso)
                const cap = Number(details.initial_capital)
                if (Number.isFinite(cap) && cap > 0) setCapital(cap)
                const st = String(details.status || '').toUpperCase()
                setRunning(st === 'RUNNING' || st === 'QUEUED')
                setError(st === 'FAILED' ? (details.error_message || 'Ошибка прогона') : null)
                if (opts?.scroll !== false) {
                    window.requestAnimationFrame(() => {
                        resultAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    })
                }
            } catch (e) {
                toast.show(fmtErr(e), 'error')
                syncRunQuery(null)
                openedFromQueryRef.current = null
            } finally {
                setOpeningRun(false)
            }
        },
        [syncRunQuery, toast],
    )

    useEffect(() => {
        const raw = searchParams.get('run') || searchParams.get('runId')
        if (!raw) return
        const qid = Number(raw)
        if (!Number.isFinite(qid) || qid <= 0) return
        if (openedFromQueryRef.current === qid) return
        if (runId === qid && status) {
            openedFromQueryRef.current = qid
            return
        }
        openedFromQueryRef.current = qid
        void openHistoryRun(qid, { scroll: false })
    }, [searchParams, openHistoryRun, runId, status])

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            const t = e.target as HTMLElement | null
            const tag = t?.tagName?.toLowerCase()
            if (tag === 'input' || tag === 'textarea' || tag === 'select' || t?.isContentEditable) return
            if (e.key === 'r' || e.key === 'R') {
                e.preventDefault()
                void loadHistory()
            } else if (e.key === 'n' || e.key === 'N') {
                e.preventDefault()
                launchFocusRef.current?.focus()
            }
        }
        window.addEventListener('keydown', onKey)
        return () => window.removeEventListener('keydown', onKey)
    }, [loadHistory])

    const historyConfigOptions = useMemo(() => {
        const usable = history.filter(h => {
            const s = String(h.status).toUpperCase()
            return s === 'SUCCESS' || s === 'CANCELLED' || s === 'FAILED'
        })
        return [
            { value: '', label: 'Выберите прогон…' },
            ...usable.map(h => {
                const labelBits = [
                    `#${h.run_id}`,
                    h.config_label || null,
                    h.requested_from ? String(h.requested_from).slice(0, 10) : null,
                ].filter(Boolean)
                return {
                    value: String(h.run_id),
                    label: labelBits.join(' · '),
                    tag: String(h.status),
                }
            }),
        ]
    }, [history])

    const robotPickOptions = useMemo(
        () => [
            { value: '', label: 'Выберите робота…' },
            ...tradingRobots.map(r => ({
                value: String(r.id),
                label: `${r.name} (#${r.id})`,
                tag: archetypeOfConfig(r.config) || undefined,
            })),
        ],
        [tradingRobots],
    )

    const ret = payload.total_return_percent ?? status?.total_return_percent ?? null
    const dd = payload.max_drawdown_percent ?? status?.max_drawdown_percent ?? null
    const finalEq = payload.final_equity ?? status?.final_equity ?? null
    const winRate = payload.win_rate_percent ?? status?.win_rate_percent ?? null
    const sharpe = payload.sharpe_ratio ?? status?.sharpe_ratio ?? null
    const sortino = payload.sortino_ratio ?? status?.sortino_ratio ?? null
    const calmar = payload.calmar_ratio ?? status?.calmar_ratio ?? null
    const progress = Number(status?.progress_percent ?? 0)
    const phaseLabel = status?.phase_label || status?.run_phase || (isActive ? 'Запуск…' : '')
    const hasRunSelection = runId != null && (status != null || openingRun || isActive)

    return (
        <div className="page" data-page="robots" data-screen="backtest">
            <PageHero
                className="dashboard-hero--node"
                eyebrow="БЭКТЕСТ"
                title="ЛАБОРАТОРИЯ"
                subtitle="Отдельный экран: готовые правила, прогон на истории, журнал каждой сделки. Биржу это не трогает."
                actions={
                    <>
                        {isActive ? (
                            <Button
                                type="button"
                                variant="danger"
                                size="sm"
                                loading={cancelling}
                                onClick={() => void onCancel()}
                            >
                                Отменить
                            </Button>
                        ) : (
                            <Button
                                type="button"
                                size="sm"
                                loading={running}
                                disabled={scalperBlocked}
                                onClick={() => void onRun()}
                            >
                                Запустить
                            </Button>
                        )}
                    </>
                }
            />

            <div className="dashboard-layout">
                {/* L1 Launch — portfolio history-zone chrome, full width */}
                <Card className="dashboard-totals-card portfolio-history-zone robots-v2-lab-zone">
                    <div className="portfolio-history-zone__toolbar">
                        <div className="portfolio-history-zone__lead">
                            <h3 className="portfolio-history-zone__title">
                                <span className="dashboard-collapse__label">
                                    <span className="dashboard-icon" aria-hidden>↗</span>
                                    Новый прогон
                                </span>
                                {runStatus ? (
                                    <Badge variant={statusVariant(runStatus)}>
                                        {sessionStateLabel(runStatus) || runStatus}
                                    </Badge>
                                ) : null}
                            </h3>
                        </div>
                        <div className="portfolio-history-zone__controls">
                            <SegmentedControl
                                className="portfolio-history-tabs robots-v2-segmented"
                                aria-label="Источник конфига"
                                options={[
                                    { value: 'visual', label: 'Настроить' },
                                    { value: 'robot', label: 'Робот' },
                                    { value: 'history', label: 'Прошлый' },
                                ]}
                                value={source}
                                onChange={v => {
                                    setSource(v as ConfigSource)
                                    setLaunchError(null)
                                    setSourceHint(null)
                                }}
                            />
                            <div className="portfolio-history-period" aria-label="Период бэктеста">
                                <div className="portfolio-history-period__row robots-v2-lab-period-row">
                                    <SegmentedControl
                                        className="portfolio-period-control"
                                        aria-label="Пресет периода"
                                        options={[
                                            ...PRESETS.map(p => ({ value: p.id, label: p.label })),
                                            { value: 'custom', label: 'Свой' },
                                        ]}
                                        value={PRESETS.find(p => spanDays === p.days)?.id ?? 'custom'}
                                        onChange={id => {
                                            const preset = PRESETS.find(p => p.id === id)
                                            if (!preset) return
                                            setFromDate(daysAgoUtc(preset.days - 1))
                                            setToDate(todayUtc())
                                        }}
                                    />
                                    <DateRangePicker
                                        variant="fields"
                                        fromValue={fromDate ? `${fromDate}T00:00` : ''}
                                        toValue={toDate ? `${toDate}T00:00` : ''}
                                        onFromChange={v => setFromDate(v ? v.slice(0, 10) : '')}
                                        onToChange={v => setToDate(v ? v.slice(0, 10) : '')}
                                        fromLabel="С"
                                        toLabel="По"
                                        showLabel={false}
                                    />
                                    <label className="robots-v2-field robots-v2-lab-capital">
                                        <span>Капитал</span>
                                        <input
                                            type="number"
                                            className="robots-v2-input"
                                            min={10}
                                            step={1000}
                                            value={capital}
                                            onChange={e => setCapital(Number(e.target.value) || 0)}
                                        />
                                    </label>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="portfolio-history-zone__panels robots-v2-lab-zone__panels">
                        {source === 'visual' && (
                            <>
                                <BacktestStartGuide
                                    draft={draft}
                                    activePreset={matchingPreset(draft)}
                                    onApplyPreset={applyPreset}
                                />
                                <LabConfigForm draft={draft} onChange={patchDraft} compact={false} />
                            </>
                        )}

                        {source === 'robot' && (
                            <div className="robots-v2-form">
                                <label className="robots-v2-field">
                                    <span>Робот</span>
                                    {robotsLoading ? (
                                        <Skeleton height="36px" />
                                    ) : (
                                        <Select
                                            className="robots-v2-select"
                                            options={robotPickOptions}
                                            value={selectedRobotId}
                                            onChange={v => setSelectedRobotId(v)}
                                            placeholder="Выберите робота…"
                                            size="sm"
                                        />
                                    )}
                                    <small className="robots-v2-hint">
                                        Берутся сохранённые правила этого робота. После успешного прогона можно создать нового — он останется остановленным.
                                    </small>
                                </label>
                                {selectedRobot ? (
                                    <p className="robots-v2-hint">
                                        Архетип: {archetypeOfConfig(selectedRobot.config) || '—'}
                                    </p>
                                ) : null}
                            </div>
                        )}

                        {source === 'history' && (
                            <div className="robots-v2-form robots-v2-lab-history-source">
                                <label className="robots-v2-field">
                                    <span>Прошлый прогон</span>
                                    <Select
                                        className="robots-v2-select"
                                        options={historyConfigOptions}
                                        value={historyRunId}
                                        onChange={v => setHistoryRunId(v)}
                                        placeholder="Выберите прогон…"
                                        size="sm"
                                        disabled={historyConfigOptions.length <= 1}
                                    />
                                </label>
                                {historyHydrating ? <Skeleton height="24px" /> : null}
                                {sourceHint ? <p className="robots-v2-hint">{sourceHint}</p> : null}
                                {config && !historyHydrating ? (
                                    <p className="robots-v2-hint">
                                        Архетип: {archetypeOfConfig(config) || '—'}
                                        {selectedRobotId
                                            ? ` · soft-bind #${selectedRobotId}`
                                            : ' · без робота'}
                                    </p>
                                ) : null}
                                {historyConfigOptions.length <= 1 ? (
                                    <p className="robots-v2-hint">
                                        Пока нет завершённых прогонов — сначала запустите бэктест в режиме «Настроить»
                                    </p>
                                ) : null}
                            </div>
                        )}

                        {scalperBlocked && (
                            <div className="robots-v2-banner robots-v2-banner--error">
                                Scalper работает на тиках и order-flow. Бар-бэктест для этого архетипа недоступен.
                            </div>
                        )}

                        <small className="robots-v2-hint">
                            Реальные свечи MOEX ISS / Bybit klines.
                            {spanDays > 0 ? ` · ${spanDays} дн.` : ''}
                            {spanDays > 180
                                ? ' Длинный период на мелком ТФ может занять несколько минут.'
                                : ''}
                        </small>

                        {launchError ? (
                            <div className="robots-v2-banner robots-v2-banner--error">{launchError}</div>
                        ) : null}

                        <div
                            ref={launchFocusRef}
                            tabIndex={-1}
                            className="dashboard-settings-actions robots-v2-lab-launch-focus"
                        >
                            {isNarrow && isActive ? (
                                <Button
                                    type="button"
                                    variant="danger"
                                    loading={cancelling}
                                    onClick={() => void onCancel()}
                                >
                                    Отменить прогон
                                </Button>
                            ) : (
                                <Button
                                    type="button"
                                    loading={running}
                                    disabled={scalperBlocked || isActive}
                                    onClick={() => void onRun()}
                                >
                                    Запустить бэктест
                                </Button>
                            )}
                        </div>
                    </div>
                </Card>

                {/* L2 Runs table — full width */}
                {historyLoading && history.length === 0 ? (
                    <Card className="dashboard-assets-card dashboard-skeleton-card">
                        <Skeleton height="280px" />
                    </Card>
                ) : historyError && history.length === 0 ? (
                    <Card className="dashboard-totals-card dashboard-error-card">
                        <p className="dashboard-empty">Не удалось загрузить историю</p>
                        <p className="robots-v2-hint">{historyError}</p>
                        <div className="dashboard-error-card__actions">
                            <Button type="button" onClick={() => void loadHistory()}>Повторить</Button>
                        </div>
                    </Card>
                ) : (
                    <BacktestHistoryCard
                        history={history}
                        historyLoading={historyLoading}
                        historyError={historyError}
                        selectedIds={selectedIds}
                        activeRunId={runId}
                        compare={compare}
                        onRefresh={() => void loadHistory()}
                        onCompare={() => void onCompare()}
                        onToggleSelect={toggleSelect}
                        onOpenRun={id => void openHistoryRun(id)}
                        statusVariant={statusVariant}
                        showBindColumn
                        showConfigColumn
                        title="Все прогоны"
                        emptyText="Нет прогонов"
                        emptyCta={(
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={() => launchFocusRef.current?.focus()}
                            >
                                Настройте первый бэктест выше
                            </Button>
                        )}
                        onBindClick={rid => navigate(`/robots/${rid}/backtest`)}
                        embedCompare={false}
                    />
                )}

                {/* L3 Compare */}
                <BacktestCompareStrip
                    compare={compare}
                    selectedIds={selectedIds}
                    onCompare={() => void onCompare()}
                />

                {/* L4 Results */}
                <div ref={resultAnchorRef} />

                {!hasRunSelection ? (
                    <p className="robots-v2-hint robots-v2-lab-select-hint">
                        Выберите прогон в таблице, чтобы открыть результаты
                    </p>
                ) : null}

                {(isActive || openingRun) && (
                    <RobotStageCard
                        title={openingRun ? 'Загрузка прогона…' : (phaseLabel || 'Прогон')}
                        progress={progress}
                        ariaLabel="Прогресс бэктеста"
                        meta={
                            status?.phase_units_total ? (
                                <span className="robots-v2-hint">
                                    {formatBacktestPhaseUnits(
                                        status.run_phase,
                                        status.phase_units_done ?? 0,
                                        status.phase_units_total,
                                    )}
                                </span>
                            ) : null
                        }
                    />
                )}

                {(error || (runStatus === 'FAILED' && !isActive)) && (
                    <Card className="dashboard-totals-card dashboard-error-card">
                        <p className="dashboard-empty">
                            {error || status?.error_message || 'Прогон завершился с ошибкой'}
                        </p>
                    </Card>
                )}

                {runStatus === 'SUCCESS' && runId != null && (
                    <BacktestVerdictCard
                        totalReturnPercent={ret == null ? null : Number(ret)}
                        maxDrawdownPercent={dd == null ? null : Number(dd)}
                        winRatePercent={winRate == null ? null : Number(winRate)}
                        tradeCount={trades.length}
                        initialCapital={Number(payload.initial_capital ?? capital)}
                        finalEquity={finalEq == null ? null : Number(finalEq)}
                        reasonCodes={collectReasonCodes(trades)}
                        onSaveAsRobot={() => setSaveAsOpen(true)}
                    />
                )}

                {(runStatus === 'SUCCESS'
                    || (runStatus === 'CANCELLED' && !isActive && (
                        equityCurve.length > 0 || trades.length > 0 || runSignals.length > 0
                    ))) && (
                    <BacktestResultsPanel
                        key={runId ?? 'run'}
                        runId={runId}
                        runStatus={runStatus}
                        partialResult={status?.partial_result ?? (runStatus === 'CANCELLED' ? true : null)}
                        capital={capital}
                        initialCapital={Number(payload.initial_capital ?? capital)}
                        finalEquity={finalEq}
                        totalReturnPercent={ret}
                        maxDrawdownPercent={dd}
                        winRatePercent={winRate}
                        sharpeRatio={sharpe}
                        sortinoRatio={sortino}
                        calmarRatio={calmar}
                        stages={payload.stages}
                        historyStats={(payload.history_stats || null) as Record<string, unknown> | null}
                        fundingChargesTotal={
                            (payload as { funding_charges_total?: number | null }).funding_charges_total
                            ?? null
                        }
                        observability={
                            status?.observability
                            ?? (payload.observability as BacktestObservability | null | undefined)
                            ?? null
                        }
                        executionModel={
                            status?.execution_model
                            ?? (payload as { execution_model?: unknown }).execution_model
                            ?? null
                        }
                        feeSummary={feeSummary}
                        portfolioSnapshots={portfolioSnapshots}
                        narrative={narrative}
                        requestedFrom={status?.requested_from ?? fromDate}
                        requestedTo={status?.requested_to ?? toDate}
                        signalsTotal={status?.signals_total ?? null}
                        trades={trades as unknown as Array<Record<string, unknown>>}
                        chartPoints={chartPoints}
                        signals={runSignals as unknown as Array<Record<string, unknown>>}
                        orders={runOrders as unknown as Array<Record<string, unknown>>}
                        dailySummary={dailySummary as unknown as Array<Record<string, unknown>>}
                        chartRef={chartRef}
                        seriesRef={seriesRef}
                    />
                )}

                {runStatus === 'CANCELLED' && !isActive
                    && equityCurve.length === 0 && trades.length === 0 && runSignals.length === 0 && (
                    <Card className="dashboard-totals-card">
                        <p className="dashboard-empty">Прогон отменён — артефактов нет</p>
                    </Card>
                )}

                {runId != null && (
                    <SaveAsRobotModal
                        open={saveAsOpen}
                        onClose={() => setSaveAsOpen(false)}
                        runId={runId}
                        defaultName={saveAsDefaultName}
                        suggestedTokenId={saveAsSuggestedTokenId}
                        runAlreadyBound={runAlreadyBound}
                        onSaved={robotId => {
                            setSaveAsOpen(false)
                            toast.show('Робот создан из прогона', 'success')
                            void loadHistory()
                            navigate(`/robots/edit/${robotId}`)
                        }}
                    />
                )}
            </div>
        </div>
    )
}
