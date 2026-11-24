import React from 'react'
import { Card } from '@/components/ui/Card'
import { TickerWarningMark } from '@/pages/robots/components/TickerWarningMark'

export type MonitorPositionRow = {
    id: string
    tickerLabel: string
    tickerWarning: string
    side: string
    quantity: string
    /** When the position was opened (buy fill / ledger opened_at). */
    boughtAtLabel: string
    entry: string
    current: string
    currentTone: 'up' | 'down' | 'neutral'
    /** e.g. «305,5 → 289,2» */
    entryToNow: string
    sl: string
    tp: string
    slTp: string
    /** Under ticker: «лимит TP выставлен» / «до SL 29 · без лимита» */
    subtitle: string
    pnlText: string
    pnlTone: 'up' | 'down' | 'neutral'
    pnlAbs: number
}

type MonitorPositionsCardProps = {
    rows: MonitorPositionRow[]
    /** Sum label e.g. «−214 ₽ (−2,6%)» */
    totalPnlLabel?: string | null
    totalPnlTone?: 'up' | 'down' | 'neutral'
    brokerSoftStopHint: boolean
    isRunning: boolean
    /** Skip foot total when parent already renders chrome. */
    bare?: boolean
}

/**
 * Positions blotter on card substrate: table + total foot.
 */
export function MonitorPositionsCard({
    rows,
    totalPnlLabel,
    totalPnlTone = 'neutral',
    brokerSoftStopHint,
    isRunning,
    bare = false,
}: MonitorPositionsCardProps) {
    const emptySub = isRunning
        ? (brokerSoftStopHint
            ? 'Ждём сверку с брокером — позиции подтянутся после синка.'
            : 'Сейчас пусто — робот работает, ждём сигнал на вход из пула.')
        : 'Сейчас пусто — на брокере нет открытых позиций.'

    const sorted = [...rows].sort((a, b) => Math.abs(b.pnlAbs) - Math.abs(a.pnlAbs)
        || a.tickerLabel.localeCompare(b.tickerLabel))

    const body = (
        <>
            {!bare ? (
                <div className="dashboard-assets-card__head robots-monitor-orders__head">
                    <h3 className="dashboard-panel-title">
                        Позиции
                        {sorted.length > 0 ? (
                            <span className="robots-hint"> · {sorted.length}</span>
                        ) : null}
                    </h3>
                </div>
            ) : null}
            {sorted.length === 0 ? (
                <div className="robots-monitor-empty">
                    <p className="robots-monitor-empty__sub">{emptySub}</p>
                </div>
            ) : (
                <table className="robots-monitor-blot" aria-label="Открытые позиции">
                    <thead>
                        <tr>
                            <th>Позиция</th>
                            <th>Закупка</th>
                            <th className="robots-monitor-blot__num">Вход → сейчас</th>
                            <th className="robots-monitor-blot__num">SL / TP</th>
                            <th className="robots-monitor-blot__num">PnL</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sorted.map(r => (
                            <tr key={r.id}>
                                <td>
                                    <span className="robots-monitor-blot__tk">
                                        {r.tickerWarning ? <TickerWarningMark text={r.tickerWarning} /> : null}
                                        {r.tickerLabel}
                                    </span>
                                    {' '}
                                    <span className="robots-monitor-blot__qty">×{r.quantity}</span>
                                    {r.subtitle ? (
                                        <span className="robots-monitor-blot__sub">{r.subtitle}</span>
                                    ) : null}
                                </td>
                                <td className="mono robots-monitor-blot__muted">{r.boughtAtLabel}</td>
                                <td className="robots-monitor-blot__num">
                                    <span className="mono">{r.entry}</span>
                                    {' → '}
                                    <span className={`mono robots-pnl--${r.currentTone}`}>{r.current}</span>
                                </td>
                                <td className="robots-monitor-blot__num mono robots-monitor-blot__muted">
                                    {r.slTp}
                                </td>
                                <td className={`robots-monitor-blot__num mono robots-pnl--${r.pnlTone}`}>
                                    {r.pnlText}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {totalPnlLabel && !bare ? (
                <div className="robots-monitor-positions__foot">
                    <span className={`robots-monitor-positions__total robots-pnl--${totalPnlTone}`}>
                        {totalPnlLabel}
                    </span>
                </div>
            ) : null}
        </>
    )

    if (bare) {
        return <div className="robots-monitor-positions robots-monitor-positions">{body}</div>
    }

    return (
        <Card className="dashboard-assets-card robots-monitor-positions robots-monitor-positions">
            {body}
        </Card>
    )
}
