import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'

type SideRailProps = {
    children: React.ReactNode
    'aria-label': string
    title?: React.ReactNode
    className?: string
    dimmed?: boolean
}

type SideRailItemProps = {
    name: React.ReactNode
    meta?: React.ReactNode
    mark?: React.ReactNode
    icon?: React.ReactNode
    active?: boolean
    disabled?: boolean
    className?: string
    onClick?: () => void
    'aria-current'?: 'page' | 'step' | 'true' | 'false' | boolean
}

type SideRailAddProps = {
    children: React.ReactNode
    className?: string
    onClick?: () => void
}

function prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function railAxis(el: HTMLElement): 'x' | 'y' {
    return window.getComputedStyle(el).flexDirection.startsWith('row') ? 'x' : 'y'
}

/** Scroll offset that keeps the active tab on screen with its neighbors. */
function neighborScrollTarget(el: HTMLElement): number | null {
    const active = el.querySelector<HTMLElement>('.side-rail__item.is-active')
    if (!active) return null
    const items = Array.from(el.querySelectorAll<HTMLElement>('.side-rail__item'))
    const index = items.indexOf(active)
    if (index < 0) return null
    const prev = items[index - 1] ?? null
    const next = items[index + 1] ?? null

    if (railAxis(el) === 'x') {
        const view = el.clientWidth
        const rangeStart = (prev ?? active).offsetLeft
        const rangeEndEl = next ?? active
        const rangeEnd = rangeEndEl.offsetLeft + rangeEndEl.offsetWidth
        const span = rangeEnd - rangeStart
        let target: number
        if (span <= view) {
            target = rangeStart - (view - span) / 2
        } else {
            const activeLeft = active.offsetLeft
            const activeRight = activeLeft + active.offsetWidth
            const peek = Math.min(48, Math.max(24, view * 0.16))
            target = activeLeft - (view - active.offsetWidth) / 2
            if (prev) target = Math.min(target, prev.offsetLeft + prev.offsetWidth - peek)
            if (next) target = Math.max(target, next.offsetLeft + peek - view)
            target = Math.max(target, activeRight - view)
            target = Math.min(target, activeLeft)
        }
        const max = Math.max(0, el.scrollWidth - view)
        return Math.max(0, Math.min(max, target))
    }

    const view = el.clientHeight
    const rangeStart = (prev ?? active).offsetTop
    const rangeEndEl = next ?? active
    const rangeEnd = rangeEndEl.offsetTop + rangeEndEl.offsetHeight
    const span = rangeEnd - rangeStart
    let target: number
    if (span <= view) {
        target = rangeStart - (view - span) / 2
    } else {
        const activeTop = active.offsetTop
        const activeBottom = activeTop + active.offsetHeight
        const peek = Math.min(36, Math.max(20, view * 0.2))
        target = activeTop - (view - active.offsetHeight) / 2
        if (prev) target = Math.min(target, prev.offsetTop + prev.offsetHeight - peek)
        if (next) target = Math.max(target, next.offsetTop + peek - view)
        target = Math.max(target, activeBottom - view)
        target = Math.min(target, activeTop)
    }
    const max = Math.max(0, el.scrollHeight - view)
    return Math.max(0, Math.min(max, target))
}

/** Mark sits on the viewport, so it stays visible while the tab row scrolls. */
function placeIndicator(nav: HTMLElement, indicator: HTMLSpanElement, scroll: number | null, animate: boolean) {
    const active = nav.querySelector<HTMLElement>('.side-rail__item.is-active')
    const shown = window.getComputedStyle(indicator).display !== 'none'
    if (!animate) indicator.style.transition = 'none'
    if (!active || !shown) {
        indicator.style.opacity = '0'
        if (!animate) {
            indicator.getBoundingClientRect()
            indicator.style.transition = ''
        }
        return
    }
    const axis = railAxis(nav)
    indicator.dataset.axis = axis
    indicator.style.opacity = '1'
    if (axis === 'x') {
        const left = active.offsetLeft - (scroll ?? nav.scrollLeft)
        indicator.style.width = `${active.offsetWidth}px`
        indicator.style.height = '2px'
        indicator.style.transform = `translate3d(${left}px, 0, 0)`
    } else {
        const top = active.offsetTop - (scroll ?? nav.scrollTop)
        indicator.style.width = '2px'
        indicator.style.height = `${Math.max(8, active.offsetHeight - 16)}px`
        indicator.style.transform = `translate3d(4px, ${top + 8}px, 0)`
    }
    if (!animate) {
        indicator.getBoundingClientRect()
        indicator.style.transition = ''
    }
}

