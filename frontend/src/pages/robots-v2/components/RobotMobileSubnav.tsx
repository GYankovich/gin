import React, { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import type { RobotChromeActive } from '@/pages/robots-v2/components/RobotPageChrome'

export type RobotMobileNavItem = {
    id: RobotChromeActive
    label: string
    path: string
}

type RobotMobileSubnavProps = {
    items: RobotMobileNavItem[]
    active?: RobotChromeActive
}

/** Horizontal chip nav for robot detail pages. Sits under the hero so tabs do not crowd the title. */
export function RobotMobileSubnav({ items, active }: RobotMobileSubnavProps) {
    const navigate = useNavigate()
    const scrollerRef = useRef<HTMLElement>(null)

    useEffect(() => {
        const root = scrollerRef.current
        const current = root?.querySelector<HTMLElement>('[aria-current="page"]')
        if (!root || !current) return
        const left = current.offsetLeft - (root.clientWidth - current.clientWidth) / 2
        root.scrollTo({ left: Math.max(0, left) })
    }, [active, items])

    if (items.length === 0) return null

    return (
        <nav ref={scrollerRef} className="robots-mobile-subnav" aria-label="Разделы робота">
            {items.map(item => {
                const isActive = item.id === active
                return (
                    <button
                        key={item.id}
                        type="button"
                        className={`robots-mobile-subnav__item${isActive ? ' robots-mobile-subnav__item--active' : ''}`}
                        aria-current={isActive ? 'page' : undefined}
                        onClick={() => navigate(item.path)}
                    >
                        {item.label}
                    </button>
                )
            })}
        </nav>
    )
}
