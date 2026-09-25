import React from 'react'
import { Card } from '@/components/ui/Card'
import { StatTile } from '@/components/ui/StatTile'

type PnlTone = 'up' | 'down' | 'neutral'

type MonitorSummaryCardProps = {
    dayLabel: string
    statusLoaded: boolean
    dayTrades: number
    dayPlus: { text: string; tone: PnlTone }
    dayMinus: { text: string; tone: PnlTone }
    dayDelta: { text: string; tone: PnlTone }
    showSessionStats: boolean
    isSyncing: boolean
    equityLabel: string
    cashLabel: string
    cycle: number
    positionsCount: number
}

export function MonitorSummaryCard({
    dayLabel,
    statusLoaded,
    dayTrades,
    dayPlus,
    dayMinus,
    dayDelta,
    showSessionStats,
    isSyncing,
    equityLabel,
    cashLabel,
    cycle,
    positionsCount,
}: MonitorSummaryCardProps) {
    return (
        <Card className="dashboard-totals-card">
            <div className="dashboard-totals-card__head">
                <h3 className="dashboard-panel-title">Сводка за день · {dayLabel}</h3>
            </div>
            {statusLoaded ? (
                <div className="portfolio-stats-grid dashboard-summary-grid robots-v2-day-stats">
                    <StatTile label="Сделки" value={dayTrades} />
                    <StatTile
                        label="Сумма +"
                        value={dayPlus.text}
                        valueClassName={`robots-v2-pnl--${dayPlus.tone}`}
                    />
                    <StatTile
                        label="Сумма −"
                        value={dayMinus.text}
                        valueClassName={`robots-v2-pnl--${dayMinus.tone}`}
                    />
                    <StatTile
                        label="Дельта"
                        value={dayDelta.text}
                        valueClassName={`robots-v2-pnl--${dayDelta.tone}`}
                    />
                </div>
            ) : (
                <p className="dashboard-empty robots-v2-session-placeholder">Загрузка…</p>
            )}
            {showSessionStats ? (
                <div className="portfolio-stats-grid dashboard-summary-grid robots-v2-session-stats">
                    <StatTile label="Equity" value={equityLabel} />
                    <StatTile label="Cash" value={cashLabel} />
                    <StatTile label="Cycle" value={cycle} />
                    <StatTile label="Позиции" value={positionsCount} />
                </div>
            ) : statusLoaded ? (
                <p className="dashboard-empty robots-v2-session-placeholder">
                    {isSyncing ? 'Робот синхронизируется' : 'Робот не работает'}
                </p>
            ) : null}
        </Card>
    )
}
