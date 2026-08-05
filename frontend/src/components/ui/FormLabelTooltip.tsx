import React, { useCallback, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

type Props = {
    text: string
}

/** Classic light square-question–style mark (FA Pro Light not in free packages). */
function SquareQuestionIcon() {
    return (
        <svg className="form-label-tooltip__icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden>
            <rect
                x="1.25"
                y="1.25"
                width="13.5"
                height="13.5"
                rx="1.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.25"
            />
            <path
                d="M6.15 6.05c0-1.05.88-1.85 1.85-1.85s1.85.8 1.85 1.85c0 .72-.4 1.2-1.05 1.48-.48.2-.7.48-.7.92v.35"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.25"
                strokeLinecap="round"
            />
            <circle cx="8" cy="11.15" r="0.85" fill="currentColor" />
        </svg>
    )
}

export function FormLabelTooltip({ text }: Props) {
    const tipId = useId()
    const triggerRef = useRef<HTMLSpanElement>(null)
    const [open, setOpen] = useState(false)
    const [pos, setPos] = useState({ top: 0, left: 0 })

    const updatePos = useCallback(() => {
        const el = triggerRef.current
        if (!el) return
        const r = el.getBoundingClientRect()
        const pad = 8
        const maxW = Math.min(280, window.innerWidth - pad * 2)
        let left = r.left
        if (left + maxW > window.innerWidth - pad) {
            left = Math.max(pad, window.innerWidth - pad - maxW)
        }
        setPos({ top: r.bottom + 8, left })
    }, [])

    const show = useCallback(() => {
        updatePos()
        setOpen(true)
    }, [updatePos])

    const hide = useCallback(() => setOpen(false), [])

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
                className="form-label-tooltip"
                tabIndex={0}
                role="note"
                aria-label={text}
                aria-describedby={open ? tipId : undefined}
                onMouseEnter={show}
                onMouseLeave={hide}
                onFocus={show}
                onBlur={hide}
            >
                <SquareQuestionIcon />
            </span>
            {open &&
                createPortal(
                    <span
                        id={tipId}
                        className="form-label-tooltip__bubble"
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
