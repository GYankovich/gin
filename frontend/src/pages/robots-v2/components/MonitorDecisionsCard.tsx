import React from 'react'
import { Card } from '@/components/ui/Card'

type MonitorDecisionsCardProps = {
    decisions: Array<Record<string, unknown>>
}

export function MonitorDecisionsCard({ decisions }: MonitorDecisionsCardProps) {
    return (
        <Card className="dashboard-assets-card robots-v2-monitor-decisions">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Решения</h3>
                {decisions.length > 0 ? (
                    <span className="robots-v2-hint">{Math.min(decisions.length, 12)}</span>
                ) : null}
            </div>
            {decisions.length === 0 ? (
                <p className="dashboard-empty">Пока нет решений риска</p>
            ) : (
                <ul className="robots-v2-event-list robots-v2-event-list--compact">
                    {decisions.slice(0, 12).map((d, i) => (
                        <li key={i}>
                            <strong>{String(d.code ?? '—')}</strong>
                            <span className="robots-v2-monitor-decisions__msg">
                                {' '}{String(d.message ?? '')}{' '}
                                {d.ticker ? `(${String(d.ticker)})` : ''}
                            </span>
                        </li>
                    ))}
                </ul>
            )}
        </Card>
    )
}
