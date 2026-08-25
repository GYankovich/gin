import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
    faClone,
    faEllipsisVertical,
    faPause,
    faPencil,
    faPlay,
    faPlus,
    faStop,
    faTrashCan,
} from '@fortawesome/free-solid-svg-icons'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { MobileDockDropdown } from '@/components/ui/MobileDockDropdown'
import { PageHero } from '@/components/ui/PageHero'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { useToast } from '@/components/ui/Toast'
import { robotV2Service } from '@/services/robotV2Service'
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
        if (robot.status === 1) return { label: statusName || 'Включен', variant: 'up' }
        if (robot.status === 2) return { label: statusName || 'Выключен', variant: 'neutral' }
        return { label: statusName || 'Удален', variant: 'down' }
    }
    if (isSessionRunning(sessionState)) return { label: 'В работе', variant: 'up' }
    if (robot.status === 1) return { label: statusName || 'Включен', variant: 'warn' }
    if (robot.status === 2) return { label: statusName || 'Выключен', variant: 'neutral' }
    return { label: statusName || '—', variant: 'down' }
}

function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    return err?.message || 'Ошибка'
}

function archetypeOf(robot: RobotV2): string {
    const strategy = (robot.config?.strategy || {}) as Record<string, unknown>
    return String(strategy.archetype || '—')
}

function modeOf(robot: RobotV2): string {
    const core = (robot.config?.core || {}) as Record<string, unknown>
    return String(core.mode || 'paper')
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

function formatDate(iso: string | null | undefined): string {
    if (!iso) return '—'
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return iso
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    })
}

function sessionStateOf(robot: RobotV2): string | null {
    return (robot.sessionState ?? robot.session_state ?? null) as string | null
}

function FleetSkeleton() {
    return (
        <div className="dashboard-layout" aria-busy="true" aria-label="Загрузка флота">
            {[0, 1].map(group => (
                <Card key={group} className="dashboard-account-card dashboard-skeleton-card">
                    <Skeleton width="32%" height="18px" borderRadius="4px" />
                    <div style={{ marginTop: 'var(--space-3)' }}>
                        <Skeleton width="100%" height="88px" borderRadius="8px" />
                    </div>
                </Card>
            ))}
        </div>
    )
}

