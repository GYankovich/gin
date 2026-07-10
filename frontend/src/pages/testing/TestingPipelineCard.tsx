import React, { type Dispatch, type SetStateAction, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { FILTER_META, type PipelineFilter, type PipelineFilterType } from '@/pages/testing/testingPipeline'
import { parseTickers } from '@/pages/testing/testingUtils'
import {
    ScreeningAddChips,
    ScreeningFilterTile,
    ScreeningMoexControls,
    ScreeningPresetBar,
} from '@/pages/testing/components/screeningPipelineUi'
import {
    moexTestingPipelineFromPreset,
    UNIVERSE_FILTER_PRESET_META,
    type UniverseFilterPresetId,
} from '@/modules/robots/config/universeFilterPresets'

export type TestingPipelineCardProps = {
    pipelineMode: 'ALL' | 'ANY'
    onPipelineModeChange: (mode: 'ALL' | 'ANY') => void
    filters: PipelineFilter[]
    setFilters: Dispatch<SetStateAction<PipelineFilter[]>>
    onAddFilter: (t: PipelineFilterType) => void
    onRemoveFilter: (id: string) => void
    onConfigDirty: () => void
    universeRefreshMinutes?: number
    onUniverseRefreshMinutesChange?: (v: number) => void
    embedded?: boolean
    compact?: boolean
    className?: string
}

export function TestingPipelineCard({
    pipelineMode,
    onPipelineModeChange,
    filters,
    setFilters,
    onAddFilter,
    onRemoveFilter,
    onConfigDirty,
    universeRefreshMinutes = 0,
    onUniverseRefreshMinutesChange,
    embedded = false,
    compact = false,
    className = '',
}: TestingPipelineCardProps) {
    const [activePreset, setActivePreset] = useState<UniverseFilterPresetId | null>('moderate')
    const dirty = () => onConfigDirty()

    const applyPreset = (presetId: UniverseFilterPresetId) => {
        const preset = moexTestingPipelineFromPreset(presetId)
        onPipelineModeChange(preset.mode)
        setFilters(preset.filters)
        setActivePreset(presetId)
        dirty()
    }

    const renderFilterInputs = (f: PipelineFilter) => {
        if (f.type === 'security_status') return <input className="form-input screening-filter__input" value={f.eq ?? 'A'} disabled />
        if (f.type === 'trading_status') return <input className="form-input screening-filter__input" value={f.eq ?? 'T'} disabled />
        if (['volume', 'num_trades', 'capitalization'].includes(f.type)) {
            return (
                <input
                    className="form-input screening-filter__input"
                    type="number"
                    value={f.min ?? ''}
                    onChange={e => {
                        setFilters(prev =>
                            prev.map(x => (x.id === f.id ? { ...x, min: Number(e.target.value || 0) } : x)),
                        )
                        dirty()
                    }}
                />
            )
        }
        if (['spread', 'price_vs_open', 'opening_range'].includes(f.type)) {
            return (
                <input
                    className="form-input screening-filter__input"
                    type="number"
                    step="0.01"
                    value={f.max_percent ?? f.min_percent ?? ''}
                    onChange={e => {
                        const n = Number(e.target.value || 0)
                        setFilters(prev =>
                            prev.map(x => (x.id === f.id ? { ...x, max_percent: n, min_percent: n } : x)),
                        )
                        dirty()
                    }}
                />
            )
        }
        if (f.type === 'atr') {
            return (
                <div className="screening-filter__inline">
                    <input
                        className="form-input screening-filter__input"
                        type="number"
                        step="0.1"
                        placeholder="%"
                        value={f.min_percent ?? ''}
                        onChange={e => {
                            setFilters(prev =>
                                prev.map(x =>
                                    x.id === f.id ? { ...x, min_percent: Number(e.target.value || 0) } : x,
                                ),
                            )
                            dirty()
                        }}
                    />
                    <input
                        className="form-input screening-filter__input screening-filter__input--sm"
                        type="number"
                        placeholder="период"
                        value={f.period ?? 14}
                        onChange={e => {
                            setFilters(prev =>
                                prev.map(x =>
                                    x.id === f.id ? { ...x, period: Number(e.target.value || 14) } : x,
                                ),
                            )
                            dirty()
                        }}
                    />
                </div>
            )
        }
        if (f.type === 'gap') {
            return (
                <div className="screening-filter__inline">
                    <input
                        className="form-input screening-filter__input"
                        type="number"
                        step="0.1"
                        value={f.max_percent ?? ''}
                        onChange={e => {
                            setFilters(prev =>
                                prev.map(x =>
                                    x.id === f.id ? { ...x, max_percent: Number(e.target.value || 0) } : x,
                                ),
                            )
                            dirty()
                        }}
                    />
                    <Select
                        size="sm"
                        searchable={false}
                        options={[
                            { value: 'BOTH', label: 'Оба' },
                            { value: 'UP_ONLY', label: 'Вверх' },
                            { value: 'DOWN_ONLY', label: 'Вниз' },
                        ]}
                        value={f.direction || 'BOTH'}
                        onChange={v => {
                            setFilters(prev =>
                                prev.map(x =>
                                    x.id === f.id ? { ...x, direction: v as PipelineFilter['direction'] } : x,
                                ),
                            )
                            dirty()
                        }}
                    />
                </div>
            )
        }
        if (['allowed_tickers', 'excluded_tickers'].includes(f.type)) {
            return (
                <input
                    className="form-input screening-filter__input"
                    value={Array.isArray(f.list) ? f.list.join(', ') : ''}
                    onChange={e => {
                        setFilters(prev =>
                            prev.map(x => (x.id === f.id ? { ...x, list: parseTickers(e.target.value) } : x)),
                        )
                        dirty()
                    }}
                />
            )
        }
        if (f.type === 'min_step_ratio') {
            return (
                <input
                    className="form-input screening-filter__input"
                    type="number"
                    value={f.max_steps ?? ''}
                    onChange={e => {
                        setFilters(prev =>
                            prev.map(x =>
                                x.id === f.id ? { ...x, max_steps: Number(e.target.value || 0) } : x,
                            ),
                        )
                        dirty()
                    }}
                />
            )
        }
        if (f.type === 'turnover') {
            return (
                <input
                    className="form-input screening-filter__input"
                    type="number"
                    step="0.01"
                    value={f.min_percent ?? ''}
                    onChange={e => {
                        setFilters(prev =>
                            prev.map(x =>
                                x.id === f.id ? { ...x, min_percent: Number(e.target.value || 0) } : x,
                            ),
                        )
                        dirty()
                    }}
                />
            )
        }
        if (f.type === 'gap_retention') {
            return (
                <input
                    className="form-input screening-filter__input"
                    type="number"
                    step="0.01"
                    value={f.min_ratio ?? ''}
                    onChange={e => {
                        setFilters(prev =>
                            prev.map(x =>
                                x.id === f.id ? { ...x, min_ratio: Number(e.target.value || 0) } : x,
                            ),
                        )
                        dirty()
                    }}
                />
            )
        }
        return null
    }

    const presetHint = activePreset ? UNIVERSE_FILTER_PRESET_META[activePreset].hint : null

    const compactContent = (
        <div className="screening-pipeline">
            <ScreeningPresetBar activePreset={activePreset} onApply={applyPreset} hint={presetHint} />
            <ScreeningMoexControls
                pipelineMode={pipelineMode}
                onPipelineModeChange={onPipelineModeChange}
                universeRefreshMinutes={universeRefreshMinutes}
                onUniverseRefreshMinutesChange={onUniverseRefreshMinutesChange}
                onConfigDirty={onConfigDirty}
            />
            <div className="screening-filter-grid">
                {filters.map(f => {
                    const lockStatus = f.type === 'security_status' || f.type === 'trading_status'
                    return (
                        <ScreeningFilterTile
                            key={f.id}
                            label={FILTER_META[f.type].label}
                            locked={lockStatus}
                            onRemove={lockStatus ? undefined : () => onRemoveFilter(f.id)}
                        >
                            {renderFilterInputs(f)}
                        </ScreeningFilterTile>
                    )
                })}
            </div>
            <ScreeningAddChips
                items={(Object.keys(FILTER_META) as PipelineFilterType[])
                    .filter(t => !filters.some(f => f.type === t))
                    .map(t => ({ key: t, label: FILTER_META[t].label }))}
                onAdd={key => onAddFilter(key as PipelineFilterType)}
            />
        </div>
    )

    const legacyContent = (
        <>
            {!embedded && (
                <div className="pipeline-header">
                    <h3 className="card__section-title pipeline-title">
                        <span className="cyber-bracket">[</span>
                        УПРАВЛЕНИЕ ПАЙПЛАЙНОМ
                        <span className="cyber-bracket">]</span>
                    </h3>
                    <div className="pipeline-mode cyber-select-wrap">
                        <Select
                            searchable={false}
                            options={[
                                { value: 'ALL', label: 'Все условия' },
                                { value: 'ANY', label: 'Любое условие' },
                            ]}
                            value={pipelineMode}
                            onChange={v => onPipelineModeChange(v === 'ANY' ? 'ANY' : 'ALL')}
                        />
                    </div>
                </div>
            )}
            <ScreeningPresetBar activePreset={activePreset} onApply={applyPreset} />
            {embedded && (
                <ScreeningMoexControls
                    pipelineMode={pipelineMode}
                    onPipelineModeChange={onPipelineModeChange}
                    universeRefreshMinutes={universeRefreshMinutes}
                    onUniverseRefreshMinutesChange={onUniverseRefreshMinutesChange}
                    onConfigDirty={onConfigDirty}
                />
            )}
            <div className="pipeline-filter-grid">
                {filters.map(f => {
                    const lockStatus = f.type === 'security_status' || f.type === 'trading_status'
                    return (
                        <div key={f.id} className="form-group pipeline-filter-card">
                            <div className="pipeline-filter-row">
                                <strong className="pipeline-filter-label">{FILTER_META[f.type].label}:</strong>
                                <div className="pipeline-filter-inputs">{renderFilterInputs(f)}</div>
                                {!lockStatus && (
                                    <button
                                        type="button"
                                        className="screening-filter__remove"
                                        onClick={() => onRemoveFilter(f.id)}
                                    >
                                        ×
                                    </button>
                                )}
                            </div>
                        </div>
                    )
                })}
            </div>
            <ScreeningAddChips
                items={(Object.keys(FILTER_META) as PipelineFilterType[])
                    .filter(t => !filters.some(f => f.type === t))
                    .map(t => ({ key: t, label: FILTER_META[t].label }))}
                onAdd={key => onAddFilter(key as PipelineFilterType)}
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
