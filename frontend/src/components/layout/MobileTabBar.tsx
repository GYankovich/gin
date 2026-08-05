///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsLayoutMobiletabbar [1]
///@ Исходный модуль `frontend/src/components/layout/MobileTabBar.tsx` — floating cyber dock (mobile shell).

import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { api } from '@/services/api'

type TabIconProps = { className?: string }

function IconPortfolio({ className }: TabIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 9.5h16v9.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19V9.5Z" stroke="currentColor" strokeWidth="1.5" />
            <path d="M8.5 9.5V7.2A1.7 1.7 0 0 1 10.2 5.5h3.6A1.7 1.7 0 0 1 15.5 7.2v2.3" stroke="currentColor" strokeWidth="1.5" />
            <path d="M4 13.5h16" stroke="currentColor" strokeWidth="1.5" />
        </svg>
    )
}

function IconRobots({ className }: TabIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="5.5" y="7.5" width="13" height="11" rx="2" stroke="currentColor" strokeWidth="1.5" />
            <path d="M12 4.5v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="12" cy="4" r="1.25" fill="currentColor" />
            <circle cx="9.25" cy="12.25" r="1.35" fill="currentColor" />
            <circle cx="14.75" cy="12.25" r="1.35" fill="currentColor" />
            <path d="M9 16h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M3.5 11v4M20.5 11v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
    )
}

function IconTesting({ className }: TabIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
                d="M9 3.5h6M10 3.5v5.2L5.8 16.4A2.4 2.4 0 0 0 7.9 20h8.2a2.4 2.4 0 0 0 2.1-3.6L14 8.7V3.5"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinejoin="round"
            />
            <path d="M8.2 14.5h7.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
    )
}

function IconLive({ className }: TabIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="2.25" fill="currentColor" />
            <path d="M7.2 7.2a6.8 6.8 0 0 0 0 9.6M16.8 7.2a6.8 6.8 0 0 1 0 9.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M4.4 4.4a10.8 10.8 0 0 0 0 15.2M19.6 4.4a10.8 10.8 0 0 1 0 15.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.55" />
        </svg>
    )
}

function IconTheme({ className }: TabIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="8.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="M12 3.75a8.25 8.25 0 0 0 0 16.5V3.75Z" fill="currentColor" />
        </svg>
    )
}

const LONG_PRESS_MS = 420
const TOOLTIP_HIDE_MS = 1400
const SUPPRESS_NAV_MS = 450
const MOVE_CANCEL_PX = 12

const tabs = [
    { to: '/portfolio', label: 'Портфель', Icon: IconPortfolio },
    { to: '/robots', label: 'Роботы', Icon: IconRobots },
    { to: '/testing', label: 'Тест', Icon: IconTesting },
    { to: '/live', label: 'Live', Icon: IconLive, accent: 'live' as const },
]

type TooltipState = {
    to: string
    label: string
    left: number
} | null

type MobileTabProps = {
    to: string
    label: string
    Icon: React.ComponentType<TabIconProps>
    accent?: 'live'
    onShowTooltip: (next: { to: string; label: string; left: number }) => void
    onDismissTooltip: () => void
    isTooltipTarget: boolean
    suppressNavUntilRef: React.MutableRefObject<number>
}

