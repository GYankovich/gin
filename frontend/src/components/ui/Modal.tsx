///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiModal [1]
///@ Исходный модуль `frontend/src/components/ui/Modal.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'

interface ModalProps {
    open: boolean
    onClose: () => void
    title?: React.ReactNode
    width?: string
    className?: string
    /** Zero body padding — for layouts that bring their own (e.g. dashboard-settings). */
    flush?: boolean
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
    children,
}: ModalProps) {
    const onKeyDown = useCallback((e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose()
    }, [onClose])

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

    if (!open) return null

    return createPortal(
        <div
            className="modal-backdrop dashboard-modal-backdrop"
            onClick={onClose}
            role="presentation"
        >
            <div
                className={['modal', 'dashboard-modal', flush ? 'modal--flush' : '', className]
                    .filter(Boolean)
                    .join(' ')}
                style={{ maxWidth: width }}
                role="dialog"
                aria-modal="true"
                aria-label={typeof title === 'string' ? title : undefined}
                onClick={(e) => e.stopPropagation()}
            >
                {title != null && title !== '' ? (
                    <div className="modal__header">
                        <h2 className="modal__title">{title}</h2>
                        <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть">
                            ×
                        </button>
                    </div>
                ) : null}
                <div className="modal__body">{children}</div>
            </div>
        </div>,
        document.body,
    )
}
