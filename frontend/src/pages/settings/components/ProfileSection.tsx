import React, { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPencil } from '@fortawesome/free-solid-svg-icons'
import { useToast } from '@/components/ui/Toast'
import { EditUserModal } from '@/pages/settings/components/ProfileModals'
import { useCopyableField } from '@/pages/settings/hooks/useLongPressCopy'
import { formatLoginTime, formatProfileDate } from '@/pages/settings/utils'

type Props = {
    login?: string | null
    email?: string | null
    phone?: string | null
    createdAt?: string | null
    loginAt?: string | null
}

function ProfileRow({
    label,
    value,
    copyValue,
}: {
    label: string
    value: string
    copyValue?: string
}) {
    const toast = useToast()
    const { className: copyClass, ...copyHandlers } = useCopyableField(copyValue, {
        onCopied: () => toast.show(`${label} скопирован`, 'success'),
        onFailed: () => toast.show('Не удалось скопировать', 'error'),
    })

    return (
        <div className="settings-profile-row">
            <span className="settings-profile-row__label">{label}</span>
            <div className="settings-profile-row__value-wrap">
                {copyValue ? (
                    <span
                        className={`settings-profile-row__value mono ${copyClass}`}
                        {...copyHandlers}
                    >
                        {value || '—'}
                    </span>
                ) : (
                    <span className="settings-profile-row__value mono">{value || '—'}</span>
                )}
            </div>
        </div>
    )
}

export function ProfileSection({ login, email, phone, createdAt, loginAt }: Props) {
    const [editOpen, setEditOpen] = useState(false)
    const initials = login?.slice(0, 2).toUpperCase() || 'U'

    return (
        <div className="settings-profile-panel">
            <div className="settings-profile-panel__head">
                <div className="settings-profile-panel__who">
                    <div className="settings-profile-panel__avatar" aria-hidden>
                        {initials}
                    </div>
                    <div className="settings-profile-panel__identity">
                        <h2 className="settings-profile-panel__name">{login || 'Пользователь'}</h2>
                        <span className="settings-profile-panel__login-at mono">
                            вход {formatLoginTime(loginAt)}
                        </span>
                    </div>
                </div>
                <button
                    type="button"
                    className="settings-profile-panel__edit"
                    onClick={() => setEditOpen(true)}
                    aria-label="Редактировать профиль"
                >
                    <FontAwesomeIcon icon={faPencil} className="settings-profile-panel__edit-icon" />
                </button>
            </div>

            <div className="settings-profile-rows">
                <ProfileRow label="Email" value={email || '—'} copyValue={email || undefined} />
                <ProfileRow label="Телефон" value={phone || '—'} copyValue={phone || undefined} />
                <ProfileRow label="Создан" value={formatProfileDate(createdAt)} />
            </div>

            <EditUserModal
                open={editOpen}
                onClose={() => setEditOpen(false)}
                login={login}
                email={email}
                phone={phone}
            />
        </div>
    )
}
