import React, { useState } from 'react'

type Props = {
    title: string
    hint?: string
    badge?: React.ReactNode
    /** Контент справа в шапке (тогглы и т.п.) — клик не сворачивает секцию. */
    headerEnd?: React.ReactNode
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
    headerEnd,
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
            <div className="collapsible-section__toggle">
                <button
                    type="button"
                    className="collapsible-section__toggle-main"
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
                {headerEnd != null && (
                    <div
                        className="collapsible-section__header-end"
                        onClick={e => e.stopPropagation()}
                        onKeyDown={e => e.stopPropagation()}
                    >
                        {headerEnd}
                    </div>
                )}
            </div>
            {hint && !open && <p className="collapsible-section__hint">{hint}</p>}
            {open && <div className="collapsible-section__body">{children}</div>}
        </section>
    )
}
