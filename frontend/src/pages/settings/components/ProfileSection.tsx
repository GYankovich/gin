import React from 'react'

import { CopyButton } from '@/pages/settings/components/CopyButton'

import { formatLoginTime } from '@/pages/settings/utils'



type Props = {

    login?: string | null

    email?: string | null

    phone?: string | null

    loginAt?: string | null

    sessionActive: boolean

}



function InfoRow({

    label,

    value,

    copyValue,

    index,

}: {

    label: string

    value: string

    copyValue?: string

    index: number

}) {

    return (

        <div className="settings-profile-field" style={{ animationDelay: `${index * 45}ms` }}>

            <span className="settings-profile-field__label">{label}</span>

            <div className="settings-profile-field__value-wrap">

                <span className="settings-profile-field__value mono">{value || '—'}</span>

                {copyValue && <CopyButton value={copyValue} label={`Скопировать ${label.toLowerCase()}`} />}

            </div>

        </div>

    )

}



export function ProfileSection({ login, email, phone, loginAt, sessionActive }: Props) {

    const initials = login?.slice(0, 2).toUpperCase() || 'U'



    return (

        <div className="settings-profile-panel">

            <div className="settings-profile-panel__hero">

                <div className="settings-profile-panel__avatar-ring">

                    <div className="settings-profile-panel__avatar">{initials}</div>

                </div>

                <div className="settings-profile-panel__identity">

                    <div className="settings-profile-panel__name">{login || 'Пользователь'}</div>

                    <span

                        className={`token-chip token-chip--status token-chip--status-${sessionActive ? 'up' : 'neutral'}`}

                    >

                        {sessionActive ? 'Сессия активна' : 'Сессия неактивна'}

                    </span>

                </div>

            </div>



            <div className="settings-profile-panel__fields">

                <InfoRow label="Логин" value={login || '—'} copyValue={login || undefined} index={0} />

                <InfoRow label="Email" value={email || '—'} copyValue={email || undefined} index={1} />

                <InfoRow label="Телефон" value={phone || '—'} copyValue={phone || undefined} index={2} />

                <InfoRow label="Последний вход" value={formatLoginTime(loginAt)} index={3} />

            </div>

        </div>

    )

}


