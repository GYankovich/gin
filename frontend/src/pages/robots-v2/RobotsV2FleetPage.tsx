import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPlus, faClipboardList, faRobot } from '@fortawesome/free-solid-svg-icons'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { PageHero } from '@/components/ui/PageHero'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { useToast } from '@/components/ui/Toast'
import { FleetRobotCard } from '@/pages/robots-v2/components/FleetRobotCard'
import { RobotConfirmModal } from '@/pages/robots-v2/components/RobotConfirmModal'
import { fmtErr } from '@/pages/robots-v2/formatters'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2 } from '@/types/robotV2'

type ConfirmAction =
    | { kind: 'delete'; robot: RobotV2 }
    | { kind: 'hardStop'; robot: RobotV2 }
    | null

function modeOf(robot: RobotV2): string {
    const core = (robot.config?.core || {}) as Record<string, unknown>
    return String(core.mode || 'paper')
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
    const [confirm, setConfirm] = useState<ConfirmAction>(null)

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

    const runStop = async (robot: RobotV2, stopMode: 'soft' | 'hard') => {
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

    const onStop = (robot: RobotV2, stopMode: 'soft' | 'hard' = 'soft') => {
        if (stopMode === 'hard') {
            setConfirm({ kind: 'hardStop', robot })
            return
        }
        void runStop(robot, 'soft')
    }

    const onClone = async (robot: RobotV2) => {
        setBusyId(robot.id)
        try {
            const cloned = await robotV2Service.clone(robot.id)
            toast.show(`Создана копия #${cloned.id}`, 'success')
            await load()
            navigate(`/robots/edit/${cloned.id}`)
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

    const runDelete = async (robot: RobotV2) => {
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

    const onDelete = (robot: RobotV2) => {
        setConfirm({ kind: 'delete', robot })
    }

    const onConfirmAction = async () => {
        if (!confirm) return
        const action = confirm
        if (action.kind === 'delete') {
            await runDelete(action.robot)
        } else {
            await runStop(action.robot, 'hard')
        }
        setConfirm(null)
    }

    const renderRobotCard = (robot: RobotV2) => (
        <FleetRobotCard
            key={robot.id}
            robot={robot}
            busy={busyId === robot.id}
            statusMenuOpen={statusMenuId === robot.id}
            actionsMenuOpen={actionsMenuId === robot.id}
            onStatusMenuOpenChange={open => setStatusMenuId(open ? robot.id : null)}
            onActionsMenuOpenChange={open => setActionsMenuId(open ? robot.id : null)}
            onStart={r => void onStart(r)}
            onStop={onStop}
            onTogglePortfolio={r => void onTogglePortfolio(r)}
            onClone={r => void onClone(r)}
            onDelete={onDelete}
        />
    )

    const heroActions = (
        <>
            <Button
                type="button"
                variant="ghost"
                size="sm"
                className="dashboard-hero__cfg"
                onClick={() => navigate('/robots/new?kind=portfolio')}
                aria-label="Опросник"
            >
                <FontAwesomeIcon icon={faPlus} />
                <span className="dashboard-hero__cfg-text">Опросник</span>
            </Button>
            <Button
                type="button"
                variant="ghost"
                size="sm"
                className="dashboard-hero__cfg"
                onClick={() => navigate('/robots/new?kind=trading')}
                aria-label="Создать робота"
            >
                <FontAwesomeIcon icon={faPlus} />
                <span className="dashboard-hero__cfg-text">Создать робота</span>
            </Button>
        </>
    )

    const hardStopMessage =
        confirm?.kind === 'hardStop'
            ? modeOf(confirm.robot) === 'live'
                ? `Жёсткая остановка «${confirm.robot.name}» закроет все позиции. Продолжить?`
                : `Жёсткая остановка «${confirm.robot.name}»?`
            : ''

    if (loading && robots.length === 0 && !error) {
        return (
            <div className="page" data-page="robots" data-robots-view="fleet">
                <PageHero
                    className="dashboard-hero--node"
                    eyebrow="ROBOT NODE"
                    title="РОБОТЫ"
                    actions={heroActions}
                />
                <FleetSkeleton />
            </div>
        )
    }

    return (
        <div className="page" data-page="robots" data-robots-view="fleet">
            <PageHero
                className="dashboard-hero--node"
                eyebrow="ROBOT NODE"
                title="РОБОТЫ"
                actions={heroActions}
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
                            className="robots-v2-fleet-collapse"
                            title={(
                                <span className="dashboard-collapse__label">
                                    <FontAwesomeIcon icon={faClipboardList} className="dashboard-icon" />
                                    Опросники портфеля
                                </span>
                            )}
                            badge={<span className="robots-v2-fleet-collapse__count">{portfolioRobots.length}</span>}
                            headerEnd={(
                                <button
                                    type="button"
                                    className="settings-tokens__add"
                                    onClick={() => navigate('/robots/new?kind=portfolio')}
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
                                <p className="dashboard-empty">Нет опросников портфеля</p>
                            )}
                        </CollapsibleSection>

                        <CollapsibleSection
                            className="robots-v2-fleet-collapse"
                            title={(
                                <span className="dashboard-collapse__label">
                                    <FontAwesomeIcon icon={faRobot} className="dashboard-icon" />
                                    Торговые роботы
                                </span>
                            )}
                            badge={<span className="robots-v2-fleet-collapse__count">{tradingRobots.length}</span>}
                            headerEnd={(
                                <button
                                    type="button"
                                    className="settings-tokens__add"
                                    onClick={() => navigate('/robots/new?kind=trading')}
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
                                <p className="dashboard-empty">Нет торговых роботов</p>
                            )}
                        </CollapsibleSection>
                    </div>
                )}
            </div>

            <RobotConfirmModal
                open={confirm?.kind === 'delete'}
                onClose={() => setConfirm(null)}
                onConfirm={() => void onConfirmAction()}
                title="Удалить робота?"
                message={
                    confirm?.kind === 'delete'
                        ? `Удалить робота «${confirm.robot.name}»? Это действие нельзя отменить.`
                        : ''
                }
                confirmLabel="Удалить"
                loading={busyId != null && confirm?.kind === 'delete'}
            />
            <RobotConfirmModal
                open={confirm?.kind === 'hardStop'}
                onClose={() => setConfirm(null)}
                onConfirm={() => void onConfirmAction()}
                title="Жёсткая остановка"
                message={hardStopMessage}
                confirmLabel="Остановить"
                loading={busyId != null && confirm?.kind === 'hardStop'}
            />
        </div>
    )
}
