import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { PageHero } from '@/components/ui/PageHero'
import { Skeleton } from '@/components/ui/Skeleton'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { Toggle } from '@/components/ui/Toggle'
import { WeekdaysMaskField } from '@/components/ui/WeekdaysMaskField'
import { api } from '@/services/api'
import { robotV2Service } from '@/services/robotV2Service'
import { brokerFromTokenType, brokerLabelFromToken } from '@/modules/robots/config/tokenBroker'
import { useToast } from '@/components/ui/Toast'
import {
    ARCHETYPE_CARDS,
    PORTFOLIO_DRAFT_STORAGE_KEY,
    archetypeDefaults,
    clearDraftLocal,
    configToDraft,
    configToPortfolioDraft,
    defaultWizardDraft,
    draftToPortfolioV4Config,
    draftToV4Config,
    loadDraftLocal,
    parseFixedList,
    saveDraftLocal,
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

const TRADING_STEPS = ['Основное', 'Стратегия', 'Активы', 'Риск'] as const
const PORTFOLIO_STEPS = ['Основное', 'Синхрон'] as const
const PREVIEW_PAGE_SIZE = 20
const GOAL_OPTIONS = [
    { value: 'conservative', label: 'Консервативный' },
    { value: 'moderate', label: 'Умеренный' },
    { value: 'aggressive', label: 'Агрессивный' },
] as const
const MODE_OPTIONS = [
    { value: 'paper', label: 'Paper' },
    { value: 'live', label: 'Live' },
] as const
const UNIVERSE_OPTIONS = [
    { value: 'fixed', label: 'Список' },
    { value: 'index', label: 'Индекс' },
    { value: 'screener', label: 'Скринер' },
] as const
const STOP_MODE_OPTIONS = [
    { value: 'soft', label: 'Мягкая остановка' },
    { value: 'hard', label: 'Жёсткая остановка' },
] as const
const EOD_OPTIONS = [
    { value: 'auto', label: 'Auto' },
    { value: 'on', label: 'Включён' },
    { value: 'off', label: 'Выключен' },
] as const

function weekdaysToMask(days: boolean[]): number {
    return days.reduce((mask, selected, index) => selected ? mask | (1 << index) : mask, 0)
}

function maskToWeekdays(mask: number): boolean[] {
    return Array.from({ length: 7 }, (_, index) => Boolean(mask & (1 << index)))
}

const STEP_COPY = {
    trading: [
        ['Основа робота', 'Выберите назначение, понятное имя и брокерский аккаунт.'],
        ['Торговая логика', 'Настройте стиль торговли, стратегию и расписание запуска.'],
        ['Торговая вселенная', 'Определите инструменты, которые робот сможет анализировать.'],
        ['Защита капитала', 'Задайте лимиты позиции, убытка и правила остановки.'],
    ],
    portfolio: [
        ['Источник портфеля', 'Выберите аккаунт, из которого GIN будет получать позиции.'],
        ['Расписание синхронизации', 'Укажите, когда и как часто обновлять данные портфеля.'],
    ],
} as const

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

function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    return err?.message || 'Ошибка'
}

