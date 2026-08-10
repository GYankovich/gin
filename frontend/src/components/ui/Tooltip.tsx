import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

type Props = {
    text: string
    children: React.ReactNode
    className?: string
}

/**
 * Shared hover/focus tooltip used across settings and dashboard (FormLabelTooltip).
 * Opens above the trigger.
 */
export function Tooltip({ text, children, className = '' }: Props) {
    const tipId = useId()
    const triggerRef = useRef<HTMLSpanElement>(null)
    const bubbleRef = useRef<HTMLSpanElement>(null)
    const [open, setOpen] = useState(false)
    const [pos, setPos] = useState({ top: 0, left: 0 })

    const updatePos = useCallback(() => {
        const el = triggerRef.current
        if (!el) return
        const r = el.getBoundingClientRect()
        const pad = 8
        const gap = 8
        const maxW = Math.min(280, window.innerWidth - pad * 2)
        const bubbleH = bubbleRef.current?.offsetHeight ?? 0

        let left = r.left + r.width / 2
        left = Math.min(window.innerWidth - pad - maxW / 2, Math.max(pad + maxW / 2, left))

        // Prefer above; if not enough room, keep as high as possible above trigger.
        let top = r.top - gap
        if (bubbleH > 0 && top - bubbleH < pad) {
            top = Math.min(r.top - gap, pad + bubbleH)
        }

        setPos({ top, left })
    }, [])

    const show = useCallback(() => {
        setOpen(true)
    }, [])

    const hide = useCallback(() => setOpen(false), [])

    useLayoutEffect(() => {
        if (!open) return
        updatePos()
    }, [open, text, updatePos])

    useEffect(() => {
        if (!open) return
        const onScrollOrResize = () => updatePos()
        window.addEventListener('scroll', onScrollOrResize, true)
        window.addEventListener('resize', onScrollOrResize)
        return () => {
            window.removeEventListener('scroll', onScrollOrResize, true)
            window.removeEventListener('resize', onScrollOrResize)
        }
    }, [open, updatePos])

    return (
        <>
            <span
                ref={triggerRef}
                className={`form-label-tooltip ${className}`.trim()}
                tabIndex={0}
                role="note"
                aria-label={text}
                aria-describedby={open ? tipId : undefined}
                onMouseEnter={show}
                onMouseLeave={hide}
                onFocus={show}
                onBlur={hide}
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
            >
                {children}
            </span>
            {open &&
                createPortal(
                    <span
                        ref={bubbleRef}
                        id={tipId}
                        className="form-label-tooltip__bubble form-label-tooltip__bubble--above"
                        role="tooltip"
                        style={{ top: pos.top, left: pos.left }}
                    >
                        {text}
                    </span>,
                    document.body,
                )}
        </>
    )
}
