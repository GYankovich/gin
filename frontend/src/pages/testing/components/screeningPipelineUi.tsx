import React from 'react'
import { FilterPresetButtons } from '@/modules/robots/components/FilterPresetButtons'
import type { UniverseFilterPresetId } from '@/modules/robots/config/universeFilterPresets'
import type { CryptoScreeningFilterType } from '@/pages/testing/cryptoScreeningPipeline'
import { getCryptoFilterFieldMeta } from '@/modules/robots/config/p1ScreeningFields'

const CRYPTO_FILTER_SHORT_FALLBACK: Record<CryptoScreeningFilterType, string> = {
    min_volume_24h_usd: 'Vol 24h',
    min_last_price: 'Цена min',
    max_spread_bps: 'Спред',
    min_funding_rate_pct: 'Fund min',
    max_funding_rate_pct: 'Fund max',
    min_open_interest_usd: 'OI min',
    min_lsr: 'LSR min',
    max_lsr: 'LSR max',
    min_rvol: 'RVOL',
    min_atr_percent: 'ATR min',
    max_atr_percent: 'ATR max',
    lookback_days: 'Lookback',
    funding_lookback_hours: 'Fund h',
    refresh_every_minutes: 'Refresh',
}

/** Короткие подписи — из реестра P1, иначе fallback. */
export const CRYPTO_FILTER_SHORT: Record<CryptoScreeningFilterType, string> = Object.fromEntries(
    (Object.keys(CRYPTO_FILTER_SHORT_FALLBACK) as CryptoScreeningFilterType[]).map(type => [
        type,
        getCryptoFilterFieldMeta(type)?.shortLabel ?? CRYPTO_FILTER_SHORT_FALLBACK[type],
    ]),
) as Record<CryptoScreeningFilterType, string>

export type ScreeningPresetBarProps = {
    activePreset: UniverseFilterPresetId | null
    onApply: (presetId: UniverseFilterPresetId) => void
    hint?: string | null
}

export function ScreeningPresetBar({ activePreset, onApply, hint }: ScreeningPresetBarProps) {
    return (
        <div className="screening-toolbar">
            <span className="screening-toolbar__label">Пресет</span>
            <FilterPresetButtons
                activePreset={activePreset}
                onApply={onApply}
                className="screening-preset-bar"
            />
            {hint ? (
                <span className="screening-toolbar__hint" title={hint}>
                    {hint}
                </span>
            ) : null}
        </div>
    )
}

export type ScreeningLogicToggleProps = {
    value: 'ALL' | 'ANY'
    onChange: (mode: 'ALL' | 'ANY') => void
}

export function ScreeningLogicToggle({ value, onChange }: ScreeningLogicToggleProps) {
    return (
        <div className="screening-logic-toggle" role="radiogroup" aria-label="Логика фильтров">
            <button
                type="button"
                role="radio"
                aria-checked={value === 'ALL'}
                className={`screening-logic-toggle__btn${value === 'ALL' ? ' screening-logic-toggle__btn--active' : ''}`}
                onClick={() => onChange('ALL')}
            >
                AND
            </button>
            <button
                type="button"
                role="radio"
                aria-checked={value === 'ANY'}
                className={`screening-logic-toggle__btn${value === 'ANY' ? ' screening-logic-toggle__btn--active' : ''}`}
                onClick={() => onChange('ANY')}
            >
                OR
            </button>
        </div>
    )
}

export type ScreeningMoexControlsProps = {
    pipelineMode: 'ALL' | 'ANY'
    onPipelineModeChange: (mode: 'ALL' | 'ANY') => void
    universeRefreshMinutes?: number
    onUniverseRefreshMinutesChange?: (v: number) => void
    onConfigDirty: () => void
}

export function ScreeningMoexControls({
    pipelineMode,
    onPipelineModeChange,
    universeRefreshMinutes = 0,
    onUniverseRefreshMinutesChange,
    onConfigDirty,
}: ScreeningMoexControlsProps) {
    return (
        <div className="screening-moex-controls">
            <ScreeningLogicToggle value={pipelineMode} onChange={onPipelineModeChange} />
            {onUniverseRefreshMinutesChange && (
                <label className="screening-moex-controls__refresh">
                    <span className="screening-toolbar__label">Пересбор</span>
                    <input
                        className="form-input screening-moex-controls__refresh-input"
                        type="number"
                        min={0}
                        max={1440}
                        step={5}
                        title="Авто-пересбор universe, мин (0 = выкл)"
                        value={universeRefreshMinutes}
                        onChange={e => {
                            const n = Math.max(0, Math.min(1440, Number(e.target.value || 0)))
                            onUniverseRefreshMinutesChange(Number.isFinite(n) ? n : 0)
                            onConfigDirty()
                        }}
                    />
                    <span className="screening-moex-controls__refresh-unit">мин</span>
                </label>
            )}
        </div>
    )
}

export type ScreeningFilterTileProps = {
    label: string
    title?: string
    unit?: string
    locked?: boolean
    inactive?: boolean
    onRemove?: () => void
    children: React.ReactNode
}

export function ScreeningFilterTile({
    label,
    title,
    unit,
    locked = false,
    inactive = false,
    onRemove,
    children,
}: ScreeningFilterTileProps) {
    return (
        <div
            className={`screening-filter${locked ? ' screening-filter--locked' : ''}${inactive ? ' screening-filter--inactive' : ''}`}
        >
            <div className="screening-filter__head">
                <span className="screening-filter__label" title={title ?? label}>
                    {label}
                </span>
                {unit ? <span className="screening-filter__unit">{unit}</span> : null}
                {!locked && onRemove && (
                    <button
                        type="button"
                        className="screening-filter__remove"
                        aria-label={`Удалить ${label}`}
                        onClick={onRemove}
                    >
                        ×
                    </button>
                )}
            </div>
            <div className="screening-filter__body">{children}</div>
        </div>
    )
}

export type ScreeningAddChip = { key: string; label: string }

export type ScreeningAddChipsProps = {
    items: ScreeningAddChip[]
    onAdd: (key: string) => void
}

export function ScreeningAddChips({ items, onAdd }: ScreeningAddChipsProps) {
    if (!items.length) return null
    return (
        <div className="screening-add-chips">
            <span className="screening-add-chips__label">Добавить</span>
            <div className="screening-add-chips__list">
                {items.map(it => (
                    <button key={it.key} type="button" className="screening-add-chip" onClick={() => onAdd(it.key)}>
                        + {it.label}
                    </button>
                ))}
            </div>
        </div>
    )
}
