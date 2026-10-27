import React from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { fmtPct, sessionStateLabel } from '@/pages/robots-v2/formatters'

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
    signals_logged?: number
    signals_truncated?: boolean
    robot_id?: number | null
    bound?: boolean | null
    config_label?: string | null
}

type BacktestHistoryCardProps = {
    history: BacktestHistoryRow[]
    historyLoading?: boolean
    historyError?: string | null
    activeRunId: number | null
    onRefresh: () => void
    onOpenRun: (id: number) => void
    /** If set, run # is a real link (new tab / copy URL). */
    runHref?: (id: number) => string
    statusVariant: (status: string) => 'up' | 'down' | 'neutral' | 'warn'
    /** Lab: show soft-bind badge */
    showBindColumn?: boolean
    /** Lab: optional config_label when any row has it */
    showConfigColumn?: boolean
    title?: string
    emptyText?: string
    emptyCta?: React.ReactNode
    /** Navigate to robot backtest tab from bind badge */
    onBindClick?: (robotId: number) => void
    footer?: React.ReactNode
    tableMaxHeight?: number
}

function isBound(row: BacktestHistoryRow): boolean {
    if (typeof row.bound === 'boolean') return row.bound
    return row.robot_id != null && Number(row.robot_id) > 0
}

function shortDay(iso: string): string {
    const d = String(iso).slice(0, 10)
    if (d.length < 10) return d
    const [, m, day] = d.split('-')
    return `${day}.${m}`
}

function periodLabel(from: string, to: string): string {
    const a = String(from).slice(0, 10)
    const b = String(to).slice(0, 10)
    const y1 = a.slice(0, 4)
    const y2 = b.slice(0, 4)
    if (y1 && y1 === y2) return `${shortDay(a)} — ${shortDay(b)}`
    if (a.length >= 10 && b.length >= 10) {
        return `${shortDay(a)}.${y1.slice(2)} — ${shortDay(b)}.${y2.slice(2)}`
    }
    return `${a} — ${b}`
}

function RunHistoryTile({
    row,
    active,
    showBindColumn,
    showConfigColumn,
    runHref,
    statusVariant,
    onOpenRun,
    onBindClick,
}: {
    row: BacktestHistoryRow
    active: boolean
    showBindColumn: boolean
    showConfigColumn: boolean
    runHref?: (id: number) => string
    statusVariant: (status: string) => 'up' | 'down' | 'neutral' | 'warn'
    onOpenRun: (id: number) => void
    onBindClick?: (robotId: number) => void
}) {
    const href = runHref?.(row.run_id)
    const bound = showBindColumn && isBound(row)
    const rid = row.robot_id != null ? Number(row.robot_id) : null
    const label = showConfigColumn ? String(row.config_label || '').trim() : ''
    const ret = row.total_return_percent
    const hasReturn = ret != null && Number.isFinite(ret)
    const retClass = !hasReturn ? '' : ret >= 0 ? 'robots-v2-pnl--up' : 'robots-v2-pnl--down'
    const dd = row.max_drawdown_percent
    const sharpe = row.sharpe_ratio
    const statusInCorner = !hasReturn

    const result = statusInCorner ? (
        <Badge variant={statusVariant(row.status)}>{sessionStateLabel(row.status)}</Badge>
    ) : (
        <span className={`robots-v2-run-tile__ret ${retClass}`}>{fmtPct(ret)}</span>
    )

    const hitLabel = `Прогон #${row.run_id}`

    return (
        <article
            className={['robots-v2-run-tile', active ? 'robots-v2-run-tile--active' : '']
                .filter(Boolean)
                .join(' ')}
            role="listitem"
        >
            {href ? (
                <Link className="robots-v2-run-tile__hit" to={href} aria-label={hitLabel} />
            ) : (
                <button
                    type="button"
                    className="robots-v2-run-tile__hit"
                    aria-label={hitLabel}
                    onClick={() => onOpenRun(row.run_id)}
                />
            )}
            <div className="robots-v2-run-tile__body">
                <div className="robots-v2-run-tile__top">
                    <div className="robots-v2-run-tile__title">
                        <span className="robots-v2-run-tile__id">#{row.run_id}</span>
                        {label ? (
                            <span className="robots-v2-run-tile__cfg" title={label}>
                                {label}
                            </span>
                        ) : null}
                    </div>
                    <div className="robots-v2-run-tile__result">{result}</div>
                </div>
                <div className="robots-v2-run-tile__main">
                    {row.signals_truncated ? (
                        <div className="robots-v2-run-tile__flags">
                            <Badge variant="warn">сигналы</Badge>
                        </div>
                    ) : null}
                    <div className="robots-v2-run-tile__metrics">
                        <span>
                            <em>Сделки</em> {row.trades_total}
                        </span>
                        <span>
                            <em>Просадка</em>{' '}
                            {dd == null ? '—' : `${dd.toFixed(1)}%`}
                        </span>
                        <span title="Доходность на единицу риска: чем выше, тем лучше">
                            <em>Доход/риск</em>{' '}
                            {sharpe == null || !Number.isFinite(sharpe) ? '—' : sharpe.toFixed(2)}
                        </span>
                    </div>
                </div>
                <div className="robots-v2-run-tile__sub">
                    {bound && rid != null && rid > 0 ? (
                        <button
                            type="button"
                            className="robots-v2-lab-bind-btn robots-v2-run-tile__bind"
                            onClick={() => onBindClick?.(rid)}
                            title={`Открыть робота #${rid}`}
                        >
                            Робот #{rid}
                        </button>
                    ) : null}
                    <p className="robots-v2-run-tile__period">
                        <em>Период:</em> {periodLabel(row.requested_from, row.requested_to)}
                    </p>
                </div>
            </div>
        </article>
    )
}

