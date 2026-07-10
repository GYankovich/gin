import React, { useMemo, useState } from 'react'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { FilterPresetButtons } from '@/modules/robots/components/FilterPresetButtons'
import {
    CRYPTO_FILTER_META,
    cryptoScreeningFiltersFromPreset,
    ensureCompleteCryptoFilters,
    type CryptoScreeningFilter,
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

/**
 * Полная форма crypto_universe (Type2BybitConfig), стиль T-Invest form-row.
 * Все поля всегда на месте.
 */
export function CryptoScreeningFormFields({ filters, onFiltersChange, onConfigDirty }: Props) {
    const [activePreset, setActivePreset] = useState<UniverseFilterPresetId | null>('moderate')
    const dirty = () => onConfigDirty?.()
    const ordered = useMemo(() => ensureCompleteCryptoFilters(filters), [filters])

    const applyPreset = (presetId: UniverseFilterPresetId) => {
        onFiltersChange(cryptoScreeningFiltersFromPreset(presetId))
        setActivePreset(presetId)
        dirty()
    }

    const updateValue = (type: CryptoScreeningFilter['type'], value: number) => {
        onFiltersChange(
            ordered.map(f => (f.type === type ? { ...f, value } : f)),
        )
        setActivePreset(null)
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
                        : 'Пресет подставляет пороги crypto_universe'}
                </p>
            </div>

            {chunk(ordered, 3).map(row => (
                <div key={row.map(f => f.type).join('-')} className="form-row">
                    {row.map(f => {
                        const meta = CRYPTO_FILTER_META[f.type]
                        const reg = getCryptoFilterFieldMeta(f.type)
                        return (
                            <div key={f.type} className="form-group">
                                <label className="form-label">
                                    {reg?.label ?? meta.label}
                                    {reg?.tooltip && <FormLabelTooltip text={reg.tooltip} />}
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
                                            f.type,
                                            Number.isFinite(next) ? next : meta.defaultValue,
                                        )
                                    }}
                                />
                            </div>
                        )
                    })}
                </div>
            ))}

            <p className="field-hint-below">
                Поля = <code>crypto_universe</code>. Funding в форме в %, в конфиг уходит доля (/100).
            </p>
        </div>
    )
}
