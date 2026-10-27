import React from 'react'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import {
    BACKTEST_PRESETS,
    type BacktestPresetId,
} from '@/pages/robots-v2/backtestGuide'
import { ARCHETYPE_CARDS, type RobotV2WizardDraft } from '@/pages/robots-v2/wizardDraft'

type Props = {
    draft: RobotV2WizardDraft
    activePreset: BacktestPresetId | null
    onApplyPreset: (id: BacktestPresetId) => void
}

/** Compact presets for the Lab launch column. Does not start a run. */
export function BacktestStartGuide({ draft, activePreset, onApplyPreset }: Props) {
    const active = BACKTEST_PRESETS.find(p => p.id === activePreset)
    const currentTitle = ARCHETYPE_CARDS.find(c => c.id === draft.archetype)?.title

    return (
        <div className="robots-v2-bt-guide robots-v2-bt-guide--compact">
            <label className="robots-v2-field">
                <span>Набор</span>
                <SegmentedControl
                    className="robots-v2-segmented robots-v2-bt-presets-seg"
                    aria-label="Готовые наборы правил"
                    options={BACKTEST_PRESETS.map(preset => ({
                        value: preset.id,
                        label: preset.title,
                    }))}
                    value={activePreset ?? ('none' as BacktestPresetId)}
                    onChange={id => onApplyPreset(id)}
                />
                {active ? (
                    <small className="robots-v2-hint robots-v2-bt-guide__hint">{active.rule}</small>
                ) : (
                    <small className="robots-v2-hint robots-v2-bt-guide__hint">
                        {currentTitle || 'Правила'}
                        {draft.fixedList ? ` · ${draft.fixedList}` : ''}
                        {' · заполняет форму'}
                    </small>
                )}
            </label>
        </div>
    )
}
