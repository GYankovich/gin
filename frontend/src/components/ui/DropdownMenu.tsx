import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useLayoutEffect,
    useRef,
    useState,
} from 'react'
import { createPortal } from 'react-dom'

type Placement = 'above' | 'below'

type PanelCoords = {
    top?: number
    bottom?: number
    right: number
    maxWidth: number
    maxHeight: number
}

type DropdownContextValue = {
    open: boolean
    onOpenChange: (open: boolean) => void
    placement: Placement
    portaled: boolean
    menuRef: React.RefObject<HTMLDivElement | null>
    panelRef: React.RefObject<HTMLDivElement | null>
}

const DropdownMenuContext = createContext<DropdownContextValue | null>(null)

function useDropdownMenu() {
    const ctx = useContext(DropdownMenuContext)
    if (!ctx) {
        throw new Error('DropdownMenu subcomponents must be used within DropdownMenu')
    }
    return ctx
}

type RootProps = {
    open: boolean
    onOpenChange: (open: boolean) => void
    placement?: Placement
    portaled?: boolean
    className?: string
    children: React.ReactNode
}

function Root({
    open,
    onOpenChange,
    placement = 'below',
    portaled = false,
    className,
    children,
}: RootProps) {
    const menuRef = useRef<HTMLDivElement>(null)
    const panelRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!open) return

        const onPointerDown = (event: MouseEvent | TouchEvent) => {
            const target = event.target as Node | null
            if (!target) return
            if (menuRef.current?.contains(target)) return
            if (panelRef.current?.contains(target)) return
            onOpenChange(false)
        }
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') onOpenChange(false)
        }

        document.addEventListener('mousedown', onPointerDown)
        document.addEventListener('touchstart', onPointerDown)
        document.addEventListener('keydown', onKeyDown)
        return () => {
            document.removeEventListener('mousedown', onPointerDown)
            document.removeEventListener('touchstart', onPointerDown)
            document.removeEventListener('keydown', onKeyDown)
        }
    }, [open, onOpenChange])

    return (
        <DropdownMenuContext.Provider
            value={{ open, onOpenChange, placement, portaled, menuRef, panelRef }}
        >
            <div ref={menuRef} className={['menu-dropdown-root', className].filter(Boolean).join(' ')}>
                {children}
            </div>
        </DropdownMenuContext.Provider>
    )
}

type TriggerProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
    'aria-label': string
    asChild?: boolean
}

function Trigger({ className, children, onClick, type = 'button', asChild = false, ...props }: TriggerProps) {
    const { open, onOpenChange } = useDropdownMenu()

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
        onClick?.(e)
        if (e.defaultPrevented) return
        onOpenChange(!open)
    }

    if (asChild && React.isValidElement<React.ButtonHTMLAttributes<HTMLButtonElement>>(children)) {
        const child = children
        return React.cloneElement(child, {
            ...props,
            type,
            className: [child.props.className, className].filter(Boolean).join(' '),
            'aria-haspopup': 'menu',
            'aria-expanded': open,
            onClick: (e: React.MouseEvent<HTMLButtonElement>) => {
                child.props.onClick?.(e)
                if (!e.defaultPrevented) handleClick(e)
            },
        })
    }

    return (
        <button
            type={type}
            className={className}
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={handleClick}
            {...props}
        >
            {children}
        </button>
    )
}

type PanelProps = {
    children: React.ReactNode
    className?: string
}

