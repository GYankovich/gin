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
    /** Zone B: true when at least one of equity/cash is a finite number */
    showBalance: boolean
    /** Formatted equity; omit Equity tile when null */
    equityLabel: string | null
    /** Formatted cash; omit Cash tile when null */
    cashLabel: string | null
    equityTileLabel: string
    cashTileLabel: string
    /** Zone Bƒ honesty footnote; null when no footnote */
    balanceFootnote: string | null
    /** Optional «обновлено …» suffix appended to footnote */
    balanceAsOfLabel: string | null
    /** Live expected but balances null → one-line empty (not fake zeros) */
    showBalanceUnavailable: boolean
    /** Zone C: Cycle + Позиции only */
    showSessionOps: boolean
    isSyncing: boolean
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
    showBalance,
    equityLabel,
    cashLabel,
    equityTileLabel,
    cashTileLabel,
    balanceFootnote,
    balanceAsOfLabel,
    showBalanceUnavailable,
    showSessionOps,
    isSyncing,
    cycle,
    positionsCount,
}: MonitorSummaryCardProps) {
    const footnoteText = (() => {
        if (!balanceFootnote && !balanceAsOfLabel) return null
        if (balanceFootnote && balanceAsOfLabel) return `${balanceFootnote} · ${balanceAsOfLabel}`
        return balanceFootnote || balanceAsOfLabel
    })()

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

            {statusLoaded && showBalance ? (
                <>
                    <div className="portfolio-stats-grid dashboard-summary-grid robots-v2-balance-stats">
                        {equityLabel != null ? (
                            <StatTile label={equityTileLabel} value={equityLabel} />
                        ) : null}
                        {cashLabel != null ? (
                            <StatTile label={cashTileLabel} value={cashLabel} />
                        ) : null}
                    </div>
                    {footnoteText ? (
                        <p className="dashboard-empty robots-v2-balance-footnote">{footnoteText}</p>
                    ) : null}
                </>
            ) : null}

            {statusLoaded && !showBalance && showBalanceUnavailable ? (
                <p className="dashboard-empty robots-v2-balance-empty">Баланс недоступен</p>
            ) : null}

            {showSessionOps ? (
                <div className="portfolio-stats-grid dashboard-summary-grid robots-v2-session-stats">
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
