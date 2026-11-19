import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import type { OrderDisplayRow } from '@/pages/robots-v2/monitorUtils'

type MonitorOrdersCardProps = {
    /** Closed / settled rows for the live day only. */
    rows: OrderDisplayRow[]
}

/**
 * Day's closed trades — not open positions or resting limits
 * (limits live under the position blotter subtitle).
 */
export function MonitorOrdersCard({ rows }: MonitorOrdersCardProps) {
    const shown = useMemo(
        () => [...rows]
            .filter(row => !row.isOpen)
            .sort((a, b) => b.dateMs - a.dateMs || a.ticker.localeCompare(b.ticker)),
        [rows],
    )

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-orders">
            <div className="dashboard-assets-card__head robots-monitor-orders__head">
                <h3 className="dashboard-panel-title">Сделки дня</h3>
            </div>
            {shown.length === 0 ? (
                <p className="dashboard-empty">
                    Закрытых сегодня нет — в сводке только mark-to-market.
                </p>
            ) : (
                <div className="robots-monitor-orders">
                    {shown.map(row => (
                        <div className="robots-monitor-order" key={row.id}>
                            <div className="robots-monitor-order__top">
                                <span className="robots-monitor-order__id">
                                    <time className="mono">{row.timeLabel}</time>
                                    <b>{row.ticker}</b>
                                </span>
                                <span
                                    className={`mono robots-monitor-order__outcome robots-v2-pnl--${row.outcomeTone}`}
                                    title={row.outcomeTitle}
                                >
                                    {row.outcomeText}
                                </span>
                            </div>
                            <div className="robots-monitor-order__sub">
                                <span className="robots-monitor-order__detail">{row.detailLabel}</span>
                                <span className="robots-monitor-order__state">{row.statusLabel}</span>
                            </div>
                            <span className="robots-monitor-order__signal">{row.reasonLabel}</span>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    )
}
