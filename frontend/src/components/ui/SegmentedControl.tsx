import React from 'react'

export type SegmentedOption<T extends string> = {
    value: T
    label: string
}

type Props<T extends string> = {
    options: SegmentedOption<T>[]
    value: T
    onChange: (value: T) => void
    className?: string
    'aria-label'?: string
}

export function SegmentedControl<T extends string>({
    options,
    value,
    onChange,
    className = '',
    'aria-label': ariaLabel,
}: Props<T>) {
    return (
        <div className={`segmented-control ${className}`.trim()} role="group" aria-label={ariaLabel}>
            {options.map(opt => (
                <button
                    key={opt.value}
                    type="button"
                    className={`segmented-control__item${value === opt.value ? ' segmented-control__item--active' : ''}`}
                    aria-pressed={value === opt.value}
                    onClick={() => onChange(opt.value)}
                >
                    {opt.label}
                </button>
            ))}
        </div>
    )
}
