import React from 'react'

type Props = {
    id?: string
    title: string
    action?: React.ReactNode
    children: React.ReactNode
    className?: string
    hideHeader?: boolean
}

export function SettingsBlock({ id, title, action, children, className = '', hideHeader = false }: Props) {
    const blockClass = [
        'settings-block',
        hideHeader ? 'settings-block--headerless' : '',
        className,
    ].filter(Boolean).join(' ')

    return (
        <section id={id} className={blockClass} aria-label={hideHeader ? title : undefined}>
            {!hideHeader && (
                <header className="settings-block__header">
                    <h2 className="settings-block__title">{title}</h2>
                    {action}
                </header>
            )}
            <div className="settings-block__body">{children}</div>
        </section>
    )
}
