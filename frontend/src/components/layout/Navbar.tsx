///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsLayoutNavbar [1]
///@ Исходный модуль `frontend/src/components/layout/Navbar.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { DropdownMenu } from '@/components/ui/DropdownMenu'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { api } from '@/services/api'

export function Navbar() {
    const navigate = useNavigate()
    const logout = useAuthStore(s => s.logout)
    const user = useAuthStore(s => s.user)
    const { theme, toggle } = useThemeStore()
    const [dropdownOpen, setDropdownOpen] = React.useState(false)
    const [hasExpiredToken, setHasExpiredToken] = React.useState(false)

    const initials = user?.login?.slice(0, 2).toUpperCase() || 'U'

    React.useEffect(() => {
        let active = true
        const load = async () => {
            try {
                const { data } = await api.post('/apikey/data', {})
                const keys = Array.isArray(data?.keys) ? data.keys : []
                const hasExpired = keys.some((k: any) => Number(k?.status || 0) === 3)
                if (active) setHasExpiredToken(hasExpired)
            } catch {
                if (active) setHasExpiredToken(false)
            }
        }
        void load()
        return () => {
            active = false
        }
    }, [])

    return (
        <header className="navbar" role="navigation" aria-label="Главная навигация">
            <div className="navbar__scanline" aria-hidden />
            <div className="navbar__left">
                <div className="navbar__brand" onClick={() => navigate('/dashboard')}>
                    <div className="navbar__logo" aria-label="GIN">
                        <span className="logo-g">G</span>
                        <span className="logo-i">I</span>
                        <span className="logo-n">N</span>
                    </div>
                    <span className="navbar__brand-tag">NODE // ONLINE</span>
                </div>
                <nav className="navbar__links">
                    <NavLink to="/dashboard" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Дашборд</NavLink>
                    <NavLink to="/portfolio" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Портфель</NavLink>
                    <NavLink to="/robots" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Роботы</NavLink>
                    <NavLink to="/backtest" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Лаборатория</NavLink>
                </nav>
            </div>

            <div className="navbar__right">
                {hasExpiredToken && (
                    <button
                        type="button"
                        className="navbar__token-alert"
                        title="Перейти в настройки токенов"
                        onClick={() => navigate('/settings#tokens')}
                    >
                        Найден истекший токен!
                    </button>
                )}
                <button
                    type="button"
                    className="navbar__theme-btn"
                    onClick={toggle}
                    title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
                    aria-label={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
                >
                    <svg className="navbar__theme-icon" viewBox="0 0 24 24" aria-hidden="true">
                        <circle cx="12" cy="12" r="8.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
                        <path d="M12 3.75a8.25 8.25 0 0 0 0 16.5V3.75Z" fill="currentColor" />
                    </svg>
                </button>
                <DropdownMenu
                    open={dropdownOpen}
                    onOpenChange={setDropdownOpen}
                    placement="below"
                    className="navbar__avatar-wrap"
                >
                    <DropdownMenu.Trigger className="navbar__avatar" aria-label="Меню пользователя">
                        {initials}
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Panel>
                        <DropdownMenu.Item
                            icon="⚙"
                            onClick={() => navigate('/settings')}
                        >
                            Настройки
                        </DropdownMenu.Item>
                        <DropdownMenu.Divider />
                        <DropdownMenu.Item
                            icon="↩"
                            onClick={() => {
                                logout()
                                navigate('/login')
                            }}
                        >
                            Выход
                        </DropdownMenu.Item>
                    </DropdownMenu.Panel>
                </DropdownMenu>
            </div>
        </header>
    )
}
