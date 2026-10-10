import React from 'react'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'

type BadgeVariant = 'cyan' | 'magenta' | 'up' | 'down' | 'warn' | 'neutral'

type RobotStageCardProps = {
    title: string
    progress: number
    /** 0–1 or 0–100; values > 1 treated as percent. */
    badge?: React.ReactNode
    badgeVariant?: BadgeVariant
    ariaLabel?: string
    meta?: React.ReactNode
    detail?: React.ReactNode
    className?: string
}

function normalizeProgress(progress: number): number {
    if (!Number.isFinite(progress)) return 0
    const pct = progress > 1 ? progress : progress * 100
    return Math.min(100, Math.max(0, pct))
}

/** Shared stage / progress card for Monitor and Backtest. */
export function RobotStageCard({
    title,
    progress,
    badge,
    badgeVariant = 'neutral',
    ariaLabel = 'Прогресс',
    meta,
    detail,
    className = '',
}: RobotStageCardProps) {
    const pct = normalizeProgress(progress)

    return (
        <Card className={`dashboard-totals-card robots-v2-stage-card ${className}`.trim()}>
            <div className="dashboard-totals-card__head robots-v2-stage-card__head">
                <h3 className="dashboard-panel-title">{title}</h3>
                {badge != null ? (
                    typeof badge === 'string' || typeof badge === 'number' ? (
                        <Badge variant={badgeVariant}>{badge}</Badge>
                    ) : (
                        badge
                    )
                ) : (
                    <span className="robots-v2-hint">{Math.round(pct)}%</span>
                )}
            </div>
            <div className="robots-v2-stage-progress" aria-label={ariaLabel}>
                <div
                    className="robots-v2-stage-progress__bar"
                    style={{ width: `${Math.round(pct)}%` }}
                />
            </div>
            {(meta != null || detail != null) && (
                <div className="robots-v2-stage-meta">
                    {meta}
                    {detail}
                </div>
            )}
        </Card>
    )
}
