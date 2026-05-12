import React from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

export type TestingBacktestRunSectionProps = {
    running: boolean
    onRunBacktest: () => void
    statusWindow: string[]
}

export function TestingBacktestRunSection({ running, onRunBacktest, statusWindow }: TestingBacktestRunSectionProps) {
    return (
        <>
            <div className="mb-6 testing-actions testing-actions--run">
                <Button className="pipeline-action-btn pipeline-action-btn--test" onClick={onRunBacktest} loading={running}>
                    Запустить бэктест
                </Button>
            </div>

            {statusWindow.length > 0 && (
                <Card className="mb-6 cyber-form-card testing-cyber-card">
                    <h3 className="card__section-title pipeline-title">
                        <span className="cyber-bracket">[</span>
                        СТАТУС ПОДГОТОВКИ И ТЕСТА
                        <span className="cyber-bracket">]</span>
                    </h3>
                    <div className="form-hint">
                        {statusWindow.map((s, i) => (
                            <div key={`${s}-${i}`}>• {s}</div>
                        ))}
                    </div>
                </Card>
            )}
        </>
    )
}
