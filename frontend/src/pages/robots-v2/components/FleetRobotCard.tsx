import React from 'react'
import { useNavigate } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
    faChartLine,
    faClone,
    faEllipsisVertical,
    faList,
    faPause,
    faPencil,
    faPlay,
    faStop,
    faTrashCan,
} from '@fortawesome/free-solid-svg-icons'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { MobileDockDropdown } from '@/components/ui/MobileDockDropdown'
import { fmtDate, fmtDateTimeShort, sessionStateLabel } from '@/pages/robots-v2/formatters'
import type { RobotV2 } from '@/types/robotV2'

function isSessionRunning(state: string | null | undefined): boolean {
    return String(state || '').toUpperCase() === 'RUNNING'
}

function fleetStatusBadge(
    robot: RobotV2,
    sessionState: string | null | undefined,
): { label: string; variant: 'up' | 'neutral' | 'down' | 'warn' } {
    const statusName = robot.statusName || robot.status_name
    if (robot.type === 1) {
        if (robot.status === 1) return { label: statusName || 'Включён', variant: 'up' }
        if (robot.status === 2) return { label: statusName || 'Выключен', variant: 'neutral' }
        return { label: statusName || 'Удалён', variant: 'down' }
    }
    if (isSessionRunning(sessionState)) return { label: sessionStateLabel(sessionState), variant: 'up' }
    if (robot.status === 1) return { label: statusName || 'Включён', variant: 'warn' }
    if (robot.status === 2) return { label: statusName || 'Выключен', variant: 'neutral' }
    return { label: statusName || '—', variant: 'down' }
}

function archetypeOf(robot: RobotV2): string {
    const strategy = (robot.config?.strategy || {}) as Record<string, unknown>
    return String(strategy.archetype || '—')
}

function modeOf(robot: RobotV2): string {
    const core = (robot.config?.core || {}) as Record<string, unknown>
    return String(core.mode || 'paper')
}

function sessionStateOf(robot: RobotV2): string | null {
    return (robot.sessionState ?? robot.session_state ?? null) as string | null
}

function activityLine(robot: RobotV2, isPortfolio: boolean): string {
    const lastStarted = robot.lastStarted || robot.last_started
    const createdAt = robot.createdAt || robot.created_at
    if (lastStarted) {
        const label = isPortfolio ? 'Синхронизация' : 'Запуск'
        return `${label} ${fmtDateTimeShort(lastStarted)}`
    }
    if (createdAt) {
        return `Создан ${fmtDate(createdAt)}`
    }
    return isPortfolio ? 'Синхронизаций ещё не было' : 'Запусков ещё не было'
}

export type FleetRobotCardProps = {
    robot: RobotV2
    busy: boolean
    statusMenuOpen: boolean
    actionsMenuOpen: boolean
    onStatusMenuOpenChange: (open: boolean) => void
    onActionsMenuOpenChange: (open: boolean) => void
    onStart: (robot: RobotV2) => void
    onStop: (robot: RobotV2, mode: 'soft' | 'hard') => void
    onTogglePortfolio: (robot: RobotV2) => void
    onClone: (robot: RobotV2) => void
    onDelete: (robot: RobotV2) => void
}

