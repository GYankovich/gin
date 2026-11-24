import React from 'react'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import {
    buildBacktestVerdict,
    type BacktestVerdictInput,
} from '@/pages/robots/backtestGuide'

type Props = BacktestVerdictInput & {
    onSaveAsRobot: () => void
}

export function BacktestVerdictCard({ onSaveAsRobot, ...input }: Props) {
    const verdict = buildBacktestVerdict(input)

    const openJournal = () => {
        const node = document.getElementById('backtest-journal')
        node?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        const toggle = node?.querySelector<HTMLElement>('[aria-expanded="false"]')
        toggle?.click()
    }

    return (
        <Card className="dashboard-assets-card robots-bt-verdict">
            <h3 className="dashboard-panel-title">{verdict.headline}</h3>
            <p className="robots-hint">{verdict.body}</p>
            {verdict.digest.length > 0 ? (
                <>
                    <p className="robots-hint">Из-за чего были сделки:</p>
                    <ul className="robots-bt-verdict__digest">
                        {verdict.digest.map(line => (
                            <li key={line}>{line}</li>
                        ))}
                    </ul>
                </>
            ) : null}
            {verdict.caution ? (
                <p className="robots-banner robots-banner--warn">{verdict.caution}</p>
            ) : null}
            <div className="dashboard-settings-actions">
                <Button type="button" variant="ghost" onClick={openJournal}>
                    Открыть журнал
                </Button>
                <Button type="button" onClick={onSaveAsRobot}>
                    Создать робота из прогона
                </Button>
            </div>
        </Card>
    )
}
