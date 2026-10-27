///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsLayoutMobiletabbar [1]
///@ Исходный модуль `frontend/src/components/layout/MobileTabBar.tsx` — floating auth-capsule dock (mobile shell).

import React from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

type TabIconProps = { className?: string }

function IconPortfolio({ className }: TabIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="3.5" y="8" width="17" height="11.5" rx="3" stroke="currentColor" strokeWidth="1.5" />
            <rect x="3.5" y="8" width="17" height="11.5" rx="3" fill="currentColor" opacity="0.14" />
            <path d="M8 8V6.8A2.8 2.8 0 0 1 10.8 4h2.4A2.8 2.8 0 0 1 16 6.8V8" stroke="currentColor" strokeWidth="1.5" />
        </svg>
    )
}

function IconRobots({ className }: TabIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="5.5" y="7" width="13" height="12" rx="4" stroke="currentColor" strokeWidth="1.5" />
            <rect x="5.5" y="7" width="13" height="12" rx="4" fill="currentColor" opacity="0.14" />
            <path d="M12 3.5v3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="9.5" cy="12.2" r="1.2" fill="currentColor" />
            <circle cx="14.5" cy="12.2" r="1.2" fill="currentColor" />
        </svg>
    )
}

function IconTesting({ className }: TabIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
                d="M9 3h6M10 3v5.5L6 16.2A2.4 2.4 0 0 0 8.1 20h7.8A2.4 2.4 0 0 0 18 16.2L14 8.5V3"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinejoin="round"
            />
            <path d="M7.4 14.8h9.2C16 17 14.3 18.2 12 18.2S8 17 7.4 14.8Z" fill="currentColor" opacity="0.18" />
        </svg>
    )
}

const tabs = [
    { to: '/portfolio', label: 'Портфель', Icon: IconPortfolio },
    { to: '/robots', label: 'Роботы', Icon: IconRobots },
    { to: '/backtest', label: 'Лаб', Icon: IconTesting },
] as const

function scrollToTokens() {
    document.getElementById('tokens')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function MobileTab({
    to,
    label,
    Icon,
}: {
    to: string
    label: string
    Icon: React.ComponentType<TabIconProps>
}) {
    return (
        <NavLink
            to={to}
            className={({ isActive }) => [
                'mobile-dock__tab',
                isActive ? 'mobile-dock__tab--active' : 'mobile-dock__tab--idle',
            ].join(' ')}
            aria-label={label}
        >
            {({ isActive }) => (
                <>
                    <span className="mobile-dock__tab-icon-wrap">
                        <Icon className="mobile-dock__tab-icon" />
                    </span>
                    <span className="mobile-dock__tab-label" aria-hidden={!isActive}>
                        {label}
                    </span>
                </>
            )}
        </NavLink>
    )
}

export function MobileTabBar({ hasExpiredToken }: { hasExpiredToken: boolean }) {
    const navigate = useNavigate()
    const location = useLocation()
    const user = useAuthStore(s => s.user)
    const initials = user?.login?.slice(0, 2).toUpperCase() || 'U'

    const openSettings = (event: React.MouseEvent<HTMLAnchorElement>) => {
        if (!hasExpiredToken) return
        event.preventDefault()
        if (location.pathname === '/settings' && location.hash === '#tokens') {
            scrollToTokens()
            return
        }
        navigate('/settings#tokens')
        window.requestAnimationFrame(() => {
            window.setTimeout(scrollToTokens, 50)
        })
    }

    return (
        <div className="mobile-dock" aria-label="Мобильная навигация">
            <nav className="mobile-dock__capsule">
                <NavLink
                    to="/dashboard"
                    end
                    className={({ isActive }) => `mobile-dock__brand${isActive ? ' mobile-dock__brand--active' : ''}`}
                    aria-label="Дашборд"
                >
                    <img className="mobile-dock__logo" src="/favicon.svg" alt="" />
                </NavLink>

                <div className="mobile-dock__tabs">
                    {tabs.map(({ to, label, Icon }) => (
                        <MobileTab
                            key={to}
                            to={to}
                            label={label}
                            Icon={Icon}
                        />
                    ))}
                </div>

                <NavLink
                    to="/settings"
                    className={({ isActive }) => [
                        'mobile-dock__avatar',
                        isActive ? 'mobile-dock__avatar--active' : '',
                        hasExpiredToken ? 'mobile-dock__avatar--alert' : '',
                    ].filter(Boolean).join(' ')}
                    aria-label={hasExpiredToken ? 'Настройки, истёкший токен' : 'Настройки'}
                    onClick={openSettings}
                >
                    <span className="mobile-dock__avatar-text" aria-hidden>{initials}</span>
                    {hasExpiredToken && <span className="mobile-dock__avatar-dot" aria-hidden />}
                </NavLink>
            </nav>
        </div>
    )
}