export function FleetRobotCard({
    robot,
    busy,
    statusMenuOpen,
    actionsMenuOpen,
    onStatusMenuOpenChange,
    onActionsMenuOpenChange,
    onStart,
    onStop,
    onTogglePortfolio,
    onClone,
    onDelete,
}: FleetRobotCardProps) {
    const navigate = useNavigate()
    const isPortfolio = robot.type === 1
    const sessionState = sessionStateOf(robot)
    const badge = fleetStatusBadge(robot, sessionState)
    const arch = archetypeOf(robot)
    const mode = modeOf(robot)
    const metaBits = isPortfolio
        ? []
        : [arch, mode].filter(Boolean)

    const openRobot = () => navigate(
        isPortfolio ? `/robots/edit/${robot.id}` : `/robots/${robot.id}/monitor`,
    )

    return (
        <Card
            className="robots-v2-fleet-card dashboard-account-card--link"
            onClick={openRobot}
        >
            <div className="robots-v2-fleet-card__identity">
                <h3 className="robots-v2-fleet-card__name">
                    <span className="robots-v2-fleet-card__name-text">{robot.name}</span>
                    <span className="robots-v2-fleet-card__id mono">#{robot.id}</span>
                </h3>
                {metaBits.length > 0 ? (
                    <p className="robots-v2-fleet-card__meta mono">{metaBits.join(' · ')}</p>
                ) : null}
                <p className="robots-v2-fleet-card__activity">{activityLine(robot, isPortfolio)}</p>
            </div>

            <div
                className="robots-v2-fleet-card__controls"
                onClick={event => event.stopPropagation()}
                onKeyDown={event => event.stopPropagation()}
            >
                <MobileDockDropdown
                    open={statusMenuOpen}
                    onOpenChange={open => {
                        onStatusMenuOpenChange(open)
                        if (open) onActionsMenuOpenChange(false)
                    }}
                    placement="below"
                    portaled
                    className="robots-v2-status-menu"
                >
                    <MobileDockDropdown.Trigger
                        className={`robots-v2-status-trigger robots-v2-status-trigger--${badge.variant}`}
                        aria-label={`Управление статусом ${robot.name}`}
                        disabled={busy}
                    >
                        <span className="robots-v2-status-trigger__label">{badge.label}</span>
                        <svg
                            viewBox="0 0 20 20"
                            fill="currentColor"
                            className="robots-v2-status-trigger__chevron"
                            aria-hidden="true"
                        >
                            <path
                                d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z"
                                clipRule="evenodd"
                                fillRule="evenodd"
                            />
                        </svg>
                    </MobileDockDropdown.Trigger>
                    <MobileDockDropdown.Panel>
                        {isPortfolio ? (
                            <MobileDockDropdown.Item
                                variant={robot.status === 1 ? 'danger' : 'default'}
                                icon={(
                                    <FontAwesomeIcon
                                        icon={robot.status === 1 ? faStop : faPlay}
                                        className="mobile-dock__dropdown-icon"
                                    />
                                )}
                                disabled={busy}
                                onClick={() => onTogglePortfolio(robot)}
                            >
                                {robot.status === 1 ? 'Остановить' : 'Запустить'}
                            </MobileDockDropdown.Item>
                        ) : isSessionRunning(sessionState) ? (
                            <>
                                <MobileDockDropdown.Item
                                    variant="alert"
                                    icon={<FontAwesomeIcon icon={faPause} className="mobile-dock__dropdown-icon" />}
                                    disabled={busy}
                                    onClick={() => onStop(robot, 'soft')}
                                >
                                    Пауза
                                </MobileDockDropdown.Item>
                                <MobileDockDropdown.Item
                                    variant="danger"
                                    icon={<FontAwesomeIcon icon={faStop} className="mobile-dock__dropdown-icon" />}
                                    disabled={busy}
                                    onClick={() => onStop(robot, 'hard')}
                                >
                                    Остановить
                                </MobileDockDropdown.Item>
                            </>
                        ) : (
                            <MobileDockDropdown.Item
                                icon={<FontAwesomeIcon icon={faPlay} className="mobile-dock__dropdown-icon" />}
                                disabled={busy}
                                onClick={() => onStart(robot)}
                            >
                                Запустить
                            </MobileDockDropdown.Item>
                        )}
                    </MobileDockDropdown.Panel>
                </MobileDockDropdown>

                <MobileDockDropdown
                    open={actionsMenuOpen}
                    onOpenChange={open => {
                        onActionsMenuOpenChange(open)
                        if (open) onStatusMenuOpenChange(false)
                    }}
                    placement="below"
                    portaled
                    className="robots-v2-more-menu"
                >
                    <MobileDockDropdown.Trigger
                        asChild
                        aria-label={`Дополнительные действия ${robot.name}`}
                    >
                        <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="robots-v2-more-trigger"
                            disabled={busy}
                        >
                            <FontAwesomeIcon icon={faEllipsisVertical} />
                        </Button>
                    </MobileDockDropdown.Trigger>
                    <MobileDockDropdown.Panel>
                        {!isPortfolio && (
                            <>
                                <MobileDockDropdown.Item
                                    icon={<FontAwesomeIcon icon={faChartLine} className="mobile-dock__dropdown-icon" />}
                                    onClick={() => navigate(`/robots/${robot.id}/backtest`)}
                                >
                                    Бэктест
                                </MobileDockDropdown.Item>
                                <MobileDockDropdown.Item
                                    icon={<FontAwesomeIcon icon={faList} className="mobile-dock__dropdown-icon" />}
                                    onClick={() => navigate(`/robots/${robot.id}/logs`)}
                                >
                                    Логи
                                </MobileDockDropdown.Item>
                                <MobileDockDropdown.Divider />
                                <MobileDockDropdown.Item
                                    icon={<FontAwesomeIcon icon={faClone} className="mobile-dock__dropdown-icon" />}
                                    disabled={busy}
                                    onClick={() => onClone(robot)}
                                >
                                    Клонировать
                                </MobileDockDropdown.Item>
                            </>
                        )}
                        <MobileDockDropdown.Item
                            icon={<FontAwesomeIcon icon={faPencil} className="mobile-dock__dropdown-icon" />}
                            onClick={() => navigate(`/robots/edit/${robot.id}`)}
                        >
                            Правка
                        </MobileDockDropdown.Item>
                        <MobileDockDropdown.Divider />
                        <MobileDockDropdown.Item
                            variant="danger"
                            icon={<FontAwesomeIcon icon={faTrashCan} className="mobile-dock__dropdown-icon" />}
                            disabled={busy}
                            onClick={() => onDelete(robot)}
                        >
                            Удалить
                        </MobileDockDropdown.Item>
                    </MobileDockDropdown.Panel>
                </MobileDockDropdown>
            </div>
        </Card>
    )
}
