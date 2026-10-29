import React, { useCallback, useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faChevronRight } from '@fortawesome/free-solid-svg-icons'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { authService, type AuthSession } from '@/services/authService'

type Props = {
    onLogoutCurrent: () => void
    sheet?: boolean
}

function formatSessionWhen(iso: string | null | undefined): string {
    if (!iso) return '—'
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return '—'
    return date.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    })
}

export function SessionsSection({ onLogoutCurrent, sheet = false }: Props) {
    const [items, setItems] = useState<AuthSession[]>([])
    const [loading, setLoading] = useState(true)
    const [busyId, setBusyId] = useState<number | 'all' | null>(null)
    const [open, setOpen] = useState(false)
    const [loggingOut, setLoggingOut] = useState(false)

    const reload = useCallback(async () => {
        setLoading(true)
        try {
            const next = await authService.listSessions()
            setItems(next)
        } catch {
            setItems([])
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void reload()
    }, [reload])

    useEffect(() => {
        if (!open) return
        void reload()
    }, [open, reload])

    const onLogout = async () => {
        if (loggingOut) return
        setLoggingOut(true)
        try {
            await authService.logout()
        } finally {
            onLogoutCurrent()
        }
    }

    const onRevoke = async (session: AuthSession) => {
        if (busyId != null) return
        setBusyId(session.id)
        try {
            if (session.is_current) {
                await authService.logout()
                onLogoutCurrent()
                return
            }
            await authService.revokeSession(session.id)
            await reload()
        } catch {
            /* keep list */
        } finally {
            setBusyId(null)
        }
    }

    const onRevokeAll = async () => {
        if (busyId != null) return
        setBusyId('all')
        try {
            await authService.revokeAllSessions()
            onLogoutCurrent()
        } catch {
            setBusyId(null)
        }
    }

    const panel = (
        <section
            className={[
                'settings-sessions',
                sheet ? 'settings-sessions--sheet' : 'settings-sessions--rail',
                open ? 'is-open' : '',
            ].filter(Boolean).join(' ')}
            aria-label="Активные сессии"
        >
            <button
                type="button"
                className="settings-sessions__head settings-sessions__head--toggle"
                aria-expanded={open}
                onClick={() => setOpen(v => !v)}
            >
                <span className="settings-sessions__head-text">
                    <span className="settings-sessions__title">Активные сессии</span>
                    {!sheet ? (
                        <span className="settings-sessions__sub">
                            Устройства, где выполнен вход.
                        </span>
                    ) : null}
                </span>
                <FontAwesomeIcon
                    icon={faChevronRight}
                    className="settings-sessions__chev"
                    aria-hidden
                />
            </button>

            <div
                className="settings-sessions__collapse"
                aria-hidden={!open}
                inert={!open ? true : undefined}
            >
                <div className="settings-sessions__collapse-inner">
                    <div className="settings-sessions__body">
                        {loading && items.length === 0 ? (
                            <p className="settings-sessions__empty">Загрузка…</p>
                        ) : items.length === 0 ? (
                            <p className="settings-sessions__empty">Нет активных сессий</p>
                        ) : (
                            <ul className="settings-sessions__list">
                                {items.map((session) => (
                                    <li
                                        key={session.id}
                                        className={
                                            session.is_current
                                                ? 'settings-session is-current'
                                                : 'settings-session'
                                        }
                                    >
                                        <div className="settings-session__main">
                                            <p className="settings-session__device">
                                                {session.device_label || 'Неизвестное устройство'}
                                                {session.is_current ? (
                                                    <span className="settings-session__badge">Эта сессия</span>
                                                ) : null}
                                            </p>
                                            <p className="settings-session__meta">
                                                {session.geo_label || 'Локация неизвестна'}
                                                <span aria-hidden>·</span>
                                                вход {formatSessionWhen(session.created_at)}
                                            </p>
                                            {session.ip_masked ? (
                                                <p className="settings-session__ip">IP {session.ip_masked}</p>
                                            ) : null}
                                        </div>
                                        <button
                                            type="button"
                                            className={
                                                session.is_current
                                                    ? 'settings-session__action is-current'
                                                    : 'settings-session__action'
                                            }
                                            disabled={busyId != null}
                                            onClick={() => void onRevoke(session)}
                                        >
                                            {session.is_current ? 'Выйти' : 'Завершить'}
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        )}

                        <footer className="settings-sessions__foot">
                            <p className="settings-sessions__foot-note">
                                Выход с этого устройства завершит только текущую сессию.
                            </p>
                            <button
                                type="button"
                                className="settings-sessions__logout-all"
                                disabled={busyId != null || items.length === 0}
                                onClick={() => void onRevokeAll()}
                            >
                                Выйти везде
                            </button>
                        </footer>
                    </div>
                </div>
            </div>
        </section>
    )

    return (
        <div className="settings-sessions-wrap">
            {sheet ? panel : <Card className="dashboard-assets-card settings-sessions-card">{panel}</Card>}

            <div
                className={['settings-logout-collapse', open ? 'is-hidden' : ''].filter(Boolean).join(' ')}
                aria-hidden={open}
                inert={open ? true : undefined}
            >
                <div className="settings-logout-collapse__inner">
                    <div className="settings-logout">
                        {sheet ? (
                            <button
                                type="button"
                                className="settings-logout__sheet"
                                disabled={loggingOut}
                                onClick={() => void onLogout()}
                            >
                                Выйти
                            </button>
                        ) : (
                            <Button
                                type="button"
                                variant="ghost"
                                disabled={loggingOut}
                                onClick={() => void onLogout()}
                            >
                                Выйти
                            </Button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
