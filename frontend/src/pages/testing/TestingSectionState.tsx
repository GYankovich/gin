import React from 'react'
import { Card } from '@/components/ui/Card'

type TestingSectionStateProps = {
    title: string
    message: string
    variant?: 'empty' | 'error' | 'partial'
    actionLabel?: string
    onAction?: () => void
    compact?: boolean
}

export function TestingSectionState({
    title,
    message,
    variant = 'empty',
    actionLabel,
    onAction,
    compact = false,
}: TestingSectionStateProps) {
    const isError = variant === 'error'
    const isPartial = variant === 'partial'
    const stateClassName = [
        'testing-state-card',
        compact ? 'testing-state-card--compact' : '',
        isError ? 'testing-state-card--error' : '',
        isPartial ? 'testing-state-card--partial' : '',
    ]
        .filter(Boolean)
        .join(' ')
    const body = (
        <>
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                {title}
                <span className="cyber-bracket">]</span>
            </h3>
            {isPartial && <span className="badge badge--warn testing-state-card__badge">Частично доступно</span>}
            <p className={`form-hint ${isError ? 'color-down' : ''}`}>{message}</p>
            {actionLabel && onAction && (
                <button type="button" className="btn btn--ghost btn--sm pipeline-action-btn pipeline-action-btn--reset" onClick={onAction}>
                    {actionLabel}
                </button>
            )}
        </>
    )

    if (compact) {
        return <div className={stateClassName}>{body}</div>
    }

    return (
        <Card className={`mb-6 cyber-form-card testing-cyber-card ${stateClassName}`}>
            {body}
        </Card>
    )
}
