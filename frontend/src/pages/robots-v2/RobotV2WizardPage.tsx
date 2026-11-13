import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { SideRail } from '@/components/ui/SideRail'
import { TimeSelect } from '@/components/ui/TimeSelect'
import { Toggle } from '@/components/ui/Toggle'
import { WeekdaysMaskField } from '@/components/ui/WeekdaysMaskField'
import { api } from '@/services/api'
import { robotV2Service } from '@/services/robotV2Service'
import { brokerFromTokenType, brokerLabelFromToken } from '@/modules/robots/config/tokenBroker'
import { useToast } from '@/components/ui/Toast'
import { ScreenerCustomFilters } from '@/pages/robots-v2/components/ScreenerCustomFilters'
import { fmtErr } from '@/pages/robots-v2/formatters'
import {
    ARCHETYPE_CARDS,
    archetypeDefaults,
    configToDraft,
    configToPortfolioDraft,
    customScreenerFieldDefaults,
    defaultWizardDraft,
    draftToPortfolioV4Config,
    draftToV4Config,
    parseFixedList,
    type RobotV2WizardDraft,
    type WizardArchetype,
} from '@/pages/robots-v2/wizardDraft'
import type { StrategyArchetypeInfo, UniversePreview } from '@/types/robotV2'

type ApiToken = {
    id: number
    name?: string
    broker_type?: string | null
    token_type?: { type?: number; typeName?: string }
}

const TRADING_STEPS = ['Основное', 'Расписание', 'Стратегия', 'Активы', 'Риск'] as const
const PORTFOLIO_STEPS = ['Основное', 'Расписание'] as const
const PREVIEW_PAGE_SIZE = 20
const UNIVERSE_OPTIONS = [
    { value: 'fixed', label: 'Список' },
    { value: 'index', label: 'Индекс' },
    { value: 'screener', label: 'Скринер' },
] as const
const PARAM_LABELS: Record<string, string> = {
    maPeriod: 'Период MA',
    volumeMultiplier: 'Множитель объёма',
    breakoutLookback: 'Окно пробоя',
    indicator: 'Индикатор',
    overboughtThreshold: 'Перекупленность',
    oversoldThreshold: 'Перепроданность',
    rsiPeriod: 'Период RSI',
    gridStepAtrPct: 'Шаг сетки, % ATR',
    gridDepth: 'Уровней',
    baseAllocationPct: 'Доля на уровень, %',
    scaleMultiplier: 'Множитель объёма',
    deltaThresholdPct: 'Порог дельты, %',
    requiresWebSocket: 'Нужен WebSocket',
    minVolumeWindow: 'Окно потока, сек',
    cooldownSec: 'Пауза, сек',
    stopLossCooldownSec: 'Пауза после стопа, сек',
    trendLookbackTicks: 'Окно тренда, тиков',
    trendBlockLongBps: 'Блок лонга, б.п.',
    minHoldSec: 'Мин. удержание, сек',
    minExitMoveBps: 'Мин. выход, б.п.',
    invalidateBelowEntryBps: 'Инвалидация, б.п.',
    minFlowTicks: 'Мин. тиков потока',
}

const SCALPER_PARAM_GROUPS: Array<{ title: string; keys: string[]; columns: 4 | 5 }> = [
    {
        title: 'Вход',
        columns: 5,
        keys: ['deltaThresholdPct', 'minVolumeWindow', 'minFlowTicks', 'trendLookbackTicks', 'trendBlockLongBps'],
    },
    {
        title: 'Выход',
        columns: 4,
        keys: ['minHoldSec', 'minExitMoveBps', 'invalidateBelowEntryBps'],
    },
    {
        title: 'Паузы',
        columns: 4,
        keys: ['cooldownSec', 'stopLossCooldownSec'],
    },
]

function StrategyParamField({
    name,
    value,
    onChange,
}: {
    name: string
    value: number | string
    onChange: (next: number | string) => void
}) {
    return (
        <label className="robots-v2-field">
            <span>{PARAM_LABELS[name] ?? name}</span>
            <input
                className="robots-v2-input"
                type={typeof value === 'number' ? 'number' : 'text'}
                value={String(value)}
                onChange={e => {
                    const raw = e.target.value
                    onChange(typeof value === 'number' ? Number(raw) : raw)
                }}
            />
        </label>
    )
}

const EOD_OPTIONS = [
    { value: 'on', label: 'Включён' },
    { value: 'off', label: 'Выключен' },
] as const
const EOD_TOOLTIP = 'За указанное число минут до конца расписания робот закрывает все позиции и не открывает новые до следующей сессии.'

function weekdaysToMask(days: boolean[]): number {
    return days.reduce((mask, selected, index) => selected ? mask | (1 << index) : mask, 0)
}