function SideRailRoot({
    children,
    title,
    className = '',
    dimmed = false,
    'aria-label': ariaLabel,
}: SideRailProps) {
    const navRef = useRef<HTMLElement>(null)
    const indicatorRef = useRef<HTMLSpanElement>(null)
    const alignedOnce = useRef(false)
    const activeKey = useRef('')
    const programmatic = useRef(false)
    const settleTimer = useRef(0)
    const [fadeStart, setFadeStart] = useState(false)
    const [fadeEnd, setFadeEnd] = useState(false)

    const updateFades = () => {
        const el = navRef.current
        if (!el) return
        const horizontal = window.getComputedStyle(el).flexDirection.startsWith('row')
        if (horizontal) {
            const canScroll = el.scrollWidth > el.clientWidth + 1
            setFadeStart(canScroll && el.scrollLeft > 4)
            setFadeEnd(canScroll && el.scrollLeft + el.clientWidth < el.scrollWidth - 4)
            return
        }
        const canScroll = el.scrollHeight > el.clientHeight + 1
        setFadeStart(canScroll && el.scrollTop > 4)
        setFadeEnd(canScroll && el.scrollTop + el.clientHeight < el.scrollHeight - 4)
    }

    useLayoutEffect(() => {
        const el = navRef.current
        const indicator = indicatorRef.current
        if (!el || !indicator) return
        const active = el.querySelector<HTMLElement>('.side-rail__item.is-active')
        const key = active ? `${active.textContent ?? ''}:${railAxis(el)}` : ''
        const changed = key !== activeKey.current
        activeKey.current = key
        const animate = alignedOnce.current && changed && !prefersReducedMotion()
        const target = neighborScrollTarget(el)
        const axis = railAxis(el)
        const current = axis === 'x' ? el.scrollLeft : el.scrollTop
        if (target != null && Math.abs(current - target) > 1) {
            programmatic.current = animate
            el.scrollTo(
                axis === 'x'
                    ? { left: target, behavior: animate ? 'smooth' : 'auto' }
                    : { top: target, behavior: animate ? 'smooth' : 'auto' },
            )
        } else {
            programmatic.current = false
        }
        placeIndicator(el, indicator, target, animate)
        alignedOnce.current = true
        updateFades()
    }, [children])

    useEffect(() => {
        const el = navRef.current
        if (!el) return
        updateFades()
        const stick = () => {
            const indicator = indicatorRef.current
            if (!indicator) return
            placeIndicator(el, indicator, null, false)
        }
        const onScroll = () => {
            updateFades()
            if (programmatic.current) {
                window.clearTimeout(settleTimer.current)
                settleTimer.current = window.setTimeout(() => {
                    programmatic.current = false
                    stick()
                }, 140)
                return
            }
            stick()
        }
        const onResize = () => {
            updateFades()
            stick()
        }
        el.addEventListener('scroll', onScroll, { passive: true })
        window.addEventListener('resize', onResize)
        const ro = typeof ResizeObserver !== 'undefined'
            ? new ResizeObserver(() => onResize())
            : null
        ro?.observe(el)
        return () => {
            el.removeEventListener('scroll', onScroll)
            window.removeEventListener('resize', onResize)
            window.clearTimeout(settleTimer.current)
            ro?.disconnect()
        }
    }, [])

    return (
        <aside
            className={[
                'side-rail',
                dimmed ? 'side-rail--dim' : '',
                fadeStart ? 'side-rail--fade-start' : '',
                fadeEnd ? 'side-rail--fade-end' : '',
                className,
            ].filter(Boolean).join(' ')}
        >
            {title ? <p className="side-rail__title">{title}</p> : null}
            <div className="side-rail__viewport">
                <nav ref={navRef} className="side-rail__nav" aria-label={ariaLabel}>
                    {children}
                </nav>
                <span ref={indicatorRef} className="side-rail__indicator" aria-hidden />
            </div>
        </aside>
    )
}

function SideRailItem({
    name,
    meta,
    mark,
    icon,
    active = false,
    disabled = false,
    className = '',
    onClick,
    'aria-current': ariaCurrent,
}: SideRailItemProps) {
    return (
        <button
            type="button"
            className={[
                'side-rail__item',
                active ? 'is-active' : '',
                className,
            ].filter(Boolean).join(' ')}
            aria-current={ariaCurrent === true ? 'true' : ariaCurrent || undefined}
            disabled={disabled}
            onClick={onClick}
        >
            {icon}
            <span className="side-rail__item-text">
                <span className="side-rail__item-name">{name}</span>
                {meta != null && meta !== '' ? (
                    <span className="side-rail__item-meta">{meta}</span>
                ) : null}
            </span>
            {mark != null && mark !== '' ? (
                <span className="side-rail__mark" aria-hidden>
                    {mark}
                </span>
            ) : null}
        </button>
    )
}

function SideRailAdd({ children, className = '', onClick }: SideRailAddProps) {
    return (
        <button
            type="button"
            className={['side-rail__add', className].filter(Boolean).join(' ')}
            onClick={onClick}
        >
            <span className="side-rail__add-plus" aria-hidden>
                +
            </span>
            {children}
        </button>
    )
}

export const SideRail = Object.assign(SideRailRoot, {
    Item: SideRailItem,
    Add: SideRailAdd,
})