export default function RobotsV2FleetPage() {
    const navigate = useNavigate()
    const toast = useToast()
    const [robots, setRobots] = useState<RobotV2[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [busyId, setBusyId] = useState<number | null>(null)
    const [statusMenuId, setStatusMenuId] = useState<number | null>(null)
    const [actionsMenuId, setActionsMenuId] = useState<number | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            const data = await robotV2Service.list()
            setRobots(data.items)
        } catch (e) {
            setError(fmtErr(e))
            setRobots([])
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void load()
    }, [load])

    const portfolioRobots = useMemo(() => robots.filter(robot => robot.type === 1), [robots])
    const tradingRobots = useMemo(() => robots.filter(robot => robot.type === 2), [robots])

    const onStart = async (robot: RobotV2) => {
        setBusyId(robot.id)
        try {
            if (modeOf(robot) === 'live') {
                await robotV2Service.start(robot.id, {})
            } else {
                const risk = (robot.config?.risk || {}) as Record<string, unknown>
                const capital = Number(risk.capital || 100_000)
                await robotV2Service.start(robot.id, { virtualCapital: capital })
            }
            toast.show(`Робот #${robot.id} запущен`, 'success')
            await load()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    const onStop = async (robot: RobotV2, stopMode: 'soft' | 'hard' = 'soft') => {
        if (stopMode === 'hard') {
            const mode = modeOf(robot)
            const msg =
                mode === 'live'
                    ? `Жёсткая остановка «${robot.name}» закроет все позиции. Продолжить?`
                    : `Жёсткая остановка «${robot.name}»?`
            if (!window.confirm(msg)) return
        }
        setBusyId(robot.id)
        try {
            await robotV2Service.stop(robot.id, stopMode)
            toast.show(
                stopMode === 'hard' ? `Робот #${robot.id}: жёсткая остановка` : `Робот #${robot.id} остановлен`,
                'info',
            )
            await load()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    const onClone = async (robot: RobotV2) => {
        setBusyId(robot.id)
        try {
            const cloned = await robotV2Service.clone(robot.id)
            toast.show(`Создана копия #${cloned.id}`, 'success')
            await load()
            navigate(`/robots-v2/edit/${cloned.id}`)
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    const onTogglePortfolio = async (robot: RobotV2) => {
        const nextStatus = robot.status === 1 ? 2 : 1
        setBusyId(robot.id)
        try {
            await robotV2Service.changeStatus(robot.id, nextStatus)
            toast.show(nextStatus === 1 ? 'Опросник включён' : 'Опросник выключен', 'success')
            await load()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    const onDelete = async (robot: RobotV2) => {
        if (!window.confirm(`Удалить робота «${robot.name}»?`)) return
        setBusyId(robot.id)
        try {
            await robotV2Service.delete(robot.id)
            toast.show('Удалён', 'success')
            await load()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    const renderRobotCard = (robot: RobotV2) => {
        const badge = fleetStatusBadge(robot, sessionStateOf(robot))
        const mode = modeOf(robot)
        const arch = archetypeOf(robot)
        const lastStarted = robot.lastStarted || robot.last_started
        const createdAt = robot.createdAt || robot.created_at
        const isPortfolio = robot.type === 1
        const openRobot = () => navigate(
            isPortfolio ? `/robots-v2/edit/${robot.id}` : `/robots-v2/${robot.id}/monitor`,
        )

        return (
            <Card
                key={robot.id}
                className="dashboard-account-card dashboard-account-card--link robots-v2-fleet-card"
                onClick={openRobot}
            >
                <div className="dashboard-account-card__head">
                    <h3 className="dashboard-account-card__title">
                        <span className="dashboard-account-card__name">
                            <span className="dashboard-account-card__name-text">{robot.name}</span>
                        </span>
                        <span className="dashboard-account-card__meta-primary mono">
                            #{robot.id}{isPortfolio ? '' : ` · ${arch} · ${mode}`}
                        </span>
                    </h3>
                    <MobileDockDropdown
                        open={statusMenuId === robot.id}
                        onOpenChange={open => {
                            setStatusMenuId(open ? robot.id : null)
                            if (open) setActionsMenuId(null)
                        }}
                        placement="below"
                        portaled
                        className="robots-v2-status-menu"
                    >
                        <MobileDockDropdown.Trigger
                            className={`robots-v2-status-trigger robots-v2-status-trigger--${badge.variant}`}
                            aria-label={`Управление статусом ${robot.name}`}
                            disabled={busyId === robot.id}
                            onClick={event => event.stopPropagation()}
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
                            {robot.type === 1 ? (
                                <MobileDockDropdown.Item
                                    variant={robot.status === 1 ? 'danger' : 'default'}
                                    icon={(
                                        <FontAwesomeIcon
                                            icon={robot.status === 1 ? faStop : faPlay}
                                            className="mobile-dock__dropdown-icon"
                                        />
                                    )}
                                    disabled={busyId === robot.id}
                                    onClick={() => void onTogglePortfolio(robot)}
                                >
                                    {robot.status === 1 ? 'Остановить' : 'Запустить'}
                                </MobileDockDropdown.Item>
                            ) : isSessionRunning(sessionStateOf(robot)) ? (
                                <>
                                    <MobileDockDropdown.Item
                                        variant="alert"
                                        icon={<FontAwesomeIcon icon={faPause} className="mobile-dock__dropdown-icon" />}
                                        disabled={busyId === robot.id}
                                        onClick={() => void onStop(robot, 'soft')}
                                    >
                                        Пауза
                                    </MobileDockDropdown.Item>
                                    <MobileDockDropdown.Item
                                        variant="danger"
                                        icon={<FontAwesomeIcon icon={faStop} className="mobile-dock__dropdown-icon" />}
                                        disabled={busyId === robot.id}
                                        onClick={() => void onStop(robot, 'hard')}
                                    >
                                        Остановить
                                    </MobileDockDropdown.Item>
                                </>
                            ) : (
                                <MobileDockDropdown.Item
                                    icon={<FontAwesomeIcon icon={faPlay} className="mobile-dock__dropdown-icon" />}
                                    disabled={busyId === robot.id}
                                    onClick={() => void onStart(robot)}
                                >
                                    Запустить
                                </MobileDockDropdown.Item>
                            )}
                        </MobileDockDropdown.Panel>
                    </MobileDockDropdown>
                    <div className="dashboard-account-card__meta-sync">
                        <div className="dashboard-account-card__meta mono">
                            <span className="dashboard-account-card__meta-opened">
                                <span>Создан {formatDate(createdAt)}</span>
                                <span className="robots-v2-fleet-card__activity">
                                    {lastStarted
                                        ? `${isPortfolio ? 'Синхронизация' : 'Последний запуск'} ${formatLastStarted(lastStarted)}`
                                        : isPortfolio
                                          ? 'Синхронизаций ещё не было'
                                          : 'Запусков ещё не было'}
                                </span>
                            </span>
                        </div>
                    </div>
                </div>
                <div className="robots-v2-fleet-card__actions">
                    {robot.type === 2 ? (
                        <>
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="robots-v2-fleet-card__action"
                                onClick={event => {
                                event.stopPropagation()
                                navigate(`/robots-v2/${robot.id}/backtest`)
                            }}>
                                Бэктест
                            </Button>
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="robots-v2-fleet-card__action"
                                onClick={event => {
                                event.stopPropagation()
                                navigate(`/robots-v2/${robot.id}/logs`)
                            }}>
                                Логи
                            </Button>
                        </>
                    ) : null}
                    <MobileDockDropdown
                        open={actionsMenuId === robot.id}
                        onOpenChange={open => {
                            setActionsMenuId(open ? robot.id : null)
                            if (open) setStatusMenuId(null)
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
                                disabled={busyId === robot.id}
                                onClick={event => event.stopPropagation()}
                            >
                                <FontAwesomeIcon icon={faEllipsisVertical} />
                            </Button>
                        </MobileDockDropdown.Trigger>
                        <MobileDockDropdown.Panel>
                            {robot.type === 2 && (
                                <MobileDockDropdown.Item
                                    icon={<FontAwesomeIcon icon={faClone} className="mobile-dock__dropdown-icon" />}
                                    disabled={busyId === robot.id}
                                    onClick={() => void onClone(robot)}
                                >
                                    Клонировать
                                </MobileDockDropdown.Item>
                            )}
                            <MobileDockDropdown.Item
                                icon={<FontAwesomeIcon icon={faPencil} className="mobile-dock__dropdown-icon" />}
                                onClick={() => navigate(`/robots-v2/edit/${robot.id}`)}
                            >
                                Правка
                            </MobileDockDropdown.Item>
                            <MobileDockDropdown.Divider />
                            <MobileDockDropdown.Item
                                variant="danger"
                                icon={<FontAwesomeIcon icon={faTrashCan} className="mobile-dock__dropdown-icon" />}
                                disabled={busyId === robot.id}
                                onClick={() => void onDelete(robot)}
                            >
                                Удалить
                            </MobileDockDropdown.Item>
                        </MobileDockDropdown.Panel>
                    </MobileDockDropdown>
                </div>
            </Card>
        )
    }

    if (loading && robots.length === 0 && !error) {
        return (
            <div className="page" data-page="robots-v2">
                <PageHero
                    title="РОБОТЫ V2"
                    className="robots-v2-fleet-hero"
                />
                <FleetSkeleton />
            </div>
        )
    }

    return (
        <div className="page" data-page="robots-v2">
            <PageHero
                title="РОБОТЫ V2"
                className="robots-v2-fleet-hero"
            />

            <div className="dashboard-layout">
                {!loading && error && (
                    <Card className="dashboard-totals-card dashboard-error-card">
                        <div className="dashboard-error-card__robot" aria-hidden>
                            <RobotIllustration size={96} mode="inactive" interactive={false} />
                        </div>
                        <p className="dashboard-empty">{error}</p>
                        <div className="dashboard-error-card__actions">
                            <Button type="button" onClick={() => void load()}>Повторить</Button>
                        </div>
                    </Card>
                )}

                {!loading && !error && (
                    <div className="robots-v2-fleet-groups">
                        <CollapsibleSection
                            className="portfolio-collapse settings-tokens-collapse robots-v2-fleet-collapse"
                            title="Опросники портфеля"
                            badge={<span className="portfolio-collapse__count">{portfolioRobots.length}</span>}
                            headerEnd={(
                                <button
                                    type="button"
                                    className="settings-tokens__add"
                                    onClick={() => navigate('/robots-v2/new?kind=portfolio')}
                                    aria-label="Создать опросник портфеля"
                                >
                                    <FontAwesomeIcon icon={faPlus} className="settings-tokens__add-icon" />
                                </button>
                            )}
                            defaultOpen
                        >
                            {portfolioRobots.length > 0 ? (
                                <div className="dashboard-account-stack robots-v2-fleet-stack">
                                    {portfolioRobots.map(renderRobotCard)}
                                </div>
                            ) : (
                                <div className="robots-v2-group-empty">
                                    <span>Нет опросников портфеля</span>
                                </div>
                            )}
                        </CollapsibleSection>

                        <CollapsibleSection
                            className="portfolio-collapse settings-tokens-collapse robots-v2-fleet-collapse"
                            title="Торговые роботы"
                            badge={<span className="portfolio-collapse__count">{tradingRobots.length}</span>}
                            headerEnd={(
                                <button
                                    type="button"
                                    className="settings-tokens__add"
                                    onClick={() => navigate('/robots-v2/new?kind=trading')}
                                    aria-label="Создать торгового робота"
                                >
                                    <FontAwesomeIcon icon={faPlus} className="settings-tokens__add-icon" />
                                </button>
                            )}
                            defaultOpen
                        >
                            {tradingRobots.length > 0 ? (
                                <div className="dashboard-account-stack robots-v2-fleet-stack">
                                    {tradingRobots.map(renderRobotCard)}
                                </div>
                            ) : (
                                <div className="robots-v2-group-empty">
                                    <span>Нет торговых роботов</span>
                                </div>
                            )}
                        </CollapsibleSection>
                    </div>
                )}
            </div>
        </div>
    )
}
