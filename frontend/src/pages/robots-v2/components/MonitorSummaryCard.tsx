import React from 'react'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { StatTile } from '@/components/ui/StatTile'

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
    equityTileLabel: string
    cashTileLabel: string
    /** Honesty footnote; null when no footnote */
    balanceFootnote: string | null
    /** Optional «обновлено …» suffix appended to footnote */
    balanceAsOfLabel: string | null
    /** Live expected but balances null → one-line empty (not fake zeros) */
    showBalanceUnavailable: boolean
    /** Session cycle number (always shown in cockpit strip) */
    cycle: number | string
    positionsCount: number
    openOrderCount: number
    /** When syncing / idle — muted session hint under KPIs (optional) */
    sessionHint?: string | null
}

/**
 * Cockpit KPI strip (UX-08 zone K): merges UX-06 day + balance + session into one row.
 * Δ дня · Equity · Cash · Цикл · Позиции · Заявки
 */
export function MonitorSummaryCard({
    dayLabel,
    statusLoaded,
    dayTrades,
    dayDelta,
    showBalance,
    equityLabel,
    cashLabel,
    equityTileLabel,
    cashTileLabel,
    balanceFootnote,
    balanceAsOfLabel,
    showBalanceUnavailable,
    cycle,
    positionsCount,
    openOrderCount,
    sessionHint,
}: MonitorSummaryCardProps) {
    const footnoteText = (() => {
        if (!balanceFootnote && !balanceAsOfLabel) return null
        if (balanceFootnote && balanceAsOfLabel) return `${balanceFootnote} · ${balanceAsOfLabel}`
        return balanceFootnote || balanceAsOfLabel
    })()

    return (
        <Card className="dashboard-totals-card robots-v2-cockpit__kpi robots-v2-cockpit-kpi-card">
            <div className="dashboard-totals-card__head">
                <h3 className="dashboard-panel-title">Сводка · {dayLabel}</h3>
            </div>
            {!statusLoaded ? (
                <div className="portfolio-stats-grid robots-v2-cockpit-kpis" aria-busy="true" aria-label="Загрузка сводки">
                    {Array.from({ length: 6 }).map((_, i) => (
                        <div key={i} className="portfolio-stat-tile">
                            <Skeleton width="40%" height="12px" borderRadius="4px" />
                            <div style={{ marginTop: 'var(--space-2)' }}>
                                <Skeleton width="70%" height="22px" borderRadius="4px" />
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="portfolio-stats-grid robots-v2-cockpit-kpis">
                    <StatTile
                        label="Δ дня"
                        value={dayDelta.text}
                        valueClassName={`robots-v2-pnl--${dayDelta.tone}`}
                        hint={dayTrades > 0 ? `${dayTrades} сделок` : 'нет сделок'}
                    />
                    <StatTile
                        label={equityTileLabel || 'Equity'}
                        value={showBalance && equityLabel != null ? equityLabel : '—'}
                    />
                    <StatTile
                        label={cashTileLabel || 'Cash'}
                        value={showBalance && cashLabel != null ? cashLabel : '—'}
                    />
                    <StatTile label="Цикл" value={cycle} />
                    <StatTile label="Позиции" value={positionsCount} />
                    <StatTile
                        label="Заявки"
                        value={openOrderCount}
                        valueClassName={openOrderCount > 0 ? 'color-warn' : ''}
                        hint={openOrderCount > 0 ? 'open' : undefined}
                    />
                </div>
            )}

            {statusLoaded && showBalance && footnoteText ? (
                <p className="dashboard-empty robots-v2-balance-footnote">{footnoteText}</p>
            ) : null}

            {statusLoaded && !showBalance && showBalanceUnavailable ? (
                <p className="dashboard-empty robots-v2-balance-empty">Баланс недоступен</p>
            ) : null}

            {statusLoaded && sessionHint ? (
                <p className="dashboard-empty robots-v2-session-placeholder">{sessionHint}</p>
            ) : null}
        </Card>
    )
}
