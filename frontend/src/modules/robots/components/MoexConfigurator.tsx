import React from 'react'
import { Select } from '@/components/ui/Select'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { SnapshotFiltersEditor } from '@/pages/robots/components/SnapshotFiltersEditor'
import { GrainSeedP1ScreeningParams } from '@/pages/robots/GrainSeedP1ScreeningParams'
import { P1ScreeningFieldSections } from '@/modules/robots/components/P1ScreeningFieldSections'
import { TRADING_UNIVERSE_MODE_OPTIONS, type UniverseMode } from '@/utils/universeMode'
import { normalizeSignalInterval } from '@/pages/testing/testingPipeline'
import type { PipelineFilter } from '@/pages/robots/pipelineFilterMeta'
import type { ValidationIssue } from '@/modules/robots/config/validate/collectIssues'
import type { UniverseFilterPresetId } from '@/modules/robots/config/universeFilterPresets'

export type MoexConfiguratorStage = 'p1' | 'p2'

export type MoexPreviewRow = {
    ticker: string
    result: string
    reason?: string
    value_today?: number
    gap_percent?: number | null
    spread_percent?: number | null
    atr_percent?: number | null
}

export type MoexConfiguratorProps = {
    stage: MoexConfiguratorStage
    universeMode: UniverseMode
    onUniverseModeChange: (raw: unknown) => void
    fixedTickersText: string
    onFixedTickersTextChange: (v: string) => void
    historicalInterval: string
    onHistoricalIntervalChange: (v: string) => void
    historicalLookbackDays: number
    onHistoricalLookbackDaysChange: (v: number) => void
    historicalDailyAtMsk: string
    onHistoricalDailyAtMskChange: (v: string) => void
    paperRefreshMinutes: number
    onPaperRefreshMinutesChange: (v: number) => void
    pipelineMode: 'ALL' | 'ANY'
    onPipelineModeChange: (v: 'ALL' | 'ANY') => void
    onApplyPreset: (preset: UniverseFilterPresetId) => void
    filters: PipelineFilter[]
    onFiltersChange: (filters: PipelineFilter[]) => void
    isGrainSeed: boolean
    strategyParams: Record<string, unknown>
    onStrategyParamChange: (key: string, value: number) => void
    onAtrFilterSync?: (period: number, minPercent: number) => void
    preview?: {
        total_checked: number
        passed: number
        rejected: number
        sample: MoexPreviewRow[]
    } | null
    universeFieldIssues?: ValidationIssue[]
    onConfigDirty?: () => void
}

function fieldIssues(issues: ValidationIssue[] | undefined, field: string): ValidationIssue[] {
    return (issues || []).filter(i => i.field === field)
}

