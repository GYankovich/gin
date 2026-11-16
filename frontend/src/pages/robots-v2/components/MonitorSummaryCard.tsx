import React from 'react'
import { Skeleton } from '@/components/ui/Skeleton'

type PnlTone = 'up' | 'down' | 'neutral'

type MonitorSummaryCardProps = {
    dayLabel: string
    statusLoaded: boolean
    dayTrades: number
    dayDelta: { text: string; tone: PnlTone }
    /** Zone B: true when at least one of equity/cash is a finite number */
    showBalance: boolean
    /** Formatted equity; show «—» when null */
    equityLabel: string | null
    /** Formatted cash; show «—» when null */
    cashLabel: string | null
    cashTileLabel: string
    /** Live expected but balances null → one-line empty (not fake zeros) */
    showBalanceUnavailable: boolean
    /** Session cycle number */
    cycle: number | string
    positionsCount: number
    openOrderCount: number
    /** When syncing / idle — muted session hint under the numbers */
    sessionHint?: string | null
}

function tradeCountLabel(count: number): string | null {
    if (count <= 0) return null
    const mod10 = count % 10
    const mod100 = count % 100
    const word = mod10 === 1 && mod100 !== 11
        ? 'сделка'
        : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
            ? 'сделки'
            : 'сделок'
    return `${count} ${word}`
}

/**
 * Left side of the monitor cockpit: equity hero, day result, cash / positions / orders / cycle.
 */
export function MonitorSummaryCard({
    dayLabel,
    statusLoaded,
    dayTrades,
    dayDelta,
    showBalance,
    equityLabel,
    cashLabel,
    cashTileLabel,
    showBalanceUnavailable,
    cycle,
    positionsCount,
    openOrderCount,
    sessionHint,
}: MonitorSummaryCardProps) {
    const trades = tradeCountLabel(dayTrades)

    if (!statusLoaded) {
        return (
            <div className="robots-monitor-hero" aria-busy="true" aria-label="Загрузка сводки">
                <Skeleton width="46%" height="12px" borderRadius="4px" />
                <div style={{ marginTop: 10 }}>
                    <Skeleton width="62%" height="32px" borderRadius="6px" />
                </div>
                <div style={{ marginTop: 10 }}>
                    <Skeleton width="48%" height="14px" borderRadius="4px" />
                </div>
                <div className="robots-monitor-hero__mini">
                    {Array.from({ length: 4 }).map((_, i) => (
                        <Skeleton key={i} width="70%" height="28px" borderRadius="4px" />
                    ))}
                </div>
            </div>
        )
    }

    return (
        <div className="robots-monitor-hero">
            <div className="robots-monitor-hero__label">Стоимость · {dayLabel}</div>
            <div className="robots-monitor-hero__value">
                {showBalance && equityLabel != null ? equityLabel : '—'}
            </div>
            <p className={`robots-monitor-hero__delta robots-v2-pnl--${dayDelta.tone}`}>
                {dayDelta.text}
                <span>
                    {' '}за день
                    {trades ? ` · ${trades}` : ''}
                </span>
            </p>
            <div className="robots-monitor-hero__mini">
                <div>
                    <span>{cashTileLabel || 'Cash'}</span>
                    <strong>{showBalance && cashLabel != null ? cashLabel : '—'}</strong>
                </div>
                <div>
                    <span>Позиции</span>
                    <strong>{positionsCount}</strong>
                </div>
                <div>
                    <span>Заявки</span>
                    <strong className={openOrderCount > 0 ? 'color-warn' : undefined}>{openOrderCount}</strong>
                </div>
                <div>
                    <span>Цикл</span>
                    <strong>{cycle}</strong>
                </div>
            </div>
            {showBalanceUnavailable ? (
                <p className="dashboard-empty robots-v2-balance-empty">Баланс недоступен</p>
            ) : null}
            {sessionHint ? (
                <p className="dashboard-empty robots-v2-session-placeholder">{sessionHint}</p>
            ) : null}
        </div>
    )
}
