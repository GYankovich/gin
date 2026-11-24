import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { MonitorTableViewport } from '@/pages/robots-v2/components/MonitorTableViewport'
import type { OrderDisplayRow } from '@/pages/robots-v2/monitorUtils'

type MonitorOrdersCardProps = {
    rows: OrderDisplayRow[]
    /** Sum label for closed PnL, e.g. «+1 250 ₽». */
    dayTotalLabel?: string | null
    dayTotalTone?: 'up' | 'down' | 'neutral'
    /** Card title. Pass null to hide the head (История C2). Default «Сделки дня». */
    title?: string | null
    emptyTitle?: string
    emptySub?: string
    ariaLabel?: string
    /** Include still-open round trips (no sell yet). */
    includeOpen?: boolean
    /** Pin open rows to the top of the list. */
    openFirst?: boolean
    /** Render blotter without outer Card (parent already wraps). */
    bare?: boolean
    className?: string
}

function sortTradeRows(
    rows: OrderDisplayRow[],
    opts: { includeOpen: boolean; openFirst: boolean },
): OrderDisplayRow[] {
    return [...rows]
        .filter(row => opts.includeOpen || !row.isOpen)
        .sort((a, b) => {
            if (opts.openFirst && a.isOpen !== b.isOpen) return a.isOpen ? -1 : 1
            return b.dateMs - a.dateMs || a.ticker.localeCompare(b.ticker)
        })
}

/**
 * Trades blotter — shared by Лайв («Сделки дня») and История («Сделки»).
 */
export function MonitorOrdersCard({
    rows,
    dayTotalLabel = null,
    dayTotalTone = 'neutral',
    title = 'Сделки дня',
    emptyTitle = 'Сегодня закрытых нет — день в KPI считается по equity, пока не было выходов.',
    emptySub,
    ariaLabel = 'Сделки дня',
    includeOpen = false,
    openFirst = false,
    bare = false,
    className = '',
}: MonitorOrdersCardProps) {
    const sorted = useMemo(
        () => sortTradeRows(rows, { includeOpen, openFirst }),
        [rows, includeOpen, openFirst],
    )

    const body = sorted.length === 0 ? (
        <div className="robots-monitor-empty">
            <p className="robots-monitor-empty__sub">
                <b>{emptyTitle}</b>
            </p>
            {emptySub ? (
                <p className="robots-monitor-empty__sub">{emptySub}</p>
            ) : null}
        </div>
    ) : (
        <>
            <MonitorTableViewport
                ariaLabel={ariaLabel}
                syncKey={sorted.map(r => r.id).join('|')}
                renderHead={() => (
                    <tr>
                        <th>Вход</th>
                        <th>Тикер</th>
                        <th>Почему купил</th>
                        <th>Выход</th>
                        <th>Почему продал</th>
                        <th className="robots-monitor-day-trades__num">Вход → выход</th>
                        <th className="robots-monitor-day-trades__num">Комиссия</th>
                        <th className="robots-monitor-day-trades__num">Результат</th>
                    </tr>
                )}
                bodyRows={sorted.map(row => (
                    <tr key={row.id} className={row.isOpen ? 'robots-monitor-day-trades__row--open' : undefined}>
                        <td className="mono">{row.boughtAtLabel}</td>
                        <td>
                            <b className="robots-monitor-day-trades__tk">{row.ticker}</b>
                            <span className="robots-monitor-day-trades__muted">
                                {' '}×{row.qtyLabel}
                            </span>
                            {row.isOpen ? (
                                <div className="robots-monitor-day-trades__muted">открыта</div>
                            ) : null}
                        </td>
                        <td title={row.signalLabel}>{row.signalLabel}</td>
                        <td className="mono">{row.filledAtLabel}</td>
                        <td title={row.reasonLabel}>
                            {row.reasonLabel}
                            {row.placedAtLabel !== '—' ? (
                                <div className="robots-monitor-day-trades__muted">
                                    выст. {row.placedAtLabel}
                                </div>
                            ) : null}
                        </td>
                        <td className="robots-monitor-day-trades__num">
                            <span className="mono">{row.buyPxLabel}</span>
                            {' → '}
                            <span className={`mono robots-v2-pnl--${row.outcomeTone}`}>
                                {row.sellPxLabel}
                            </span>
                        </td>
                        <td className="robots-monitor-day-trades__num mono robots-monitor-day-trades__muted">
                            {row.commissionText}
                        </td>
                        <td
                            className={`robots-monitor-day-trades__num mono robots-v2-pnl--${row.outcomeTone}`}
                            title={row.outcomeTitle}
                        >
                            {row.outcomeText}
                        </td>
                    </tr>
                ))}
            />
            {dayTotalLabel ? (
                <div className="robots-monitor-positions__foot">
                    <span className={`robots-monitor-positions__total robots-v2-pnl--${dayTotalTone}`}>
                        {dayTotalLabel}
                    </span>
                </div>
            ) : null}
        </>
    )

    if (bare) {
        return <div className={`robots-monitor-day-trades ${className}`.trim()}>{body}</div>
    }

    return (
        <Card className={`dashboard-assets-card robots-v2-monitor-orders robots-monitor-day-trades ${className}`.trim()}>
            {title != null ? (
                <div className="dashboard-assets-card__head robots-monitor-orders__head">
                    <h3 className="dashboard-panel-title">
                        {title}
                        {sorted.length > 0 ? (
                            <span className="robots-v2-hint"> · {sorted.length}</span>
                        ) : null}
                    </h3>
                </div>
            ) : null}
            {body}
        </Card>
    )
}
