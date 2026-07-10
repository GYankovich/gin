import React, { useCallback, useMemo, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { FilterPresetButtons } from '@/modules/robots/components/FilterPresetButtons'
import type { UniverseFilterPresetId } from '@/modules/robots/config/universeFilterPresets'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import {
    ADDABLE_SNAPSHOT_FILTER_TYPES,
    FILTER_DEFAULTS,
    FILTER_FIELD_HINT,
    FILTER_META,
    type PipelineFilter,
    type PipelineFilterType,
} from '@/pages/robots/pipelineFilterMeta'
import { HISTORICAL_FILTER_TYPES } from '@/utils/robotConfigV2'

function parseTickers(v: string): string[] {
    return v
        .split(',')
        .map(x => x.trim().toUpperCase())
        .filter(Boolean)
}

function chunk<T>(items: T[], size: number): T[][] {
    const out: T[][] = []
    for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
    return out
}

type Props = {
    filters: PipelineFilter[]
    scope?: 'paper' | 'historical'
    excludeFilterTypes?: PipelineFilterType[]
    pipelineMode?: 'ALL' | 'ANY'
    onPipelineModeChange?: (mode: 'ALL' | 'ANY') => void
    onFiltersChange: (filters: PipelineFilter[]) => void
    onApplyPreset?: (preset: UniverseFilterPresetId) => void
    showPipelineMode?: boolean
    showPresets?: boolean
    sectionTitle?: string
}

const ADDABLE_HISTORICAL_FILTER_TYPES: PipelineFilterType[] = ['atr']

export function SnapshotFiltersEditor({
    filters,
    scope = 'paper',
    excludeFilterTypes = [],
    pipelineMode = 'ALL',
    onPipelineModeChange,
    onFiltersChange,
    onApplyPreset,
    showPipelineMode = true,
    showPresets = true,
    sectionTitle = 'Активные фильтры',
}: Props) {
    const isHistorical = scope === 'historical'
    const excludeSet = useMemo(() => new Set(excludeFilterTypes), [excludeFilterTypes])

    const historicalFilters = useMemo(
        () => filters.filter(f => HISTORICAL_FILTER_TYPES.has(f.type) && !excludeSet.has(f.type)),
        [filters, excludeSet],
    )
    const paperFiltersAll = useMemo(
        () => filters.filter(f => !HISTORICAL_FILTER_TYPES.has(f.type)),
        [filters],
    )

    const activeFilters = isHistorical ? historicalFilters : paperFiltersAll

    const mergeActiveFilters = useCallback(
        (nextActive: PipelineFilter[]) => {
            if (isHistorical) {
                onFiltersChange([...paperFiltersAll, ...nextActive])
            } else {
                onFiltersChange([...historicalFilters, ...nextActive])
            }
        },
        [historicalFilters, isHistorical, onFiltersChange, paperFiltersAll],
    )

    const [showAddMenu, setShowAddMenu] = useState(false)

    const addablePool = isHistorical ? ADDABLE_HISTORICAL_FILTER_TYPES : ADDABLE_SNAPSHOT_FILTER_TYPES
    const addableTypes = addablePool.filter(t => !activeFilters.some(f => f.type === t) && !excludeSet.has(t))

    const updateFilter = (id: string, patch: Partial<PipelineFilter>) => {
        mergeActiveFilters(activeFilters.map(f => (f.id === id ? { ...f, ...patch } : f)))
    }

    const removeFilter = (id: string) => {
        mergeActiveFilters(activeFilters.filter(f => f.id !== id))
    }

    const addFilter = (type: PipelineFilterType) => {
        const defaults = FILTER_DEFAULTS[type]
        if (!defaults) return
        mergeActiveFilters([
            ...activeFilters,
            { ...defaults, id: `${type}-${Date.now()}` } as PipelineFilter,
        ])
        setShowAddMenu(false)
    }

    const isLocked = (type: PipelineFilterType) =>
        !isHistorical && (type === 'security_status' || type === 'trading_status')

    const canRemove = (type: PipelineFilterType) =>
        !isLocked(type) && !(isHistorical === false && type === 'atr')

    const renderInputs = (f: PipelineFilter) => {
        if (f.type === 'volume') {
            return (
                <div className="form-row pipeline-inline-row">
                    <input
                        className="form-input cyber-input"
                        type="number"
                        value={Number(f.min || 0)}
                        onChange={e => updateFilter(f.id, { min: Number(e.target.value || 0) })}
                    />
                    <span className="cyber-unit">₽</span>
                </div>
            )
        }
        if (f.type === 'num_trades') {
            return (
                <input
                    className="form-input cyber-input"
                    type="number"
                    value={Number(f.min || 0)}
                    onChange={e => updateFilter(f.id, { min: Number(e.target.value || 0) })}
                />
            )
        }
        if (f.type === 'gap') {
            return (
                <div className="form-row pipeline-inline-row">
                    <input
                        className="form-input cyber-input"
                        type="number"
                        step="0.1"
                        value={Number(f.max_percent || 0)}
                        onChange={e => updateFilter(f.id, { max_percent: Number(e.target.value || 0) })}
                    />
                    <span className="cyber-unit">%</span>
                    <SegmentedControl
                        options={[
                            { value: 'BOTH', label: 'Оба' },
                            { value: 'UP_ONLY', label: '↑' },
                            { value: 'DOWN_ONLY', label: '↓' },
                        ]}
                        value={f.direction || 'BOTH'}
                        onChange={v =>
                            updateFilter(f.id, {
                                direction: v as 'BOTH' | 'UP_ONLY' | 'DOWN_ONLY',
                            })
                        }
                    />
                </div>
            )
        }
        if (f.type === 'spread') {
            return (
                <div className="form-row pipeline-inline-row">
                    <input
                        className="form-input cyber-input"
                        type="number"
                        step="0.01"
                        value={Number(f.max_percent || 0)}
                        onChange={e => updateFilter(f.id, { max_percent: Number(e.target.value || 0) })}
                    />
                    <span className="cyber-unit">%</span>
                </div>
            )
        }
        if (f.type === 'atr') {
            return (
                <div className="form-row pipeline-inline-row">
                    <input
                        className="form-input cyber-input"
                        type="number"
                        step="0.1"
                        value={Number(f.min_percent || 0)}
                        onChange={e => updateFilter(f.id, { min_percent: Number(e.target.value || 0) })}
                    />
                    <span className="cyber-unit">%</span>
                    <input
                        className="form-input cyber-input"
                        type="number"
                        min={5}
                        max={60}
                        value={Number(f.period || 14)}
                        onChange={e => updateFilter(f.id, { period: Number(e.target.value || 14) })}
                    />
                    <span className="cyber-unit">дн.</span>
                </div>
            )
        }
        if (f.type === 'capitalization') {
            return (
                <input
                    className="form-input cyber-input"
                    type="number"
                    value={Number(f.min || 0)}
                    onChange={e => updateFilter(f.id, { min: Number(e.target.value || 0) })}
                />
            )
        }
        if (f.type === 'turnover') {
            return (
                <div className="form-row pipeline-inline-row">
                    <input
                        className="form-input cyber-input"
                        type="number"
                        step="0.01"
                        value={Number(f.min_percent || 0)}
                        onChange={e => updateFilter(f.id, { min_percent: Number(e.target.value || 0) })}
                    />
                    <span className="cyber-unit">% выпуска</span>
                </div>
            )
        }
        if (f.type === 'gap_retention') {
            return (
                <input
                    className="form-input cyber-input"
                    type="number"
                    step="0.1"
                    min={0}
                    max={5}
                    value={Number(f.min_ratio || 0)}
                    onChange={e => updateFilter(f.id, { min_ratio: Number(e.target.value || 0) })}
                />
            )
        }
        if (f.type === 'price_vs_open') {
            return (
                <div className="form-row pipeline-inline-row">
                    <input
                        className="form-input cyber-input"
                        type="number"
                        step="0.001"
                        min={0.9}
                        max={1.1}
                        value={Number(f.min_percent || 0.998)}
                        onChange={e => updateFilter(f.id, { min_percent: Number(e.target.value || 0.998) })}
                    />
                    <span className="cyber-unit">доля от OPEN</span>
                </div>
            )
        }
        if (f.type === 'opening_range') {
            return (
                <div className="form-row pipeline-inline-row">
                    <input
                        className="form-input cyber-input"
                        type="number"
                        step="0.1"
                        min={0}
                        max={100}
                        value={Number(f.min_percent || 0)}
                        onChange={e => updateFilter(f.id, { min_percent: Number(e.target.value || 0) })}
                    />
                    <span className="cyber-unit">%</span>
                </div>
            )
        }
        if (f.type === 'min_step_ratio') {
            return (
                <input
                    className="form-input cyber-input"
                    type="number"
                    step="0.5"
                    value={Number(f.max_steps || 5)}
                    onChange={e => updateFilter(f.id, { max_steps: Number(e.target.value || 5) })}
                />
            )
        }
        if (f.type === 'excluded_tickers' || f.type === 'allowed_tickers') {
            return (
                <input
                    className="form-input cyber-input"
                    placeholder="SBER, LKOH"
                    value={Array.isArray(f.list) ? f.list.join(', ') : ''}
                    onChange={e => updateFilter(f.id, { list: parseTickers(e.target.value) })}
                />
            )
        }
        if (f.type === 'security_status' || f.type === 'trading_status') {
            return <input className="form-input cyber-input" value={String(f.eq || '')} readOnly />
        }
        return null
    }

    return (
        <div className="snapshot-filters-editor">
            <div className="snapshot-filters-editor__header">
                <div>
                    <h4 className="card__subsection-title">{sectionTitle}</h4>
                    {showPipelineMode && onPipelineModeChange && (
                        <p className="form-hint snapshot-filters-editor__mode-hint">
                            Режим: все фильтры должны пройти (ALL) или достаточно одного (ANY).
                        </p>
                    )}
                </div>
                {showPipelineMode && onPipelineModeChange && (
                    <SegmentedControl
                        options={[
                            { value: 'ALL', label: 'Все (AND)' },
                            { value: 'ANY', label: 'Любой (OR)' },
                        ]}
                        value={pipelineMode}
                        onChange={onPipelineModeChange}
                        aria-label="Режим фильтров"
                    />
                )}
            </div>

            {showPresets && onApplyPreset && (
                <div className="pipeline-presets-row">
                    <span className="pipeline-presets-row__label">Пресет</span>
                    <FilterPresetButtons onApply={onApplyPreset} />
                </div>
            )}

            <div className="snapshot-filters-editor__list">
                {chunk(activeFilters, 2).map(row => (
                    <div key={row.map(f => f.id).join('-')} className="form-row">
                        {row.map(f => (
                            <div key={f.id} className="form-group">
                                <label className="form-label">
                                    {FILTER_META[f.type].label}
                                    {FILTER_FIELD_HINT[f.type] && (
                                        <FormLabelTooltip text={FILTER_FIELD_HINT[f.type]} />
                                    )}
                                    {canRemove(f.type) && (
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
                                    )}
                                </label>
                                {renderInputs(f)}
                            </div>
                        ))}
                    </div>
                ))}
            </div>

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
                                {FILTER_META[t].label}
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