function maskToWeekdays(mask: number): boolean[] {
    return Array.from({ length: 7 }, (_, index) => Boolean(mask & (1 << index)))
}

function mergeArchetypeCards(apiItems: StrategyArchetypeInfo[]): Array<{
    id: WizardArchetype
    title: string
    description: string
}> {
    if (!apiItems.length) return ARCHETYPE_CARDS
    const apiIds = new Set(apiItems.map(a => String(a.archetype)))
    const ordered: Array<{ id: WizardArchetype; title: string; description: string }> = []
    for (const fallback of ARCHETYPE_CARDS) {
        if (!apiIds.has(fallback.id)) continue
        const api = apiItems.find(a => String(a.archetype) === fallback.id)
        const req = api?.requiredData ?? (api as { required_data?: string[] })?.required_data
        ordered.push({
            ...fallback,
            description: req?.length ? `${fallback.description} · ${req.join(', ')}` : fallback.description,
        })
    }
    return ordered.length ? ordered : ARCHETYPE_CARDS
}

export default function RobotV2WizardPage() {
    const navigate = useNavigate()
    const { id: editIdParam } = useParams()
    const [search] = useSearchParams()
    const editId = editIdParam ? Number(editIdParam) : null
    const toast = useToast()
    const kindFromUrl = search.get('kind') === 'portfolio' ? 'portfolio' : 'trading'
    const kindPinned = Boolean(editId) || search.has('kind')

    const [kind, setKind] = useState<'trading' | 'portfolio'>(kindFromUrl)
    const [step, setStep] = useState(0)
    const [draft, setDraft] = useState<RobotV2WizardDraft>(() => ({ ...defaultWizardDraft(), mode: 'live' }))
    const [tokens, setTokens] = useState<ApiToken[]>([])
    const [saving, setSaving] = useState(false)
    const [editLoading, setEditLoading] = useState(Boolean(editId))
    const [persistedRobotId, setPersistedRobotId] = useState<number | null>(editId)
    const [preview, setPreview] = useState<UniversePreview | null>(null)
    const [previewPage, setPreviewPage] = useState(1)
    const [previewLoading, setPreviewLoading] = useState(false)
    const [fieldErrors, setFieldErrors] = useState<string[]>([])
    const [archetypeCards, setArchetypeCards] = useState(ARCHETYPE_CARDS)

    useEffect(() => {
        void (async () => {
            try {
                const { data } = await api.post('/apikey/data', {})
                setTokens(Array.isArray(data?.keys) ? data.keys : [])
            } catch {
                setTokens([])
            }
        })()
    }, [])

    useEffect(() => {
        void (async () => {
            try {
                const items = await robotV2Service.listArchetypes()
                setArchetypeCards(mergeArchetypeCards(items))
            } catch {
                setArchetypeCards(ARCHETYPE_CARDS)
            }
        })()
    }, [])

    useEffect(() => {
        if (editId) return
        setKind(kindFromUrl)
        setStep(0)
    }, [editId, kindFromUrl])

    useEffect(() => {
        setStep(current => Math.min(current, (kind === 'portfolio' ? PORTFOLIO_STEPS : TRADING_STEPS).length - 1))
    }, [kind])

    useEffect(() => {
        if (editId) {
            void (async () => {
                try {
                    const robot = await robotV2Service.getById(editId)
                    if (robot.type === 1) {
                        setKind('portfolio')
                        setDraft(configToPortfolioDraft(robot.config, robot.name, robot.tokenId, robot.status))
                    } else {
                        setKind('trading')
                        setDraft({ ...configToDraft(robot.config, robot.name, robot.tokenId), mode: 'live' })
                    }
                } catch (e) {
                    toast.show(fmtErr(e), 'error')
                } finally {
                    setEditLoading(false)
                }
            })()
            return
        }
        setDraft({ ...defaultWizardDraft(), mode: 'live' })
    }, [editId, kindFromUrl]) // eslint-disable-line react-hooks/exhaustive-deps

    const selectedBroker = useMemo(() => {
        if (!draft.tokenId) return null
        return brokerFromTokenType(tokens.find(t => t.id === draft.tokenId)?.token_type)
    }, [draft.tokenId, tokens])

    const patch = (partial: Partial<RobotV2WizardDraft>) => {
        setDraft(prev => ({ ...prev, ...partial }))
        setFieldErrors([])
    }

    const selectKind = (next: 'trading' | 'portfolio') => {
        if (editId || next === kind) return
        setKind(next)
        setStep(0)
        setFieldErrors([])
        if (next === 'portfolio') {
            setDraft(prev => ({ ...prev, portfolioEnabled: true }))
        }
        const params = new URLSearchParams(search)
        params.set('kind', next)
        navigate(`/robots/new?${params.toString()}`, { replace: true })
    }

    const steps = kind === 'portfolio' ? PORTFOLIO_STEPS : TRADING_STEPS
    const lastStep = steps.length - 1
    const railTitle = `${editId ? 'Правка' : 'Создание'} ${kind === 'portfolio' ? 'опросника' : 'торгового'}`

    const validateStep = (s: number): string[] => {
        const errs: string[] = []
        if (s === 0) {
            if (!draft.name.trim()) errs.push('Укажите название')
            if (!draft.tokenId) errs.push('Выберите API-ключ')
        }
        if (s === 1 && (kind === 'trading' || kind === 'portfolio')) {
            if (!draft.weekdays.some(Boolean)) errs.push('Выберите хотя бы один день')
            if (draft.timeFrom >= draft.timeTo) errs.push('timeFrom должен быть раньше timeTo')
        }
        if (kind === 'trading') {
            if (s === 2) {
                if (!draft.archetype) errs.push('Выберите архетип')
            }
            if (s === 3) {
                if (draft.universeMode === 'fixed' && parseFixedList(draft.fixedList).length === 0) {
                    errs.push('Укажите хотя бы один тикер')
                }
                if (draft.universeMode === 'index' && !draft.indexCode.trim()) errs.push('Укажите индекс')
            }
            if (s === 4) {
                if (draft.mode === 'paper' && draft.capital <= 0) errs.push('Капитал должен быть > 0')
                if (draft.stopLossPct >= draft.takeProfitPct) errs.push('SL должен быть меньше TP')
            }
        }
        return errs
    }

    const allStepErrors = () => steps.flatMap((_, index) => validateStep(index))

    const goNext = () => {
        setFieldErrors([])
        setStep(s => Math.min(lastStep, s + 1))
    }

    const goToStep = (target: number) => {
        if (target === step) return
        setFieldErrors([])
        setStep(target)
    }

    const requireSaveBasics = (): string[] => {
        const errs: string[] = []
        if (!draft.name.trim()) errs.push('Укажите название')
        if (!draft.tokenId) errs.push('Выберите API-ключ')
        return errs
    }

    const selectArchetype = (id: WizardArchetype) => {
        const defs = archetypeDefaults(id)
        patch({
            archetype: id,
            timeframe: defs.timeframe,
            strategyParams: defs.params,
            advancedMode: defs.advancedMode ?? draft.advancedMode,
        })
    }

    const runPreview = async (page = previewPage) => {
        if (!draft.tokenId) {
            toast.show('Сначала выберите API-ключ', 'warning')
            return
        }
        setPreviewLoading(true)
        try {
            const cfg = draftToV4Config(draft)
            const data = await robotV2Service.previewUniverse({
                tokenId: draft.tokenId,
                instrumentType: draft.instrumentType,
                universe: cfg.universe as Record<string, unknown>,
                page,
                pageSize: PREVIEW_PAGE_SIZE,
            })
            setPreview(data)
            setPreviewPage(page)
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setPreviewLoading(false)
        }
    }

    const saveRobot = async (andStart: boolean) => {
        const basicErrs = requireSaveBasics()
        if (basicErrs.length) {
            setFieldErrors(basicErrs)
            toast.show(basicErrs.join('; '), 'error')
            return
        }
        if (andStart) {
            const errs = allStepErrors()
            setFieldErrors(errs)
            if (errs.length) {
                toast.show(errs.join('; '), 'error')
                return
            }
        } else {
            setFieldErrors([])
        }
        if (!draft.tokenId) return
        setSaving(true)
        try {
            const config = draftToV4Config(draft)
            if (andStart) {
                const validated = await robotV2Service.validate({ type: 2, config })
                if (!validated.valid) {
                    toast.show(validated.errors.map(e => e.message).join('; ') || 'Конфиг невалиден', 'error')
                    return
                }
            }
            const robot = await robotV2Service.createOrUpdate({
                id: editId || persistedRobotId || undefined,
                name: draft.name.trim(),
                type: 2,
                tokenId: draft.tokenId,
                config,
                status: andStart ? undefined : (editId || persistedRobotId ? undefined : 2),
            })
            setPersistedRobotId(robot.id)
            if (andStart) {
                try {
                    if (draft.mode === 'live') {
                        await robotV2Service.start(robot.id, {})
                        toast.show('Робот сохранён и запущен (live · капитал со счёта)', 'success')
                    } else {
                        await robotV2Service.start(robot.id, { virtualCapital: draft.capital })
                        toast.show('Робот сохранён и запущен (paper)', 'success')
                    }
                } catch (e) {
                    toast.show(`Робот #${robot.id} сохранён, но не запущен: ${fmtErr(e)}`, 'error')
                    return
                }
                navigate(`/robots/${robot.id}/monitor`)
            } else {
                toast.show(editId ? 'Робот сохранён' : 'Робот создан', 'success')
                navigate('/robots')
            }
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setSaving(false)
        }
    }

    const savePortfolioRobot = async () => {
        const basicErrs = requireSaveBasics()
        if (basicErrs.length) {
            setFieldErrors(basicErrs)
            toast.show(basicErrs.join('; '), 'error')
            return
        }
        const completeErrs = allStepErrors()
        const wantEnable = draft.portfolioEnabled
        if (wantEnable && completeErrs.length) {
            setFieldErrors(completeErrs)
            toast.show(`Сохраняем выключенным: ${completeErrs.join('; ')}`, 'warning')
        } else {
            setFieldErrors([])
        }
        if (!draft.tokenId) return
        setSaving(true)
        try {
            const config = draftToPortfolioV4Config(draft)
            const enable = wantEnable && completeErrs.length === 0
            if (enable) {
                const validated = await robotV2Service.validate({ type: 1, config })
                if (!validated.valid) {
                    toast.show(validated.errors.map(e => e.message).join('; ') || 'Конфиг невалиден', 'error')
                    return
                }
            }
            await robotV2Service.createOrUpdate({
                id: editId || undefined,
                name: draft.name.trim(),
                type: 1,
                tokenId: draft.tokenId,
                config,
                status: enable ? 1 : 2,
            })
            toast.show(
                enable
                    ? (editId ? 'Опросник сохранён и включён' : 'Опросник создан и включён')
                    : (editId ? 'Опросник сохранён' : 'Опросник создан'),
                'success',
            )
            navigate('/robots')
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setSaving(false)
        }
    }

    const configComplete = allStepErrors().length === 0

    const railNav = (
        <SideRail
            className="robots-v2-wizard-rail"
            title={railTitle}
            aria-label="Шаги мастера"
            dimmed={Boolean(editLoading)}
        >
            {steps.map((label, i) => {
                const active = i === step
                return (
                    <SideRail.Item
                        key={label}
                        active={active}
                        aria-current={active ? 'step' : undefined}
                        disabled={Boolean(editLoading)}
                        onClick={() => goToStep(i)}
                        name={label}
                    />
                )
            })}
        </SideRail>
    )

    if (editId && editLoading) {
        return (
            <div className="page" data-page="robots" data-robots-view="wizard" data-robot-kind={kind}>
                <div className="dashboard-layout robots-v2-wizard-layout">
                    <div className="robots-v2-wizard-rail-layout">
                        {railNav}
                        <Card className="robots-v2-wizard-card" aria-busy="true">
                            <Skeleton width="35%" height="24px" borderRadius="6px" />
                            <div style={{ marginTop: 'var(--space-4)' }}>
                                <Skeleton width="100%" height="280px" borderRadius="10px" />
                            </div>
                        </Card>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="page" data-page="robots" data-robots-view="wizard" data-robot-kind={kind}>
            <div className="dashboard-layout robots-v2-wizard-layout">
                {fieldErrors.length > 0 && (
                    <div className="robots-v2-banner robots-v2-banner--error" role="alert">
                        <strong>Проверьте настройки</strong>
                        <span>{fieldErrors.join(' · ')}</span>
                    </div>
                )}

                <div className="robots-v2-wizard-rail-layout">
                    {railNav}

                <div className="robots-v2-wizard-main">
                <Card className="robots-v2-wizard-card">
                    {step === 0 && (
                        <div className="robots-v2-form">
                            {!kindPinned ? (
                                <div className="robots-v2-field">
                                    <span>Что нужно автоматизировать?</span>
                                    <div className="robots-v2-type-grid">
                                        <button
                                            type="button"
                                            className={`robots-v2-type-card ${kind === 'trading' ? 'robots-v2-type-card--on' : ''}`}
                                            aria-pressed={kind === 'trading'}
                                            onClick={() => selectKind('trading')}
                                        >
                                            <strong>Торговый робот</strong>
                                        </button>
                                        <button
                                            type="button"
                                            className={`robots-v2-type-card ${kind === 'portfolio' ? 'robots-v2-type-card--on' : ''}`}
                                            aria-pressed={kind === 'portfolio'}
                                            onClick={() => selectKind('portfolio')}
                                        >
                                            <strong>Опросник портфеля</strong>
                                        </button>
                                    </div>
                                </div>
                            ) : null}
                            <label className="robots-v2-field">
                                <span>Название</span>
                                <input
                                    className="robots-v2-input"
                                    value={draft.name}
                                    maxLength={50}
                                    onChange={e => patch({ name: e.target.value })}
                                    placeholder={kind === 'portfolio' ? 'Portfolio sync' : 'MOEX Momentum'}
                                />
                            </label>
                            <label className="robots-v2-field">
                                <span>
                                    Токен брокера
                                    <FormLabelTooltip text="API-ключ определяет брокера, доступные инструменты и счёт для операций." />
                                </span>
                                <Select
                                    className="robots-v2-select"
                                    value={draft.tokenId}
                                    placeholder="Выберите токен…"
                                    searchable={tokens.length > 6}
                                    options={tokens.map(token => ({
                                        value: token.id,
                                        label: `${token.name || `Token #${token.id}`} — ${brokerLabelFromToken(token.id, tokens)}`,
                                    }))}
                                    onChange={value => {
                                        const id = Number(value) || null
                                        const broker = id
                                            ? brokerFromTokenType(tokens.find(t => t.id === id)?.token_type)
                                            : null
                                        patch({
                                            tokenId: id,
                                            instrumentType: broker === 'bybit' ? 'perpetual' : 'stock',
                                            fixedList: broker === 'bybit' ? 'BTCUSDT, ETHUSDT' : draft.fixedList,
                                            capital: broker === 'bybit' && draft.capital === 100_000 ? 10_000 : draft.capital,
                                        })
                                    }}
                                />
                            </label>
                        </div>
                    )}

                    {step === 1 && (
                        <div className="robots-v2-form">
                            <div className="robots-v2-field">
                                <WeekdaysMaskField
                                    value={weekdaysToMask(draft.weekdays)}
                                    onChange={mask => patch({ weekdays: maskToWeekdays(mask) })}
                                />
                            </div>
                            <div className="robots-v2-schedule-grid">
                                <label className="robots-v2-field">
                                    <span>Начало</span>
                                    <TimeSelect
                                        className="robots-v2-time"
                                        aria-label="Начало"
                                        value={draft.timeFrom}
                                        onChange={timeFrom => patch({ timeFrom })}
                                    />
                                </label>
                                <label className="robots-v2-field">
                                    <span>Окончание</span>
                                    <TimeSelect
                                        className="robots-v2-time"
                                        aria-label="Окончание"
                                        value={draft.timeTo}
                                        onChange={timeTo => patch({ timeTo })}
                                    />
                                </label>
                                <label className="robots-v2-field">
                                    <span>Интервал</span>
                                    <Select
                                        className="robots-v2-select"
                                        value={draft.pollInterval}
                                        searchable={false}
                                        options={[
                                            { value: '1m', label: '1 мин' },
                                            { value: '5m', label: '5 мин' },
                                            { value: '15m', label: '15 мин' },
                                            { value: '1h', label: '1 час' },
                                        ]}
                                        onChange={value => patch({
                                            pollInterval: value as RobotV2WizardDraft['pollInterval'],
                                        })}
                                    />
                                </label>
                            </div>
                        </div>
                    )}

                    {kind === 'trading' && step === 2 && (
                        <div className="robots-v2-form">
                            <div className="robots-v2-form-group">
                                <div className="robots-v2-field">
                                    <span>Архетип</span>
                                    <div className="robots-v2-archetype-grid">
                                        {archetypeCards.map(card => (
                                            <button
                                                key={card.id}
                                                type="button"
                                                className={`robots-v2-archetype ${draft.archetype === card.id ? 'robots-v2-archetype--on' : ''}`}
                                                onClick={() => selectArchetype(card.id)}
                                            >
                                                <strong>{card.title}</strong>
                                                <span>{card.description}</span>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                            <div className="robots-v2-form-group">
                                <div className="robots-v2-grid robots-v2-grid--2">
                                    <label className="robots-v2-field">
                                        <span>Тип инструмента</span>
                                        <Select
                                            className="robots-v2-select"
                                            value={draft.instrumentType}
                                            searchable={false}
                                            options={selectedBroker === 'bybit'
                                                ? [
                                                    { value: 'perpetual', label: 'Perpetual (USDT linear)' },
                                                    { value: 'coin_futures', label: 'Coin futures (inverse)' },
                                                ]
                                                : [
                                                    { value: 'stock', label: 'Акции' },
                                                    { value: 'futures', label: 'Фьючерсы' },
                                                ]}
                                            onChange={value =>
                                                patch({
                                                    instrumentType: value as RobotV2WizardDraft['instrumentType'],
                                                })
                                            }
                                        />
                                    </label>
                                    <label className="robots-v2-field">
                                        <span>Таймфрейм</span>
                                        <Select
                                            className="robots-v2-select"
                                            value={draft.timeframe}
                                            searchable={false}
                                            options={['1m', '5m', '15m', '1h', '4h', '1d'].map(tf => ({
                                                value: tf,
                                                label: tf,
                                            }))}
                                            onChange={timeframe => patch({ timeframe })}
                                        />
                                    </label>
                                </div>
                            </div>
                            {draft.archetype === 'scalper' ? (
                                SCALPER_PARAM_GROUPS.map(group => {
                                    const fields = group.keys.filter(key => {
                                        const val = draft.strategyParams[key]
                                        return val != null && typeof val !== 'boolean'
                                    })
                                    if (!fields.length) return null
                                    return (
                                        <div key={group.title} className="robots-v2-form-group">
                                            <p className="robots-v2-param-group__title">{group.title}</p>
                                            <div className={`robots-v2-grid robots-v2-grid--${group.columns}`}>
                                                {fields.map(key => {
                                                    const val = draft.strategyParams[key]
                                                    if (val == null || typeof val === 'boolean') return null
                                                    return (
                                                        <StrategyParamField
                                                            key={key}
                                                            name={key}
                                                            value={val}
                                                            onChange={next => patch({
                                                                strategyParams: { ...draft.strategyParams, [key]: next },
                                                            })}
                                                        />
                                                    )
                                                })}
                                            </div>
                                        </div>
                                    )
                                })
                            ) : Object.keys(draft.strategyParams).length > 0 && (
                                <div className="robots-v2-form-group">
                                    <div className="robots-v2-grid robots-v2-grid--4">
                                        {Object.entries(draft.strategyParams).flatMap(([key, val]) => (
                                            typeof val === 'boolean' ? [] : [(
                                                <StrategyParamField
                                                    key={key}
                                                    name={key}
                                                    value={val}
                                                    onChange={next => patch({
                                                        strategyParams: { ...draft.strategyParams, [key]: next },
                                                    })}
                                                />
                                            )]
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {kind === 'trading' && step === 3 && (
                    <div className="robots-v2-form">
                        <div className="robots-v2-form-group">
                            <div className="robots-v2-grid robots-v2-grid--4">
                                <label className={`robots-v2-field ${draft.universeMode === 'fixed' ? 'robots-v2-span-all' : 'robots-v2-span-2'}`}>
                                    <span>Источник активов</span>
                                    <SegmentedControl
                                        className="robots-v2-segmented"
                                        aria-label="Источник активов"
                                        options={[...UNIVERSE_OPTIONS]}
                                        value={draft.universeMode}
                                        onChange={universeMode => patch({ universeMode })}
                                    />
                                </label>
                                {draft.universeMode === 'index' && (
                                    <label className="robots-v2-field robots-v2-span-2">
                                        <span>Индекс</span>
                                        <input
                                            className="robots-v2-input"
                                            value={draft.indexCode}
                                            onChange={e => patch({ indexCode: e.target.value.toUpperCase() })}
                                            placeholder="IMOEX"
                                        />
                                    </label>
                                )}
                                {draft.universeMode === 'screener' && (
                                    <label className="robots-v2-field robots-v2-span-2">
                                        <span>Пресет</span>
                                        <Select
                                            className="robots-v2-select"
                                            value={draft.screenerPreset}
                                            searchable={false}
                                            options={[
                                                { value: 'high_liquidity', label: 'Высокая ликвидность' },
                                                { value: 'volatile', label: 'Волатильные' },
                                                { value: 'low_price', label: 'Низкая цена' },
                                                { value: 'custom', label: 'Свой' },
                                            ]}
                                            onChange={value => {
                                                const screenerPreset = value as RobotV2WizardDraft['screenerPreset']
                                                if (screenerPreset === 'custom' && draft.screenerPreset !== 'custom') {
                                                    patch({
                                                        screenerPreset,
                                                        ...customScreenerFieldDefaults(draft.instrumentType),
                                                    })
                                                    return
                                                }
                                                patch({ screenerPreset })
                                            }}
                                        />
                                    </label>
                                )}
                            </div>
                            {draft.universeMode === 'fixed' && (
                                <label className="robots-v2-field">
                                    <span>Тикеры через запятую</span>
                                    <textarea
                                        className="robots-v2-input robots-v2-input--area"
                                        rows={3}
                                        value={draft.fixedList}
                                        onChange={e => patch({ fixedList: e.target.value })}
                                    />
                                </label>
                            )}
                        </div>
                        {draft.universeMode === 'screener' && draft.screenerPreset === 'custom' && (
                            <div className="robots-v2-form-group">
                                <p className="robots-v2-param-group__title">Свой отбор</p>
                                <ScreenerCustomFilters draft={draft} patch={patch} columns={3} />
                            </div>
                        )}
                        <div className="robots-v2-form-group">
                            <div className="robots-v2-grid robots-v2-grid--4 robots-v2-assets-actions">
                                <label className="robots-v2-field">
                                    <span>Макс. активов</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        min={1}
                                        max={200}
                                        value={draft.maxAssets}
                                        onChange={e => patch({ maxAssets: Number(e.target.value) })}
                                    />
                                </label>
                                <div className="robots-v2-toggle-row robots-v2-span-2">
                                    <span>Закрывать при исключении</span>
                                    <Toggle
                                        checked={draft.exitOnDrop}
                                        aria-label="Закрывать позицию при исключении актива"
                                        onChange={exitOnDrop => patch({ exitOnDrop })}
                                    />
                                </div>
                                <Button type="button" variant="secondary" loading={previewLoading} onClick={() => void runPreview(1)}>
                                    Превью состава
                                </Button>
                            </div>
                        {preview && (
                            <div className="robots-v2-preview">
                                <div className="robots-v2-preview__meta">
                                    Показано {preview.assets?.length ?? 0} из {preview.total}
                                </div>
                                <div className="robots-v2-preview__rows">
                                    {(preview.assets || []).map(a => (
                                        <div key={a.ticker} className="robots-v2-preview__row">
                                            <strong>{a.ticker}</strong>
                                            <span>{a.name || ''}</span>
                                            <em>{a.price != null ? a.price : ''}</em>
                                        </div>
                                    ))}
                                </div>
                                {preview.total > PREVIEW_PAGE_SIZE && (
                                    <div className="robots-v2-preview__pager">
                                        <Button
                                            type="button"
                                            size="sm"
                                            variant="ghost"
                                            disabled={previewPage <= 1 || previewLoading}
                                            onClick={() => void runPreview(previewPage - 1)}
                                        >
                                            Назад
                                        </Button>
                                        <span>
                                            {previewPage} / {Math.max(1, Math.ceil(preview.total / PREVIEW_PAGE_SIZE))}
                                        </span>
                                        <Button
                                            type="button"
                                            size="sm"
                                            variant="ghost"
                                            disabled={
                                                previewLoading
                                                || previewPage >= Math.ceil(preview.total / PREVIEW_PAGE_SIZE)
                                            }
                                            onClick={() => void runPreview(previewPage + 1)}
                                        >
                                            Далее
                                        </Button>
                                    </div>
                                )}
                                {preview.rejectedSample && preview.rejectedSample.length > 0 && (
                                    <div className="robots-v2-preview__rejected">
                                        <strong>Отклонено</strong>
                                        {preview.rejectedSample.map((row, i) => {
                                            const ticker = String(row.ticker ?? row.code ?? `#${i + 1}`)
                                            const reason = String(row.reason ?? row.message ?? row.detail ?? '—')
                                            return (
                                                <div key={`${ticker}-${i}`} className="robots-v2-preview__row">
                                                    <strong>{ticker}</strong>
                                                    <span>{reason}</span>
                                                </div>
                                            )
                                        })}
                                    </div>
                                )}
                            </div>
                        )}
                        </div>
                    </div>
                    )}

                    {kind === 'trading' && step === 4 && (
                    <div className="robots-v2-form">
                        <div className="robots-v2-form-group">
                            <p className="robots-v2-param-group__title">Размер</p>
                            <div className="robots-v2-grid robots-v2-grid--3">
                                <label className="robots-v2-field robots-v2-span-mobile">
                                    <span>{selectedBroker === 'bybit' ? 'Капитал (USDT)' : 'Капитал'}</span>
                                    {draft.mode === 'live' ? (
                                        <p className="robots-v2-hint">
                                            Берётся со счёта при синхронизации.
                                        </p>
                                    ) : (
                                        <input
                                            className="robots-v2-input"
                                            type="number"
                                            value={draft.capital}
                                            onChange={e => patch({ capital: Number(e.target.value) })}
                                        />
                                    )}
                                </label>
                                <label className="robots-v2-field">
                                    <span>Доля позиции, %</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        value={draft.maxPositionSharePct}
                                        onChange={e => patch({ maxPositionSharePct: Number(e.target.value) })}
                                    />
                                </label>
                                <label className="robots-v2-field">
                                    <span>Макс. позиций</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        min={1}
                                        max={10}
                                        value={draft.maxConcurrentPositions}
                                        onChange={e => patch({ maxConcurrentPositions: Number(e.target.value) })}
                                    />
                                </label>
                            </div>
                        </div>
                        <div className="robots-v2-form-group">
                            <p className="robots-v2-param-group__title">Выход</p>
                            <div className="robots-v2-grid robots-v2-grid--4">
                                <label className="robots-v2-field">
                                    <span>Stop-loss %</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        value={draft.stopLossPct}
                                        onChange={e => patch({ stopLossPct: Number(e.target.value) })}
                                    />
                                </label>
                                <label className="robots-v2-field">
                                    <span>Take-profit %</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        value={draft.takeProfitPct}
                                        onChange={e => patch({ takeProfitPct: Number(e.target.value) })}
                                    />
                                </label>
                                <label className="robots-v2-field">
                                    <span>Макс. дневной убыток</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        value={draft.maxDailyLoss}
                                        onChange={e => patch({ maxDailyLoss: Number(e.target.value) })}
                                    />
                                </label>
                                <label className="robots-v2-field">
                                    <span>Макс. просадка %</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        value={draft.maxDrawdownPct}
                                        onChange={e => patch({ maxDrawdownPct: Number(e.target.value) })}
                                    />
                                </label>
                            </div>
                        </div>
                        <div className="robots-v2-form-group">
                            <p className="robots-v2-param-group__title">Остановка</p>
                            <div className="robots-v2-grid robots-v2-grid--2">
                                <div className="robots-v2-field">
                                    <span>
                                        Закрытие сессии
                                        <FormLabelTooltip text={EOD_TOOLTIP} />
                                    </span>
                                    <SegmentedControl
                                        className="robots-v2-segmented"
                                        aria-label="Закрытие сессии"
                                        options={[...EOD_OPTIONS]}
                                        value={draft.eodFlattenEnabled ? 'on' : 'off'}
                                        onChange={value => patch({ eodFlattenEnabled: value === 'on' })}
                                    />
                                </div>
                                <label className="robots-v2-field">
                                    <span>Минут до закрытия</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        min={1}
                                        max={120}
                                        value={draft.eodMinutesBeforeClose}
                                        onChange={e => patch({ eodMinutesBeforeClose: Number(e.target.value) })}
                                    />
                                </label>
                            </div>
                        </div>
                        <div className="robots-v2-form-group">
                            <p className="robots-v2-param-group__title">Издержки</p>
                            <div className="robots-v2-grid robots-v2-grid--3">
                                <label className="robots-v2-field">
                                    <span>Комиссия %</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        step="0.01"
                                        value={draft.brokerCommissionPct}
                                        onChange={e => patch({ brokerCommissionPct: Number(e.target.value) })}
                                    />
                                </label>
                                <label className="robots-v2-field">
                                    <span>Налог %</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        value={draft.taxPct}
                                        onChange={e => patch({ taxPct: Number(e.target.value) })}
                                    />
                                </label>
                                <label className="robots-v2-field">
                                    <span>Slippage %</span>
                                    <input
                                        className="robots-v2-input"
                                        type="number"
                                        step="0.1"
                                        value={draft.slippagePct}
                                        onChange={e => patch({ slippagePct: Number(e.target.value) })}
                                    />
                                </label>
                            </div>
                        </div>
                    </div>
                    )}

                </Card>
                    <footer className="robots-v2-wizard-footer">
                        {step > 0 ? (
                            <Button
                                type="button"
                                variant="ghost"
                                onClick={() => setStep(s => Math.max(0, s - 1))}
                            >
                                Назад
                            </Button>
                        ) : (
                            <span />
                        )}
                        <div className="robots-v2-wizard-footer__right">
                            {step < lastStep ? (
                                <Button type="button" onClick={goNext}>Далее</Button>
                            ) : kind === 'portfolio' ? (
                                <Button type="button" loading={saving} onClick={() => void savePortfolioRobot()}>
                                    {editId
                                        ? (draft.portfolioEnabled && configComplete ? 'Сохранить и включить' : 'Сохранить')
                                        : (draft.portfolioEnabled && configComplete ? 'Создать и включить' : 'Создать')}
                                </Button>
                            ) : (
                                <>
                                    <Button
                                        type="button"
                                        variant="secondary"
                                        loading={saving}
                                        onClick={() => void saveRobot(false)}
                                    >
                                        {editId || persistedRobotId ? 'Сохранить' : 'Создать'}
                                    </Button>
                                    <Button
                                        type="button"
                                        loading={saving}
                                        disabled={!configComplete}
                                        title={configComplete ? undefined : 'Заполнение всех шагов нужно только для запуска'}
                                        onClick={() => void saveRobot(true)}
                                    >
                                        {persistedRobotId || editId ? 'Сохранить и запустить' : 'Создать и запустить'}
                                    </Button>
                                </>
                            )}
                        </div>
                    </footer>
                </div>
                </div>
            </div>
        </div>
    )
}
