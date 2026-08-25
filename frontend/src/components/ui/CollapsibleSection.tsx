import React, { useState } from 'react'

type Props = {
    title: React.ReactNode
    hint?: string
    badge?: React.ReactNode
    /** Контент справа в шапке (тогглы и т.п.) — клик не сворачивает секцию. */
    headerEnd?: React.ReactNode
    defaultOpen?: boolean
    open?: boolean
    onOpenChange?: (open: boolean) => void
    /** Держать children в DOM при закрытии (модалки/состояние в headerEnd). */
    keepMounted?: boolean
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
    keepMounted = false,
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

    const toggle = () => setOpen(!open)
    const showBody = open || keepMounted

    return (
        <section id={id} className={`collapsible-section ${open ? 'collapsible-section--open' : ''} ${className}`.trim()}>
            <div
                className="collapsible-section__toggle"
                role="button"
                tabIndex={0}
                aria-expanded={open}
                onClick={toggle}
                onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        toggle()
                    }
                }}
            >
                <span className="collapsible-section__toggle-main">
                    <span className="collapsible-section__chevron" aria-hidden>
                        {open ? '▾' : '▸'}
                    </span>
                    <span className="collapsible-section__title-row">
                        <span className="collapsible-section__title">{title}</span>
                        {badge}
                    </span>
                </span>
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
            {showBody && (
                <div
                    className="collapsible-section__body"
                    hidden={!open}
                    inert={!open && keepMounted ? true : undefined}
                >
                    {children}
                </div>
            )}
        </section>
    )
}
