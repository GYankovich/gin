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
type ItemVariant = 'default' | 'alert' | 'danger'

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

const MobileDockDropdownContext = createContext<DropdownContextValue | null>(null)

function useMobileDockDropdown() {
    const ctx = useContext(MobileDockDropdownContext)
    if (!ctx) {
        throw new Error('MobileDockDropdown subcomponents must be used within MobileDockDropdown')
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
    placement = 'above',
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
        <MobileDockDropdownContext.Provider
            value={{ open, onOpenChange, placement, portaled, menuRef, panelRef }}
        >
            <div ref={menuRef} className={['mobile-dock__menu', className].filter(Boolean).join(' ')}>
                {children}
            </div>
        </MobileDockDropdownContext.Provider>
    )
}

type TriggerProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
    'aria-label': string
}

function Trigger({ className, children, onClick, type = 'button', ...props }: TriggerProps) {
    const { open, onOpenChange } = useMobileDockDropdown()

    return (
        <button
            type={type}
            className={className}
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={(e) => {
                onClick?.(e)
                if (e.defaultPrevented) return
                onOpenChange(!open)
            }}
            {...props}
        >
            {children}
        </button>
    )
}

type PanelProps = {
    children: React.ReactNode
}

function Panel({ children }: PanelProps) {
    const { open, placement, portaled, menuRef, panelRef } = useMobileDockDropdown()
    const [coords, setCoords] = useState<PanelCoords | null>(null)

    const updateCoords = useCallback(() => {
        const menu = menuRef.current
        if (!menu) return

        const trigger = menu.querySelector('[aria-haspopup="menu"]') as HTMLElement | null
        if (!trigger) return

        const rect = trigger.getBoundingClientRect()
        const gap = 10
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
        'mobile-dock__dropdown',
        placement === 'below' ? 'mobile-dock__dropdown--below' : '',
        portaled ? 'mobile-dock__dropdown--portaled' : '',
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
    variant?: ItemVariant
}

function Item({ icon, children, onClick, disabled, variant = 'default' }: ItemProps) {
    const { onOpenChange } = useMobileDockDropdown()

    const variantClass =
        variant === 'alert'
            ? 'mobile-dock__dropdown-alert'
            : variant === 'danger'
              ? 'mobile-dock__dropdown-item--danger'
              : undefined

    return (
        <button
            type="button"
            role="menuitem"
            disabled={disabled}
            className={variantClass}
            onClick={(e) => {
                e.stopPropagation()
                onOpenChange(false)
                onClick(e)
            }}
        >
            {icon}
            {children}
        </button>
    )
}

function Divider() {
    return <div className="mobile-dock__dropdown-divider" />
}

export const MobileDockDropdown = Object.assign(Root, {
    Trigger,
    Panel,
    Item,
    Divider,
})
