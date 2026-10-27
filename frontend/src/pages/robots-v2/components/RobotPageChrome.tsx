import React, { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faTowerBroadcast } from '@fortawesome/free-solid-svg-icons'
import { Button } from '@/components/ui/Button'
import { PageHero } from '@/components/ui/PageHero'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import {
    RobotMobileSubnav,
    type RobotMobileNavItem,
} from '@/pages/robots-v2/components/RobotMobileSubnav'

export type RobotChromeActive =
    | 'fleet'
    | 'monitor'
    | 'edit'
    | 'logs'
    | 'backtest'
    | 'wizard'

type RobotPageChromeProps = {
    eyebrow: string
    title: string
    subtitle?: React.ReactNode
    /** Robot id for detail links; omit on fleet / create wizard. */
    robotId?: number | string | null
    active?: RobotChromeActive
    /** Extra primary actions after subnav (Start/Stop, Export, …). */
    actions?: React.ReactNode
    /** When true, show only Флот (create wizard). */
    fleetOnly?: boolean
    className?: string
    /** Quiet title + pill nav. Used by the live monitor. */
    variant?: 'hero' | 'quiet'
    /** Status beside the title in the quiet variant. */
    status?: React.ReactNode
}

/**
 * Shared header for a robot: Флот · Лайв · История.
 * Правка открывается из списка флота. Бэктест живёт в лаборатории.
 */
export function RobotPageChrome({
    eyebrow,
    title,
    subtitle,
    robotId,
    active,
    actions,
    fleetOnly = false,
    className = 'dashboard-hero--node',
    variant = 'hero',
    status,
}: RobotPageChromeProps) {
    const navigate = useNavigate()
    const isNarrow = useMediaQuery('(max-width: 767px)')
    const id = robotId != null && robotId !== '' ? String(robotId) : null

    const navItems = useMemo<RobotMobileNavItem[]>(() => {
        const items: RobotMobileNavItem[] = [
            { id: 'fleet', label: 'Флот', path: '/robots' },
        ]
        if (!fleetOnly && id) {
            items.push(
                { id: 'monitor', label: 'Лайв', path: `/robots/${id}/monitor` },
                { id: 'logs', label: 'История', path: `/robots/${id}/logs` },
            )
        }
        return items
    }, [fleetOnly, id])

    const navBtn = (
        label: string,
        path: string,
        isActive: boolean,
        icon?: React.ReactNode,
    ) => (
        <Button
            type="button"
            variant="ghost"
            size="sm"
            className={variant === 'quiet'
                ? `robots-quiet-chrome__tab${isActive ? ' robots-quiet-chrome__tab--active' : ''}`
                : `dashboard-hero__cfg${isActive ? ' robots-v2-chrome-nav--active' : ''}`}
            aria-current={isActive ? 'page' : undefined}
            onClick={() => navigate(path)}
        >
            {icon}
            {label}
        </Button>
    )

    const desktopNav = (
        <>
            {navBtn('Флот', '/robots', active === 'fleet')}
            {!fleetOnly && id ? (
                <>
                    {navBtn(
                        'Лайв',
                        `/robots/${id}/monitor`,
                        active === 'monitor',
                        variant === 'quiet' ? undefined : <FontAwesomeIcon icon={faTowerBroadcast} />,
                    )}
                    {navBtn('История', `/robots/${id}/logs`, active === 'logs')}
                </>
            ) : null}
        </>
    )

    const showDesktopNav = !isNarrow
    const heroActions = showDesktopNav || actions != null ? (
        <>
            {showDesktopNav ? desktopNav : null}
            {actions}
        </>
    ) : undefined

    if (variant === 'quiet') {
        return (
            <header className="robots-quiet-chrome">
                <div className="robots-quiet-chrome__top">
                    <div className="robots-quiet-chrome__copy">
                        <div className="robots-quiet-chrome__title-row">
                            <h1 className="robots-quiet-chrome__title">{title}</h1>
                            {status}
                        </div>
                        {subtitle}
                    </div>
                    {actions ? <div className="robots-quiet-chrome__actions">{actions}</div> : null}
                </div>
                {showDesktopNav ? (
                    <nav className="robots-quiet-chrome__nav" aria-label="Разделы робота">
                        {desktopNav}
                    </nav>
                ) : null}
                {isNarrow && navItems.length > 0 && (fleetOnly || id) ? (
                    <RobotMobileSubnav items={navItems} active={active} />
                ) : null}
            </header>
        )
    }

    return (
        <>
            <PageHero
                className={className}
                eyebrow={eyebrow}
                title={title}
                subtitle={subtitle}
                actions={heroActions}
            />
            {isNarrow && navItems.length > 0 && (fleetOnly || id) ? (
                <RobotMobileSubnav items={navItems} active={active} />
            ) : null}
        </>
    )
}
