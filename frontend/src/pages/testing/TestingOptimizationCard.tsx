import React, { useState } from 'react'
import type {
    OptimizationBatchItem,
    OptimizationBatchStatusResponse,
    OptimizationFailedRunItem,
    OptimizationGoal,
    OptimizationMode,
    OptimizationParamSuggestion,
    OptimizationPlanCandidate,
    OptimizationRankItem,
} from '@/types/optimization'
import type { RecommendationFormActions } from '@/pages/testing/recommendationApply'
import { applyParamSummary, applySuggestedChanges } from '@/pages/testing/recommendationApply'
import {
    TestingBacktestHistoryCard,
    type TestingBacktestHistoryCardProps,
} from '@/pages/testing/TestingBacktestHistoryCard'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'

const GOAL_OPTIONS: Array<{ value: OptimizationGoal; label: string }> = [
    { value: 'balanced', label: 'Баланс' },
    { value: 'max_return', label: 'Доходность' },
    { value: 'min_drawdown', label: 'Просадка' },
    { value: 'max_sharpe', label: 'Sharpe' },
]

const OPT_TABS = [
    { id: 'rank' as const, label: 'Ранг' },
    { id: 'plan' as const, label: 'Сетка' },
    { id: 'batch' as const, label: 'Прогресс' },
    { id: 'history' as const, label: 'История' },
]

function fmtPct(v: number | null | undefined): string {
    if (v == null || Number.isNaN(v)) return '—'
    return `${v.toFixed(2)}%`
}

function fmtNum(v: number | null | undefined, digits = 2): string {
    if (v == null || Number.isNaN(v)) return '—'
    return v.toFixed(digits)
}

function paramPreview(summary: Record<string, unknown>): string {
    const parts = Object.entries(summary)
        .slice(0, 6)
        .map(([k, v]) => `${k.split('.').pop()}=${String(v)}`)
    return parts.join(', ') || '—'
}

function ParamChips({ summary, max = 2 }: { summary: Record<string, unknown>; max?: number }) {
    const entries = Object.entries(summary)
    if (!entries.length) return <span className="testing-opt-muted">—</span>
    const visible = entries.slice(0, max)
    const rest = entries.length - visible.length
    return (
        <div className="testing-opt-param-chips" title={paramPreview(summary)}>
            {visible.map(([k, v]) => (
                <span key={k} className="testing-opt-param-chip">
                    <span className="testing-opt-param-chip__key">{k.split('.').pop()}</span>
                    <span className="testing-opt-param-chip__val">{String(v)}</span>
                </span>
            ))}
            {rest > 0 && <span className="testing-opt-param-chip testing-opt-param-chip--more">+{rest}</span>}
        </div>
    )
}

function metricClass(v: number | null | undefined, invert = false): string {
    if (v == null || Number.isNaN(v)) return 'testing-opt-metric'
    const up = invert ? v <= 0 : v >= 0
    return `testing-opt-metric ${up ? 'color-up' : 'color-down'}`
}

function rejectsPreview(topRejects: Record<string, number> | undefined): string {
    if (!topRejects || !Object.keys(topRejects).length) return '—'
    return Object.entries(topRejects)
        .slice(0, 3)
        .map(([k, v]) => `${k} ×${v}`)
        .join('; ')
}

function suggestionsPreview(changes: OptimizationParamSuggestion[] | undefined): string {
    if (!changes?.length) return '—'
    return changes
        .slice(0, 2)
        .map(ch => `${ch.path.split('.').pop()}: ${String(ch.current_value ?? '?')} → ${String(ch.suggested_value ?? '?')}`)
        .join('; ')
}

type FailedRunRowProps = {
    item: OptimizationFailedRunItem
    onApply?: (changes: OptimizationParamSuggestion[]) => void
    onOpenRun?: (runId: number) => void
}

