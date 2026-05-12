import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { DataTable } from '@/components/ui/DataTable'
import type { RobotBacktestHistoryItem } from '@/types/robot'

export type TestingBacktestHistoryCardProps = {
    historyLoading: boolean
    onRefresh: () => void | Promise<void>
    historyRuns: RobotBacktestHistoryItem[]
    filteredHistoryRuns: RobotBacktestHistoryItem[]
    historySearch: string
    onHistorySearchChange: (v: string) => void
    historyMinReturn: number | null
    onHistoryMinReturnChange: (v: number | null) => void
    compareLeftId: number | null
    onCompareLeftIdChange: (id: number | null) => void
    compareRightId: number | null
    onCompareRightIdChange: (id: number | null) => void
    onOpenRun: (r: RobotBacktestHistoryItem) => void | Promise<void>
}

export function TestingBacktestHistoryCard({
    historyLoading,
    onRefresh,
    historyRuns,
    filteredHistoryRuns,
    historySearch,
    onHistorySearchChange,
    historyMinReturn,
    onHistoryMinReturnChange,
    compareLeftId,
    onCompareLeftIdChange,
    compareRightId,
    onCompareRightIdChange,
    onOpenRun,
}: TestingBacktestHistoryCardProps) {
    const leftRun = useMemo(
        () => historyRuns.find(x => x.id === compareLeftId) ?? null,
        [historyRuns, compareLeftId],
    )
    const rightRun = useMemo(
        () => historyRuns.find(x => x.id === compareRightId) ?? null,
        [historyRuns, compareRightId],
    )

    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card testing-history-card">
            <div className="card__header">
                <h3 className="pipeline-title">
                    <span className="cyber-bracket">[</span>
                    ИСТОРИЯ БЭКТЕСТОВ
                    <span className="cyber-bracket">]</span>
                </h3>
                <Button
                    size="sm"
                    variant="ghost"
                    className="pipeline-action-btn pipeline-action-btn--reset"
                    loading={historyLoading}
                    onClick={() => void onRefresh()}
                >
                    Обновить
                </Button>
            </div>
            <div className="form-row" style={{ marginBottom: 'var(--space-3)', gap: 'var(--space-3)' }}>
                <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
                    <label className="form-label">Поиск</label>
                    <input
                        className="form-input"
                        value={historySearch}
                        onChange={e => onHistorySearchChange(e.target.value)}
                        placeholder="id, дата, доходность"
                    />
                </div>
                <div className="form-group" style={{ marginBottom: 0, width: 220 }}>
                    <label className="form-label">Мин. доходность %</label>
                    <input
                        className="form-input"
                        value={historyMinReturn == null ? '' : String(historyMinReturn)}
                        onChange={e => {
                            const raw = e.target.value.trim()
                            if (!raw) {
                                onHistoryMinReturnChange(null)
                                return
                            }
                            const n = Number(raw.replace(',', '.'))
                            onHistoryMinReturnChange(Number.isFinite(n) ? n : null)
                        }}
                        placeholder="например, 5"
                    />
                </div>
            </div>
            <DataTable
                columns={[
                    {
                        key: 'created_at',
                        header: 'Запуск',
                        render: (r: RobotBacktestHistoryItem) => new Date(r.created_at).toLocaleString('ru-RU'),
                    },
                    {
                        key: 'requested_from',
                        header: 'Период',
                        render: (r: RobotBacktestHistoryItem) =>
                            `${new Date(r.requested_from).toLocaleDateString('ru-RU')} - ${new Date(r.requested_to).toLocaleDateString('ru-RU')}`,
                    },
                    {
                        key: 'total_return_percent',
                        header: 'Доходность',
                        align: 'right',
                        render: (r: RobotBacktestHistoryItem) => (
                            <span className={r.total_return_percent >= 0 ? 'color-up' : 'color-down'}>
                                {r.total_return_percent.toFixed(2)}%
                            </span>
                        ),
                    },
                    {
                        key: 'final_equity',
                        header: 'Итог',
                        align: 'right',
                        render: (r: RobotBacktestHistoryItem) =>
                            `${r.final_equity.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽`,
                    },
                    {
                        key: 'open',
                        header: '',
                        render: (r: RobotBacktestHistoryItem) => (
                            <Button size="sm" variant="secondary" onClick={() => void onOpenRun(r)}>
                                Открыть
                            </Button>
                        ),
                    },
                ]}
                data={filteredHistoryRuns}
                keyField="id"
                emptyText={historyLoading ? 'Загрузка...' : 'Нет сохраненных прогонов'}
            />
            {historyRuns.length > 1 && (
                <div style={{ marginTop: 'var(--space-4)' }}>
                    <h4 style={{ marginBottom: 'var(--space-2)' }}>Сравнение прогонов</h4>
                    <div className="form-row" style={{ gap: 'var(--space-3)' }}>
                        <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
                            <label className="form-label">Левый прогон</label>
                            <Select
                                options={[
                                    { value: '', label: 'Выберите прогон' },
                                    ...historyRuns.map(r => ({
                                        value: String(r.id),
                                        label: `#${r.id} • ${new Date(r.created_at).toLocaleString('ru-RU')}`,
                                    })),
                                ]}
                                value={compareLeftId != null ? String(compareLeftId) : ''}
                                onChange={v => onCompareLeftIdChange(v ? Number(v) : null)}
                            />
                        </div>
                        <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
                            <label className="form-label">Правый прогон</label>
                            <Select
                                options={[
                                    { value: '', label: 'Выберите прогон' },
                                    ...historyRuns.map(r => ({
                                        value: String(r.id),
                                        label: `#${r.id} • ${new Date(r.created_at).toLocaleString('ru-RU')}`,
                                    })),
                                ]}
                                value={compareRightId != null ? String(compareRightId) : ''}
                                onChange={v => onCompareRightIdChange(v ? Number(v) : null)}
                            />
                        </div>
                    </div>
                    {leftRun && rightRun && (
                        <div className="grid-kpi" style={{ marginTop: 'var(--space-3)' }}>
                            <div className="kpi-tile">
                                <span className="kpi-tile__label">Δ Доходность</span>
                                <span
                                    className={`kpi-tile__value mono ${
                                        rightRun.total_return_percent - leftRun.total_return_percent >= 0 ? 'color-up' : 'color-down'
                                    }`}
                                >
                                    {(rightRun.total_return_percent - leftRun.total_return_percent).toFixed(2)}%
                                </span>
                            </div>
                            <div className="kpi-tile">
                                <span className="kpi-tile__label">Δ Итоговый капитал</span>
                                <span
                                    className={`kpi-tile__value mono ${
                                        rightRun.final_equity - leftRun.final_equity >= 0 ? 'color-up' : 'color-down'
                                    }`}
                                >
                                    {(rightRun.final_equity - leftRun.final_equity).toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                                </span>
                            </div>
                            <div className="kpi-tile">
                                <span className="kpi-tile__label">Δ Сделок</span>
                                <span className="kpi-tile__value mono">
                                    {(rightRun.result_payload?.trades?.length ?? 0) - (leftRun.result_payload?.trades?.length ?? 0)}
                                </span>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </Card>
    )
}
