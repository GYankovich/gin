///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiModal [1]
///@ Исходный модуль `frontend/src/components/ui/Modal.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { useEffect, useCallback } from 'react'

interface ModalProps {
    open: boolean
    onClose: () => void
    title?: string
    width?: string
    children: React.ReactNode
}

export function Modal({ open, onClose, title, width = '560px', children }: ModalProps) {
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

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal" style={{ maxWidth: width }} onClick={(e) => e.stopPropagation()}>
                {title && (
                    <div className="modal__header">
                        <h2 className="modal__title">{title}</h2>
                        <button className="modal__close" onClick={onClose}>×</button>
                    </div>
                )}
                <div className="modal__body">{children}</div>
            </div>
        </div>
    )
}
