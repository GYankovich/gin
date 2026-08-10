import React, { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { authService } from '@/services/authService'
import { useAuthStore } from '@/stores/authStore'

type EditUserModalProps = {
    open: boolean
    onClose: () => void
    login?: string | null
    email?: string | null
    phone?: string | null
}

function detailMessage(detail: unknown, fallback: string): string {
    if (Array.isArray(detail)) {
        return detail.map((x: any) => x?.msg || x).join('; ')
    }
    if (typeof detail === 'object' && detail && 'msg' in detail) {
        return String((detail as { msg: unknown }).msg)
    }
    if (detail != null && detail !== '') return String(detail)
    return fallback
}

export function EditUserModal({ open, onClose, login, email, phone }: EditUserModalProps) {
    const toast = useToast()
    const updateUser = useAuthStore((s) => s.updateUser)
    const [loginValue, setLoginValue] = useState('')
    const [emailValue, setEmailValue] = useState('')
    const [phoneValue, setPhoneValue] = useState('')
    const [currentPassword, setCurrentPassword] = useState('')
    const [newPassword, setNewPassword] = useState('')
    const [saving, setSaving] = useState(false)

    useEffect(() => {
        if (!open) return
        setLoginValue(login || '')
        setEmailValue(email || '')
        setPhoneValue(phone || '')
        setCurrentPassword('')
        setNewPassword('')
    }, [open, login, email, phone])

    const loginTrim = loginValue.trim()
    const emailTrim = emailValue.trim()
    const phoneTrim = phoneValue.trim()
    const hasAnyPassword = Boolean(currentPassword || newPassword)
    const passwordComplete = Boolean(currentPassword && newPassword && newPassword.length >= 3)
    const canSave =
        loginTrim.length >= 2 &&
        Boolean(emailTrim || phoneTrim) &&
        (!hasAnyPassword || passwordComplete)

    const handleSave = async () => {
        if (loginTrim.length < 2) {
            toast.show('Логин должен содержать минимум 2 символа', 'error')
            return
        }
        if (!emailTrim && !phoneTrim) {
            toast.show('Укажите телефон или email', 'error')
            return
        }
        if (hasAnyPassword && !passwordComplete) {
            toast.show('Для смены пароля укажите текущий и новый пароль (от 3 символов)', 'error')
            return
        }

        setSaving(true)
        try {
            const payload: {
                login: string
                email: string | null
                phone: string | null
                current_password?: string
                new_password?: string
            } = {
                login: loginTrim,
                email: emailTrim || null,
                phone: phoneTrim || null,
            }
            if (hasAnyPassword) {
                payload.current_password = currentPassword
                payload.new_password = newPassword
            }

            const user = await authService.changeUser(payload)
            updateUser(user)
            toast.show(hasAnyPassword ? 'Профиль и пароль обновлены' : 'Профиль обновлён', 'success')
            onClose()
        } catch (e: any) {
            toast.show(detailMessage(e?.response?.data?.detail, e?.message || 'Не удалось сохранить'), 'error')
        } finally {
            setSaving(false)
        }
    }

    return (
        <Modal
            open={open}
            onClose={onClose}
            title="Редактировать пользователя"
            width="520px"
            className="dashboard-modal"
        >
            <div className="form-group">
                <label className="form-label" htmlFor="profile-login">Логин</label>
                <input
                    id="profile-login"
                    className="gin-select__trigger"
                    value={loginValue}
                    onChange={(e) => setLoginValue(e.target.value)}
                    placeholder="login"
                    autoComplete="username"
                    required
                />
            </div>
            <div className="form-group">
                <label className="form-label" htmlFor="profile-phone">Телефон</label>
                <input
                    id="profile-phone"
                    className="gin-select__trigger"
                    type="tel"
                    value={phoneValue}
                    onChange={(e) => setPhoneValue(e.target.value)}
                    placeholder="+79001234567"
                    autoComplete="tel"
                />
            </div>
            <div className="form-group">
                <label className="form-label" htmlFor="profile-email">Email</label>
                <input
                    id="profile-email"
                    className="gin-select__trigger"
                    type="email"
                    value={emailValue}
                    onChange={(e) => setEmailValue(e.target.value)}
                    placeholder="name@example.com"
                    autoComplete="email"
                />
            </div>
                <div className="form-group">
                <label className="form-label" htmlFor="profile-current-password">Старый пароль</label>
                <input
                    id="profile-current-password"
                    className="gin-select__trigger"
                    type="password"
                    name="profile-current-password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    autoComplete="off"
                    autoCorrect="off"
                    autoCapitalize="off"
                    spellCheck={false}
                    data-lpignore="true"
                    data-1p-ignore="true"
                    data-form-type="other"
                />
            </div>
            <div className="form-group">
                <label className="form-label" htmlFor="profile-new-password">Новый пароль</label>
                <input
                    id="profile-new-password"
                    className="gin-select__trigger"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Минимум 3 символа"
                    autoComplete="new-password"
                />
            </div>
            {hasAnyPassword && !passwordComplete && (
                <div className="form-hint" style={{ color: 'var(--color-down)' }}>
                    Для смены - заполните оба поля
                </div>
            )}
            <div className="dashboard-settings-actions">
                <Button
                    loading={saving}
                    disabled={!canSave}
                    onClick={() => void handleSave()}
                >
                    Сохранить
                </Button>
            </div>
        </Modal>
    )
}
