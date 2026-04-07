import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'

export function Navbar() {
    const navigate = useNavigate()
    const logout = useAuthStore(s => s.logout)
    const user = useAuthStore(s => s.user)
    const { theme, toggle } = useThemeStore()
    const [dropdownOpen, setDropdownOpen] = React.useState(false)

    const initials = user?.login?.slice(0, 2).toUpperCase() || 'U'

    return (
        <header className="navbar" role="navigation" aria-label="Главная навигация">
            <div className="navbar__left">
                <div className="navbar__logo" onClick={() => navigate('/dashboard')}>
                    <span className="logo-g">G</span>
                    <span className="logo-i">I</span>
                    <span className="logo-n">N</span>
                </div>
                <nav className="navbar__links">
                    <NavLink to="/dashboard" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Дашборд</NavLink>
                    <NavLink to="/portfolio" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Портфель</NavLink>
                    <NavLink to="/robots" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Роботы</NavLink>
                    <NavLink to="/analytics" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Аналитика</NavLink>
                    <NavLink to="/testing" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Тестирование</NavLink>
                    <NavLink to="/live" className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>Live</NavLink>
                </nav>
            </div>

            <div className="navbar__right">
                <button className="navbar__theme-btn" onClick={toggle} title="Сменить тему">
                    {theme === 'dark' ? '☀' : '🌙'}
                </button>
                <div className="navbar__avatar-wrap" onClick={() => setDropdownOpen(!dropdownOpen)}>
                    <div className="navbar__avatar">{initials}</div>
                    {dropdownOpen && (
                        <div className="navbar__dropdown">
                            <button onClick={() => { setDropdownOpen(false); navigate('/settings') }}>
                                <span>⚙</span> Настройки
                            </button>
                            <div className="navbar__dropdown-divider" />
                            <button onClick={() => { setDropdownOpen(false); logout(); navigate('/login') }}>
                                <span>↩</span> Выход
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </header>
    )
}
