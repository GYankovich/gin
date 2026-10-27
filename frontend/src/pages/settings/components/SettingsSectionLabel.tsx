import React from 'react'

type Props = {
    children: React.ReactNode
    icon?: React.ReactNode
    end?: React.ReactNode
}

/** Mobile stacked-sheet section caption (Тема / Брокеры). */
export function SettingsSectionLabel({ children, icon, end }: Props) {
    return (
        <div className="settings-section-label">
            {icon ? <span className="settings-section-label__icon" aria-hidden>{icon}</span> : null}
            <span className="settings-section-label__text">{children}</span>
            {end != null ? <span className="settings-section-label__end">{end}</span> : null}
        </div>
    )
}

export function IconThemeMark({ className = '' }: { className?: string }) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.5" />
            <path d="M12 4v16M4 12h16" stroke="currentColor" strokeWidth="1.5" opacity=".35" />
        </svg>
    )
}

export function IconBrokerMark({ className = '' }: { className?: string }) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="4" y="7" width="16" height="11" rx="2.5" stroke="currentColor" strokeWidth="1.5" />
            <path
                d="M8 7V5.5A2 2 0 0 1 10 3.5h4A2 2 0 0 1 16 5.5V7"
                stroke="currentColor"
                strokeWidth="1.5"
            />
        </svg>
    )
}
