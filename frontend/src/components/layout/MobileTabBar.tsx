import React from 'react'
import { NavLink } from 'react-router-dom'

const tabs = [
    { to: '/dashboard', label: 'Дашборд', icon: '📊' },
    { to: '/portfolio', label: 'Портфель', icon: '💼' },
    { to: '/robots', label: 'Роботы', icon: '🤖' },
    { to: '/testing', label: 'Тест', icon: '🧪' },
    { to: '/settings', label: 'Ещё', icon: '⚙' },
]

export function MobileTabBar() {
    return (
        <nav className="mobile-tab-bar">
            {tabs.map(t => (
                <NavLink key={t.to} to={t.to} className={({ isActive }) => `mobile-tab ${isActive ? 'mobile-tab--active' : ''}`}>
                    <span className="mobile-tab__icon">{t.icon}</span>
                    <span className="mobile-tab__label">{t.label}</span>
                </NavLink>
            ))}
        </nav>
    )
}
