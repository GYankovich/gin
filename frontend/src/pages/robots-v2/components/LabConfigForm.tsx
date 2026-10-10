import React, { useMemo } from 'react'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { Toggle } from '@/components/ui/Toggle'
import { WeekdaysMaskField } from '@/components/ui/WeekdaysMaskField'
import {
    ARCHETYPE_CARDS,
    archetypeDefaults,
    type RobotV2WizardDraft,
    type WizardArchetype,
} from '@/pages/robots-v2/wizardDraft'

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
    { value: 'soft', label: 'Мягкая' },
    { value: 'hard', label: 'Жёсткая' },
] as const

const EOD_OPTIONS = [
    { value: 'auto', label: 'Auto' },
    { value: 'on', label: 'Вкл' },
    { value: 'off', label: 'Выкл' },
] as const

function weekdaysToMask(days: boolean[]): number {
    return days.reduce((mask, selected, index) => (selected ? mask | (1 << index) : mask), 0)
}

function maskToWeekdays(mask: number): boolean[] {
    return Array.from({ length: 7 }, (_, index) => Boolean(mask & (1 << index)))
}

const PARAM_LABELS: Record<string, string> = {
    maPeriod: 'Период средней, баров',
    volumeMultiplier: 'Объём выше обычного, раз',
    breakoutLookback: 'Окно пробоя, баров',
    indicator: 'Индикатор',
    overboughtThreshold: 'Порог перекупленности',
    oversoldThreshold: 'Порог перепроданности',
    rsiPeriod: 'Период RSI',
    gridStepAtrPct: 'Шаг сетки, % ATR',
    gridDepth: 'Сколько уровней',
    baseAllocationPct: 'Доля капитала на уровень, %',
    scaleMultiplier: 'Множитель объёма к следующему уровню',
}

export type LabConfigFormProps = {
    draft: RobotV2WizardDraft
    onChange: (patch: Partial<RobotV2WizardDraft>) => void
    /** Hide schedule / live mode extras for denser Lab column. */
    compact?: boolean
}

/** Visual trading config for Backtest Lab — same fields as robot wizard steps 1–3. */
export function LabConfigForm({ draft, onChange, compact = true }: LabConfigFormProps) {
    const patch = (next: Partial<RobotV2WizardDraft>) => onChange(next)

    const selectArchetype = (id: WizardArchetype) => {
        const defaults = archetypeDefaults(id)
        patch({
            archetype: id,
            timeframe: defaults.timeframe,
            strategyParams: defaults.params,
            ...(defaults.advancedMode != null ? { advancedMode: defaults.advancedMode } : {}),
        })
    }

    const rr = useMemo(() => {
        const sl = Number(draft.stopLossPct) || 0
        const tp = Number(draft.takeProfitPct) || 0
        if (sl <= 0) return 0
        return tp / sl
    }, [draft.stopLossPct, draft.takeProfitPct])

    const instrumentOptions = draft.instrumentType === 'perpetual' || draft.instrumentType === 'coin_futures'
        ? [
            { value: 'perpetual', label: 'Perpetual (USDT)' },
            { value: 'coin_futures', label: 'Coin futures' },
        ]
        : [
            { value: 'stock', label: 'Акции' },
            { value: 'futures', label: 'Фьючерсы' },
            { value: 'perpetual', label: 'Perpetual (USDT)' },
            { value: 'coin_futures', label: 'Coin futures' },
        ]

    return (
        <div className={`robots-v2-lab-config ${compact ? 'robots-v2-lab-config--compact' : ''}`}>
            <CollapsibleSection
                className="dashboard-assets-collapse"
                defaultOpen
                title={(
                    <span className="dashboard-collapse__label">
                        <span className="dashboard-icon" aria-hidden>↗</span>
                        Стратегия
                    </span>
                )}
            >
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
                            options={instrumentOptions}
                            onChange={value =>
                                patch({
                                    instrumentType: value as RobotV2WizardDraft['instrumentType'],
                                })
                            }
                        />
                    </label>
                    <div className="robots-v2-archetype-grid robots-v2-archetype-grid--lab">
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
                                <span title={key}>{PARAM_LABELS[key] ?? key}</span>
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
                            <FormLabelTooltip text="Для бэктеста обычно Paper. Конфиг сохранится с выбранным режимом." />
                        </span>
                        <SegmentedControl
                            className="robots-v2-segmented"
                            aria-label="Режим торговли"
                            options={[...MODE_OPTIONS]}
                            value={draft.mode}
                            onChange={mode => patch({ mode })}
                        />
                    </label>
                    {!compact && (
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
                                    <span>Частота</span>
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
                </div>
            </CollapsibleSection>

            <CollapsibleSection
                className="dashboard-assets-collapse"
                defaultOpen
                title={(
                    <span className="dashboard-collapse__label">
                        <span className="dashboard-icon" aria-hidden>◈</span>
                        Активы
                    </span>
                )}
            >
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
                                rows={2}
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
                            label="Закрывать при исключении"
                        />
                    </div>
                </div>
            </CollapsibleSection>

            <CollapsibleSection
                className="dashboard-assets-collapse"
                defaultOpen
                title={(
                    <span className="dashboard-collapse__label">
                        <span className="dashboard-icon" aria-hidden>◎</span>
                        Риск
                    </span>
                )}
            >
                <div className="robots-v2-form robots-v2-form--risk">
                    <label className="robots-v2-field">
                        <span>Капитал (в конфиге)</span>
                        <input
                            className="robots-v2-input"
                            type="number"
                            min={10}
                            value={draft.capital}
                            onChange={e => patch({ capital: Number(e.target.value) })}
                        />
                        <small className="robots-v2-hint">
                            Поле «Капитал» ниже в запуске может переопределить сумму прогона.
                        </small>
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
                        <span>Режим остановки</span>
                        <SegmentedControl
                            className="robots-v2-segmented"
                            aria-label="Режим остановки"
                            options={[...STOP_MODE_OPTIONS]}
                            value={draft.stopMode}
                            onChange={stopMode => patch({ stopMode })}
                        />
                    </label>
                    <label className="robots-v2-field">
                        <span>EOD flatten</span>
                        <SegmentedControl
                            className="robots-v2-segmented"
                            aria-label="Закрытие к концу сессии"
                            options={[...EOD_OPTIONS]}
                            value={draft.eodFlattenEnabled === null ? 'auto' : draft.eodFlattenEnabled ? 'on' : 'off'}
                            onChange={value => patch({
                                eodFlattenEnabled: value === 'auto' ? null : value === 'on',
                            })}
                        />
                    </label>
                    <div className="robots-v2-inline">
                        <label className="robots-v2-field">
                            <span>Комиссия %</span>
                            <input
                                className="robots-v2-input"
                                type="number"
                                step={0.01}
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
                                step={0.01}
                                value={draft.slippagePct}
                                onChange={e => patch({ slippagePct: Number(e.target.value) })}
                            />
                        </label>
                    </div>
                </div>
            </CollapsibleSection>
        </div>
    )
}
