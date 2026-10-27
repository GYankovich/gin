///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiModal [1]
///@ Исходный модуль `frontend/src/components/ui/Modal.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'

interface ModalProps {
    open: boolean
    onClose: () => void
    title?: React.ReactNode
    width?: string
    className?: string
    /** Zero body padding — for layouts that bring their own (e.g. dashboard-settings). */
    flush?: boolean
    /** Copy beside the card. Turns the dialog into the login-style scene. */
    lead?: React.ReactNode
    /** Extra block inside `.modal__header`, after the title and close button. */
    headerExtra?: React.ReactNode
    children: React.ReactNode
}

/** Shared glass modal. Visual skin: `.dashboard-modal` (default product chrome). */
export function Modal({
    open,
    onClose,
    title,
    width = '560px',
    className = '',
    flush = false,
    lead,
    headerExtra,
    children,
}: ModalProps) {
    const onKeyDown = useCallback((e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose()
    }, [onClose])
    const backdropRef = useRef<HTMLDivElement>(null)
    const liftAboveKeyboard = className.split(/\s+/).includes('auth-modal')

    useEffect(() => {
        if (open) {
            document.addEventListener('keydown', onKeyDown)
            document.body.style.overflow = 'hidden'
        }
        return () => {
            document.removeEventListener('keydown', onKeyDown)
            document.body.style.overflow = ''
        }
    }, [open, onKeyDown])

    useEffect(() => {
        if (!open || !liftAboveKeyboard) return
        const backdrop = backdropRef.current
        const vv = window.visualViewport
        if (!backdrop || !vv) return

        const mobileQuery = window.matchMedia('(max-width: 767px)')
        let frame = 0

        const revealField = () => {
            const field = backdrop.querySelector('input:focus, textarea:focus')
            const scroller = field?.closest('.modal__body')
            if (!(field instanceof HTMLElement) || !(scroller instanceof HTMLElement)) return
            const fieldRect = field.getBoundingClientRect()
            const box = scroller.getBoundingClientRect()
            const margin = 16
            if (fieldRect.bottom > box.bottom - margin) {
                scroller.scrollTop += fieldRect.bottom - (box.bottom - margin)
            } else if (fieldRect.top < box.top + margin) {
                scroller.scrollTop -= (box.top + margin) - fieldRect.top
            }
        }

        const sync = () => {
            if (!mobileQuery.matches) {
                backdrop.style.removeProperty('--keyboard-overlap')
                return
            }
            // Distance from the layout bottom to the visible bottom. The URL bar
            // is a small gap; a keyboard is much taller. If the browser already
            // shrinks the layout viewport, this stays near zero and the sheet
            // is not lifted twice.
            const covered = window.innerHeight - vv.offsetTop - vv.height
            const overlap = covered >= 100 ? covered : 0
            backdrop.style.setProperty('--keyboard-overlap', `${Math.round(overlap)}px`)
            cancelAnimationFrame(frame)
            frame = requestAnimationFrame(revealField)
        }

        sync()
        vv.addEventListener('resize', sync)
        vv.addEventListener('scroll', sync)
        window.addEventListener('resize', sync)
        mobileQuery.addEventListener('change', sync)
        return () => {
            cancelAnimationFrame(frame)
            vv.removeEventListener('resize', sync)
            vv.removeEventListener('scroll', sync)
            window.removeEventListener('resize', sync)
            mobileQuery.removeEventListener('change', sync)
            backdrop.style.removeProperty('--keyboard-overlap')
        }
    }, [open, liftAboveKeyboard])

    if (!open) return null

    const label = typeof title === 'string' ? title : undefined
    const closeButton = (
        <button
            type="button"
            className={lead ? 'modal__close modal__close--round modal-scene__close' : 'modal__close'}
            onClick={onClose}
            aria-label="Закрыть"
        >
            ×
        </button>
    )
    const card = (
        <div
            className={['modal', 'dashboard-modal', flush ? 'modal--flush' : '', lead ? 'modal-scene__card' : '', className]
                .filter(Boolean)
                .join(' ')}
            style={lead ? undefined : { maxWidth: width }}
            role={lead ? undefined : 'dialog'}
            aria-modal={lead ? undefined : true}
            aria-label={lead ? undefined : label}
            onClick={(e) => e.stopPropagation()}
        >
            {!lead && title != null && title !== '' ? (
                <div className="modal__header">
                    <h2 className="modal__title">{title}</h2>
                    {closeButton}
                    {headerExtra}
                </div>
            ) : null}
            <div className="modal__body">
                {lead ? headerExtra : null}
                {children}
            </div>
        </div>
    )

    return createPortal(
        <div
            ref={backdropRef}
            className={['modal-backdrop', 'dashboard-modal-backdrop', lead ? 'modal-backdrop--scene' : '']
                .filter(Boolean)
                .join(' ')}
            onClick={onClose}
            role="presentation"
        >
            {lead ? (
                <>
                    {closeButton}
                    <div
                        className="modal-scene"
                        role="dialog"
                        aria-modal="true"
                        aria-label={label}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="modal-scene__scroll">
                            <div className="modal-scene__lead">{lead}</div>
                            {card}
                        </div>
                    </div>
                </>
            ) : card}
        </div>,
        document.body,
    )
}
