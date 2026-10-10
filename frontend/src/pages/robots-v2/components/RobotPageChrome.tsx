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
 * Shared PageHero + subnav for Robots V2 detail pages.
 * Full set: Флот · Лайв · Правка · Audit · Бэктест
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
                { id: 'edit', label: 'Правка', path: `/robots/edit/${id}` },
                { id: 'logs', label: 'Audit', path: `/robots/${id}/logs` },
                { id: 'backtest', label: 'Бэктест', path: `/robots/${id}/backtest` },
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
                    {navBtn('Правка', `/robots/edit/${id}`, active === 'edit')}
                    {navBtn('Audit', `/robots/${id}/logs`, active === 'logs')}
                    {navBtn('Бэктест', `/robots/${id}/backtest`, active === 'backtest')}
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
