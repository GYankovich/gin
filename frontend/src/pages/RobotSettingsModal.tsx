import React, { useState, useEffect } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { robotService } from '@/services/robotService'
import { portfolioService } from '@/services/portfolioService'
import type { Robot, StrategyParam } from '@/types/robot'
import type { TokenResponse } from '@/types/portfolio'

interface Props {
    open: boolean
    onClose: () => void
    robot?: Robot | null
    onSaved: () => void
}

const TABS = ['Общие', 'Стратегия', 'Риски', 'Инструменты', 'Расписание'] as const

const CANDLE_LABELS: Record<string, string> = {
    CANDLE_INTERVAL_5_SEC: '5 секунд',
    CANDLE_INTERVAL_10_SEC: '10 секунд',
    CANDLE_INTERVAL_30_SEC: '30 секунд',
    CANDLE_INTERVAL_1_MIN: '1 минута',
    CANDLE_INTERVAL_2_MIN: '2 минуты',
    CANDLE_INTERVAL_3_MIN: '3 минуты',
    CANDLE_INTERVAL_5_MIN: '5 минут',
    CANDLE_INTERVAL_10_MIN: '10 минут',
    CANDLE_INTERVAL_15_MIN: '15 минут',
    CANDLE_INTERVAL_30_MIN: '30 минут',
    CANDLE_INTERVAL_HOUR: '1 час',
    CANDLE_INTERVAL_2_HOUR: '2 часа',
    CANDLE_INTERVAL_4_HOUR: '4 часа',
    CANDLE_INTERVAL_DAY: 'День',
    CANDLE_INTERVAL_WEEK: 'Неделя',
    CANDLE_INTERVAL_MONTH: 'Месяц',
}

function candleIntervalLabel(v: string): string {
    return CANDLE_LABELS[v] ?? v
}

