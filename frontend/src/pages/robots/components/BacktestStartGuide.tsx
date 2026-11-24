import React from 'react'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import {
    BACKTEST_PRESETS,
    type BacktestPresetId,
} from '@/pages/robots/backtestGuide'
import { ARCHETYPE_CARDS, type TradingRobotWizardDraft } from '@/pages/robots/wizardDraft'

type Props = {
    draft: TradingRobotWizardDraft
    activePreset: BacktestPresetId | null
    onApplyPreset: (id: BacktestPresetId) => void
}

/** Compact presets for the Lab launch column. Does not start a run. */
export function BacktestStartGuide({ draft, activePreset, onApplyPreset }: Props) {
    const active = BACKTEST_PRESETS.find(p => p.id === activePreset)
    const currentTitle = ARCHETYPE_CARDS.find(c => c.id === draft.archetype)?.title

    return (
        <div className="robots-bt-guide robots-bt-guide--compact">
            <label className="robots-field">
                <span>Набор</span>
                <SegmentedControl
                    className="robots-segmented robots-bt-presets-seg"
                    aria-label="Готовые наборы правил"
                    options={BACKTEST_PRESETS.map(preset => ({
                        value: preset.id,
                        label: preset.title,
                    }))}
                    value={activePreset ?? ('none' as BacktestPresetId)}
                    onChange={id => onApplyPreset(id)}
                />
                {active ? (
                    <small className="robots-hint robots-bt-guide__hint">{active.rule}</small>
                ) : (
                    <small className="robots-hint robots-bt-guide__hint">
                        {currentTitle || 'Правила'}
                        {draft.fixedList ? ` · ${draft.fixedList}` : ''}
                        {' · заполняет форму'}
                    </small>
                )}
            </label>
        </div>
    )
}