function MobileTab({
    to,
    label,
    Icon,
    accent,
    onShowTooltip,
    onDismissTooltip,
    isTooltipTarget,
    suppressNavUntilRef,
}: MobileTabProps) {
    const pressTimerRef = React.useRef<number | null>(null)
    const startPosRef = React.useRef<{ x: number; y: number } | null>(null)
    const longPressRef = React.useRef(false)
    const linkRef = React.useRef<HTMLAnchorElement | null>(null)
    const isActiveRef = React.useRef(false)

    const clearPressTimer = React.useCallback(() => {
        if (pressTimerRef.current != null) {
            window.clearTimeout(pressTimerRef.current)
            pressTimerRef.current = null
        }
    }, [])

    const armSuppressNav = React.useCallback(() => {
        suppressNavUntilRef.current = Date.now() + SUPPRESS_NAV_MS
    }, [suppressNavUntilRef])

    const onPointerDown = (event: React.PointerEvent<HTMLAnchorElement>) => {
        if (event.pointerType === 'mouse' && event.button !== 0) return

        longPressRef.current = false
        clearPressTimer()
        onDismissTooltip()
        startPosRef.current = { x: event.clientX, y: event.clientY }

        pressTimerRef.current = window.setTimeout(() => {
            pressTimerRef.current = null
            if (isActiveRef.current) return

            longPressRef.current = true
            armSuppressNav()

            const el = linkRef.current
            if (!el) return
            const rect = el.getBoundingClientRect()
            onShowTooltip({
                to,
                label,
                left: rect.left + rect.width / 2,
            })
        }, LONG_PRESS_MS)
    }

    const onPointerMove = (event: React.PointerEvent<HTMLAnchorElement>) => {
        const start = startPosRef.current
        if (!start || pressTimerRef.current == null) return
        const dx = Math.abs(event.clientX - start.x)
        const dy = Math.abs(event.clientY - start.y)
        if (dx > MOVE_CANCEL_PX || dy > MOVE_CANCEL_PX) {
            clearPressTimer()
        }
    }

    const endPress = () => {
        clearPressTimer()
        startPosRef.current = null
    }

    const onClick = (event: React.MouseEvent<HTMLAnchorElement>) => {
        if (longPressRef.current || Date.now() < suppressNavUntilRef.current) {
            event.preventDefault()
            longPressRef.current = false
            return
        }
        onDismissTooltip()
    }

    const onContextMenu = (event: React.MouseEvent<HTMLAnchorElement>) => {
        event.preventDefault()
        if (!isActiveRef.current && !longPressRef.current) {
            const el = linkRef.current
            if (el) {
                const rect = el.getBoundingClientRect()
                armSuppressNav()
                onShowTooltip({ to, label, left: rect.left + rect.width / 2 })
            }
        }
    }

    React.useEffect(() => () => clearPressTimer(), [clearPressTimer])

    return (
        <NavLink
            ref={linkRef}
            to={to}
            aria-label={label}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endPress}
            onPointerCancel={endPress}
            onPointerLeave={endPress}
            onClick={onClick}
            onContextMenu={onContextMenu}
            className={({ isActive }) => {
                isActiveRef.current = isActive
                return [
                    'mobile-dock__tab',
                    isActive ? 'mobile-dock__tab--active' : 'mobile-dock__tab--idle',
                    accent === 'live' ? 'mobile-dock__tab--live' : '',
                    isTooltipTarget ? 'mobile-dock__tab--tip' : '',
                ]
                    .filter(Boolean)
                    .join(' ')
            }}
        >
            <span className="mobile-dock__tab-indicator" aria-hidden />
            <span className="mobile-dock__tab-icon-wrap">
                <Icon className="mobile-dock__tab-icon" />
            </span>
            <span className="mobile-dock__tab-label" aria-hidden="true">
                {label}
            </span>
        </NavLink>
    )
}

