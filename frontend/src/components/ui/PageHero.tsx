import React from 'react'
import cyberHero from '@/assets/dashboard/cyber-hero.png'

type PageHeroProps = {
    eyebrow: string
    title: string
    subtitle?: React.ReactNode
    actions?: React.ReactNode
    className?: string
}

/** Shared cyber hero strip used on dashboard, portfolio, live, robots, testing. */
export function PageHero({ eyebrow, title, subtitle, actions, className = '' }: PageHeroProps) {
    return (
        <header className={`dashboard-hero ${className}`.trim()}>
            <div className="dashboard-hero__bg" style={{ backgroundImage: `url(${cyberHero})` }} aria-hidden />
            <div className="dashboard-hero__veil" aria-hidden />
            <div className="dashboard-hero__content">
                <div className="dashboard-hero__top">
                    <p className="dashboard-hero__eyebrow">{eyebrow}</p>
                    {actions ? <div className="dashboard-hero__actions">{actions}</div> : null}
                </div>
                <h1 className="dashboard-hero__title">
                    <span className="dashboard-hero__title-glitch" data-text={title}>{title}</span>
                </h1>
                {subtitle != null ? (
                    typeof subtitle === 'string' || typeof subtitle === 'number' ? (
                        <p className="dashboard-hero__sub">{subtitle}</p>
                    ) : (
                        subtitle
                    )
                ) : null}
            </div>
        </header>
    )
}