export function MoexConfigurator({
    stage,
    universeMode,
    onUniverseModeChange,
    fixedTickersText,
    onFixedTickersTextChange,
    historicalInterval,
    onHistoricalIntervalChange,
    historicalLookbackDays,
    onHistoricalLookbackDaysChange,
    historicalDailyAtMsk,
    onHistoricalDailyAtMskChange,
    paperRefreshMinutes,
    onPaperRefreshMinutesChange,
    pipelineMode,
    onPipelineModeChange,
    onApplyPreset,
    filters,
    onFiltersChange,
    isGrainSeed,
    strategyParams,
    onStrategyParamChange,
    onAtrFilterSync,
    preview,
    universeFieldIssues,
    onConfigDirty,
}: MoexConfiguratorProps) {
    const dirty = () => onConfigDirty?.()

    if (stage === 'p1') {
        return (
            <>
                <p className="form-hint">
                    Подбор кандидатов для торгов. Результат — пул кандидатов.
                    Пересчёт по расписанию до открытия сессии.
                </p>
                <P1ScreeningFieldSections
                    market="moex"
                    values={{
                        lookbackDays: historicalLookbackDays,
                        candleInterval: historicalInterval,
                        refreshDailyAtMsk: historicalDailyAtMsk,
                    }}
                    handlers={{
                        onLookbackDaysChange: onHistoricalLookbackDaysChange,
                        onCandleIntervalChange: v => onHistoricalIntervalChange(normalizeSignalInterval(v)),
                        onRefreshDailyAtMskChange: onHistoricalDailyAtMskChange,
                        onDirty: dirty,
                    }}
                />
                {isGrainSeed ? (
                    <GrainSeedP1ScreeningParams
                        params={strategyParams}
                        onParamChange={(key, value) => {
                            onStrategyParamChange(key, value)
                            dirty()
                        }}
                        onAtrFilterSync={onAtrFilterSync}
                    />
                ) : (
                    <SnapshotFiltersEditor
                        scope="historical"
                        filters={filters}
                        onFiltersChange={v => {
                            onFiltersChange(v)
                            dirty()
                        }}
                        showPipelineMode={false}
                        showPresets={false}
                        sectionTitle="Фильтры отбора по истории"
                    />
                )}
            </>
        )
    }

    return (
        <>
            {universeMode === 'fixed' ? (
                <>
                    <p className="form-hint">
                        Фиксированный список тикеров — поиск идей и отбор по снапшоту не используются.
                    </p>
                    <div className="form-group">
                        <label className="form-label">
                            Режим universe
                            <FormLabelTooltip text="Фиксированный список TQBR без автоматического отбора по MOEX и DMS." />
                        </label>
                        <div className="cyber-select-wrap">
                            <Select
                                options={TRADING_UNIVERSE_MODE_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
                                value={universeMode === 'dms_pipeline' ? 'tqbr_scan' : universeMode}
                                onChange={v => {
                                    onUniverseModeChange(v)
                                    dirty()
                                }}
                            />
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Тикеры TQBR</label>
                        <textarea
                            className="form-input cyber-input"
                            rows={3}
                            placeholder="SBER, GAZP, LKOH"
                            value={fixedTickersText}
                            onChange={e => {
                                onFixedTickersTextChange(e.target.value)
                                dirty()
                            }}
                        />
                        <p className="field-hint-below">Через запятую или с новой строки.</p>
                        {fieldIssues(universeFieldIssues, 'universe').map(issue => (
                            <p key={issue.id} className="field-inline-error">{issue.message}</p>
                        ))}
                    </div>
                </>
            ) : (
                <>
                    <p className="form-hint">
                        Отбор по снапшоту DMS в торговую сессию. Результат — список FIGI для торговли.
                        Пересчёт по интервалу в сессии или по кнопке «Запустить».
                    </p>
                    <div className="form-row">
                        <div className="form-group">
                            <label className="form-label">
                                Режим universe
                                <FormLabelTooltip text="Источник universe: скан TQBR, pipeline MOEX+DMS или фиксированный список." />
                            </label>
                            <div className="cyber-select-wrap">
                                <Select
                                    options={TRADING_UNIVERSE_MODE_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
                                    value={universeMode === 'dms_pipeline' ? 'tqbr_scan' : universeMode}
                                    onChange={v => {
                                        onUniverseModeChange(v)
                                        dirty()
                                    }}
                                />
                            </div>
                        </div>
                        <div className="form-group">
                            <label className="form-label">
                                Пересчёт отбора (мин, в сессии)
                                <FormLabelTooltip text="Интервал автоматического пересчёта в торговую сессию. 0 — только по кнопке «Запустить»." />
                            </label>
                            <input
                                className="form-input cyber-input"
                                type="number"
                                min={0}
                                max={1440}
                                value={paperRefreshMinutes}
                                onChange={e => {
                                    onPaperRefreshMinutesChange(Math.max(0, Number(e.target.value || 0)))
                                    dirty()
                                }}
                            />
                        </div>
                        <div className="form-group">
                            <label className="form-label">
                                Режим фильтров
                                <FormLabelTooltip text="ALL — все фильтры должны пройти; ANY — достаточно одного." />
                            </label>
                            <SegmentedControl
                                options={[
                                    { value: 'ALL', label: 'Все (AND)' },
                                    { value: 'ANY', label: 'Любой (OR)' },
                                ]}
                                value={pipelineMode}
                                onChange={v => {
                                    onPipelineModeChange(v as 'ALL' | 'ANY')
                                    dirty()
                                }}
                                aria-label="Режим фильтров"
                            />
                        </div>
                    </div>
                    <SnapshotFiltersEditor
                        scope="paper"
                        filters={filters}
                        pipelineMode={pipelineMode}
                        onPipelineModeChange={onPipelineModeChange}
                        onFiltersChange={v => {
                            onFiltersChange(v)
                            dirty()
                        }}
                        onApplyPreset={onApplyPreset}
                        showPipelineMode={false}
                    />
                </>
            )}

            {preview && universeMode !== 'fixed' && (
                <div style={{ marginTop: 12 }}>
                    <div className="form-hint" style={{ marginBottom: 8 }}>
                        Проверено: {preview.total_checked} · Прошли: {preview.passed} · Отклонено: {preview.rejected}
                    </div>
                    <DataTable
                        columns={[
                            { key: 'ticker', header: 'Тикер', sortable: true } as Column<MoexPreviewRow>,
                            { key: 'result', header: 'Результат', sortable: true } as Column<MoexPreviewRow>,
                            {
                                key: 'reason',
                                header: 'Причина',
                                sortable: true,
                                render: (r: MoexPreviewRow) => r.reason || '—',
                            } as Column<MoexPreviewRow>,
                            {
                                key: 'value_today',
                                header: 'Объем (руб)',
                                align: 'right',
                                render: (r: MoexPreviewRow) => Number(r.value_today || 0).toLocaleString('ru-RU'),
                            } as Column<MoexPreviewRow>,
                            {
                                key: 'gap_percent',
                                header: 'Гэп %',
                                align: 'right',
                                render: (r: MoexPreviewRow) =>
                                    r.gap_percent != null ? Number(r.gap_percent).toFixed(2) : '—',
                            } as Column<MoexPreviewRow>,
                            {
                                key: 'spread_percent',
                                header: 'Спред %',
                                align: 'right',
                                render: (r: MoexPreviewRow) =>
                                    r.spread_percent != null ? Number(r.spread_percent).toFixed(3) : '—',
                            } as Column<MoexPreviewRow>,
                            {
                                key: 'atr_percent',
                                header: 'ATR %',
                                align: 'right',
                                render: (r: MoexPreviewRow) =>
                                    r.atr_percent != null ? Number(r.atr_percent).toFixed(2) : '—',
                            } as Column<MoexPreviewRow>,
                        ]}
                        data={preview.sample || []}
                        keyField="ticker"
                        emptyText="Нет данных preview"
                        maxHeight={260}
                    />
                </div>
            )}
        </>
    )
}
