import React, { useMemo } from 'react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { StatTile } from '@/components/ui/StatTile'
import { fmtMoney, fmtPct } from '@/pages/robots-v2/formatters'

export type BacktestHistoryRow = {
    run_id: number
    status: string
    requested_from: string
    requested_to: string
    started_at: string
    initial_capital: number
    total_return_percent?: number | null
    max_drawdown_percent?: number | null
    sharpe_ratio?: number | null
    final_equity?: number | null
    trades_total: number
}

type CompareState = {
    metrics_base: Record<string, number | null>
    metrics_compare: Record<string, number | null>
    metrics_diff: Record<string, number | null>
    config_diff: Record<string, { base: unknown; compare: unknown }>
    base_run_id: number
    compare_run_id: number
}

type BacktestHistoryCardProps = {
    history: BacktestHistoryRow[]
    historyLoading?: boolean
    historyError?: string | null
    selectedIds: number[]
    activeRunId: number | null
    compare: CompareState | null
    onRefresh: () => void
    onCompare: () => void
    onToggleSelect: (id: number) => void
    onOpenRun: (id: number) => void
    statusVariant: (status: string) => 'up' | 'down' | 'neutral' | 'warn'
}

type HistoryTableRow = BacktestHistoryRow & { id: number }

export function BacktestHistoryCard({
    history,
    historyLoading = false,
    historyError = null,
    selectedIds,
    activeRunId,
    compare,
    onRefresh,
    onCompare,
    onToggleSelect,
    onOpenRun,
    statusVariant,
}: BacktestHistoryCardProps) {
    const rows = useMemo(
        () => history.map(row => ({ ...row, id: row.run_id })),
        [history],
    )

    const columns = useMemo<Column<HistoryTableRow>[]>(() => [
        {
            key: 'select',
            header: '',
            width: '40px',
            render: row => (
                <input
                    type="checkbox"
                    checked={selectedIds.includes(row.run_id)}
                    onClick={e => e.stopPropagation()}
                    onChange={() => onToggleSelect(row.run_id)}
                    aria-label={`Выбрать прогон ${row.run_id} для сравнения`}
                />
            ),
        },
        {
            key: 'run_id',
            header: '#',
            sortable: true,
            render: row => <span className="robots-v2-chip">{row.run_id}</span>,
        },
        {
            key: 'status',
            header: 'Статус',
            sortable: true,
            render: row => <Badge variant={statusVariant(row.status)}>{row.status}</Badge>,
        },
        {
            key: 'requested_from',
            header: 'Период',
            render: row => (
                <span className="mono">
                    {String(row.requested_from).slice(0, 10)} → {String(row.requested_to).slice(0, 10)}
                </span>
            ),
        },
        {
            key: 'initial_capital',
            header: 'Капитал',
            sortable: true,
            render: row => <span className="mono">{fmtMoney(row.initial_capital)}</span>,
        },
        {
            key: 'total_return_percent',
            header: 'Доходность',
            sortable: true,
            render: row => {
                const retH = row.total_return_percent
                return (
                    <span className={`mono ${(retH ?? 0) >= 0 ? 'robots-v2-pnl--up' : 'robots-v2-pnl--down'}`}>
                        {fmtPct(retH)}
                    </span>
                )
            },
        },
        {
            key: 'max_drawdown_percent',
            header: 'Max DD',
            sortable: true,
            render: row => (
                <span className="mono">
                    {row.max_drawdown_percent == null ? '—' : `${row.max_drawdown_percent.toFixed(2)}%`}
                </span>
            ),
        },
        {
            key: 'sharpe_ratio',
            header: 'Sharpe',
            sortable: true,
            render: row => (
                <span className="mono">
                    {row.sharpe_ratio == null || !Number.isFinite(row.sharpe_ratio)
                        ? '—'
                        : row.sharpe_ratio.toFixed(2)}
                </span>
            ),
        },
        {
            key: 'trades_total',
            header: 'Сделки',
            sortable: true,
            render: row => <span className="mono">{row.trades_total}</span>,
        },
    ], [selectedIds, onToggleSelect, statusVariant])

    const configDiffRows = useMemo(() => {
        if (!compare) return []
        return Object.entries(compare.config_diff).map(([path, pair]) => ({
            id: path,
            path,
            base: pair.base,
            compare: pair.compare,
        }))
    }, [compare])

    const configColumns = useMemo<Column<(typeof configDiffRows)[number]>[]>(() => {
        if (!compare) return []
        return [
            {
                key: 'path',
                header: 'Параметр',
                render: row => <span className="robots-v2-scan-reason">{row.path}</span>,
            },
            {
                key: 'base',
                header: `#${compare.base_run_id}`,
                render: row => <span className="mono">{JSON.stringify(row.base)}</span>,
            },
            {
                key: 'compare',
                header: `#${compare.compare_run_id}`,
                render: row => <span className="mono">{JSON.stringify(row.compare)}</span>,
            },
        ]
    }, [compare])

    return (
        <Card className="dashboard-assets-card">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">История прогонов</h3>
                <div className="robots-v2-chip-row">
                    <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        loading={historyLoading}
                        onClick={onRefresh}
                    >
                        Обновить
                    </Button>
                    <Button
                        type="button"
                        size="sm"
                        disabled={selectedIds.length !== 2}
                        onClick={onCompare}
                    >
                        Сравнить
                    </Button>
                </div>
            </div>
            {historyError ? (
                <p className="dashboard-empty robots-v2-hint" style={{ marginBottom: 'var(--space-2)' }}>
                    {historyError}
                </p>
            ) : null}
            <DataTable
                columns={columns}
                data={rows}
                keyField="id"
                emptyText="Сохранённых прогонов пока нет"
                maxHeight={420}
                onRowClick={row => onOpenRun(row.run_id)}
                rowClassName={row => (activeRunId === row.run_id ? 'robots-v2-table__row--active' : '')}
                mobilePrimary={row => (
                    <div className="portfolio-mobile-split">
                        <strong>#{row.run_id}</strong>
                        <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
                    </div>
                )}
                mobileDetails={row =>
                    `${String(row.requested_from).slice(0, 10)} → ${String(row.requested_to).slice(0, 10)} · ${fmtPct(row.total_return_percent)}`
                }
            />
            {compare && (
                <div className="robots-v2-form" style={{ marginTop: 'var(--space-3)' }}>
                    <p className="robots-v2-hint">
                        Сравнение #{compare.base_run_id} → #{compare.compare_run_id} (разница = compare − base)
                    </p>
                    <div className="portfolio-stats-grid dashboard-summary-grid">
                        {Object.entries(compare.metrics_diff).map(([key, delta]) => (
                            <StatTile
                                key={key}
                                label={key.replace(/_/g, ' ')}
                                value={
                                    delta == null
                                        ? '—'
                                        : key.includes('percent')
                                            ? fmtPct(delta)
                                            : key.includes('ratio') || key === 'trades_total'
                                                ? Number(delta).toFixed(key === 'trades_total' ? 0 : 2)
                                                : fmtMoney(delta)
                                }
                                valueClassName={(delta ?? 0) >= 0 ? 'color-up' : 'color-down'}
                            />
                        ))}
                    </div>
                    {configDiffRows.length > 0 ? (
                        <div style={{ marginTop: 'var(--space-2)' }}>
                            <DataTable
                                columns={configColumns}
                                data={configDiffRows}
                                keyField="id"
                                emptyText="—"
                                maxHeight={240}
                            />
                        </div>
                    ) : (
                        <p className="robots-v2-hint">Конфиги совпадают — отличаются период/капитал или случайность исполнения</p>
                    )}
                </div>
            )}
        </Card>
    )
}
