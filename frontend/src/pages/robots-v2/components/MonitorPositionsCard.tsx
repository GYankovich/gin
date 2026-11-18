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
    breakEven: string
    current: string
    currentTone: 'up' | 'down' | 'neutral'
    sl: string
    tp: string
}

type MonitorPositionsCardProps = {
    rows: MonitorPositionRow[]
    positionsCount: number
    positionsUpdatedAt: string | null | undefined
    brokerSoftStopHint: boolean
    isRunning: boolean
    /** Drop the card chrome when the section header already names the block. */
    bare?: boolean
}

export function MonitorPositionsCard({
    rows,
    positionsCount,
    positionsUpdatedAt,
    brokerSoftStopHint,
    isRunning,
    bare = false,
}: MonitorPositionsCardProps) {
    const empty = isRunning
        ? 'Нет открытых позиций — робот ещё не вошёл в сделку'
        : 'Нет открытых позиций на брокере (в universe / по audit fills)'
    const body = (
        <>
            {brokerSoftStopHint ? (
                <p className="robots-v2-hint robots-v2-universe-caption">
                    Сессия остановлена · позиции с брокера (soft stop их не закрывает).
                    После Start робот подхватит и продолжит торговать.
                </p>
            ) : null}
            <div className="robots-monitor-position-cards" aria-label="Открытые позиции">
                {rows.length === 0 ? (
                    <p className="dashboard-empty">{empty}</p>
                ) : (
                    rows.map(r => (
                        <article key={r.id} className="robots-monitor-position-card">
                            <div className="robots-monitor-position-card__head">
                                <strong className="robots-monitor-position-card__title">
                                    {r.tickerWarning ? <TickerWarningMark text={r.tickerWarning} /> : null}
                                    {r.tickerLabel}
                                </strong>
                                <span>{r.side} · {r.quantity}</span>
                            </div>
                            <div className="robots-monitor-position-card__line">
                                <span>Вход <strong className="mono">{r.entry}</strong></span>
                                <span>Сейчас <strong className={`mono robots-v2-pnl--${r.currentTone}`}>{r.current}</strong></span>
                            </div>
                            <div className="robots-monitor-position-card__line">
                                <span>Безубыток <strong className="mono">{r.breakEven}</strong></span>
                                <span>SL / TP <strong className="mono">{r.sl} / {r.tp}</strong></span>
                            </div>
                        </article>
                    ))
                )}
            </div>
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
                <h3 className="dashboard-panel-title">Открытые позиции</h3>
                {positionsCount > 0 ? (
                    <span className="robots-v2-hint">{positionsCount}</span>
                ) : null}
            </div>
            {body}
        </Card>
    )
}
