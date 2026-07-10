import React, { type Dispatch, type SetStateAction, useState } from 'react'
import { Card } from '@/components/ui/Card'
import {
    CRYPTO_FILTER_META,
    CRYPTO_SCREENING_FILTER_TYPES,
    cryptoScreeningFiltersFromPreset,
    type CryptoScreeningFilter,
    type CryptoScreeningFilterType,
} from '@/pages/testing/cryptoScreeningPipeline'
import {
    CRYPTO_FILTER_SHORT,
    ScreeningAddChips,
    ScreeningFilterTile,
    ScreeningPresetBar,
} from '@/pages/testing/components/screeningPipelineUi'
import { parseNum } from '@/pages/testing/testingUtils'
import { UNIVERSE_FILTER_PRESET_META, type UniverseFilterPresetId } from '@/modules/robots/config/universeFilterPresets'

export type TestingCryptoPipelineCardProps = {
    filters: CryptoScreeningFilter[]
    setFilters: Dispatch<SetStateAction<CryptoScreeningFilter[]>>
    onAddFilter: (type: CryptoScreeningFilterType) => void
    onRemoveFilter: (id: string) => void
    onConfigDirty: () => void
    embedded?: boolean
    compact?: boolean
    className?: string
}

function FilterTile({
    f,
    onRemoveFilter,
    setFilters,
    clearPreset,
    dirty,
}: {
    f: CryptoScreeningFilter
    onRemoveFilter: (id: string) => void
    setFilters: Dispatch<SetStateAction<CryptoScreeningFilter[]>>
    clearPreset: () => void
    dirty: () => void
}) {
    const meta = CRYPTO_FILTER_META[f.type]
    const shortLabel = CRYPTO_FILTER_SHORT[f.type]
    return (
        <ScreeningFilterTile
            label={shortLabel}
            title={meta.label}
            inactive={false}
            onRemove={() => onRemoveFilter(f.id)}
        >
            <input
                className="form-input screening-filter__input"
                type="number"
                step={meta.step}
                min={meta.min}
                max={meta.max}
                value={f.value}
                onChange={e => {
                    const allowDecimal = !meta.integer
                    const next = parseNum(e.target.value, allowDecimal, meta.min, meta.max)
                    setFilters(prev => prev.map(x => (x.id === f.id ? { ...x, value: next } : x)))
                    clearPreset()
                    dirty()
                }}
            />
        </ScreeningFilterTile>
    )
}

/** ByBit DailyMarketScanner — компактные плитки фильтров (common + crypto из реестра). */
export function TestingCryptoPipelineCard({
    filters,
    setFilters,
    onAddFilter,
    onRemoveFilter,
    onConfigDirty,
    embedded = false,
    compact = false,
    className = '',
}: TestingCryptoPipelineCardProps) {
    const [activePreset, setActivePreset] = useState<UniverseFilterPresetId | null>('moderate')
    const dirty = () => onConfigDirty()

    const applyPreset = (presetId: UniverseFilterPresetId) => {
        setFilters(cryptoScreeningFiltersFromPreset(presetId))
        setActivePreset(presetId)
        dirty()
    }

    const clearPreset = () => setActivePreset(null)

    const presetHint = activePreset ? UNIVERSE_FILTER_PRESET_META[activePreset].hint : null

    const compactContent = (
        <div className="screening-pipeline">
            <ScreeningPresetBar activePreset={activePreset} onApply={applyPreset} hint={presetHint} />
            <div className="screening-filter-grid">
                {filters.map(f => (
                    <FilterTile
                        key={f.id}
                        f={f}
                        onRemoveFilter={onRemoveFilter}
                        setFilters={setFilters}
                        clearPreset={clearPreset}
                        dirty={dirty}
                    />
                ))}
            </div>
            <ScreeningAddChips
                items={CRYPTO_SCREENING_FILTER_TYPES.filter(t => !filters.some(f => f.type === t)).map(t => ({
                    key: t,
                    label: CRYPTO_FILTER_SHORT[t],
                }))}
                onAdd={key => onAddFilter(key as CryptoScreeningFilterType)}
            />
        </div>
    )

    const legacyContent = (
        <>
            <div className="pipeline-presets-row">
                <span className="pipeline-presets-row__label">Пресет</span>
                <ScreeningPresetBar activePreset={activePreset} onApply={applyPreset} />
                <p className="form-hint">
                    {activePreset
                        ? UNIVERSE_FILTER_PRESET_META[activePreset].hint
                        : 'Пресет подставляет пороги объёма, спреда, funding и волатильности'}
                </p>
            </div>
            <div className="pipeline-filter-grid">
                {filters.map(f => {
                    const meta = CRYPTO_FILTER_META[f.type]
                    return (
                        <div key={f.id} className="form-group pipeline-filter-card">
                            <div className="pipeline-filter-row">
                                <strong className="pipeline-filter-label">{meta.label}</strong>
                                <div className="pipeline-filter-inputs">
                                    <input
                                        className="form-input"
                                        type="number"
                                        step={meta.step}
                                        min={meta.min}
                                        max={meta.max}
                                        value={f.value}
                                        onChange={e => {
                                            const allowDecimal = !meta.integer
                                            const next = parseNum(e.target.value, allowDecimal, meta.min, meta.max)
                                            setFilters(prev =>
                                                prev.map(x => (x.id === f.id ? { ...x, value: next } : x)),
                                            )
                                            clearPreset()
                                            dirty()
                                        }}
                                    />
                                </div>
                                <button
                                    type="button"
                                    className="screening-filter__remove"
                                    onClick={() => onRemoveFilter(f.id)}
                                >
                                    ×
                                </button>
                            </div>
                        </div>
                    )
                })}
            </div>
            <ScreeningAddChips
                items={CRYPTO_SCREENING_FILTER_TYPES.filter(t => !filters.some(f => f.type === t)).map(t => ({
                    key: t,
                    label: CRYPTO_FILTER_META[t].label,
                }))}
                onAdd={key => onAddFilter(key as CryptoScreeningFilterType)}
            />
        </>
    )

    const content = compact ? compactContent : legacyContent

    if (embedded) {
        return (
            <div
                className={`pipeline-card pipeline-card--embedded${compact ? ' pipeline-card--compact' : ''} ${className}`.trim()}
            >
                {content}
            </div>
        )
    }
    return <Card className={`mb-6 pipeline-card ${className}`.trim()}>{content}</Card>
}
