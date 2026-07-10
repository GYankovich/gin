import React, { useState } from 'react'

type Props = {
    title: string
    hint?: string
    badge?: React.ReactNode
    defaultOpen?: boolean
    open?: boolean
    onOpenChange?: (open: boolean) => void
    children: React.ReactNode
    className?: string
    id?: string
}

export function CollapsibleSection({
    title,
    hint,
    badge,
    defaultOpen = false,
    open: controlledOpen,
    onOpenChange,
    children,
    className = '',
    id,
}: Props) {
    const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen)
    const open = controlledOpen ?? uncontrolledOpen

    const setOpen = (next: boolean) => {
        if (controlledOpen === undefined) setUncontrolledOpen(next)
        onOpenChange?.(next)
    }

    return (
        <section id={id} className={`collapsible-section ${open ? 'collapsible-section--open' : ''} ${className}`.trim()}>
            <button
                type="button"
                className="collapsible-section__toggle"
                aria-expanded={open}
                onClick={() => setOpen(!open)}
            >
                <span className="collapsible-section__chevron" aria-hidden>
                    {open ? '▾' : '▸'}
                </span>
                <span className="collapsible-section__title-row">
                    <span className="collapsible-section__title">{title}</span>
                    {badge}
                </span>
            </button>
            {hint && !open && <p className="collapsible-section__hint">{hint}</p>}
            {open && <div className="collapsible-section__body">{children}</div>}
        </section>
    )
}
