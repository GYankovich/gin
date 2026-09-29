import React from 'react'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { useRobotV2Optimization } from '@/pages/robots-v2/hooks/useRobotV2Optimization'
import type { OptimizationGoal, OptimizationMode } from '@/types/optimization'

const GOAL_OPTIONS: Array<{ value: OptimizationGoal; label: string }> = [
    { value: 'balanced', label: 'Баланс' },
    { value: 'max_return', label: 'Доходность' },
    { value: 'min_drawdown', label: 'Просадка' },
    { value: 'max_sharpe', label: 'Sharpe' },
]

type Props = {
    robotId: number
    fromDate: string
    toDate: string
    initialCapital: number
    onOpenRun?: (runId: number) => void
    disabled?: boolean
}

function fmtPct(v: number | null | undefined): string {
    if (v == null || Number.isNaN(v)) return '—'
    return `${v.toFixed(2)}%`
}

export function RobotV2OptimizationCard({
    robotId,
    fromDate,
    toDate,
    initialCapital,
    onOpenRun,
    disabled = false,
}: Props) {
    const opt = useRobotV2Optimization(robotId)
    const batchActive = opt.batchData?.status === 'running' || opt.batchData?.status === 'queued'

    const start = async (mode: OptimizationMode) => {
        await opt.runBatch(mode, { fromDate, toDate, initialCapital })
    }

    return (
        <Card className="dashboard-totals-card robots-v2-opt-card">
            <div className="robots-v2-opt-card__head">
                <h3 className="robots-v2-section-title">Оптимизация</h3>
                <Select
                    value={opt.goal}
                    onChange={v => opt.setGoal(v as OptimizationGoal)}
                    options={GOAL_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
                    disabled={disabled || batchActive}
                />
            </div>
            <p className="robots-v2-hint">
                Ранжирование завершённых бэктестов и сетка параметров по текущему периоду/капиталу формы выше.
            </p>

            {opt.error && <p className="dashboard-empty color-down">{opt.error}</p>}

            <div className="robots-v2-inline robots-v2-opt-actions">
                <Button size="sm" variant="secondary" onClick={() => void opt.refreshRank()} disabled={opt.loadingRank}>
                    {opt.loadingRank ? 'Ранг…' : 'Обновить ранг'}
                </Button>
                <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void opt.loadPlan('speed')}
                    disabled={disabled || opt.loadingPlan || batchActive}
                >
                    {opt.loadingPlan ? 'План…' : 'План (speed)'}
                </Button>
                <Button
                    size="sm"
                    onClick={() => void start('speed')}
                    disabled={disabled || opt.startingBatch || batchActive}
                >
                    {opt.startingBatch ? 'Старт…' : 'Запустить сетку'}
                </Button>
                {batchActive && (
                    <Button size="sm" variant="danger" onClick={() => void opt.cancelBatch()}>
                        Отменить batch
                    </Button>
                )}
            </div>

            {opt.batchData && (
                <p className="robots-v2-hint">
                    Batch #{opt.batchData.batch_id}: {opt.batchData.status}
                    {opt.batchData.progress
                        ? ` · ${opt.batchData.progress.done}/${opt.batchData.total_candidates}`
                        : ''}
                </p>
            )}

            {opt.planData && (
                <p className="robots-v2-hint">
                    План: {opt.planData.total_candidates} кандидатов ({opt.planData.mode}) — {opt.planData.note}
                </p>
            )}

            {opt.rankData && opt.rankData.ranked.length > 0 && (
                <div className="robots-v2-opt-rank">
                    <table className="robots-v2-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Run</th>
                                <th>Score</th>
                                <th>Return</th>
                                <th>DD</th>
                                <th>Sharpe</th>
                                <th />
                            </tr>
                        </thead>
                        <tbody>
                            {opt.rankData.ranked.slice(0, 8).map(row => (
                                <tr key={row.run_id}>
                                    <td>{row.rank}</td>
                                    <td>#{row.run_id}</td>
                                    <td>{row.score.toFixed(2)}</td>
                                    <td>{fmtPct(row.total_return_percent)}</td>
                                    <td>{fmtPct(row.max_drawdown_percent)}</td>
                                    <td>{row.sharpe_ratio != null ? row.sharpe_ratio.toFixed(2) : '—'}</td>
                                    <td>
                                        {onOpenRun && (
                                            <Button size="sm" variant="ghost" onClick={() => onOpenRun(row.run_id)}>
                                                Открыть
                                            </Button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {opt.rankData.overfitting_warnings?.length > 0 && (
                        <ul className="robots-v2-hint">
                            {opt.rankData.overfitting_warnings.map(w => (
                                <li key={w}>{w}</li>
                            ))}
                        </ul>
                    )}
                </div>
            )}

            {opt.rankData && opt.rankData.ranked.length === 0 && !opt.loadingRank && (
                <p className="robots-v2-hint">Нет успешных бэктестов для ранжирования — сначала прогоните период выше.</p>
            )}
        </Card>
    )
}