export function MobileTabBar() {
    const navigate = useNavigate()
    const logout = useAuthStore(s => s.logout)
    const user = useAuthStore(s => s.user)
    const { theme, toggle } = useThemeStore()

    const [tooltip, setTooltip] = React.useState<TooltipState>(null)
    const [menuOpen, setMenuOpen] = React.useState(false)
    const [hasExpiredToken, setHasExpiredToken] = React.useState(false)

    const hideTimerRef = React.useRef<number | null>(null)
    const suppressNavUntilRef = React.useRef(0)
    const dockRef = React.useRef<HTMLElement | null>(null)
    const menuRef = React.useRef<HTMLDivElement | null>(null)

    const initials = user?.login?.slice(0, 2).toUpperCase() || 'U'

    React.useEffect(() => {
        let active = true
        const load = async () => {
            try {
                const { data } = await api.post('/apikey/data', {})
                const keys = Array.isArray(data?.keys) ? data.keys : []
                const hasExpired = keys.some((k: { status?: number }) => Number(k?.status || 0) === 3)
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
        if (!menuOpen) return

        const onPointerDown = (event: MouseEvent | TouchEvent) => {
            const root = menuRef.current
            const target = event.target as Node | null
            if (root && target && !root.contains(target)) {
                setMenuOpen(false)
            }
        }
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setMenuOpen(false)
        }

        document.addEventListener('mousedown', onPointerDown)
        document.addEventListener('touchstart', onPointerDown)
        document.addEventListener('keydown', onKeyDown)
        return () => {
            document.removeEventListener('mousedown', onPointerDown)
            document.removeEventListener('touchstart', onPointerDown)
            document.removeEventListener('keydown', onKeyDown)
        }
    }, [menuOpen])

    const clearHideTimer = React.useCallback(() => {
        if (hideTimerRef.current != null) {
            window.clearTimeout(hideTimerRef.current)
            hideTimerRef.current = null
        }
    }, [])

    const dismissTooltip = React.useCallback(() => {
        clearHideTimer()
        setTooltip(null)
    }, [clearHideTimer])

    const showTooltip = React.useCallback((next: { to: string; label: string; left: number }) => {
        clearHideTimer()
        setMenuOpen(false)
        const dockLeft = dockRef.current?.getBoundingClientRect().left ?? 0
        setTooltip({ ...next, left: next.left - dockLeft })
        hideTimerRef.current = window.setTimeout(() => {
            setTooltip(null)
            hideTimerRef.current = null
        }, TOOLTIP_HIDE_MS)
    }, [clearHideTimer])

    React.useEffect(() => () => clearHideTimer(), [clearHideTimer])

    return (
        <div className="mobile-dock" aria-label="Мобильная навигация">
            <nav ref={dockRef} className="mobile-dock__capsule">
                <div className="mobile-dock__scanline" aria-hidden />
                <button
                    type="button"
                    className="mobile-dock__brand"
                    aria-label="GIN — на дашборд"
                    onClick={() => {
                        dismissTooltip()
                        setMenuOpen(false)
                        navigate('/dashboard')
                    }}
                >
                    <span className="mobile-dock__brand-g">G</span>
                    <span className="mobile-dock__brand-i">I</span>
                    <span className="mobile-dock__brand-n">N</span>
                </button>

                <div className="mobile-dock__divider" aria-hidden />

                <div className="mobile-dock__tabs">
                    {tabs.map(({ to, label, Icon, accent }) => (
                        <MobileTab
                            key={to}
                            to={to}
                            label={label}
                            Icon={Icon}
                            accent={accent}
                            onShowTooltip={showTooltip}
                            onDismissTooltip={dismissTooltip}
                            isTooltipTarget={tooltip?.to === to}
                            suppressNavUntilRef={suppressNavUntilRef}
                        />
                    ))}
                </div>

                <div className="mobile-dock__divider" aria-hidden />

                <div className="mobile-dock__menu" ref={menuRef}>
                    <button
                        type="button"
                        className={`mobile-dock__avatar ${menuOpen ? 'mobile-dock__avatar--open' : ''} ${hasExpiredToken ? 'mobile-dock__avatar--alert' : ''}`}
                        aria-label="Меню профиля"
                        aria-haspopup="menu"
                        aria-expanded={menuOpen}
                        onClick={() => {
                            dismissTooltip()
                            setMenuOpen(open => !open)
                        }}
                    >
                        <span className="mobile-dock__avatar-text">{initials}</span>
                        {hasExpiredToken && <span className="mobile-dock__avatar-dot" aria-hidden />}
                    </button>

                    {menuOpen && (
                        <div className="mobile-dock__dropdown" role="menu">
                            {hasExpiredToken && (
                                <button
                                    type="button"
                                    role="menuitem"
                                    className="mobile-dock__dropdown-alert"
                                    onClick={() => {
                                        setMenuOpen(false)
                                        navigate('/settings#tokens')
                                    }}
                                >
                                    Истёкший токен
                                </button>
                            )}
                            <button
                                type="button"
                                role="menuitem"
                                onClick={() => {
                                    setMenuOpen(false)
                                    toggle()
                                }}
                            >
                                <IconTheme className="mobile-dock__dropdown-icon" />
                                {theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
                            </button>
                            <button
                                type="button"
                                role="menuitem"
                                onClick={() => {
                                    setMenuOpen(false)
                                    navigate('/settings')
                                }}
                            >
                                <span className="mobile-dock__dropdown-glyph" aria-hidden>⚙</span>
                                Настройки
                            </button>
                            <div className="mobile-dock__dropdown-divider" />
                            <button
                                type="button"
                                role="menuitem"
                                onClick={() => {
                                    setMenuOpen(false)
                                    logout()
                                    navigate('/login')
                                }}
                            >
                                <span className="mobile-dock__dropdown-glyph" aria-hidden>↩</span>
                                Выход
                            </button>
                        </div>
                    )}
                </div>

                {tooltip && (
                    <span
                        className="mobile-dock__tooltip"
                        role="tooltip"
                        style={{ left: tooltip.left }}
                    >
                        {tooltip.label}
                    </span>
                )}
            </nav>
        </div>
    )
}