export default function RobotV2WizardPage() {
    const navigate = useNavigate()
    const { id: editIdParam } = useParams()
    const [search] = useSearchParams()
    const editId = editIdParam ? Number(editIdParam) : null
    const toast = useToast()
    const kindFromUrl = search.get('kind') === 'portfolio' ? 'portfolio' : 'trading'

    const [kind, setKind] = useState<'trading' | 'portfolio'>(kindFromUrl)
    const [step, setStep] = useState(0)
    const [draft, setDraft] = useState<RobotV2WizardDraft>(defaultWizardDraft)
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
    }, [editId, kindFromUrl])

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
                        setDraft(configToDraft(robot.config, robot.name, robot.tokenId))
                    }
                } catch (e) {
                    toast.show(fmtErr(e), 'error')
                } finally {
                    setEditLoading(false)
                }
            })()
            return
        }
        const storageKey = kindFromUrl === 'portfolio' ? PORTFOLIO_DRAFT_STORAGE_KEY : undefined
        if (search.get('restore') === '0') {
            clearDraftLocal(storageKey)
            setDraft(defaultWizardDraft())
            return
        }
        const local = loadDraftLocal(storageKey)
        if (local && !search.get('fresh')) {
            const ok = window.confirm('Есть несохранённый черновик. Восстановить?')
            if (ok) setDraft(local)
            else {
                clearDraftLocal(storageKey)
                setDraft(defaultWizardDraft())
            }
        } else {
            setDraft(defaultWizardDraft())
        }
    }, [editId, kindFromUrl]) // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        if (editId) return
        const key = kind === 'portfolio' ? PORTFOLIO_DRAFT_STORAGE_KEY : undefined
        const t = window.setTimeout(() => saveDraftLocal(draft, key), 500)
        return () => window.clearTimeout(t)
    }, [draft, editId, kind])

    const selectedBroker = useMemo(() => {
        if (!draft.tokenId) return null
        return brokerFromTokenType(tokens.find(t => t.id === draft.tokenId)?.token_type)
    }, [draft.tokenId, tokens])

    const patch = (partial: Partial<RobotV2WizardDraft>) => {
        setDraft(prev => ({ ...prev, ...partial }))
        setFieldErrors([])
    }

    const steps = kind === 'portfolio' ? PORTFOLIO_STEPS : TRADING_STEPS
    const lastStep = steps.length - 1
    const stepCopy = STEP_COPY[kind][step]
    const selectedToken = tokens.find(token => token.id === draft.tokenId)
    const selectedArchetype = archetypeCards.find(card => card.id === draft.archetype)

    const validateStep = (s: number): string[] => {
        const errs: string[] = []
        if (s === 0) {
            if (!draft.name.trim()) errs.push('Укажите название')
            if (!draft.tokenId) errs.push('Выберите API-ключ')
        }
        if (kind === 'trading') {
            if (s === 1) {
                if (!draft.weekdays.some(Boolean)) errs.push('Выберите хотя бы один день')
                if (draft.timeFrom >= draft.timeTo) errs.push('timeFrom должен быть раньше timeTo')
                if (!draft.archetype) errs.push('Выберите архетип')
                if (draft.archetype === 'scalper' && !draft.advancedMode) errs.push('Scalper требует advanced mode')
            }
            if (s === 2) {
                if (draft.universeMode === 'fixed' && parseFixedList(draft.fixedList).length === 0) {
                    errs.push('Укажите хотя бы один тикер')
                }
                if (draft.universeMode === 'index' && !draft.indexCode.trim()) errs.push('Укажите индекс')
            }
            if (s === 3) {
                if (draft.mode === 'paper' && draft.capital <= 0) errs.push('Капитал должен быть > 0')
                if (draft.stopLossPct >= draft.takeProfitPct) errs.push('SL должен быть меньше TP')
            }
        } else if (s === 1) {
            if (!draft.weekdays.some(Boolean)) errs.push('Выберите хотя бы один день')
            if (draft.timeFrom >= draft.timeTo) errs.push('timeFrom должен быть раньше timeTo')
        }
        return errs
    }

    const goNext = () => {
        const errs = validateStep(step)
        setFieldErrors(errs)
        if (errs.length) {
            toast.show(errs.join('; '), 'error')
            return
        }
        setStep(s => Math.min(lastStep, s + 1))
    }

    const goToStep = (target: number) => {
        if (target === step) return
        if (target < step) {
            setFieldErrors([])
            setStep(target)
            return
        }
        const errs: string[] = []
        for (let s = 0; s < target; s++) {
            errs.push(...validateStep(s))
        }
        setFieldErrors(errs)
        if (errs.length) {
            toast.show(errs.join('; '), 'error')
            return
        }
        setFieldErrors([])
        setStep(target)
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
        const errs = steps.flatMap((_, index) => validateStep(index))
        setFieldErrors(errs)
        if (errs.length) {
            toast.show(errs.join('; '), 'error')
            return
        }
        if (!draft.tokenId || !draft.archetype) return
        setSaving(true)
        try {
            const config = draftToV4Config(draft)
            const validated = await robotV2Service.validate({ type: 2, config })
            if (!validated.valid) {
                toast.show(validated.errors.map(e => e.message).join('; ') || 'Конфиг невалиден', 'error')
                return
            }
            const robot = await robotV2Service.createOrUpdate({
                id: editId || persistedRobotId || undefined,
                name: draft.name.trim(),
                type: 2,
                tokenId: draft.tokenId,
                config,
            })
            setPersistedRobotId(robot.id)
            clearDraftLocal()
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
                navigate(`/robots-v2/${robot.id}/monitor`)
            } else {
                toast.show(editId ? 'Робот сохранён' : 'Робот создан', 'success')
                navigate('/robots-v2')
            }
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setSaving(false)
        }
    }

    const savePortfolioRobot = async () => {
        const errs = steps.flatMap((_, index) => validateStep(index))
        setFieldErrors(errs)
        if (errs.length) {
            toast.show(errs.join('; '), 'error')
            return
        }
        if (!draft.tokenId) return
        setSaving(true)
        try {
            const config = draftToPortfolioV4Config(draft)
            const validated = await robotV2Service.validate({ type: 1, config })
            if (!validated.valid) {
                toast.show(validated.errors.map(e => e.message).join('; ') || 'Конфиг невалиден', 'error')
                return
            }
            await robotV2Service.createOrUpdate({
                id: editId || undefined,
                name: draft.name.trim(),
                type: 1,
                tokenId: draft.tokenId,
                config,
                status: draft.portfolioEnabled ? 1 : 2,
            })
            clearDraftLocal(PORTFOLIO_DRAFT_STORAGE_KEY)
            toast.show(editId ? 'Опросник сохранён' : 'Опросник создан', 'success')
            navigate('/robots-v2')
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setSaving(false)
        }
    }

    const notional = draft.mode === 'live'
        ? null
        : (draft.capital * draft.maxPositionSharePct) / 100
    const rr = draft.stopLossPct > 0 ? draft.takeProfitPct / draft.stopLossPct : 0

    if (editId && editLoading) {
        return (
            <div className="page" data-page="robots-v2">
                <PageHero
                    eyebrow="SETUP NODE"
                    title={`ПРАВКА #${editId}`}
                    subtitle="Загружаем конфигурацию робота…"
                />
                <div className="dashboard-layout">
                    <Card className="dashboard-totals-card robots-v2-wizard-card" aria-busy="true">
                        <Skeleton width="35%" height="24px" borderRadius="6px" />
                        <div style={{ marginTop: 'var(--space-4)' }}>
                            <Skeleton width="100%" height="280px" borderRadius="10px" />
                        </div>
                    </Card>
                </div>
            </div>
        )
    }

    return (
        <div className="page" data-page="robots-v2">
            <PageHero
                eyebrow="SETUP NODE"
                title={editId ? `ПРАВКА #${editId}` : kind === 'portfolio' ? 'НОВЫЙ ОПРОСНИК' : 'НОВЫЙ РОБОТ'}
                subtitle={
                    kind === 'portfolio'
                        ? 'Мастер · основное → синхронизация портфеля'
                        : 'Мастер · основное → стратегия → активы → риск'
                }
                actions={
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="dashboard-hero__cfg"
                        onClick={() => navigate('/robots-v2')}
                    >
                        Флот
                    </Button>
                }
            />

            <div className="dashboard-layout">
                <div className="robots-v2-wizard-shell">
                    <nav className="robots-v2-steps" aria-label="Шаги мастера">
                        {steps.map((label, i) => (
                            <button
                                key={label}
                                type="button"
                                className={[
                                    'robots-v2-steps__item',
                                    i === step ? 'robots-v2-steps__item--active' : '',
                                    i < step ? 'robots-v2-steps__item--done' : '',
                                ].filter(Boolean).join(' ')}
                                aria-current={i === step ? 'step' : undefined}
                                onClick={() => goToStep(i)}
                            >
                                <span className="robots-v2-steps__num">{i < step ? '✓' : i + 1}</span>
                                <span className="robots-v2-steps__label">
                                    <small>Шаг {i + 1}</small>
                                    <strong>{label}</strong>
                                </span>
                            </button>
                        ))}
                    </nav>

                    {fieldErrors.length > 0 && (
                        <div className="robots-v2-banner robots-v2-banner--error" role="alert">
                            <strong>Проверьте настройки</strong>
                            <span>{fieldErrors.join(' · ')}</span>
                        </div>
                    )}

                    <main className="robots-v2-wizard-main">
                        <Card className="dashboard-totals-card robots-v2-wizard-card">
                            <header className="robots-v2-wizard-card__head">
                                <span className="robots-v2-wizard-card__eyebrow">
                                    {kind === 'portfolio' ? 'СИНХРОНИЗАЦИЯ' : 'ТОРГОВЫЙ РОБОТ'} · {step + 1}/{steps.length}
                                </span>
                                <h2>{stepCopy[0]}</h2>
                                <p>{stepCopy[1]}</p>
                            </header>
                    {step === 0 && (
                        <div className="robots-v2-form">
                            <div className="robots-v2-field">
                                <span>Что нужно автоматизировать?</span>
                                <div className="robots-v2-type-grid">
                                    <button
                                        type="button"
                                        className={`robots-v2-type-card ${kind === 'trading' ? 'robots-v2-type-card--on' : ''}`}
                                        aria-pressed={kind === 'trading'}
                                        disabled={Boolean(editId)}
                                        onClick={() => setKind('trading')}
                                    >
                                        <span className="robots-v2-type-card__icon" aria-hidden>↗</span>
                                        <strong>Торговый робот</strong>
                                        <small>Ищет сигналы, открывает позиции и контролирует риск.</small>
                                    </button>
                                    <button
                                        type="button"
                                        className={`robots-v2-type-card ${kind === 'portfolio' ? 'robots-v2-type-card--on' : ''}`}
                                        aria-pressed={kind === 'portfolio'}
                                        disabled={Boolean(editId)}
                                        onClick={() => {
                                            patch({ portfolioEnabled: true })
                                            setKind('portfolio')
                                        }}
                                    >
                                        <span className="robots-v2-type-card__icon" aria-hidden>↻</span>
                                        <strong>Синхронизация портфеля</strong>
                                        <small>Переносит позиции и операции брокера в GIN.</small>
                                    </button>
                                </div>
                            </div>
                            <label className="robots-v2-field">
                                <span>Название <small>Будет видно в списке и уведомлениях</small></span>
                                <input
                                    className="robots-v2-input"
                                    value={draft.name}
                                    maxLength={50}
                                    onChange={e => patch({ name: e.target.value })}
                                    placeholder={kind === 'portfolio' ? 'Portfolio sync' : 'MOEX Momentum Paper'}
                                />
                            </label>
                            <label className="robots-v2-field">
                                <span>
                                    Брокерский аккаунт
                                    <FormLabelTooltip text="API-ключ определяет брокера, доступные инструменты и счёт для операций." />
                                    <small>Ключи настраиваются в разделе профиля</small>
                                </span>
                                <Select
                                    className="robots-v2-select"
                                    value={draft.tokenId}
                                    placeholder="Выберите аккаунт…"
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
                                {selectedBroker && (
                                    <small className="robots-v2-hint">
                                        Брокер: {selectedBroker}
                                        {kind === 'trading' ? ' (read-only из токена)' : ''}
                                    </small>
                                )}
                            </label>
                        </div>
                    )}

                    {kind === 'portfolio' && step === 1 && (
                        <div className="robots-v2-form">
                            <p className="robots-v2-hint">
                                Опросник читает позиции и операции брокера по расписанию и обновляет портфель в GIN.
                            </p>
                            <Toggle
                                checked={draft.portfolioEnabled}
                                onChange={portfolioEnabled => patch({ portfolioEnabled })}
                                label={draft.portfolioEnabled ? 'Синхронизация включена' : 'Синхронизация выключена'}
                            />
                            <div className="robots-v2-field">
                                <WeekdaysMaskField
                                    value={weekdaysToMask(draft.weekdays)}
                                    onChange={mask => patch({ weekdays: maskToWeekdays(mask) })}
                                />
                                <div className="robots-v2-schedule-grid">
                                    <label className="robots-v2-field">
                                        <span>Начало</span>
                                        <input
                                            className="robots-v2-input"
                                            type="time"
                                            value={draft.timeFrom}
                                            onChange={e => patch({ timeFrom: e.target.value })}
                                        />
                                    </label>
                                    <label className="robots-v2-field">
                                        <span>Окончание</span>
                                        <input
                                            className="robots-v2-input"
                                            type="time"
                                            value={draft.timeTo}
                                            onChange={e => patch({ timeTo: e.target.value })}
                                        />
                                    </label>
                                    <label className="robots-v2-field">
                                        <span>Частота опроса</span>
                                        <Select
                                            className="robots-v2-select"
                                            value={draft.pollInterval}
                                            searchable={false}
                                            options={[
                                                { value: '1m', label: 'Каждую минуту' },
                                                { value: '5m', label: 'Каждые 5 минут' },
                                                { value: '15m', label: 'Каждые 15 минут' },
                                                { value: '1h', label: 'Каждый час' },
                                            ]}
                                            onChange={value => patch({
                                                pollInterval: value as RobotV2WizardDraft['pollInterval'],
                                            })}
                                        />
                                    </label>
                                </div>
                            </div>
                        </div>
                    )}

                    {kind === 'trading' && step === 1 && (
                        <div className="robots-v2-form">
                            <label className="robots-v2-field">
                                <span>Цель</span>
                                <SegmentedControl
                                    className="robots-v2-segmented"
                                    aria-label="Цель стратегии"
                                    options={[...GOAL_OPTIONS]}
                                    value={draft.goal}
                                    onChange={goal => patch({ goal })}
                                />
                            </label>
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
                                {selectedBroker === 'bybit' && (
                                    <small className="robots-v2-hint">
                                        Paper short разрешён. EOD flatten выключен для crypto.
                                    </small>
                                )}
                            </label>
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
                            <div className="robots-v2-params">
                                {Object.entries(draft.strategyParams).map(([key, val]) => (
                                    <label key={key} className="robots-v2-field">
                                        <span>{key}</span>
                                        <input
                                            className="robots-v2-input"
                                            type={typeof val === 'number' ? 'number' : 'text'}
                                            value={String(val)}
                                            onChange={e => {
                                                const raw = e.target.value
                                                const next = typeof val === 'number' ? Number(raw) : raw
                                                patch({ strategyParams: { ...draft.strategyParams, [key]: next } })
                                            }}
                                        />
                                    </label>
                                ))}
                            </div>
                            {draft.archetype === 'scalper' && (
                                <Toggle
                                    checked={draft.advancedMode}
                                    onChange={advancedMode => patch({ advancedMode })}
                                    label="Advanced mode (обязателен для scalper)"
                                />
                            )}
                            <label className="robots-v2-field">
                                <span>
                                    Режим
                                    <FormLabelTooltip text="Paper симулирует сделки. Live отправляет реальные заявки брокеру." />
                                </span>
                                <SegmentedControl
                                    className="robots-v2-segmented"
                                    aria-label="Режим торговли"
                                    options={[...MODE_OPTIONS]}
                                    value={draft.mode}
                                    onChange={mode => patch({ mode })}
                                />
                                <small className="robots-v2-hint">
                                    Бэктест на исторических свечах запускается с карточки робота после сохранения.
                                </small>
                            </label>
                            <div className="robots-v2-field">
                                <WeekdaysMaskField
                                    value={weekdaysToMask(draft.weekdays)}
                                    onChange={mask => patch({ weekdays: maskToWeekdays(mask) })}
                                />
                                <div className="robots-v2-schedule-grid">
                                    <label className="robots-v2-field">
                                        <span>Начало</span>
                                        <input
                                            className="robots-v2-input"
                                            type="time"
                                            value={draft.timeFrom}
                                            onChange={e => patch({ timeFrom: e.target.value })}
                                        />
                                    </label>
                                    <label className="robots-v2-field">
                                        <span>Окончание</span>
                                        <input
                                            className="robots-v2-input"
                                            type="time"
                                            value={draft.timeTo}
                                            onChange={e => patch({ timeTo: e.target.value })}
                                        />
                                    </label>
                                    <label className="robots-v2-field">
                                        <span>Частота проверки</span>
                                        <Select
                                            className="robots-v2-select"
                                            value={draft.pollInterval}
                                            searchable={false}
                                            options={[
                                                { value: '1m', label: 'Каждую минуту' },
                                                { value: '5m', label: 'Каждые 5 минут' },
                                                { value: '15m', label: 'Каждые 15 минут' },
                                                { value: '1h', label: 'Каждый час' },
                                            ]}
                                            onChange={value => patch({
                                                pollInterval: value as RobotV2WizardDraft['pollInterval'],
                                            })}
                                        />
                                    </label>
                                </div>
                            </div>
                        </div>
                    )}

                    {kind === 'trading' && step === 2 && (
                    <div className="robots-v2-form">
                        <SegmentedControl
                            className="robots-v2-segmented"
                            aria-label="Источник активов"
                            options={[...UNIVERSE_OPTIONS]}
                            value={draft.universeMode}
                            onChange={universeMode => patch({ universeMode })}
                        />
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
                        {draft.universeMode === 'index' && (
                            <label className="robots-v2-field">
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
                            <label className="robots-v2-field">
                                <span>Пресет</span>
                                <Select
                                    className="robots-v2-select"
                                    value={draft.screenerPreset}
                                    searchable={false}
                                    options={[
                                        { value: 'high_liquidity', label: 'Высокая ликвидность' },
                                        { value: 'volatile', label: 'Волатильные' },
                                        { value: 'low_price', label: 'Низкая цена' },
                                        { value: 'custom', label: 'Custom' },
                                    ]}
                                    onChange={value =>
                                        patch({ screenerPreset: value as RobotV2WizardDraft['screenerPreset'] })
                                    }
                                />
                            </label>
                        )}
                        <div className="robots-v2-inline">
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
                            <Toggle
                                checked={draft.exitOnDrop}
                                onChange={exitOnDrop => patch({ exitOnDrop })}
                                label="Закрывать позицию при исключении актива"
                            />
                        </div>
                        <Button type="button" variant="secondary" loading={previewLoading} onClick={() => void runPreview(1)}>
                            Превью состава
                        </Button>
                        {preview && (
                            <div className="robots-v2-preview">
                                <div className="robots-v2-preview__meta">
                                    Страница {preview.page ?? previewPage} · показано {preview.assets?.length ?? 0} из {preview.total}
                                </div>
                                <ul className="robots-v2-preview__list">
                                    {(preview.assets || []).map(a => (
                                        <li key={a.ticker}>
                                            <strong>{a.ticker}</strong>
                                            {a.name ? ` — ${a.name}` : ''}
                                            {a.price != null ? ` · ${a.price}` : ''}
                                        </li>
                                    ))}
                                </ul>
                                {preview.total > PREVIEW_PAGE_SIZE && (
                                    <div className="robots-v2-inline" style={{ marginTop: 'var(--space-2)' }}>
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
                                    <div className="robots-v2-preview__rejected" style={{ marginTop: 'var(--space-3)' }}>
                                        <strong>Отклонено (пример):</strong>
                                        <ul className="robots-v2-preview__list">
                                            {preview.rejectedSample.map((row, i) => {
                                                const ticker = String(row.ticker ?? row.code ?? `#${i + 1}`)
                                                const reason = String(row.reason ?? row.message ?? row.detail ?? '—')
                                                return (
                                                    <li key={`${ticker}-${i}`}>
                                                        <strong>{ticker}</strong> — {reason}
                                                    </li>
                                                )
                                            })}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                    )}

                    {kind === 'trading' && step === 3 && (
                    <div className="robots-v2-form robots-v2-form--risk">
                        <label className="robots-v2-field">
                            <span>{selectedBroker === 'bybit' ? 'Капитал (USDT)' : 'Капитал'}</span>
                            {draft.mode === 'live' ? (
                                <p className="robots-v2-hint">
                                    В live капитал берётся со счёта брокера при синхронизации (не эмулируется).
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
                            <small className="robots-v2-hint">
                                {notional == null
                                    ? 'Нотионал = доля % от equity счёта'
                                    : `≈ ${notional.toLocaleString('ru-RU')} на сделку`}
                            </small>
                        </label>
                        <div className="robots-v2-inline">
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
                        </div>
                        <small className="robots-v2-hint">Risk/Reward ≈ {rr.toFixed(2)}</small>
                        <div className="robots-v2-inline">
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
                        <label className="robots-v2-field">
                            <span>
                                Режим остановки
                                <FormLabelTooltip text="Мягкая остановка не открывает новые позиции. Жёсткая также закрывает текущие." />
                            </span>
                            <SegmentedControl
                                className="robots-v2-segmented"
                                aria-label="Режим остановки"
                                options={[...STOP_MODE_OPTIONS]}
                                value={draft.stopMode}
                                onChange={stopMode => patch({ stopMode })}
                            />
                        </label>
                        <div className="robots-v2-field">
                            <span>
                                Закрытие позиций к концу сессии
                                <FormLabelTooltip text="Auto включает закрытие для акций MOEX и выключает его для круглосуточных рынков." />
                            </span>
                            <SegmentedControl
                                className="robots-v2-segmented"
                                aria-label="Закрытие позиций к концу сессии"
                                options={[...EOD_OPTIONS]}
                                value={draft.eodFlattenEnabled === null ? 'auto' : draft.eodFlattenEnabled ? 'on' : 'off'}
                                onChange={value => patch({
                                    eodFlattenEnabled: value === 'auto' ? null : value === 'on',
                                })}
                            />
                            <label className="robots-v2-field">
                                <span>За сколько минут до закрытия</span>
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
                        <details className="robots-v2-advanced">
                            <summary>Расширенные: комиссия / налог / slippage</summary>
                            <div className="robots-v2-inline">
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
                        </details>
                    </div>
                    )}
                        </Card>

                        <footer className="robots-v2-wizard-footer">
                            <Button type="button" variant="ghost" disabled={step === 0} onClick={() => setStep(s => Math.max(0, s - 1))}>
                                ← Назад
                            </Button>
                            <span className="robots-v2-wizard-footer__save">Черновик сохраняется автоматически</span>
                            <div className="robots-v2-wizard-footer__right">
                                {step < lastStep ? (
                                    <Button type="button" onClick={goNext}>Продолжить →</Button>
                                ) : kind === 'portfolio' ? (
                                    <Button type="button" loading={saving} onClick={() => void savePortfolioRobot()}>
                                        {editId ? 'Сохранить' : 'Создать синхронизацию'}
                                    </Button>
                                ) : (
                                    <>
                                        <Button type="button" variant="secondary" loading={saving} onClick={() => void saveRobot(false)}>
                                            Сохранить без запуска
                                        </Button>
                                        <Button type="button" loading={saving} onClick={() => void saveRobot(true)}>
                                            {persistedRobotId ? 'Сохранить и запустить' : 'Создать и запустить'}
                                        </Button>
                                    </>
                                )}
                            </div>
                        </footer>
                    </main>

                    <aside className="robots-v2-wizard-summary" aria-label="Сводка настроек">
                        <div className="robots-v2-wizard-summary__head">
                            <span>Сводка</span>
                            <strong>{draft.name.trim() || 'Новый робот'}</strong>
                        </div>
                        <dl>
                            <div>
                                <dt>Тип</dt>
                                <dd>{kind === 'portfolio' ? 'Синхронизация' : 'Торговля'}</dd>
                            </div>
                            <div>
                                <dt>Аккаунт</dt>
                                <dd>{selectedToken?.name || (draft.tokenId ? `Ключ #${draft.tokenId}` : 'Не выбран')}</dd>
                            </div>
                            {kind === 'trading' && (
                                <>
                                    <div>
                                        <dt>Стратегия</dt>
                                        <dd>{selectedArchetype?.title || 'Не выбрана'}</dd>
                                    </div>
                                    <div>
                                        <dt>Режим</dt>
                                        <dd className={draft.mode === 'live' ? 'color-down' : 'color-up'}>
                                            {draft.mode === 'live' ? 'Live · реальные средства' : 'Paper · симуляция'}
                                        </dd>
                                    </div>
                                    <div>
                                        <dt>Активы</dt>
                                        <dd>
                                            {draft.universeMode === 'fixed'
                                                ? `${parseFixedList(draft.fixedList).length} в списке`
                                                : draft.universeMode === 'index'
                                                    ? draft.indexCode || 'Индекс не выбран'
                                                    : `Скринер · до ${draft.maxAssets}`}
                                        </dd>
                                    </div>
                                    <div>
                                        <dt>Риск на позицию</dt>
                                        <dd>{draft.maxPositionSharePct}% капитала</dd>
                                    </div>
                                </>
                            )}
                        </dl>
                        <div className="robots-v2-wizard-summary__tip">
                            <span aria-hidden>i</span>
                            Настройки можно изменить после создания.
                        </div>
                    </aside>
                </div>
            </div>
        </div>
    )
}
