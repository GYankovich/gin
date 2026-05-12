import React, { type Dispatch, type SetStateAction } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import {
    FILTER_META,
    type PipelineFilter,
    type PipelineFilterType,
} from '@/pages/testing/testingPipeline'
import { parseTickers } from '@/pages/testing/testingUtils'

export type TestingPipelineCardProps = {
    pipelineMode: 'ALL' | 'ANY'
    onPipelineModeChange: (mode: 'ALL' | 'ANY') => void
    filters: PipelineFilter[]
    setFilters: Dispatch<SetStateAction<PipelineFilter[]>>
    onAddFilter: (t: PipelineFilterType) => void
    onRemoveFilter: (id: string) => void
    onConfigDirty: () => void
}

export function TestingPipelineCard({
    pipelineMode,
    onPipelineModeChange,
    filters,
    setFilters,
    onAddFilter,
    onRemoveFilter,
    onConfigDirty,
}: TestingPipelineCardProps) {
    const dirty = () => onConfigDirty()

    return (
        <Card className="mb-6 pipeline-card">
            <div className="pipeline-header">
                <h3 className="card__section-title pipeline-title">
                    <span className="cyber-bracket">[</span>
                    УПРАВЛЕНИЕ ПАЙПЛАЙНОМ
                    <span className="cyber-bracket">]</span>
                </h3>
                <div className="pipeline-mode">
                    <span>Режим:</span>
                    <Select
                        options={[
                            { value: 'ALL', label: 'Все условия' },
                            { value: 'ANY', label: 'Любое условие' },
                        ]}
                        value={pipelineMode}
                        onChange={v => onPipelineModeChange(v === 'ANY' ? 'ANY' : 'ALL')}
                    />
                </div>
            </div>
            {filters.map(f => {
                const lockStatus = f.type === 'security_status' || f.type === 'trading_status'
                return (
                    <div key={f.id} className="form-group pipeline-filter-card">
                        <div className="pipeline-filter-row">
                            <strong className="pipeline-filter-label">{FILTER_META[f.type].label}:</strong>
                            <div className="pipeline-filter-inputs">
                                {f.type === 'security_status' && <input className="form-input" value={f.eq ?? 'A'} disabled />}
                                {f.type === 'trading_status' && <input className="form-input" value={f.eq ?? 'T'} disabled />}
                                {['volume', 'num_trades', 'capitalization'].includes(f.type) && (
                                    <input
                                        className="form-input"
                                        type="number"
                                        value={f.min ?? ''}
                                        onChange={e => {
                                            setFilters(prev =>
                                                prev.map(x => (x.id === f.id ? { ...x, min: Number(e.target.value || 0) } : x)),
                                            )
                                            dirty()
                                        }}
                                    />
                                )}
                                {['spread', 'price_vs_open', 'opening_range'].includes(f.type) && (
                                    <input
                                        className="form-input"
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
                                )}
                                {f.type === 'atr' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input
                                            className="form-input"
                                            type="number"
                                            step="0.1"
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
                                            className="form-input"
                                            type="number"
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
                                )}
                                {f.type === 'gap' && (
                                    <div className="form-row pipeline-inline-row">
                                        <input
                                            className="form-input"
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
                                            options={[
                                                { value: 'BOTH', label: 'Оба направления' },
                                                { value: 'UP_ONLY', label: 'Только вверх' },
                                                { value: 'DOWN_ONLY', label: 'Только вниз' },
                                            ]}
                                            value={f.direction || 'BOTH'}
                                            onChange={v => {
                                                setFilters(prev =>
                                                    prev.map(x =>
                                                        x.id === f.id
                                                            ? { ...x, direction: v as PipelineFilter['direction'] }
                                                            : x,
                                                    ),
                                                )
                                                dirty()
                                            }}
                                        />
                                    </div>
                                )}
                                {['allowed_tickers', 'excluded_tickers'].includes(f.type) && (
                                    <input
                                        className="form-input"
                                        value={Array.isArray(f.list) ? f.list.join(', ') : ''}
                                        onChange={e => {
                                            setFilters(prev =>
                                                prev.map(x =>
                                                    x.id === f.id ? { ...x, list: parseTickers(e.target.value) } : x,
                                                ),
                                            )
                                            dirty()
                                        }}
                                    />
                                )}
                                {f.type === 'min_step_ratio' && (
                                    <input
                                        className="form-input"
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
                                )}
                                {f.type === 'turnover' && (
                                    <input
                                        className="form-input"
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
                                )}
                                {f.type === 'gap_retention' && (
                                    <input
                                        className="form-input"
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
                                )}
                            </div>
                            {!lockStatus && (
                                <Button size="sm" variant="ghost" className="pipeline-delete-btn" onClick={() => onRemoveFilter(f.id)}>
                                    ×
                                </Button>
                            )}
                        </div>
                    </div>
                )
            })}
            <div className="pipeline-chip-list">
                {(Object.keys(FILTER_META) as PipelineFilterType[])
                    .filter(t => !filters.some(f => f.type === t))
                    .map(t => (
                        <Button key={t} size="sm" variant="ghost" onClick={() => onAddFilter(t)}>
                            + {FILTER_META[t].label}
                        </Button>
                    ))}
            </div>
        </Card>
    )
}
