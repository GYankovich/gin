import React from 'react'

type ToggleProps = {
    checked: boolean
    onChange: (checked: boolean) => void
    disabled?: boolean
    className?: string
    /** Текст справа от свитча */
    label?: React.ReactNode
    title?: string
    'aria-label'?: string
}

export function Toggle({
    checked,
    onChange,
    disabled = false,
    className = '',
    label,
    title,
    'aria-label': ariaLabel,
}: ToggleProps) {
    const switchEl = (
        <span className="dashboard-settings-toggle">
            <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={(e) => onChange(e.target.checked)}
                aria-label={ariaLabel}
                title={label == null ? title : undefined}
            />
            <span className="dashboard-settings-toggle__track" aria-hidden>
                <span className="dashboard-settings-toggle__thumb" />
            </span>
        </span>
    )

    if (label == null) {
        return (
            <span className={['dashboard-settings-toggle-wrap', className].filter(Boolean).join(' ')}>
                {switchEl}
            </span>
        )
    }

    return (
        <label
            className={['dashboard-settings-toggle-field', className].filter(Boolean).join(' ')}
            title={title}
        >
            {switchEl}
            <span className="dashboard-settings-toggle-field__label">{label}</span>
        </label>
    )
}
