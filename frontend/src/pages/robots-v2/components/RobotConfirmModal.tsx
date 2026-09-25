import React from 'react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'

type RobotConfirmModalProps = {
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

/** Confirm dialog replacing window.confirm on Robots V2 pages. */
export function RobotConfirmModal({
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
}: RobotConfirmModalProps) {
    return (
        <Modal
            open={open}
            onClose={loading ? () => undefined : onClose}
            title={title}
            width={width}
            className="dashboard-modal"
        >
            <div className="robots-v2-confirm">
                {typeof message === 'string' ? <p className="robots-v2-confirm__copy">{message}</p> : message}
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
