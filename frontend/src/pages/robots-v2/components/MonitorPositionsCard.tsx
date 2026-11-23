import React from 'react'
import { Card } from '@/components/ui/Card'
import { TickerWarningMark } from '@/pages/robots-v2/components/TickerWarningMark'

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
    const empty = isRunning
        ? (brokerSoftStopHint
            ? 'Ждём сверку позиций с брокером'
            : 'Нет открытых позиций — робот ещё не вошёл в сделку')
        : 'Нет открытых позиций на брокере'

    const sorted = [...rows].sort((a, b) => Math.abs(b.pnlAbs) - Math.abs(a.pnlAbs)
        || a.tickerLabel.localeCompare(b.tickerLabel))

    const body = (
        <>
            {sorted.length === 0 ? (
                <p className="dashboard-empty">{empty}</p>
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
                                    <span className={`mono robots-v2-pnl--${r.currentTone}`}>{r.current}</span>
                                </td>
                                <td className="robots-monitor-blot__num mono robots-monitor-blot__muted">
                                    {r.slTp}
                                </td>
                                <td className={`robots-monitor-blot__num mono robots-v2-pnl--${r.pnlTone}`}>
                                    {r.pnlText}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {totalPnlLabel && !bare ? (
                <div className="robots-monitor-positions__foot">
                    <span className={`robots-monitor-positions__total robots-v2-pnl--${totalPnlTone}`}>
                        {totalPnlLabel}
                    </span>
                </div>
            ) : null}
        </>
    )

    if (bare) {
        return <div className="robots-v2-monitor-positions robots-monitor-positions">{body}</div>
    }

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-positions robots-monitor-positions">
            {body}
        </Card>
    )
}