function Panel({ children, className }: PanelProps) {
    const { open, placement, portaled, menuRef, panelRef } = useDropdownMenu()
    const [coords, setCoords] = useState<PanelCoords | null>(null)

    const updateCoords = useCallback(() => {
        const menu = menuRef.current
        const panel = panelRef.current
        if (!menu) return

        const trigger = menu.querySelector('[aria-haspopup="menu"]') as HTMLElement | null
        if (!trigger) return

        const rect = trigger.getBoundingClientRect()
        const gap = 8
        const margin = 8
        const vw = window.innerWidth
        const vh = window.innerHeight
        const maxWidth = Math.max(160, Math.min(320, vw - margin * 2))
        const panelWidth = Math.min(Math.max(panel?.offsetWidth || 0, 188), maxWidth)
        const panelHeight = panel?.offsetHeight || 0

        // Align to trigger's right edge, then keep the panel inside the viewport.
        let right = vw - rect.right
        const maxRight = Math.max(margin, vw - panelWidth - margin)
        right = Math.min(Math.max(margin, right), maxRight)

        const spaceBelow = Math.max(0, vh - rect.bottom - gap - margin)
        const spaceAbove = Math.max(0, rect.top - gap - margin)
        const placeBelow = placement === 'below'
            ? spaceBelow >= Math.min(panelHeight || 160, spaceAbove) || spaceBelow >= spaceAbove
            : spaceAbove < 120 && spaceBelow > spaceAbove

        if (placeBelow) {
            setCoords({
                top: rect.bottom + gap,
                right,
                maxWidth,
                maxHeight: Math.max(120, spaceBelow),
            })
            return
        }

        setCoords({
            bottom: vh - rect.top + gap,
            right,
            maxWidth,
            maxHeight: Math.max(120, spaceAbove),
        })
    }, [menuRef, panelRef, placement])

    useLayoutEffect(() => {
        if (!open || !portaled) {
            setCoords(null)
            return
        }

        updateCoords()
        const raf = window.requestAnimationFrame(updateCoords)
        window.addEventListener('resize', updateCoords)
        window.addEventListener('scroll', updateCoords, true)
        return () => {
            window.cancelAnimationFrame(raf)
            window.removeEventListener('resize', updateCoords)
            window.removeEventListener('scroll', updateCoords, true)
        }
    }, [open, portaled, updateCoords])

    if (!open) return null

    const panelClassName = [
        'menu-dropdown',
        placement === 'above' ? 'menu-dropdown--above' : '',
        portaled ? 'menu-dropdown--portaled' : '',
        className,
    ]
        .filter(Boolean)
        .join(' ')

    const panelStyle: React.CSSProperties | undefined =
        portaled && coords
            ? {
                  top: coords.top,
                  bottom: coords.bottom,
                  right: coords.right,
                  left: 'auto',
                  maxWidth: coords.maxWidth,
                  maxHeight: coords.maxHeight,
                  width: 'max-content',
                  overflow: 'auto',
              }
            : undefined

    const panel = (
        <div ref={panelRef} className={panelClassName} style={panelStyle} role="menu">
            {children}
        </div>
    )

    if (portaled) {
        return createPortal(panel, document.body)
    }

    return panel
}

type ItemProps = {
    icon?: React.ReactNode
    children: React.ReactNode
    onClick: (event: React.MouseEvent<HTMLButtonElement>) => void
    disabled?: boolean
    variant?: 'default' | 'danger'
}

function Item({ icon, children, onClick, disabled, variant = 'default' }: ItemProps) {
    const { onOpenChange } = useDropdownMenu()

    return (
        <button
            type="button"
            role="menuitem"
            disabled={disabled}
            className={variant === 'danger' ? 'is-danger' : undefined}
            onClick={(e) => {
                e.stopPropagation()
                onOpenChange(false)
                onClick(e)
            }}
        >
            {icon != null ? (
                <span className="menu-dropdown__icon" aria-hidden>
                    {icon}
                </span>
            ) : null}
            <span className="menu-dropdown__label">{children}</span>
        </button>
    )
}

function Divider() {
    return <div className="menu-dropdown__divider" />
}

/** Shared dropdown: navbar avatar, create FAB, and similar menus. */
export const DropdownMenu = Object.assign(Root, {
    Trigger,
    Panel,
    Item,
    Divider,
})
