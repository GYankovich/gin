import React from 'react'
import type { ThemePreference } from '@/stores/themeStore'
import { themePreferenceLabel } from '@/stores/themeStore'

type Props = {
    preference: ThemePreference
    onChange: (preference: ThemePreference) => void
}

const OPTIONS: ThemePreference[] = ['system', 'dark', 'light']

export function ThemeSection({ preference, onChange }: Props) {
    return (
        <div className="settings-theme-tabs" role="radiogroup" aria-label="Тема оформления">
            {OPTIONS.map((option) => {
                const selected = preference === option
                return (
                    <button
                        key={option}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        className={`settings-theme-tab${selected ? ' is-active' : ''}`}
                        onClick={() => onChange(option)}
                    >
                        {themePreferenceLabel(option)}
                    </button>
                )
            })}
        </div>
    )
}
