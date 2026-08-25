///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsLayoutNavbar [1]
///@ Исходный модуль `frontend/src/components/layout/Navbar.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
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
    const avatarWrapRef = React.useRef<HTMLDivElement>(null)

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

    React.useEffect(() => {
        if (!dropdownOpen) return

        const onPointerDown = (event: MouseEvent | TouchEvent) => {
            const root = avatarWrapRef.current
            const target = event.target as Node | null
            if (root && target && !root.contains(target)) {
                setDropdownOpen(false)
            }
        }

        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setDropdownOpen(false)
        }

        document.addEventListener('mousedown', onPointerDown)
        document.addEventListener('touchstart', onPointerDown)
        document.addEventListener('keydown', onKeyDown)
        return () => {
            document.removeEventListener('mousedown', onPointerDown)
            document.removeEventListener('touchstart', onPointerDown)
            document.removeEventListener('keydown', onKeyDown)
        }
    }, [dropdownOpen])

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
                    <NavLink to="/robots-v2" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Роботы</NavLink>
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
                <div
                    className="navbar__avatar-wrap"
                    ref={avatarWrapRef}
                    onClick={() => setDropdownOpen(open => !open)}
                >
                    <div className="navbar__avatar" aria-haspopup="menu" aria-expanded={dropdownOpen}>
                        {initials}
                    </div>
                    {dropdownOpen && (
                        <div className="navbar__dropdown" role="menu">
                            <button
                                type="button"
                                role="menuitem"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    setDropdownOpen(false)
                                    navigate('/settings')
                                }}
                            >
                                <span>⚙</span> Настройки
                            </button>
                            <div className="navbar__dropdown-divider" />
                            <button
                                type="button"
                                role="menuitem"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    setDropdownOpen(false)
                                    logout()
                                    navigate('/login')
                                }}
                            >
                                <span>↩</span> Выход
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </header>
    )
}
