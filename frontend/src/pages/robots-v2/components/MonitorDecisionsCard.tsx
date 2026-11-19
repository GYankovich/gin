import React from 'react'
import { Card } from '@/components/ui/Card'
import { decisionCodeLabel, decisionMessageRu } from '@/pages/robots-v2/monitorUtils'

type MonitorDecisionsCardProps = {
    decisions: Array<Record<string, unknown>>
    bare?: boolean
    /** How many rows to show. Defaults to 12. */
    limit?: number
}

export function MonitorDecisionsCard({ decisions, bare = false, limit = 12 }: MonitorDecisionsCardProps) {
    const shown = decisions.slice(0, limit)
    const body = shown.length === 0 ? (
        <p className="dashboard-empty">Пока нет решений риска</p>
    ) : (
        <ul className="robots-v2-event-list robots-v2-event-list--compact">
            {shown.map((d, i) => (
                <li key={i}>
                    <strong>{decisionCodeLabel(d.code)}</strong>
                    <span className="robots-v2-monitor-decisions__msg">
                        {' '}{decisionMessageRu(d.message, d.ticker)}
                    </span>
                </li>
            ))}
        </ul>
    )

    if (bare) {
        return <div className="robots-v2-monitor-decisions">{body}</div>
    }

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-decisions">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Решения</h3>
                {decisions.length > 0 ? (
                    <span className="robots-v2-hint">{Math.min(decisions.length, limit)}</span>
                ) : null}
            </div>
            {body}
        </Card>
    )
}
