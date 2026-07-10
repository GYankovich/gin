import React from 'react'
import { Button } from '@/components/ui/Button'
import {
    UNIVERSE_FILTER_PRESET_META,
    type UniverseFilterPresetId,
} from '@/modules/robots/config/universeFilterPresets'

const PRESET_ORDER: UniverseFilterPresetId[] = ['conservative', 'moderate', 'aggressive']

export type FilterPresetButtonsProps = {
    onApply: (presetId: UniverseFilterPresetId) => void
    activePreset?: UniverseFilterPresetId | null
    className?: string
    size?: 'sm' | 'md'
}

/** Кнопки пресетов: консервативная / умеренная / агрессивная. */
export function FilterPresetButtons({
    onApply,
    activePreset = null,
    className = '',
    size = 'sm',
}: FilterPresetButtonsProps) {
    return (
        <div className={`preset-buttons ${className}`.trim()}>
            {PRESET_ORDER.map(id => {
                const meta = UNIVERSE_FILTER_PRESET_META[id]
                const isActive = activePreset === id
                return (
                    <Button
                        key={id}
                        size={size}
                        variant={isActive ? 'primary' : 'ghost'}
                        title={meta.hint}
                        onClick={() => onApply(id)}
                    >
                        {meta.label}
                    </Button>
                )
            })}
        </div>
    )
}
