import React, { useEffect } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import type { Robot } from '@/types/robot'

type Props = {
    robots: Robot[]
    loading: boolean
    error: string | null
    selectedRobotId: number | null
    isNewRobot: boolean
    onRetry: () => void
    onSelect: (robotId: number) => void
    onCreate: () => void
    /** Drawer open state when forceDrawer. */
    mobileOpen?: boolean
    onMobileClose?: () => void
    /** When true, sidebar only appears as drawer (≤1279). */
    forceDrawer?: boolean
}

function statusBadgeVariant(robot: Robot): 'up' | 'neutral' | 'down' | 'warn' {
    if (robot.status === 1) return 'up'
    return 'down'
}

function formatLastStarted(iso: string): string {
    const t = new Date(iso).getTime()
    if (Number.isNaN(t)) return iso
    return new Date(t).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    })
}

export function FleetPanel({
    robots,
    loading,
    error,
    selectedRobotId,
    isNewRobot,
    onRetry,
    onSelect,
    onCreate,
    mobileOpen = false,
    onMobileClose,
    forceDrawer = false,
}: Props) {
    useEffect(() => {
        if (!mobileOpen) return
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onMobileClose?.()
        }
        window.addEventListener('keydown', onKey)
        const prev = document.body.style.overflow
        document.body.style.overflow = 'hidden'
        return () => {
            window.removeEventListener('keydown', onKey)
            document.body.style.overflow = prev
        }
    }, [mobileOpen, onMobileClose])

    const selectRobot = (robotId: number) => {
        onSelect(robotId)
        onMobileClose?.()
    }

    const createRobot = () => {
        onCreate()
        onMobileClose?.()
    }

    return (
        <>
            {mobileOpen && (
                <button
                    type="button"
                    className="robots-fleet-backdrop"
                    aria-label="Закрыть список роботов"
                    onClick={onMobileClose}
                />
            )}
            <aside
                id="robots-fleet-sidebar"
                className={[
                    'robots-workspace__sidebar',
                    forceDrawer ? 'robots-workspace__sidebar--drawer' : '',
                    mobileOpen ? 'robots-workspace__sidebar--open' : '',
                ].filter(Boolean).join(' ')}
            >
                <Card className="robots-list-card portfolio-panel">
                    <div className="robots-list-card__head">
                        <h3 className="dashboard-panel-title">Роботы</h3>
                        <div className="robots-list-card__head-actions">
                            {robots.length > 0 && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="robot-create-btn"
                                    onClick={createRobot}
                                >
                                    + Создать
                                </Button>
                            )}
                            {forceDrawer && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="robots-fleet-close"
                                    onClick={onMobileClose}
                                    aria-label="Закрыть"
                                >
                                    ✕
                                </Button>
                            )}
                        </div>
                    </div>

                    {error && (
                        <div className="robots-fleet-error" role="alert">
                            <p className="dashboard-empty">{error}</p>
                            <Button variant="ghost" size="sm" onClick={onRetry}>
                                Повторить
                            </Button>
                        </div>
                    )}

                    {loading && !error ? (
                        <p className="dashboard-empty">Загрузка…</p>
                    ) : robots.length === 0 && !error ? (
                        <div className="robots-empty-fleet">
                            <p className="dashboard-empty">Нет роботов</p>
                            <Button variant="ghost" size="sm" className="robot-create-btn" onClick={createRobot}>
                                + Создать
                            </Button>
                        </div>
                    ) : (
                        <div className="robots-list-cards">
                            {robots.map(r => {
                                const isActive = r.status === 1
                                const selected = !isNewRobot && selectedRobotId === r.id
                                return (
                                    <div
                                        key={r.id}
                                        role="button"
                                        tabIndex={0}
                                        className={`robots-list-item${selected ? ' robots-list-item--selected' : ''}${isActive ? ' robots-list-item--active' : ' robots-list-item--error'}`}
                                        onClick={() => selectRobot(r.id)}
                                        onKeyDown={e => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                                e.preventDefault()
                                                selectRobot(r.id)
                                            }
                                        }}
                                    >
                                        <div className={`robots-list-item__head robots-list-item__head--${isActive ? 'active' : 'error'}`}>
                                            <strong>{r.name}</strong>
                                            <Badge variant={statusBadgeVariant(r)}>
                                                {r.statusName || (isActive ? 'Активен' : 'Стоп')}
                                            </Badge>
                                        </div>
                                        <div className="robots-list-item__meta mono">
                                            {r.typeName}
                                            {r.token?.typeName ? ` · ${r.token.typeName}` : ''}
                                        </div>
                                        {r.last_started ? (
                                            <div className="robots-list-item__session mono">
                                                {formatLastStarted(r.last_started)}
                                            </div>
                                        ) : null}
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </Card>
            </aside>
        </>
    )
}