function FailedRunRow({ item, onApply, onOpenRun }: FailedRunRowProps) {
    const canApply = (item.suggested_changes?.length ?? 0) > 0
    const reason = item.failure_category === 'no_universe' ? 'Нет бумаг' : item.failure_category
    return (
        <tr className="testing-opt-table__failed">
            <td>
                <span className="testing-opt-run-id">#{item.run_id}</span>
            </td>
            <td>
                <span className="badge badge--warn testing-opt-badge">{reason}</span>
            </td>
            <td className="testing-opt-table__params" title={rejectsPreview(item.top_rejects)}>
                {rejectsPreview(item.top_rejects)}
            </td>
            <td className="testing-opt-table__params" title={suggestionsPreview(item.suggested_changes)}>
                {suggestionsPreview(item.suggested_changes)}
            </td>
            <td className="testing-opt-table__actions">
                {onOpenRun && (
                    <Button size="sm" variant="ghost" onClick={() => onOpenRun(item.run_id)}>
                        Открыть
                    </Button>
                )}
                {canApply && onApply && (
                    <Button size="sm" variant="primary" onClick={() => onApply(item.suggested_changes)}>
                        Смягчить
                    </Button>
                )}
            </td>
        </tr>
    )
}

type BatchFailedRowProps = {
    item: OptimizationBatchItem
    onApply?: (changes: OptimizationParamSuggestion[]) => void
    onOpenRun?: (runId: number) => void
}

function BatchFailedRow({ item, onApply, onOpenRun }: BatchFailedRowProps) {
    const isFailed = item.status === 'failed'
    const changes = item.suggested_changes ?? []
    const statusClass =
        item.status === 'success'
            ? 'badge--up'
            : item.status === 'failed'
              ? 'badge--down'
              : 'badge--neutral'
    return (
        <tr className={isFailed ? 'testing-opt-table__failed' : undefined}>
            <td>#{item.candidate_index}</td>
            <td>
                {item.run_id != null ? (
                    <span className="testing-opt-run-id">#{item.run_id}</span>
                ) : (
                    <span className="testing-opt-muted">—</span>
                )}
            </td>
            <td>
                <span className={`badge testing-opt-badge ${statusClass}`}>{item.status}</span>
            </td>
            <td className="testing-opt-metric testing-opt-metric--num">{fmtNum(item.score, 3)}</td>
            <td className={metricClass(item.total_return_percent)}>{fmtPct(item.total_return_percent)}</td>
            <td className="testing-opt-table__params">
                {isFailed ? (
                    <>
                        <span title={item.failure_summary ?? item.error_message ?? undefined}>
                            {item.failure_category === 'no_universe' ? 'Нет бумаг' : item.error_message ?? item.status}
                        </span>
                        {Object.keys(item.top_rejects ?? {}).length > 0 && (
                            <div className="testing-opt-muted testing-opt-table__sub">{rejectsPreview(item.top_rejects)}</div>
                        )}
                    </>
                ) : (
                    <ParamChips summary={item.param_summary} />
                )}
            </td>
            <td className="testing-opt-table__actions">
                {item.run_id != null && onOpenRun && (
                    <Button size="sm" variant="ghost" onClick={() => onOpenRun(item.run_id!)}>
                        {isFailed ? 'Открыть' : 'Анализ'}
                    </Button>
                )}
                {isFailed && changes.length > 0 && onApply && (
                    <Button size="sm" variant="primary" onClick={() => onApply(changes)}>
                        Смягчить
                    </Button>
                )}
            </td>
        </tr>
    )
}

type RankRowProps = {
    item: OptimizationRankItem
    onApply?: (item: OptimizationRankItem) => void
    onOpenRun?: (runId: number) => void
}

function RankRow({ item, onApply, onOpenRun }: RankRowProps) {
    const canApply = Object.keys(item.param_summary).length > 0
    return (
        <tr>
            <td>
                <span className="testing-opt-rank">#{item.rank}</span>
                <span className="testing-opt-run-id">run {item.run_id}</span>
            </td>
            <td className="testing-opt-metric testing-opt-metric--num">{fmtNum(item.score, 3)}</td>
            <td className={metricClass(item.total_return_percent)}>{fmtPct(item.total_return_percent)}</td>
            <td className={metricClass(item.max_drawdown_percent, true)}>{fmtPct(item.max_drawdown_percent)}</td>
            <td className="testing-opt-metric testing-opt-metric--num">{fmtNum(item.sharpe_ratio)}</td>
            <td className="testing-opt-metric testing-opt-metric--num">{item.trades_total ?? '—'}</td>
            <td className="testing-opt-table__params">
                <ParamChips summary={item.param_summary} />
            </td>
            <td className="testing-opt-table__actions">
                {onOpenRun && (
                    <Button size="sm" variant="secondary" onClick={() => onOpenRun(item.run_id)}>
                        Анализ
                    </Button>
                )}
                {canApply && onApply && (
                    <Button size="sm" variant="primary" onClick={() => onApply(item)}>
                        В форму
                    </Button>
                )}
            </td>
        </tr>
    )
}

