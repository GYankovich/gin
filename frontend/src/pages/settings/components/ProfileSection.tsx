import React from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPencil } from '@fortawesome/free-solid-svg-icons'
import { formatProfileDate } from '@/pages/settings/utils'

type Props = {
    login?: string | null
    email?: string | null
    createdAt?: string | null
    onEdit: () => void
    /** Full-row tap target matching mobile mockup. */
    sheet?: boolean
}

export function ProfileSection({ login, email, createdAt, onEdit, sheet = false }: Props) {
    const initials = (login || 'U').slice(0, 2).toUpperCase()

    if (sheet) {
        return (
            <button type="button" className="settings-profile settings-profile--sheet" onClick={onEdit}>
                <span className="settings-profile__avatar" aria-hidden>
                    {initials}
                </span>
                <span className="settings-profile__identity">
                    <span className="settings-profile__row">
                        <strong className="settings-profile__login">{login || 'Пользователь'}</strong>
                        <span className="settings-profile__since">с {formatProfileDate(createdAt)}</span>
                    </span>
                    <span className="settings-profile__meta">{email || '—'}</span>
                </span>
                <span className="settings-profile__edit" aria-hidden>
                    <FontAwesomeIcon icon={faPencil} className="settings-profile__edit-icon" />
                </span>
            </button>
        )
    }

    return (
        <div className="settings-profile">
            <button
                type="button"
                className="settings-profile__edit"
                onClick={onEdit}
                aria-label="Изменить профиль"
            >
                <FontAwesomeIcon icon={faPencil} className="settings-profile__edit-icon" />
            </button>

            <div className="settings-profile__avatar" aria-hidden>
                {initials}
            </div>
            <div className="settings-profile__identity">
                <div className="settings-profile__row">
                    <strong className="settings-profile__login">{login || 'Пользователь'}</strong>
                    <span className="settings-profile__since">с {formatProfileDate(createdAt)}</span>
                </div>
                <span className="settings-profile__meta">{email || '—'}</span>
            </div>
        </div>
    )
}
