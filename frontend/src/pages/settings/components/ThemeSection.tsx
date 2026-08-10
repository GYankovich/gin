import React from 'react'
import type { ThemePreference } from '@/stores/themeStore'
import { themePreferenceLabel } from '@/stores/themeStore'

type Props = {
    preference: ThemePreference
    onChange: (preference: ThemePreference) => void
}

const OPTIONS: Array<{ id: ThemePreference; previewClass: string }> = [
    { id: 'dark', previewClass: 'theme-preview-card__mock--dark' },
    { id: 'light', previewClass: 'theme-preview-card__mock--light' },
    { id: 'system', previewClass: 'theme-preview-card__mock--system' },
]

export function ThemeSection({ preference, onChange }: Props) {
    return (
        <div className="settings-theme-picker" role="radiogroup" aria-label="Тема оформления">
            {OPTIONS.map((option) => {
                const selected = preference === option.id
                const label = themePreferenceLabel(option.id)
                return (
                    <button
                        key={option.id}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        className={`theme-option${selected ? ' theme-option--selected' : ''}`}
                        onClick={() => onChange(option.id)}
                    >
                        <span
                            className={`theme-option__swatch theme-option__swatch--${option.id}`}
                            aria-hidden
                        />
                        <span className={`theme-option__preview ${option.previewClass}`} aria-hidden>
                            <span className="theme-preview-card__bar" />
                            <span className="theme-preview-card__line" />
                            <span className="theme-preview-card__line theme-preview-card__line--short" />
                        </span>
                        <span className="theme-option__copy">
                            <span className="theme-option__label">{label}</span>
                            {selected ? <span className="theme-option__badge">выбрано</span> : null}
                        </span>
                    </button>
                )
            })}
        </div>
    )
}
