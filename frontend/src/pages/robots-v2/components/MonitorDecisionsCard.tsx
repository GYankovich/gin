import React from 'react'
import { Card } from '@/components/ui/Card'

type MonitorDecisionsCardProps = {
    decisions: Array<Record<string, unknown>>
}

export function MonitorDecisionsCard({ decisions }: MonitorDecisionsCardProps) {
    return (
        <Card className="dashboard-assets-card">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Решения</h3>
            </div>
            {decisions.length === 0 ? (
                <p className="dashboard-empty">Пока нет решений риска</p>
            ) : (
                <ul className="robots-v2-event-list">
                    {decisions.slice(0, 12).map((d, i) => (
                        <li key={i}>
                            <strong>{String(d.code ?? '—')}</strong> {String(d.message ?? '')}{' '}
                            {d.ticker ? `(${String(d.ticker)})` : ''}
                        </li>
                    ))}
                </ul>
            )}
        </Card>
    )
}
