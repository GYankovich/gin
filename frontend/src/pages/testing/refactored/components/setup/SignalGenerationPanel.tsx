import React from 'react'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import {
    StrategyParamsPanel,
    type StrategyParamsPanelProps,
} from '@/pages/testing/refactored/components/setup/StrategyParamsPanel'
import { PollFrequencyField } from '@/pages/testing/refactored/components/setup/PollFrequencyField'

export type SignalGenerationPanelProps = StrategyParamsPanelProps & {
    strategyOptions: Array<{ value: string; label: string }>
    strategy: string
    onStrategyChange: (v: string) => void
    pollValue: number
    onPollValueChange: (v: number) => void
    pollUnit: 'minutes' | 'hours'
    onPollUnitChange: (u: 'minutes' | 'hours') => void
}

/** Параметры стратегии + имитация live-цикла робота. */
export function SignalGenerationPanel({
    strategyOptions,
    strategy,
    onStrategyChange,
    pollValue,
    onPollValueChange,
    pollUnit,
    onPollUnitChange,
    onConfigDirty,
    market,
    params,
    onParamChange,
}: SignalGenerationPanelProps) {
    const dirty = () => onConfigDirty?.()

    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card testing-signal-generation-panel">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                ПАРАМЕТРЫ СТРАТЕГИИ
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="form-group">
                <label className="form-label">Стратегия</label>
                <Select
                    options={strategyOptions}
                    value={strategy}
                    onChange={v => {
                        onStrategyChange(String(v || 'grain_seed'))
                        dirty()
                    }}
                />
            </div>
            <StrategyParamsPanel
                market={market}
                strategy={strategy}
                params={params}
                onParamChange={onParamChange}
                onConfigDirty={dirty}
                embedded
                sectionTitle=""
                className="testing-signal-generation-panel__strategy"
            />

            <div className="testing-signal-generation-panel__poll">
                <h4 className="card__subsection-title testing-signal-generation-panel__poll-title">
                    Имитация запуска робота
                </h4>
                <PollFrequencyField
                    pollValue={pollValue}
                    onPollValueChange={onPollValueChange}
                    pollUnit={pollUnit}
                    onPollUnitChange={onPollUnitChange}
                    onConfigDirty={dirty}
                />
            </div>
        </Card>
    )
}
