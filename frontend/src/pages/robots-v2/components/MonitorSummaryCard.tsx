import React from 'react'
import { Skeleton } from '@/components/ui/Skeleton'

type PnlTone = 'up' | 'down' | 'neutral'

type MonitorSummaryCardProps = {
    statusLoaded: boolean
    dayTrades: number
    dayDelta: { text: string; tone: PnlTone }
    /** Mark-to-market day line (equity curve); falls back to closed-trade delta. */
    dayMtm?: { text: string; tone: PnlTone } | null
    showBalance: boolean
    equityLabel: string | null
    cashLabel: string | null
    showBalanceUnavailable: boolean
    positionsCount: number
    limitCount: number
    /** Session cycle number from status. */
    cycle?: number | null
    sessionHint?: string | null
}

function tradeCountLabel(count: number): string {
    if (count <= 0) return '0 закрытий'
    const mod10 = count % 10
    const mod100 = count % 100
    const word = mod10 === 1 && mod100 !== 11
        ? 'закрытие'
        : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
            ? 'закрытия'
            : 'закрытий'
    return `${count} ${word}`
}

/**
 * Left side of the monitor cockpit: equity + two quiet metric tiles.
 */
export function MonitorSummaryCard({
    statusLoaded,
    dayTrades,
    dayDelta,
    dayMtm,
    showBalance,
    equityLabel,
    cashLabel,
    showBalanceUnavailable,
    positionsCount,
    limitCount,
    cycle,
    sessionHint,
}: MonitorSummaryCardProps) {
    const dayLine = dayMtm ?? dayDelta
    const trades = tradeCountLabel(dayTrades)

    if (!statusLoaded) {
        return (
            <div className="robots-monitor-hero" aria-busy="true" aria-label="Загрузка сводки">
                <Skeleton width="62%" height="32px" borderRadius="6px" />
                <div className="robots-monitor-hero__tiles">
                    <Skeleton width="100%" height="64px" borderRadius="12px" />
                    <Skeleton width="100%" height="64px" borderRadius="12px" />
                </div>
            </div>
        )
    }

    return (
        <div className="robots-monitor-hero">
            <div className="robots-monitor-hero__value">
                {showBalance && equityLabel != null ? equityLabel : '—'}
            </div>
            <div className="robots-monitor-hero__tiles">
                <div className={`robots-monitor-hero__tile robots-monitor-hero__tile--${dayLine.tone}`}>
                    <div className={`robots-monitor-hero__tile-value robots-v2-pnl--${dayLine.tone}`}>
                        {dayLine.text}
                    </div>
                    <div className="robots-monitor-hero__tile-meta">
                        за день{dayMtm ? ' · MTM' : ''} · {trades}
                    </div>
                </div>
                <div className="robots-monitor-hero__tile">
                    <div className="robots-monitor-hero__tile-value">
                        {showBalance && cashLabel != null ? cashLabel : '—'}
                    </div>
                    <div className="robots-monitor-hero__tile-meta">
                        кэш · {positionsCount} поз. · {limitCount} лим.
                        {cycle != null && Number.isFinite(Number(cycle)) ? ` · цикл ${cycle}` : ''}
                    </div>
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