type PlanRowProps = {
    item: OptimizationPlanCandidate
    onApply?: (item: OptimizationPlanCandidate) => void
}

function PlanRow({ item, onApply }: PlanRowProps) {
    return (
        <tr>
            <td>
                <span className="testing-opt-rank">#{item.index}</span>
            </td>
            <td className="testing-opt-table__params">
                <ParamChips summary={item.param_summary} max={3} />
            </td>
            <td className="testing-opt-table__actions">
                {onApply && (
                    <Button size="sm" variant="ghost" onClick={() => onApply(item)}>
                        В форму
                    </Button>
                )}
            </td>
        </tr>
    )
}

export type TestingOptimizationCardProps = {
    goal: OptimizationGoal
    onGoalChange: (g: OptimizationGoal) => void
    rankData: import('@/types/optimization').OptimizationRankResponse | null
    sessionFailures?: OptimizationFailedRunItem[]
    robotId?: number | null
    planData: import('@/types/optimization').OptimizationPlanResponse | null
    batchData: OptimizationBatchStatusResponse | null
    loadingRank: boolean
    loadingPlan: boolean
    startingBatch: boolean
    error: string | null
    onRefreshRank: () => void
    onLoadPlan: (mode: OptimizationMode) => void
    onRunBatch: (mode: OptimizationMode) => void
    onCancelBatch?: () => void
    canRunBatch?: boolean
    formActions: RecommendationFormActions
    onApplied?: () => void
    embedded?: boolean
    onOpenBacktestRun?: (runId: number) => void | Promise<void>
    history?: Omit<TestingBacktestHistoryCardProps, 'embedded' | 'showCompare' | 'onOpenRun'> & {
        onOpenRun: (r: import('@/types/robot').RobotBacktestHistoryItem) => void | Promise<void>
    }
}

