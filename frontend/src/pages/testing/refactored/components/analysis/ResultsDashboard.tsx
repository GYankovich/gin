import React from 'react'
import type { RobotHistoryBacktestResult } from '@/types/robot'
import { buildResultKpis, type ResultKpiTile } from '@/pages/testing/refactored/components/analysis/resultKpi'

export type ResultsDashboardProps = {
    result: RobotHistoryBacktestResult
    currencyLabel: string
    className?: string
    isCrypto?: boolean
}

function toneClass(tone?: 'up' | 'down' | 'neutral'): string {
    if (tone === 'up') return 'color-up'
    if (tone === 'down') return 'color-down'
    return ''
}

function KpiTile({ tile, emphasis = false }: { tile: ResultKpiTile; emphasis?: boolean }) {
    return (
        <div className={`kpi-tile kpi-tile--compact${emphasis ? ' kpi-tile--emphasis' : ''}`}>
            <span className="kpi-tile__label">{tile.label}</span>
            <span className={`kpi-tile__value mono ${toneClass(tile.tone)}`}>{tile.value}</span>
            {tile.hint && <span className="kpi-tile__hint">{tile.hint}</span>}
        </div>
    )
}

/** T4.1 — KPI-панель результата бэктеста (компактная сетка). */
export function ResultsDashboard({
    result,
    currencyLabel,
    className = '',
    isCrypto = false,
}: ResultsDashboardProps) {
    const tiles = buildResultKpis(result, currencyLabel, { isCrypto })
    const primaryOrder = [
        'return',
        'final_equity',
        'annualized',
        'sharpe',
        'drawdown',
        'win_rate',
        'profit_factor',
    ]
    const primary = primaryOrder
        .map(id => tiles.find(t => t.id === id))
        .filter((t): t is ResultKpiTile => t != null)
    const extra = tiles.filter(t => !primaryOrder.includes(t.id))
    const hs = result.history_stats

    return (
        <div className={`testing-results-dashboard ${className}`.trim()}>
            <div className="testing-results-dashboard__grid">
                {primary.map(tile => (
                    <KpiTile key={tile.id} tile={tile} emphasis={tile.id === 'final_equity'} />
                ))}
                {extra.map(tile => (
                    <KpiTile key={tile.id} tile={tile} />
                ))}
            </div>
            {hs && (
                <div className="testing-results-dashboard__pipeline" role="status">
                    <span className="testing-results-dashboard__pipeline-item">
                        <span className="testing-results-dashboard__pipeline-label">Даты</span>
                        <span className="testing-results-dashboard__pipeline-value">{hs.total_trade_dates}</span>
                    </span>
                    <span className="testing-results-dashboard__pipeline-item">
                        <span className="testing-results-dashboard__pipeline-label">Обработано</span>
                        <span className="testing-results-dashboard__pipeline-value color-up">{hs.processed}</span>
                    </span>
                    <span className="testing-results-dashboard__pipeline-item">
                        <span className="testing-results-dashboard__pipeline-label">Fetch skip</span>
                        <span className="testing-results-dashboard__pipeline-value color-down">{hs.skipped_fetch}</span>
                    </span>
                    <span className="testing-results-dashboard__pipeline-item">
                        <span className="testing-results-dashboard__pipeline-label">Empty skip</span>
                        <span className="testing-results-dashboard__pipeline-value">{hs.skipped_empty}</span>
                    </span>
                </div>
            )}
        </div>
    )
}
