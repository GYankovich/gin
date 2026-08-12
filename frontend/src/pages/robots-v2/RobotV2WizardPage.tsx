import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { api } from '@/services/api'
import { robotV2Service } from '@/services/robotV2Service'
import { brokerFromTokenType, brokerLabelFromToken } from '@/modules/robots/config/tokenBroker'
import { useToast } from '@/components/ui/Toast'
import {
    ARCHETYPE_CARDS,
    WEEKDAY_LABELS,
    archetypeDefaults,
    clearDraftLocal,
    configToDraft,
    defaultWizardDraft,
    draftToV4Config,
    loadDraftLocal,
    parseFixedList,
    saveDraftLocal,
    type RobotV2WizardDraft,
    type WizardArchetype,
} from '@/pages/robots-v2/wizardDraft'
import type { UniversePreview } from '@/types/robotV2'

type ApiToken = {
    id: number
    name?: string
    broker_type?: string | null
    token_type?: { type?: number; typeName?: string }
}

const STEPS = ['Цель', 'Стратегия', 'Активы', 'Риск'] as const

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

    const [step, setStep] = useState(0)
    const [draft, setDraft] = useState<RobotV2WizardDraft>(defaultWizardDraft)
    const [tokens, setTokens] = useState<ApiToken[]>([])
    const [saving, setSaving] = useState(false)
    const [preview, setPreview] = useState<UniversePreview | null>(null)
    const [previewLoading, setPreviewLoading] = useState(false)
    const [fieldErrors, setFieldErrors] = useState<string[]>([])

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
        if (editId) {
            void (async () => {
                try {
                    const robot = await robotV2Service.getById(editId)
                    setDraft(configToDraft(robot.config, robot.name, robot.tokenId))
                } catch (e) {
                    toast.show(fmtErr(e), 'error')
                }
            })()
            return
        }
        if (search.get('restore') === '0') {
            clearDraftLocal()
            setDraft(defaultWizardDraft())
            return
        }
        const local = loadDraftLocal()
        if (local && !search.get('fresh')) {
            const ok = window.confirm('Есть несохранённый черновик. Восстановить?')
            if (ok) setDraft(local)
            else clearDraftLocal()
        }
    }, [editId]) // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        if (editId) return
        const t = window.setTimeout(() => saveDraftLocal(draft), 500)
        return () => window.clearTimeout(t)
    }, [draft, editId])

    const selectedBroker = useMemo(() => {
        if (!draft.tokenId) return null
        return brokerFromTokenType(tokens.find(t => t.id === draft.tokenId)?.token_type)
    }, [draft.tokenId, tokens])

    const patch = (partial: Partial<RobotV2WizardDraft>) => setDraft(prev => ({ ...prev, ...partial }))

    const validateStep = (s: number): string[] => {
        const errs: string[] = []
        if (s === 0) {
            if (!draft.name.trim()) errs.push('Укажите название')
            if (!draft.tokenId) errs.push('Выберите API-ключ')
            if (!draft.weekdays.some(Boolean)) errs.push('Выберите хотя бы один день')
            if (draft.timeFrom >= draft.timeTo) errs.push('timeFrom должен быть раньше timeTo')
        }
        if (s === 1) {
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
            if (draft.capital <= 0) errs.push('Капитал должен быть > 0')
            if (draft.stopLossPct >= draft.takeProfitPct) errs.push('SL должен быть меньше TP')
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
        setStep(s => Math.min(3, s + 1))
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

    const runPreview = async () => {
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
                page: 1,
                pageSize: 20,
            })
            setPreview(data)
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setPreviewLoading(false)
        }
    }

    const saveRobot = async (andStart: boolean) => {
        const errs = [...validateStep(0), ...validateStep(1), ...validateStep(2), ...validateStep(3)]
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
                id: editId || undefined,
                name: draft.name.trim(),
                type: 2,
                tokenId: draft.tokenId,
                config,
            })
            clearDraftLocal()
            if (andStart) {
                await robotV2Service.start(robot.id, { virtualCapital: draft.capital })
                toast.show('Робот создан и запущен (paper)', 'success')
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

    const notional = (draft.capital * draft.maxPositionSharePct) / 100
    const rr = draft.stopLossPct > 0 ? draft.takeProfitPct / draft.stopLossPct : 0

    return (
        <div className="robots-v2-page" data-page="robots-v2">
            <header className="robots-v2-page__header">
                <div>
                    <button type="button" className="robots-v2-linkish" onClick={() => navigate('/robots-v2')}>
                        ← Флот v2
                    </button>
                    <h1 className="robots-v2-page__title">{editId ? `Редактирование #${editId}` : 'Новый торговый робот'}</h1>
                    <p className="robots-v2-page__subtitle">Мастер: цель → стратегия → активы → риск</p>
                </div>
            </header>

            <nav className="robots-v2-steps" aria-label="Шаги мастера">
                {STEPS.map((label, i) => (
                    <button
                        key={label}
                        type="button"
                        className={[
                            'robots-v2-steps__item',
                            i === step ? 'robots-v2-steps__item--active' : '',
                            i < step ? 'robots-v2-steps__item--done' : '',
                        ].filter(Boolean).join(' ')}
                        onClick={() => setStep(i)}
                    >
                        <span className="robots-v2-steps__num">{i + 1}</span>
                        {label}
                    </button>
                ))}
            </nav>

            {fieldErrors.length > 0 && (
                <div className="robots-v2-banner robots-v2-banner--error">{fieldErrors.join(' · ')}</div>
            )}

            <Card className="robots-v2-wizard-card">
                {step === 0 && (
                    <div className="robots-v2-form">
                        <label className="robots-v2-field">
                            <span>Цель</span>
                            <div className="robots-v2-chip-row">
                                {(['conservative', 'moderate', 'aggressive'] as const).map(g => (
                                    <button
                                        key={g}
                                        type="button"
                                        className={`robots-v2-chip ${draft.goal === g ? 'robots-v2-chip--on' : ''}`}
                                        onClick={() => patch({ goal: g })}
                                    >
                                        {g === 'conservative' ? 'Консервативный' : g === 'moderate' ? 'Умеренный' : 'Агрессивный'}
                                    </button>
                                ))}
                            </div>
                        </label>
                        <label className="robots-v2-field">
                            <span>Название</span>
                            <input
                                className="robots-v2-input"
                                value={draft.name}
                                maxLength={50}
                                onChange={e => patch({ name: e.target.value })}
                                placeholder="MOEX Momentum Paper"
                            />
                        </label>
                        <label className="robots-v2-field">
                            <span>API-ключ</span>
                            <select
                                className="robots-v2-input"
                                value={draft.tokenId ?? ''}
                                onChange={e => {
                                    const id = Number(e.target.value) || null
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
                            >
                                <option value="">Выберите токен…</option>
                                {tokens.map(t => (
                                    <option key={t.id} value={t.id}>
                                        {t.name || `Token #${t.id}`} — {brokerLabelFromToken(t.id, tokens)}
                                    </option>
                                ))}
                            </select>
                            {selectedBroker && (
                                <small className="robots-v2-hint">Брокер: {selectedBroker} (read-only из токена)</small>
                            )}
                        </label>
                        <label className="robots-v2-field">
                            <span>Тип инструмента</span>
                            <select
                                className="robots-v2-input"
                                value={draft.instrumentType}
                                onChange={e =>
                                    patch({
                                        instrumentType: e.target.value as RobotV2WizardDraft['instrumentType'],
                                    })
                                }
                            >
                                {selectedBroker === 'bybit' ? (
                                    <>
                                        <option value="perpetual">Perpetual (USDT linear)</option>
                                        <option value="coin_futures">Coin futures (inverse)</option>
                                    </>
                                ) : (
                                    <>
                                        <option value="stock">Акции</option>
                                        <option value="futures">Фьючерсы</option>
                                    </>
                                )}
                            </select>
                            {selectedBroker === 'bybit' && (
                                <small className="robots-v2-hint">
                                    Paper short разрешён. EOD flatten выключен для crypto.
                                </small>
                            )}
                        </label>
                        <label className="robots-v2-field">
                            <span>Режим</span>
                            <div className="robots-v2-chip-row">
                                <button
                                    type="button"
                                    className={`robots-v2-chip ${draft.mode === 'paper' ? 'robots-v2-chip--on' : ''}`}
                                    onClick={() => patch({ mode: 'paper' })}
                                >
                                    Paper
                                </button>
                                <button
                                    type="button"
                                    className={`robots-v2-chip ${draft.mode === 'live' ? 'robots-v2-chip--on' : ''}`}
                                    onClick={() => patch({ mode: 'live' })}
                                >
                                    Live
                                </button>
                            </div>
                        </label>
                        <div className="robots-v2-field">
                            <span>Расписание</span>
                            <div className="robots-v2-chip-row">
                                {WEEKDAY_LABELS.map((d, i) => (
                                    <button
                                        key={d}
                                        type="button"
                                        className={`robots-v2-chip ${draft.weekdays[i] ? 'robots-v2-chip--on' : ''}`}
                                        onClick={() => {
                                            const weekdays = [...draft.weekdays]
                                            weekdays[i] = !weekdays[i]
                                            patch({ weekdays })
                                        }}
                                    >
                                        {d}
                                    </button>
                                ))}
                            </div>
                            <div className="robots-v2-inline">
                                <input
                                    className="robots-v2-input"
                                    type="time"
                                    value={draft.timeFrom}
                                    onChange={e => patch({ timeFrom: e.target.value })}
                                />
                                <span>—</span>
                                <input
                                    className="robots-v2-input"
                                    type="time"
                                    value={draft.timeTo}
                                    onChange={e => patch({ timeTo: e.target.value })}
                                />
                                <select
                                    className="robots-v2-input"
                                    value={draft.pollInterval}
                                    onChange={e => patch({ pollInterval: e.target.value as RobotV2WizardDraft['pollInterval'] })}
                                >
                                    <option value="1m">poll 1m</option>
                                    <option value="5m">poll 5m</option>
                                    <option value="15m">poll 15m</option>
                                    <option value="1h">poll 1h</option>
                                </select>
                            </div>
                        </div>
                    </div>
                )}

                {step === 1 && (
                    <div className="robots-v2-form">
                        <div className="robots-v2-archetype-grid">
                            {ARCHETYPE_CARDS.map(card => (
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
                            <select
                                className="robots-v2-input"
                                value={draft.timeframe}
                                onChange={e => patch({ timeframe: e.target.value })}
                            >
                                {['1m', '5m', '15m', '1h', '4h', '1d'].map(tf => (
                                    <option key={tf} value={tf}>{tf}</option>
                                ))}
                            </select>
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
                            <label className="robots-v2-check">
                                <input
                                    type="checkbox"
                                    checked={draft.advancedMode}
                                    onChange={e => patch({ advancedMode: e.target.checked })}
                                />
                                Advanced mode (обязателен для scalper)
                            </label>
                        )}
                    </div>
                )}

                {step === 2 && (
                    <div className="robots-v2-form">
                        <div className="robots-v2-chip-row">
                            {(['fixed', 'index', 'screener'] as const).map(m => (
                                <button
                                    key={m}
                                    type="button"
                                    className={`robots-v2-chip ${draft.universeMode === m ? 'robots-v2-chip--on' : ''}`}
                                    onClick={() => patch({ universeMode: m })}
                                >
                                    {m === 'fixed' ? 'Список' : m === 'index' ? 'Индекс' : 'Скринер'}
                                </button>
                            ))}
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
                                <select
                                    className="robots-v2-input"
                                    value={draft.screenerPreset}
                                    onChange={e =>
                                        patch({ screenerPreset: e.target.value as RobotV2WizardDraft['screenerPreset'] })
                                    }
                                >
                                    <option value="high_liquidity">Высокая ликвидность</option>
                                    <option value="volatile">Волатильные</option>
                                    <option value="low_price">Низкая цена</option>
                                    <option value="custom">Custom</option>
                                </select>
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
                            <label className="robots-v2-check">
                                <input
                                    type="checkbox"
                                    checked={draft.exitOnDrop}
                                    onChange={e => patch({ exitOnDrop: e.target.checked })}
                                />
                                Exit on drop
                            </label>
                        </div>
                        <Button type="button" variant="secondary" loading={previewLoading} onClick={() => void runPreview()}>
                            Превью состава
                        </Button>
                        {preview && (
                            <div className="robots-v2-preview">
                                <div className="robots-v2-preview__meta">
                                    Показано {preview.assets?.length ?? 0} из {preview.total}
                                </div>
                                <ul className="robots-v2-preview__list">
                                    {(preview.assets || []).slice(0, 20).map(a => (
                                        <li key={a.ticker}>
                                            <strong>{a.ticker}</strong>
                                            {a.name ? ` — ${a.name}` : ''}
                                            {a.price != null ? ` · ${a.price}` : ''}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                )}

                {step === 3 && (
                    <div className="robots-v2-form robots-v2-form--risk">
                        <label className="robots-v2-field">
                            <span>{selectedBroker === 'bybit' ? 'Капитал (USDT)' : 'Капитал'}</span>
                            <input
                                className="robots-v2-input"
                                type="number"
                                value={draft.capital}
                                onChange={e => patch({ capital: Number(e.target.value) })}
                            />
                        </label>
                        <label className="robots-v2-field">
                            <span>Доля позиции, %</span>
                            <input
                                className="robots-v2-input"
                                type="number"
                                value={draft.maxPositionSharePct}
                                onChange={e => patch({ maxPositionSharePct: Number(e.target.value) })}
                            />
                            <small className="robots-v2-hint">≈ {notional.toLocaleString('ru-RU')} на сделку</small>
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
                        <div className="robots-v2-chip-row">
                            <button
                                type="button"
                                className={`robots-v2-chip ${draft.stopMode === 'soft' ? 'robots-v2-chip--on' : ''}`}
                                onClick={() => patch({ stopMode: 'soft' })}
                            >
                                Soft stop
                            </button>
                            <button
                                type="button"
                                className={`robots-v2-chip ${draft.stopMode === 'hard' ? 'robots-v2-chip--on' : ''}`}
                                onClick={() => patch({ stopMode: 'hard' })}
                            >
                                Hard stop
                            </button>
                        </div>
                        <div className="robots-v2-field">
                            <span>EOD flatten</span>
                            <div className="robots-v2-chip-row">
                                <button
                                    type="button"
                                    className={`robots-v2-chip ${draft.eodFlattenEnabled === null ? 'robots-v2-chip--on' : ''}`}
                                    onClick={() => patch({ eodFlattenEnabled: null })}
                                >
                                    Auto (MOEX stock on)
                                </button>
                                <button
                                    type="button"
                                    className={`robots-v2-chip ${draft.eodFlattenEnabled === true ? 'robots-v2-chip--on' : ''}`}
                                    onClick={() => patch({ eodFlattenEnabled: true })}
                                >
                                    On
                                </button>
                                <button
                                    type="button"
                                    className={`robots-v2-chip ${draft.eodFlattenEnabled === false ? 'robots-v2-chip--on' : ''}`}
                                    onClick={() => patch({ eodFlattenEnabled: false })}
                                >
                                    Off
                                </button>
                            </div>
                            <label className="robots-v2-field">
                                <span>Минут до close</span>
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
                    Назад
                </Button>
                <div className="robots-v2-wizard-footer__right">
                    {step < 3 ? (
                        <Button type="button" onClick={goNext}>Далее</Button>
                    ) : (
                        <>
                            <Button type="button" variant="secondary" loading={saving} onClick={() => void saveRobot(false)}>
                                Сохранить
                            </Button>
                            <Button type="button" loading={saving} onClick={() => void saveRobot(true)}>
                                Создать и запустить
                            </Button>
                        </>
                    )}
                </div>
            </footer>
        </div>
    )
}
