import React from 'react'
import { Skeleton } from '@/components/ui/Skeleton'

type PnlTone = 'up' | 'down' | 'neutral'

type MonitorSummaryCardProps = {
    statusLoaded: boolean
    dayDelta: { text: string; tone: PnlTone }
    /** Mark-to-market day line (equity curve); falls back to closed-trade delta. */
    dayMtm?: { text: string; tone: PnlTone } | null
    showBalance: boolean
    equityLabel: string | null
    cashLabel: string | null
    showBalanceUnavailable: boolean
    positionsCount: number
    /** Session cycle number from status. */
    cycle?: number | null
    /** Closed day trades with PnL > 0. */
    dayWins?: number
    /** Closed day trades with PnL < 0. */
    dayLosses?: number
    sessionHint?: string | null
}

/**
 * Left side of the monitor cockpit: equity + KPI tiles.
 */
export function MonitorSummaryCard({
    statusLoaded,
    dayDelta,
    dayMtm,
    showBalance,
    equityLabel,
    cashLabel,
    showBalanceUnavailable,
    positionsCount,
    cycle,
    dayWins = 0,
    dayLosses = 0,
    sessionHint,
}: MonitorSummaryCardProps) {
    const dayLine = dayMtm ?? dayDelta
    const cycleLabel = cycle != null && Number.isFinite(Number(cycle)) ? String(cycle) : '—'

    if (!statusLoaded) {
        return (
            <div className="robots-monitor-hero" aria-busy="true" aria-label="Загрузка сводки">
                <Skeleton width="62%" height="32px" borderRadius="6px" />
                <div className="robots-monitor-hero__tiles">
                    <Skeleton width="100%" height="36px" borderRadius="6px" />
                    <Skeleton width="100%" height="36px" borderRadius="6px" />
                    <Skeleton width="100%" height="36px" borderRadius="6px" />
                    <Skeleton width="100%" height="36px" borderRadius="6px" />
                    <Skeleton width="100%" height="36px" borderRadius="6px" />
                    <Skeleton width="100%" height="36px" borderRadius="6px" />
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
                <div className="robots-monitor-hero__kpi">
                    <span className="robots-monitor-hero__kpi-label">День</span>
                    <b className={`robots-monitor-hero__kpi-value robots-v2-pnl--${dayLine.tone}`}>
                        {dayLine.text}
                    </b>
                </div>
                <div className="robots-monitor-hero__kpi">
                    <span className="robots-monitor-hero__kpi-label">Кэш</span>
                    <b className="robots-monitor-hero__kpi-value">
                        {showBalance && cashLabel != null ? cashLabel : '—'}
                    </b>
                </div>
                <div className="robots-monitor-hero__kpi">
                    <span className="robots-monitor-hero__kpi-label">Позиции</span>
                    <b className="robots-monitor-hero__kpi-value">{positionsCount}</b>
                </div>
                <div className="robots-monitor-hero__kpi">
                    <span className="robots-monitor-hero__kpi-label">Цикл</span>
                    <b className="robots-monitor-hero__kpi-value">{cycleLabel}</b>
                </div>
                <div className="robots-monitor-hero__kpi">
                    <span className="robots-monitor-hero__kpi-label">В плюс</span>
                    <b className="robots-monitor-hero__kpi-value robots-v2-pnl--up">{dayWins}</b>
                </div>
                <div className="robots-monitor-hero__kpi">
                    <span className="robots-monitor-hero__kpi-label">В минус</span>
                    <b className="robots-monitor-hero__kpi-value robots-v2-pnl--down">{dayLosses}</b>
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