export function TestingOptimizationCard({
    goal,
    onGoalChange,
    rankData,
    sessionFailures = [],
    robotId = null,
    planData,
    batchData,
    loadingRank,
    loadingPlan,
    startingBatch,
    error,
    onRefreshRank,
    onLoadPlan,
    onRunBatch,
    onCancelBatch,
    canRunBatch = true,
    formActions,
    onApplied,
    embedded = false,
    onOpenBacktestRun,
    history,
}: TestingOptimizationCardProps) {
    const [tab, setTab] = useState<'rank' | 'plan' | 'batch' | 'history'>('rank')
    const batchActive = batchData != null && (batchData.status === 'running' || batchData.status === 'queued')
    const displayRanked =
        batchData?.status === 'completed' && batchData.ranked.length > 0
            ? batchData.ranked
            : rankData?.ranked ?? []
    const displayWarnings =
        batchData?.overfitting_warnings?.length
            ? batchData.overfitting_warnings
            : rankData?.overfitting_warnings ?? []

    const displayFailed =
        rankData?.failed_runs?.length
            ? rankData.failed_runs
            : sessionFailures.length
              ? sessionFailures
              : (batchData?.items ?? [])
                    .filter(it => it.status === 'failed' && (it.failure_category || it.suggested_changes?.length))
                    .map(
                        (it): OptimizationFailedRunItem => ({
                            run_id: it.run_id ?? it.candidate_index,
                            error_message: it.error_message,
                            failure_category: it.failure_category ?? 'unknown',
                            failure_summary: it.failure_summary,
                            top_rejects: it.top_rejects ?? {},
                            suggested_changes: it.suggested_changes ?? [],
                            param_summary: it.param_summary,
                        }),
                    )

    const handleApplyRank = (item: OptimizationRankItem) => {
        const { applied } = applyParamSummary(item.param_summary, formActions)
        if (applied > 0) onApplied?.()
    }

    const handleApplySuggestions = (changes: OptimizationParamSuggestion[]) => {
        const { applied } = applySuggestedChanges(changes, formActions)
        if (applied > 0) onApplied?.()
    }

    const handleApplyPlan = (item: OptimizationPlanCandidate) => {
        const { applied } = applyParamSummary(item.param_summary, formActions)
        if (applied > 0) onApplied?.()
    }

    const content = (
        <div className="testing-opt">
            <div className="testing-opt__head">
                <div className="testing-opt__goal">
                    <span className="testing-opt__goal-label">Цель</span>
                    <Select
                        size="sm"
                        searchable={false}
                        className="testing-opt__goal-select"
                        options={GOAL_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
                        value={goal}
                        onChange={v => onGoalChange(v as OptimizationGoal)}
                    />
                </div>

                <nav className="testing-opt__tabs" role="tablist" aria-label="Разделы оптимизации">
                    {OPT_TABS.filter(t => t.id !== 'batch' || batchData).filter(t => t.id !== 'history' || history).map(
                        t => (
                            <button
                                key={t.id}
                                type="button"
                                role="tab"
                                aria-selected={tab === t.id}
                                className={`testing-opt__tab${tab === t.id ? ' testing-opt__tab--active' : ''}`}
                                onClick={() => setTab(t.id)}
                            >
                                {t.label}
                                {t.id === 'batch' && batchData && (
                                    <span className="testing-opt__tab-badge">{batchData.progress.percent}%</span>
                                )}
                            </button>
                        ),
                    )}
                </nav>

                <div className="testing-opt__actions">
                    {tab === 'rank' && (
                        <Button size="sm" variant="ghost" loading={loadingRank} onClick={onRefreshRank}>
                            Обновить
                        </Button>
                    )}
                    {tab === 'history' && history && (
                        <Button
                            size="sm"
                            variant="ghost"
                            loading={history.historyLoading}
                            onClick={() => void history.onRefresh()}
                        >
                            Обновить
                        </Button>
                    )}
                    {tab === 'plan' && (
                        <>
                            <Button
                                size="sm"
                                variant="ghost"
                                loading={loadingPlan}
                                onClick={() => onLoadPlan('speed')}
                            >
                                Speed
                            </Button>
                            <Button
                                size="sm"
                                variant="ghost"
                                loading={loadingPlan}
                                onClick={() => onLoadPlan('full')}
                            >
                                Full
                            </Button>
                        </>
                    )}
                </div>
            </div>

            {error && <div className="testing-opt__alert testing-opt__alert--error">{error}</div>}

            {!robotId && tab !== 'history' && (
                <p className="testing-opt__note">
                    Робот не выбран — только неуспешные прогоны. Для сетки выберите робота type=2.
                </p>
            )}

            {batchData && (
                <div className={`testing-opt-batch${batchActive ? ' testing-opt-batch--active' : ''}`}>
                    <div className="testing-opt-batch__meta">
                        <span className="testing-opt-batch__id">Пакет #{batchData.batch_id}</span>
                        <span className={`badge testing-opt-badge ${batchActive ? 'badge--cyan' : 'badge--neutral'}`}>
                            {batchData.status}
                        </span>
                        <span className="testing-opt-batch__progress">
                            {batchData.progress.done}/{batchData.total_candidates}
                        </span>
                        {batchActive && onCancelBatch && (
                            <Button size="sm" variant="ghost" onClick={onCancelBatch}>
                                Отмена
                            </Button>
                        )}
                    </div>
                    <div className="testing-opt-batch__bar" aria-hidden>
                        <div
                            className="testing-opt-batch__bar-fill"
                            style={{ width: `${Math.min(100, batchData.progress.percent)}%` }}
                        />
                    </div>
                    <div className="testing-opt-batch__kpis">
                        <span>очередь {batchData.progress.queued}</span>
                        <span>run {batchData.progress.running}</span>
                        <span className="color-up">ok {batchData.progress.success}</span>
                        <span className="color-down">err {batchData.progress.failed}</span>
                    </div>
                </div>
            )}

            <div className="testing-opt__body">
                {tab === 'rank' && (
                    <>
                        {displayWarnings.length > 0 && (
                            <ul className="testing-opt-warnings">
                                {displayWarnings.map(w => (
                                    <li key={w}>{w}</li>
                                ))}
                            </ul>
                        )}
                        {loadingRank && !displayRanked.length && !displayFailed.length ? (
                            <p className="testing-opt-empty">Загрузка ранжирования…</p>
                        ) : !displayRanked.length && !displayFailed.length ? (
                            <p className="testing-opt-empty">
                                Нет прогонов для ранжирования. Запустите сетку или смягчите фильтры universe.
                            </p>
                        ) : (
                            <>
                                {displayRanked.length > 0 && (
                                    <div className="testing-opt-table-wrap">
                                        <table className="testing-opt-table testing-opt-table--dense">
                                            <thead>
                                                <tr>
                                                    <th>Ранг</th>
                                                    <th className="testing-opt-table__num">Score</th>
                                                    <th className="testing-opt-table__num">Return</th>
                                                    <th className="testing-opt-table__num">DD</th>
                                                    <th className="testing-opt-table__num">Sharpe</th>
                                                    <th className="testing-opt-table__num">Сделки</th>
                                                    <th>Параметры</th>
                                                    <th />
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {displayRanked.map(row => (
                                                    <RankRow
                                                        key={row.run_id}
                                                        item={row}
                                                        onApply={handleApplyRank}
                                                        onOpenRun={onOpenBacktestRun}
                                                    />
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                                {displayFailed.length > 0 && (
                                    <details className="testing-opt-failed" open={displayFailed.length <= 4}>
                                        <summary className="testing-opt-failed__summary">
                                            <span>Неуспешные прогоны</span>
                                            <span className="badge badge--warn testing-opt-badge">{displayFailed.length}</span>
                                            <span className="testing-opt-failed__hint">смягчите фильтры universe</span>
                                        </summary>
                                        <div className="testing-opt-table-wrap">
                                            <table className="testing-opt-table testing-opt-table--dense">
                                                <thead>
                                                    <tr>
                                                        <th>Run</th>
                                                        <th>Причина</th>
                                                        <th>Отклонения</th>
                                                        <th>Рекомендации</th>
                                                        <th />
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {displayFailed.map(row => (
                                                        <FailedRunRow
                                                            key={row.run_id}
                                                            item={row}
                                                            onApply={handleApplySuggestions}
                                                            onOpenRun={onOpenBacktestRun}
                                                        />
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </details>
                                )}
                            </>
                        )}
                    </>
                )}

                {tab === 'plan' && (
                    <>
                        {planData?.note && <p className="testing-opt__note">{planData.note}</p>}
                        <div className="testing-opt-plan-actions">
                            <Button
                                size="sm"
                                variant="primary"
                                loading={startingBatch}
                                disabled={!canRunBatch || batchActive}
                                onClick={() => onRunBatch('speed')}
                            >
                                Запуск speed
                            </Button>
                            <Button
                                size="sm"
                                variant="ghost"
                                loading={startingBatch}
                                disabled={!canRunBatch || batchActive}
                                onClick={() => onRunBatch('full')}
                            >
                                Запуск full
                            </Button>
                            {!canRunBatch && (
                                <span className="testing-opt-muted">Нужны робот и период</span>
                            )}
                            {batchActive && (
                                <span className="testing-opt-muted">Дождитесь пакета</span>
                            )}
                        </div>
                        {!planData?.candidates.length ? (
                            <p className="testing-opt-empty">
                                Нажмите Speed / Full в шапке, чтобы сгенерировать кандидатов.
                            </p>
                        ) : (
                            <div className="testing-opt-table-wrap">
                                <table className="testing-opt-table testing-opt-table--dense">
                                    <thead>
                                        <tr>
                                            <th>#</th>
                                            <th>Параметры</th>
                                            <th />
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {planData.candidates.map(row => (
                                            <PlanRow key={row.index} item={row} onApply={handleApplyPlan} />
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </>
                )}

                {tab === 'history' && history && (
                    <TestingBacktestHistoryCard {...history} embedded showCompare={false} />
                )}

                {tab === 'batch' && batchData && (
                    <div className="testing-opt-table-wrap">
                        <table className="testing-opt-table testing-opt-table--dense">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Run</th>
                                    <th>Статус</th>
                                    <th className="testing-opt-table__num">Score</th>
                                    <th className="testing-opt-table__num">Return</th>
                                    <th>Детали</th>
                                    <th />
                                </tr>
                            </thead>
                            <tbody>
                                {batchData.items.map(item => (
                                    <BatchFailedRow
                                        key={item.candidate_index}
                                        item={item}
                                        onApply={handleApplySuggestions}
                                        onOpenRun={onOpenBacktestRun}
                                    />
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    )

    if (embedded) return content

    return <div className="testing-optimization-card">{content}</div>
}