export function BacktestHistoryCard({
    history,
    historyLoading = false,
    historyError = null,
    activeRunId,
    onRefresh,
    onOpenRun,
    runHref,
    statusVariant,
    showBindColumn = false,
    showConfigColumn = false,
    title = 'История прогонов',
    emptyText = 'Сохранённых прогонов пока нет',
    emptyCta = null,
    onBindClick,
    footer = null,
    tableMaxHeight = 420,
}: BacktestHistoryCardProps) {
    const hasConfigLabels = showConfigColumn && history.some(r => r.config_label)

    return (
        <Card className="dashboard-totals-card portfolio-history-zone robots-v2-run-list-card">
            <div className="portfolio-history-zone__toolbar">
                <div className="portfolio-history-zone__lead">
                    <h3 className="portfolio-history-zone__title">
                        <span className="dashboard-collapse__label">
                            <span className="dashboard-icon" aria-hidden>◷</span>
                            {title}
                        </span>
                        {history.length > 0 ? (
                            <span className="portfolio-history-zone__count">{history.length}</span>
                        ) : null}
                    </h3>
                </div>
                <div className="portfolio-history-zone__controls">
                    <button
                        type="button"
                        className={`portfolio-history-sync-btn${historyLoading ? ' portfolio-history-sync-btn--loading' : ''}`}
                        aria-label="Обновить"
                        title="Обновить"
                        disabled={historyLoading}
                        onClick={onRefresh}
                    >
                        <IconRefresh />
                    </button>
                </div>
            </div>
            <div className="portfolio-history-zone__panels">
                {historyError ? (
                    <p className="dashboard-empty robots-v2-hint" style={{ marginBottom: 'var(--space-2)' }}>
                        {historyError}
                    </p>
                ) : null}
                {history.length === 0 ? (
                    <p className="dashboard-empty">{emptyText}</p>
                ) : (
                    <div
                        className="robots-v2-run-list"
                        role="list"
                        style={{ maxHeight: tableMaxHeight }}
                    >
                        {history.map(row => (
                            <RunHistoryTile
                                key={row.run_id}
                                row={row}
                                active={activeRunId === row.run_id}
                                showBindColumn={showBindColumn}
                                showConfigColumn={hasConfigLabels}
                                runHref={runHref}
                                statusVariant={statusVariant}
                                onOpenRun={onOpenRun}
                                onBindClick={onBindClick}
                            />
                        ))}
                    </div>
                )}
                {!historyLoading && history.length === 0 && emptyCta ? (
                    <div className="robots-v2-lab-empty-cta">{emptyCta}</div>
                ) : null}
                {footer}
            </div>
        </Card>
    )
}

function IconRefresh() {
    return (
        <svg className="portfolio-history-sync-btn__icon" viewBox="0 0 24 24" aria-hidden>
            <path
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M20 12a8 8 0 1 1-2.34-5.66"
            />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M20 4v5h-5" />
        </svg>
    )
}