export function RobotSettingsModal({ open, onClose, robot, onSaved }: Props) {
    const [tab, setTab] = useState(0)
    const [saving, setSaving] = useState(false)
    const [tokens, setTokens] = useState<TokenResponse[]>([])
    const [strategies, setStrategies] = useState<StrategyParam[]>([])

    const cfg = robot?.config ?? {}
    const [name, setName] = useState(robot?.name ?? '')
    const [robotType, setRobotType] = useState(robot?.type ?? 2)
    const [tokenId, setTokenId] = useState(robot?.token?.id ?? 0)
    const [strategy, setStrategy] = useState(cfg.strategy ?? '')
    const [stratParams, setStratParams] = useState<Record<string, any>>(cfg.strategy_params ?? {})
    const [stopLoss, setStopLoss] = useState(cfg.stop_loss_pct ?? 2)
    const [takeProfit, setTakeProfit] = useState(cfg.take_profit_pct ?? 3)
    const [maxPosition, setMaxPosition] = useState(cfg.max_position_pct ?? 10)
    const [maxAmount, setMaxAmount] = useState(cfg.max_amount ?? 50000)
    const [dailyLimit, setDailyLimit] = useState(cfg.daily_loss_limit ?? 10000)
    const [figis, setFigis] = useState<string[]>(cfg.figis ?? [])
    const [figiInput, setFigiInput] = useState('')
    const [interval, setInterval_] = useState(cfg.interval_sec ?? 10)
    const [hoursFrom, setHoursFrom] = useState(cfg.hours_from ?? '09:00')
    const [hoursTo, setHoursTo] = useState(cfg.hours_to ?? '18:45')
    const [autoLoading, setAutoLoading] = useState(false)

    useEffect(() => {
        if (open) {
            portfolioService.getTokens().then(setTokens).catch(() => {})
            robotService.getStrategies().then(r => setStrategies(r.items)).catch(() => {})
        }
    }, [open])

    useEffect(() => {
        if (robot) {
            const c = robot.config ?? {}
            setName(robot.name)
            setRobotType(robot.type)
            setTokenId(robot.token?.id ?? 0)
            setStrategy(c.strategy ?? '')
            setStratParams(c.strategy_params ?? {})
            setStopLoss(c.stop_loss_pct ?? 2)
            setTakeProfit(c.take_profit_pct ?? 3)
            setMaxPosition(c.max_position_pct ?? 10)
            setMaxAmount(c.max_amount ?? 50000)
            setDailyLimit(c.daily_loss_limit ?? 10000)
            setFigis(c.figis ?? [])
            setInterval_(c.interval_sec ?? 10)
            setHoursFrom(c.hours_from ?? '09:00')
            setHoursTo(c.hours_to ?? '18:45')
        }
    }, [robot])

    const handleSave = async () => {
        setSaving(true)
        try {
            const payload: any = {
                name,
                type: robotType,
                token_id: tokenId,
                config: {
                    strategy,
                    strategy_params: stratParams,
                    stop_loss_pct: stopLoss,
                    take_profit_pct: takeProfit,
                    max_position_pct: maxPosition,
                    max_amount: maxAmount,
                    daily_loss_limit: dailyLimit,
                    figis,
                    interval_sec: interval,
                    hours_from: hoursFrom,
                    hours_to: hoursTo,
                },
            }
            if (robot) {
                await robotService.updateConfig(robot.id, payload)
            } else {
                await robotService.create(payload)
            }
            onSaved()
            onClose()
        } catch { /* toast error */ }
        setSaving(false)
    }

    const addFigi = () => {
        const v = figiInput.trim().toUpperCase()
        if (v && !figis.includes(v)) { setFigis([...figis, v]); setFigiInput('') }
    }

    const removeFigi = (f: string) => setFigis(figis.filter(x => x !== f))

    const handleAutoSelect = async () => {
        setAutoLoading(true)
        try {
            const res = await robotService.autoSelectInstruments({ token_id: tokenId })
            const newFigis = res.items.map((i: any) => i.figi).filter((f: string) => !figis.includes(f))
            setFigis([...figis, ...newFigis])
        } catch { /* */ }
        setAutoLoading(false)
    }

    const selectedStrat = strategies.find(s => s.name === strategy)

    return (
        <Modal open={open} onClose={onClose} title={robot ? `Настройка: ${robot.name}` : 'Новый робот'} width="640px">
            <div className="tabs">
                {TABS.map((t, i) => (
                    <button key={t} className={`tab-btn ${i === tab ? 'tab-btn--active' : ''}`} onClick={() => setTab(i)}>{t}</button>
                ))}
            </div>

            {tab === 0 && (
                <div>
                    <div className="form-group">
                        <label className="form-label">Название робота</label>
                        <input className="form-input" value={name} onChange={e => setName(e.target.value)} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Тип</label>
                        <div className="form-row">
                            <label><input type="radio" name="rt" checked={robotType === 1} onChange={() => setRobotType(1)} /> Портфельный</label>
                            <label><input type="radio" name="rt" checked={robotType === 2} onChange={() => setRobotType(2)} /> Торговый</label>
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Счёт (токен)</label>
                        <Select
                            options={[{ value: '0', label: 'Выберите токен' }, ...tokens.map(t => ({ value: String(t.id), label: t.token_name || `Токен #${t.id}` }))]}
                            value={String(tokenId)}
                            onChange={v => setTokenId(Number(v))}
                            placeholder="Выберите токен"
                        />
                    </div>
                </div>
            )}

            {tab === 1 && (
                <div>
                    <div className="form-group">
                        <label className="form-label">Стратегия</label>
                        <Select
                            options={[{ value: '', label: 'Выберите стратегию' }, ...strategies.map(s => ({ value: s.name, label: s.title }))]}
                            value={strategy}
                            onChange={v => setStrategy(v)}
                            placeholder="Выберите стратегию"
                        />
                    </div>
                    {selectedStrat?.description && <p className="form-hint">{selectedStrat.description}</p>}
                    {selectedStrat?.params_schema && Object.entries(selectedStrat.params_schema).map(([key, schema]: [string, any]) => {
                        if (schema.type === 'array') return null
                        if (schema.enum) {
                            return (
                                <div className="form-group" key={key}>
                                    <label className="form-label">{schema.label || schema.title || key}</label>
                                    <Select
                                        options={schema.enum.map((v: string) => ({ value: v, label: candleIntervalLabel(v) }))}
                                        value={stratParams[key] ?? schema.default ?? ''}
                                        onChange={v => setStratParams({ ...stratParams, [key]: v })}
                                        placeholder="Выберите..."
                                    />
                                </div>
                            )
                        }
                        return (
                            <div className="form-group" key={key}>
                                <label className="form-label">{schema.label || schema.title || key}</label>
                                <input
                                    className="form-input"
                                    type={schema.type === 'integer' || schema.type === 'number' ? 'number' : 'text'}
                                    value={stratParams[key] ?? schema.default ?? ''}
                                    onChange={e => setStratParams({ ...stratParams, [key]: schema.type === 'integer' ? parseInt(e.target.value) : e.target.value })}
                                />
                            </div>
                        )
                    })}
                </div>
            )}

            {tab === 2 && (
                <div>
                    <div className="form-group">
                        <label className="form-label">Стоп-лосс (%)</label>
                        <input className="form-input" type="number" min={0} max={20} step={0.5} value={stopLoss} onChange={e => setStopLoss(Number(e.target.value))} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Тейк-профит (%)</label>
                        <input className="form-input" type="number" min={0} max={50} step={0.5} value={takeProfit} onChange={e => setTakeProfit(Number(e.target.value))} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Макс. размер позиции (% портфеля)</label>
                        <input className="form-input" type="number" min={1} max={100} value={maxPosition} onChange={e => setMaxPosition(Number(e.target.value))} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Макс. сумма на сделку (₽)</label>
                        <input className="form-input" type="number" min={0} value={maxAmount} onChange={e => setMaxAmount(Number(e.target.value))} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Дневной лимит убытков (₽)</label>
                        <input className="form-input" type="number" min={0} value={dailyLimit} onChange={e => setDailyLimit(Number(e.target.value))} />
                    </div>
                </div>
            )}

            {tab === 3 && (
                <div>
                    <div className="form-group">
                        <label className="form-label">FIGI</label>
                        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                            <input className="form-input" style={{ flex: 1 }} placeholder="BBG004730ZJ9" value={figiInput} onChange={e => setFigiInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addFigi())} />
                            <Button size="sm" onClick={addFigi}>Добавить</Button>
                        </div>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
                        {figis.map(f => (
                            <span key={f} className="tag">{f} <button className="tag__remove" onClick={() => removeFigi(f)}>×</button></span>
                        ))}
                        {figis.length === 0 && <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>Нет инструментов</span>}
                    </div>
                    <Button variant="secondary" size="sm" loading={autoLoading} onClick={handleAutoSelect}>Автоподбор</Button>
                </div>
            )}

            {tab === 4 && (
                <div>
                    <div className="form-group">
                        <label className="form-label">Интервал запуска (сек)</label>
                        <input className="form-input" type="number" min={1} value={interval} onChange={e => setInterval_(Number(e.target.value))} />
                    </div>
                    <div className="form-row">
                        <div className="form-group">
                            <label className="form-label">Часы работы (от)</label>
                            <input className="form-input" type="time" value={hoursFrom} onChange={e => setHoursFrom(e.target.value)} />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Часы работы (до)</label>
                            <input className="form-input" type="time" value={hoursTo} onChange={e => setHoursTo(e.target.value)} />
                        </div>
                    </div>
                </div>
            )}

            <div className="form-actions">
                <Button variant="ghost" onClick={onClose}>Отмена</Button>
                <Button variant="primary" glow loading={saving} onClick={handleSave}>Сохранить</Button>
            </div>
        </Modal>
    )
}
