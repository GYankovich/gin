import React from 'react'

export type RunStatusLogProps = {
    statusWindow: string[]
    className?: string
}

/** Phase / prep log from poll status (T3.3 precursor). */
export function RunStatusLog({ statusWindow, className = '' }: RunStatusLogProps) {
    if (statusWindow.length === 0) return null

    return (
        <div className={`testing-run-status-log ${className}`.trim()}>
            <h3 className="card__section-title pipeline-title testing-runbar__pipeline-title">
                <span className="cyber-bracket">[</span>
                СТАТУС ПОДГОТОВКИ И ТЕСТА
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="form-hint">
                {statusWindow.map((s, i) => (
                    <div key={`${s}-${i}`}>• {s}</div>
                ))}
            </div>
        </div>
    )
}
