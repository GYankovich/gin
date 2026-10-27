import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { PageHero } from '@/components/ui/PageHero'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import {
    BacktestHistoryCard,
    type BacktestHistoryRow,
} from '@/pages/robots-v2/components/BacktestHistoryCard'
import { BacktestStartGuide } from '@/pages/robots-v2/components/BacktestStartGuide'
import { LabConfigForm } from '@/pages/robots-v2/components/LabConfigForm'
import {
    matchingPreset,
    presetById,
    presetDraftPatch,
    type BacktestPresetId,
} from '@/pages/robots-v2/backtestGuide'
import {
    archetypeOfConfig,
    backtestRunPath,
    backtestStatusVariant,
    normalizeHistoryItem,
    parseBacktestRunId,
    tokenIdOf,
} from '@/pages/robots-v2/backtestLabShared'
import { fmtErr } from '@/pages/robots-v2/formatters'
import {
    configToDraft,
    defaultWizardDraft,
    draftToV4Config,
    parseFixedList,
    type RobotV2WizardDraft,
} from '@/pages/robots-v2/wizardDraft'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2 } from '@/types/robotV2'

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

function httpStatusOf(e: unknown): number | null {
    const err = e as { response?: { status?: number } }
    const n = Number(err?.response?.status)
    return Number.isFinite(n) ? n : null
}

const PRESETS: Array<{ id: string; label: string; days: number }> = [
    { id: '7d', label: '7д', days: 7 },
    { id: '30d', label: '30д', days: 30 },
    { id: '90d', label: '90д', days: 90 },
    { id: '180d', label: '180д', days: 180 },
]

export default function BacktestLabPage() {
    const navigate = useNavigate()
    const [searchParams] = useSearchParams()
    const toast = useToast()
    const deepLinkRunId = parseBacktestRunId(searchParams.get('run') || searchParams.get('runId'))

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

    const [history, setHistory] = useState<BacktestHistoryRow[]>([])
    const [historyLoading, setHistoryLoading] = useState(false)
    const [historyError, setHistoryError] = useState<string | null>(null)

    const launchFocusRef = useRef<HTMLDivElement | null>(null)

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
            const snap = (
                details.config_snapshot
                || (details.result_payload as { config?: Record<string, unknown> } | undefined)?.config
                || null
            ) as Record<string, unknown> | null
            const hasTradingConfig = Boolean(
                snap && (snap.strategy || snap.universe || snap.core || snap.configVersion),
            )
            if (!hasTradingConfig || !snap) {
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
            // Lab backtests always simulate; Paper/Live only matters for live robots.
            const next = { ...prev, ...patch, mode: 'paper' as const }
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

    const archetype = archetypeOfConfig(config)
    const scalperBlocked = archetype === 'scalper'
    const spanDays = useMemo(() => {
        const a = Date.parse(`${fromDate}T00:00:00Z`)
        const b = Date.parse(`${toDate}T00:00:00Z`)
        if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return 0
        return Math.round((b - a) / 86_400_000) + 1
    }, [fromDate, toDate])

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
            const rid = wrap.status === 202 ? wrap.data.run_id : wrap.data.run_id ?? null
            if (rid != null && Number.isFinite(rid) && rid > 0) {
                toast.show(`Прогон #${rid} запущен`, 'success')
                navigate(backtestRunPath(rid))
                return
            }
            setRunning(false)
            setLaunchError('Прогон не вернул идентификатор')
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

    if (deepLinkRunId != null) {
        return <Navigate to={backtestRunPath(deepLinkRunId)} replace />
    }

    return (
        <div className="page" data-page="robots" data-screen="backtest">
            <PageHero
                className="dashboard-hero--node dashboard-hero--cabin"
                eyebrow="Прогоны"
                title="Лаборатория"
            />

            <div className="dashboard-layout robots-v2-lab-layout">
                <div className="robots-v2-lab-split">
                <div className="robots-v2-lab-main">
                <Card className="dashboard-totals-card robots-v2-lab-zone">
                    <div className="robots-v2-lab-zone__bar">
                        <h3 className="robots-v2-lab-zone__title">
                            <span className="dashboard-collapse__label">
                                <span className="dashboard-icon" aria-hidden>▣</span>
                                Новый прогон
                            </span>
                        </h3>
                        <SegmentedControl
                            className="portfolio-history-tabs"
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
                        <div className="robots-v2-lab-period" aria-label="Период бэктеста">
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
                        </div>
                    </div>

                    {source === 'robot' && (
                        <div className="robots-v2-lab-source">
                            <div className="robots-v2-grid robots-v2-grid--2">
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
                                </label>
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
                            <small className="robots-v2-hint">
                                Берутся сохранённые правила этого робота. После успешного прогона можно создать нового — он останется остановленным.
                            </small>
                            {selectedRobot ? (
                                <p className="robots-v2-hint">
                                    Архетип: {archetypeOfConfig(selectedRobot.config) || '—'}
                                </p>
                            ) : null}
                        </div>
                    )}

                    {source === 'history' && (
                        <div className="robots-v2-lab-source">
                            <div className="robots-v2-grid robots-v2-grid--2">
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

                    {launchError ? (
                        <div className="robots-v2-banner robots-v2-banner--error">{launchError}</div>
                    ) : null}
                </Card>

                {source === 'visual' && (
                    <LabConfigForm
                        draft={draft}
                        onChange={patchDraft}
                        compact
                        presetSlot={(
                            <BacktestStartGuide
                                draft={draft}
                                activePreset={matchingPreset(draft)}
                                onApplyPreset={applyPreset}
                            />
                        )}
                    />
                )}

                <Card className="dashboard-totals-card robots-v2-lab-launch">
                    <div
                        ref={launchFocusRef}
                        tabIndex={-1}
                        className="dashboard-settings-actions robots-v2-lab-zone__foot"
                    >
                        <small className="robots-v2-hint robots-v2-lab-launch-meta">
                            Свечи MOEX / Bybit
                            {spanDays > 0 ? ` · ${spanDays} дн.` : ''}
                            {spanDays > 180 ? ' · длинный прогон' : ''}
                        </small>
                        <Button
                            type="button"
                            loading={running}
                            disabled={scalperBlocked}
                            onClick={() => void onRun()}
                        >
                            Запустить
                        </Button>
                    </div>
                </Card>
                </div>

                <div className="robots-v2-lab-history">
                {historyLoading && history.length === 0 ? (
                    <Card className="dashboard-totals-card portfolio-history-zone dashboard-skeleton-card">
                        <Skeleton height="280px" />
                    </Card>
                ) : historyError && history.length === 0 ? (
                    <Card className="dashboard-totals-card portfolio-history-zone dashboard-error-card">
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
                        activeRunId={null}
                        onRefresh={() => void loadHistory()}
                        onOpenRun={id => navigate(backtestRunPath(id))}
                        runHref={backtestRunPath}
                        statusVariant={backtestStatusVariant}
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
                                Настройте первый бэктест слева
                            </Button>
                        )}
                        onBindClick={rid => navigate(`/robots/${rid}/monitor`)}
                        tableMaxHeight={640}
                    />
                )}
                </div>
                </div>
            </div>
        </div>
    )
}
