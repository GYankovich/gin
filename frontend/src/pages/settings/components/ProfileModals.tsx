import React, { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { authService } from '@/services/authService'
import { useAuthStore } from '@/stores/authStore'
import '@/pages/DashboardPage.css'

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
            title="Профиль"
            flush
            className="dash-quiet-modal dash-scene-modal"
            lead={(
                <div className="dash-scene__brand">
                    <p className="dash-scene__kicker">Настройки</p>
                    <p className="dash-scene__title">Изменить профиль</p>
                    <p className="dash-scene__line">
                        Логин и контакты. Пароль меняйте только если нужно — заполните оба поля.
                    </p>
                </div>
            )}
        >
            <div className="dashboard-settings">
                <div className="dashboard-settings-list">
                    <section className="dashboard-settings-group">
                        <div className="settings-scene-fields">
                            <label className="settings-scene-field" htmlFor="profile-login">
                                <span>Логин</span>
                                <input
                                    id="profile-login"
                                    value={loginValue}
                                    onChange={(e) => setLoginValue(e.target.value)}
                                    placeholder="login"
                                    autoComplete="username"
                                    required
                                />
                            </label>
                            <label className="settings-scene-field" htmlFor="profile-email">
                                <span>Почта</span>
                                <input
                                    id="profile-email"
                                    type="email"
                                    value={emailValue}
                                    onChange={(e) => setEmailValue(e.target.value)}
                                    placeholder="name@example.com"
                                    autoComplete="email"
                                />
                            </label>
                            <label className="settings-scene-field" htmlFor="profile-current-password">
                                <span>Старый пароль</span>
                                <input
                                    id="profile-current-password"
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
                            </label>
                            <label className="settings-scene-field" htmlFor="profile-new-password">
                                <span>Новый пароль</span>
                                <input
                                    id="profile-new-password"
                                    type="password"
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    placeholder="Минимум 3 символа"
                                    autoComplete="new-password"
                                />
                            </label>
                            {hasAnyPassword && !passwordComplete ? (
                                <p className="settings-scene-hint settings-scene-hint--warn">
                                    Для смены пароля заполните оба поля.
                                </p>
                            ) : null}
                        </div>
                    </section>
                </div>
                <div className="dashboard-settings-actions">
                    <Button
                        type="button"
                        variant="ghost"
                        size="lg"
                        className="dashboard-settings-actions__apply"
                        loading={saving}
                        disabled={!canSave}
                        onClick={() => void handleSave()}
                    >
                        Сохранить
                    </Button>
                </div>
            </div>
        </Modal>
    )
}
