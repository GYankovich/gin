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
        if (!menu) return

        const trigger = menu.querySelector('[aria-haspopup="menu"]') as HTMLElement | null
        if (!trigger) return

        const rect = trigger.getBoundingClientRect()
        const gap = 8
        const right = Math.max(8, window.innerWidth - rect.right)

        if (placement === 'below') {
            setCoords({ top: rect.bottom + gap, right })
            return
        }

        setCoords({ bottom: window.innerHeight - rect.top + gap, right })
    }, [menuRef, placement])

    useLayoutEffect(() => {
        if (!open || !portaled) {
            setCoords(null)
            return
        }

        updateCoords()
        window.addEventListener('resize', updateCoords)
        window.addEventListener('scroll', updateCoords, true)
        return () => {
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
}

function Item({ icon, children, onClick, disabled }: ItemProps) {
    const { onOpenChange } = useDropdownMenu()

    return (
        <button
            type="button"
            role="menuitem"
            disabled={disabled}
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

/** Cyber-styled dropdown shared by navbar avatar and page hero actions. */
export const DropdownMenu = Object.assign(Root, {
    Trigger,
    Panel,
    Item,
    Divider,
})
