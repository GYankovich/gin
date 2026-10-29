///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsLayoutNavbar [1]
///@ Исходный модуль `frontend/src/components/layout/Navbar.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowRightFromBracket, faGear } from '@fortawesome/free-solid-svg-icons'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { DropdownMenu } from '@/components/ui/DropdownMenu'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import logo from '@/assets/ginity-logo-infinity-g.png'

export function Navbar({ hasExpiredToken }: { hasExpiredToken: boolean }) {
    const navigate = useNavigate()
    const logout = useAuthStore(s => s.logout)
    const user = useAuthStore(s => s.user)
    const { theme, toggle } = useThemeStore()
    const [dropdownOpen, setDropdownOpen] = React.useState(false)

    const initials = user?.login?.slice(0, 2).toUpperCase() || 'U'

    return (
        <header className="navbar" role="navigation" aria-label="Главная навигация">
            <div className="navbar__left">
                <Link to="/dashboard" className="navbar__brand" aria-label="ginity">
                    <img className="navbar__logo" src={logo} alt="" />
                </Link>
                <nav className="navbar__links">
                    <NavLink
                        to="/dashboard"
                        className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
                        onMouseEnter={() => { void import('@/pages/DashboardPage') }}
                        onFocus={() => { void import('@/pages/DashboardPage') }}
                    >
                        Дашборд
                    </NavLink>
                    <NavLink
                        to="/portfolio"
                        className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
                        onMouseEnter={() => { void import('@/pages/PortfolioPage') }}
                        onFocus={() => { void import('@/pages/PortfolioPage') }}
                    >
                        Портфель
                    </NavLink>
                    <NavLink
                        to="/robots"
                        className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
                        onMouseEnter={() => { void import('@/pages/robots-v2/RobotsV2FleetPage') }}
                        onFocus={() => { void import('@/pages/robots-v2/RobotsV2FleetPage') }}
                    >
                        Роботы
                    </NavLink>
                    <NavLink
                        to="/backtest"
                        className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
                        onMouseEnter={() => { void import('@/pages/robots-v2/BacktestLabPage') }}
                        onFocus={() => { void import('@/pages/robots-v2/BacktestLabPage') }}
                    >
                        Лаборатория
                    </NavLink>
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
                            icon={<FontAwesomeIcon icon={faGear} />}
                            onClick={() => navigate('/settings')}
                        >
                            Настройки
                        </DropdownMenu.Item>
                        <DropdownMenu.Divider />
                        <DropdownMenu.Item
                            variant="danger"
                            icon={<FontAwesomeIcon icon={faArrowRightFromBracket} />}
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
