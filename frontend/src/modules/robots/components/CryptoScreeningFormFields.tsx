import React, { useMemo, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { FilterPresetButtons } from '@/modules/robots/components/FilterPresetButtons'
import {
    CRYPTO_FILTER_META,
    CRYPTO_SCREENING_FILTER_TYPES,
    cryptoScreeningFiltersFromPreset,
    defaultValueForCryptoFilterType,
    type CryptoScreeningFilter,
    type CryptoScreeningFilterType,
} from '@/pages/testing/cryptoScreeningPipeline'
import { getCryptoFilterFieldMeta } from '@/modules/robots/config/p1ScreeningFields'
import {
    UNIVERSE_FILTER_PRESET_META,
    type UniverseFilterPresetId,
} from '@/modules/robots/config/universeFilterPresets'

type Props = {
    filters: CryptoScreeningFilter[]
    onFiltersChange: (filters: CryptoScreeningFilter[]) => void
    onConfigDirty?: () => void
}

function chunk<T>(items: T[], size: number): T[][] {
    const out: T[][] = []
    for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
    return out
}

function orderFilters(filters: CryptoScreeningFilter[]): CryptoScreeningFilter[] {
    const byType = new Map(filters.map(f => [f.type, f]))
    const ordered: CryptoScreeningFilter[] = []
    for (const type of CRYPTO_SCREENING_FILTER_TYPES) {
        const f = byType.get(type)
        if (f) ordered.push(f)
    }
    // Keep any unknown/extra types at end (defensive)
    for (const f of filters) {
        if (!ordered.some(o => o.id === f.id)) ordered.push(f)
    }
    return ordered
}

/**
 * Редактор crypto_universe: пресет moderate при создании,
 * поля можно удалять и добавлять обратно.
 */
export function CryptoScreeningFormFields({ filters, onFiltersChange, onConfigDirty }: Props) {
    const [activePreset, setActivePreset] = useState<UniverseFilterPresetId | null>('moderate')
    const [showAddMenu, setShowAddMenu] = useState(false)
    const dirty = () => onConfigDirty?.()
    const active = useMemo(() => orderFilters(filters), [filters])
    const presentTypes = useMemo(() => new Set(active.map(f => f.type)), [active])
    const addableTypes = useMemo(
        () => CRYPTO_SCREENING_FILTER_TYPES.filter(t => !presentTypes.has(t)),
        [presentTypes],
    )

    const applyPreset = (presetId: UniverseFilterPresetId) => {
        onFiltersChange(cryptoScreeningFiltersFromPreset(presetId))
        setActivePreset(presetId)
        setShowAddMenu(false)
        dirty()
    }

    const updateValue = (id: string, value: number) => {
        onFiltersChange(active.map(f => (f.id === id ? { ...f, value } : f)))
        setActivePreset(null)
        dirty()
    }

    const removeFilter = (id: string) => {
        onFiltersChange(active.filter(f => f.id !== id))
        setActivePreset(null)
        dirty()
    }

    const addFilter = (type: CryptoScreeningFilterType) => {
        onFiltersChange([
            ...active,
            {
                id: `add-${type}-${Date.now()}`,
                type,
                value: defaultValueForCryptoFilterType(type),
            },
        ])
        setActivePreset(null)
        setShowAddMenu(false)
        dirty()
    }

    return (
        <div className="snapshot-filters-editor">
            <div className="pipeline-presets-row">
                <span className="pipeline-presets-row__label">Пресет</span>
                <FilterPresetButtons activePreset={activePreset} onApply={applyPreset} />
                <p className="form-hint">
                    {activePreset
                        ? UNIVERSE_FILTER_PRESET_META[activePreset].hint
                        : 'Пресет подставляет набор порогов crypto_universe. Лишние поля можно удалить.'}
                </p>
            </div>

            {active.length === 0 ? (
                <p className="dashboard-empty">Нет активных фильтров — добавьте поле или выберите пресет.</p>
            ) : (
                <div className="snapshot-filters-editor__list">
                    {chunk(active, 3).map(row => (
                        <div key={row.map(f => f.id).join('-')} className="form-row">
                            {row.map(f => {
                                const meta = CRYPTO_FILTER_META[f.type]
                                const reg = getCryptoFilterFieldMeta(f.type)
                                return (
                                    <div key={f.id} className="form-group">
                                        <label className="form-label">
                                            {reg?.label ?? meta.label}
                                            {reg?.tooltip && <FormLabelTooltip text={reg.tooltip} />}
                                            <Button
                                                type="button"
                                                size="sm"
                                                variant="ghost"
                                                className="pipeline-delete-btn"
                                                title="Убрать фильтр"
                                                onClick={() => removeFilter(f.id)}
                                                style={{ marginLeft: 6 }}
                                            >
                                                ×
                                            </Button>
                                        </label>
                                        <input
                                            className="form-input cyber-input"
                                            type="number"
                                            step={meta.step}
                                            min={meta.min}
                                            max={meta.max}
                                            value={f.value}
                                            onChange={e => {
                                                const raw = e.target.value
                                                const next = meta.integer
                                                    ? Math.round(Number(raw || 0))
                                                    : Number(raw || 0)
                                                updateValue(
                                                    f.id,
                                                    Number.isFinite(next) ? next : meta.defaultValue,
                                                )
                                            }}
                                        />
                                    </div>
                                )
                            })}
                        </div>
                    ))}
                </div>
            )}

            <div className="snapshot-filters-editor__add">
                <button
                    type="button"
                    className="btn-add-filter"
                    onClick={() => setShowAddMenu(v => !v)}
                    disabled={addableTypes.length === 0}
                >
                    + Добавить фильтр
                </button>
                {showAddMenu && addableTypes.length > 0 && (
                    <div className="snapshot-filters-editor__add-menu" role="menu">
                        {addableTypes.map(t => (
                            <button
                                key={t}
                                type="button"
                                role="menuitem"
                                className="snapshot-filters-editor__add-item"
                                onClick={() => addFilter(t)}
                            >
                                {getCryptoFilterFieldMeta(t)?.label ?? CRYPTO_FILTER_META[t].label}
                            </button>
                        ))}
                    </div>
                )}
            </div>

            <p className="field-hint-below">
                Поля = <code>crypto_universe</code> (отбор в пул). Funding в форме в %, в конфиг уходит доля (/100).
            </p>
        </div>
    )
}
