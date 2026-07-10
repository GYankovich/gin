import React from 'react'
import { Button } from '@/components/ui/Button'

export type SetupValidateBarProps = {
    onValidate: () => void
    onSave?: () => void
    onLaunch?: () => void
    canLaunch?: boolean
    launching?: boolean
    disabled?: boolean
    statusText?: string
    className?: string
}

/** Блок 5 — sticky footer: проверка, сохранение, запуск. */
export function SetupValidateBar({
    onValidate,
    onSave,
    onLaunch,
    canLaunch = false,
    launching = false,
    disabled = false,
    statusText,
    className = '',
}: SetupValidateBarProps) {
    return (
        <div className={`testing-setup-validate-bar testing-setup-validate-bar--sticky ${className}`.trim()}>
            <div className="testing-setup-validate-bar__actions">
                <Button variant="secondary" size="sm" disabled={disabled || launching} onClick={onValidate}>
                    Проверить
                </Button>
                {onSave && (
                    <Button variant="secondary" size="sm" disabled={disabled || launching} onClick={onSave}>
                        Сохранить конфиг
                    </Button>
                )}
                {onLaunch && (
                    <Button
                        variant="primary"
                        glow
                        size="sm"
                        disabled={disabled || launching || !canLaunch}
                        loading={launching}
                        onClick={onLaunch}
                    >
                        Запустить бэктест
                    </Button>
                )}
            </div>
            {statusText && <p className="form-hint testing-setup-validate-bar__hint">{statusText}</p>}
        </div>
    )
}
