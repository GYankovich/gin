import React from 'react'
import type { PipelineStageStatusView, PipelineStageVisualStatus } from '@/pages/robots/pipelineStageStatus'

const ICON: Record<PipelineStageVisualStatus, string> = {
    ok: '✅',
    pending: '⏳',
    stale: '⏳',
    error: '❌',
    disabled: '—',
}

export function PipelineStageBadges({ stages }: { stages: PipelineStageStatusView[] }) {
    if (!stages.length) return null
    return (
        <div className="pipeline-stage-badges" role="list">
            {stages.map(s => (
                <div
                    key={s.id}
                    className={`pipeline-stage-badges__item pipeline-stage-badges__item--${s.status}`}
                    role="listitem"
                    title={s.detail}
                >
                    <span className="pipeline-stage-badges__icon" aria-hidden>
                        {ICON[s.status]}
                    </span>
                    <span className="pipeline-stage-badges__text">
                        <strong>{s.label}</strong>
                        <span className="pipeline-stage-badges__detail">{s.detail}</span>
                    </span>
                </div>
            ))}
        </div>
    )
}
