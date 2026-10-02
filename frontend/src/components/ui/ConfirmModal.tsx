import React from 'react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'

export type ConfirmModalProps = {
    open: boolean
    onClose: () => void
    onConfirm: () => void
    title: string
    message: React.ReactNode
    confirmLabel?: string
    cancelLabel?: string
    confirmVariant?: 'danger' | 'primary' | 'secondary'
    loading?: boolean
    width?: string
}

/** Shared confirm dialog on top of Modal (glass / dashboard-modal skin). */
export function ConfirmModal({
    open,
    onClose,
    onConfirm,
    title,
    message,
    confirmLabel = 'Подтвердить',
    cancelLabel = 'Отмена',
    confirmVariant = 'danger',
    loading = false,
    width = '480px',
}: ConfirmModalProps) {
    return (
        <Modal
            open={open}
            onClose={loading ? () => undefined : onClose}
            title={title}
            width={width}
        >
            <div className="gin-confirm">
                {typeof message === 'string' ? <p className="gin-confirm__copy">{message}</p> : message}
                <div className="dashboard-settings-actions">
                    <Button variant="ghost" onClick={onClose} disabled={loading}>
                        {cancelLabel}
                    </Button>
                    <Button
                        variant={confirmVariant === 'primary' ? undefined : confirmVariant}
                        loading={loading}
                        onClick={onConfirm}
                    >
                        {confirmLabel}
                    </Button>
                </div>
            </div>
        </Modal>
    )
}
