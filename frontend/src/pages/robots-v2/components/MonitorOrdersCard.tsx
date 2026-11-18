import React, { useMemo, useState } from 'react'
import { Card } from '@/components/ui/Card'
import type { OrderDisplayRow } from '@/pages/robots-v2/monitorUtils'

type MonitorOrdersCardProps = {
    rows: OrderDisplayRow[]
    openOrderCount: number
}

export function MonitorOrdersCard({ rows, openOrderCount }: MonitorOrdersCardProps) {
    const [mode, setMode] = useState<'open' | 'all'>('open')
    const shown = useMemo(() => {
        const list = mode === 'open' ? rows.filter(row => row.isOpen) : rows
        return [...list].sort((a, b) => b.dateMs - a.dateMs || a.ticker.localeCompare(b.ticker))
    }, [mode, rows])

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-orders">
            <div className="dashboard-assets-card__head robots-monitor-orders__head">
                <h3 className="dashboard-panel-title">Заявки</h3>
                <div className="robots-monitor-mode" role="tablist" aria-label="Режим заявок">
                    <button
                        type="button"
                        className={`robots-monitor-mode__btn${mode === 'open' ? ' robots-monitor-mode__btn--on' : ''}`}
                        onClick={() => setMode('open')}
                    >
                        Текущие{openOrderCount > 0 ? ` · ${openOrderCount}` : ''}
                    </button>
                    <button
                        type="button"
                        className={`robots-monitor-mode__btn${mode === 'all' ? ' robots-monitor-mode__btn--on' : ''}`}
                        onClick={() => setMode('all')}
                    >
                        Все
                    </button>
                </div>
            </div>
            {shown.length === 0 ? (
                <p className="dashboard-empty">
                    {mode === 'open' ? 'Нет открытых заявок' : 'Пока нет сделок'}
                </p>
            ) : (
                <div className="robots-monitor-orders">
                    {shown.map(row => (
                        <div className="robots-monitor-order" key={row.id}>
                            <div className="robots-monitor-order__top">
                                <span className="robots-monitor-order__id">
                                    <time className="mono">{row.timeLabel}</time>
                                    <b>{row.ticker}</b>
                                </span>
                                <span
                                    className={`mono robots-monitor-order__outcome robots-v2-pnl--${row.outcomeTone}`}
                                    title={row.outcomeTitle}
                                >
                                    {row.outcomeText}
                                </span>
                            </div>
                            <div className="robots-monitor-order__sub">
                                <span className="robots-monitor-order__detail">{row.detailLabel}</span>
                                <span className="robots-monitor-order__state">{row.statusLabel}</span>
                            </div>
                            <span className="robots-monitor-order__signal">{row.reasonLabel}</span>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    )
}
