import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { MonitorTableViewport } from '@/pages/robots-v2/components/MonitorTableViewport'
import type { OrderDisplayRow } from '@/pages/robots-v2/monitorUtils'

type MonitorOrdersCardProps = {
    /** Closed / settled rows for the live day only. */
    rows: OrderDisplayRow[]
    /** Sum label for closed day PnL, e.g. «+1 250 ₽». */
    dayTotalLabel?: string | null
    dayTotalTone?: 'up' | 'down' | 'neutral'
}

/**
 * Day's closed trades — blotter with entry/exit and buy/sell reasons.
 */
export function MonitorOrdersCard({
    rows,
    dayTotalLabel = null,
    dayTotalTone = 'neutral',
}: MonitorOrdersCardProps) {
    const sorted = useMemo(
        () => [...rows]
            .filter(row => !row.isOpen)
            .sort((a, b) => b.dateMs - a.dateMs || a.ticker.localeCompare(b.ticker)),
        [rows],
    )

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-orders robots-monitor-day-trades">
            <div className="dashboard-assets-card__head robots-monitor-orders__head">
                <h3 className="dashboard-panel-title">
                    Сделки дня
                    {sorted.length > 0 ? (
                        <span className="robots-v2-hint"> · {sorted.length}</span>
                    ) : null}
                </h3>
            </div>
            {sorted.length === 0 ? (
                <div className="robots-monitor-empty">
                    <p className="robots-monitor-empty__sub">
                        Сегодня закрытых нет — день в KPI считается по equity, пока не было выходов.
                    </p>
                </div>
            ) : (
                <>
                    <MonitorTableViewport
                        ariaLabel="Сделки дня"
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
                            <tr key={row.id}>
                                <td className="mono">{row.boughtAtLabel}</td>
                                <td>
                                    <b className="robots-monitor-day-trades__tk">{row.ticker}</b>
                                    <span className="robots-monitor-day-trades__muted">
                                        {' '}×{row.qtyLabel}
                                    </span>
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
            )}
        </Card>
    )
}
