import React from 'react'
import { Card } from '@/components/ui/Card'
import { TickerWarningMark } from '@/pages/robots-v2/components/TickerWarningMark'

export type MonitorPositionRow = {
    id: string
    tickerLabel: string
    tickerWarning: string
    side: string
    quantity: string
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
    positionsCount: number
    /** Sum label e.g. «−214 ₽ · −2,6%» */
    totalPnlLabel?: string | null
    totalPnlTone?: 'up' | 'down' | 'neutral'
    positionsUpdatedAt: string | null | undefined
    brokerSoftStopHint: boolean
    isRunning: boolean
    bare?: boolean
}

export function MonitorPositionsCard({
    rows,
    positionsCount,
    totalPnlLabel,
    totalPnlTone = 'neutral',
    positionsUpdatedAt,
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
            {brokerSoftStopHint ? (
                <p className="robots-v2-hint robots-v2-universe-caption">
                    Сессия остановлена · позиции с брокера (пауза их не закрывает).
                    После запуска робот подхватит и продолжит торговать.
                </p>
            ) : null}
            {sorted.length === 0 ? (
                <p className="dashboard-empty">{empty}</p>
            ) : (
                <table className="robots-monitor-blot" aria-label="Открытые позиции">
                    <thead>
                        <tr>
                            <th>Позиция</th>
                            <th className="robots-monitor-blot__num">Вход → сейчас</th>
                            <th className="robots-monitor-blot__num">PnL</th>
                            <th className="robots-monitor-blot__num">SL / TP</th>
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
                                <td className="robots-monitor-blot__num">
                                    <span className="mono">{r.entry}</span>
                                    {' → '}
                                    <span className={`mono robots-v2-pnl--${r.currentTone}`}>{r.current}</span>
                                </td>
                                <td className={`robots-monitor-blot__num mono robots-v2-pnl--${r.pnlTone}`}>
                                    {r.pnlText}
                                </td>
                                <td className="robots-monitor-blot__num mono robots-monitor-blot__muted">
                                    {r.slTp}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {positionsUpdatedAt ? (
                <p className="robots-v2-hint robots-v2-universe-caption">
                    Цены обновлены
                    <span className="mono">
                        {' '}
                        · {new Date(positionsUpdatedAt).toLocaleString('ru-RU', {
                            day: '2-digit',
                            month: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                        })}
                    </span>
                </p>
            ) : null}
        </>
    )

    if (bare) {
        return <div className="robots-v2-monitor-positions">{body}</div>
    }

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-positions">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">
                    Позиции
                    {positionsCount > 0 ? <> · {positionsCount}</> : null}
                </h3>
                {totalPnlLabel ? (
                    <span className={`robots-v2-hint robots-v2-pnl--${totalPnlTone}`}>{totalPnlLabel}</span>
                ) : null}
            </div>
            {body}
        </Card>
    )
}
