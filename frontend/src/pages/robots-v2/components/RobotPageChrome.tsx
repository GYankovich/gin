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
}

/**
 * Hero header for fleet / wizard / backtest.
 * Live + History use {@link RobotsQuietChrome}.
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
            className={`dashboard-hero__cfg${isActive ? ' robots-v2-chrome-nav--active' : ''}`}
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
                        <FontAwesomeIcon icon={faTowerBroadcast} />,
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
