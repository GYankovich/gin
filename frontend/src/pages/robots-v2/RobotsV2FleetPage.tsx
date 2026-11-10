import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { DropdownMenu } from '@/components/ui/DropdownMenu'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { useToast } from '@/components/ui/Toast'
import { FleetRobotCard } from '@/pages/robots-v2/components/FleetRobotCard'
import { RobotConfirmModal } from '@/pages/robots-v2/components/RobotConfirmModal'
import { fmtErr } from '@/pages/robots-v2/formatters'
import { robotV2Service, type RobotV2FleetItem, type RobotV2FleetLive } from '@/services/robotV2Service'
import { usePageCacheStore } from '@/stores/pageCacheStore'
import type { RobotV2, RobotV2Status } from '@/types/robotV2'

type ConfirmAction = { kind: 'delete'; robot: RobotV2 } | null

function liveToSnapshot(robotId: number, live: RobotV2FleetLive | null | undefined): RobotV2Status | null {
    if (!live) return null
    const curve = live.equityCurve ?? live.equity_curve ?? null
    const count = live.openPositionsCount ?? live.open_positions_count
    const trades = live.tradesCount ?? live.trades_count
    const wins = live.wins
    const losses = live.losses
    const ownFunds = live.ownFunds ?? live.own_funds
    const priceDelta = live.priceDelta ?? live.price_delta
    const periodDelta = live.periodDelta ?? live.period_delta
    const statsPeriod = live.statsPeriod ?? live.stats_period ?? null
    return {
        robotId,
        status: 1,
        sessionState: live.sessionState ?? live.session_state ?? null,
        equity: live.equity ?? null,
        equityCurve: Array.isArray(curve) ? (curve as RobotV2Status['equityCurve']) : null,
        openPositions: typeof count === 'number' ? Array.from({ length: count }, () => ({})) : null,
        tradesCount: typeof trades === 'number' ? trades : null,
        trades_count: typeof trades === 'number' ? trades : null,
        wins: typeof wins === 'number' ? wins : null,
        losses: typeof losses === 'number' ? losses : null,
        ownFunds: typeof ownFunds === 'number' ? ownFunds : null,
        own_funds: typeof ownFunds === 'number' ? ownFunds : null,
        priceDelta: typeof priceDelta === 'number' ? priceDelta : null,
        price_delta: typeof priceDelta === 'number' ? priceDelta : null,
        periodDelta: typeof periodDelta === 'number' ? periodDelta : null,
        period_delta: typeof periodDelta === 'number' ? periodDelta : null,
        statsPeriod,
        stats_period: statsPeriod,
        lastCycleAt: live.lastCycleAt ?? live.last_cycle_at ?? null,
        message: live.message ?? null,
    }
}

function FleetSkeleton() {
    return (
        <div className="dashboard-layout" aria-busy="true" aria-label="Загрузка флота">
            <Card className="dashboard-account-card dashboard-skeleton-card">
                <Skeleton width="28%" height="14px" borderRadius="4px" />
                <div style={{ marginTop: 'var(--space-3)' }}>
                    <Skeleton width="100%" height="48px" borderRadius="8px" />
                </div>
            </Card>
        </div>
    )
}

export default function RobotsV2FleetPage() {
    const navigate = useNavigate()
    const toast = useToast()
    const cachedFleet = usePageCacheStore(s => s.robotsFleet)
    const setRobotsFleetCache = usePageCacheStore(s => s.setRobotsFleet)
    const [robots, setRobots] = useState<RobotV2FleetItem[]>(
        (cachedFleet?.robots as RobotV2FleetItem[] | undefined) ?? [],
    )
    const [loading, setLoading] = useState(cachedFleet == null)
    const [error, setError] = useState<string | null>(null)
    const [busyId, setBusyId] = useState<number | null>(null)
    const [actionsMenuId, setActionsMenuId] = useState<number | null>(null)
    const [createMenuOpen, setCreateMenuOpen] = useState(false)
    const [confirm, setConfirm] = useState<ConfirmAction>(null)

    const load = useCallback(async () => {
        const hasStale = usePageCacheStore.getState().robotsFleet != null
        if (!hasStale) setLoading(true)
        setError(null)
        try {
            const data = await robotV2Service.list({})
            setRobots(data.items)
            setRobotsFleetCache({
                robots: data.items,
                hasBrokerAccounts: data.hasBrokerAccounts,
            })
            setLoading(false)
        } catch (e) {
            setError(fmtErr(e))
            if (!hasStale) setRobots([])
            setLoading(false)
        }
    }, [setRobotsFleetCache])

    useEffect(() => {
        void load()
    }, [load])

    const tradingRobots = useMemo(() => robots.filter(robot => robot.type === 2), [robots])
    const portfolioRobots = useMemo(() => robots.filter(robot => robot.type === 1), [robots])

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

    const onStop = async (robot: RobotV2) => {
        setBusyId(robot.id)
        try {
            await robotV2Service.stop(robot.id, 'soft')
            toast.show(`Робот #${robot.id} остановлен`, 'info')
            await load()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    const onTogglePortfolio = async (robot: RobotV2) => {
        setBusyId(robot.id)
        try {
            const next = robot.status === 1 ? 2 : 1
            await robotV2Service.changeStatus(robot.id, next)
            toast.show(next === 1 ? 'Опросник включён' : 'Опросник остановлен', 'success')
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
            toast.show('Копия создана', 'success')
            navigate(`/robots/edit/${cloned.id}`)
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
        if (!confirm || confirm.kind !== 'delete') return
        await runDelete(confirm.robot)
        setConfirm(null)
    }

    const renderRobotCard = (robot: RobotV2FleetItem) => (
        <FleetRobotCard
            key={robot.id}
            robot={robot}
            snapshot={liveToSnapshot(robot.id, robot.live)}
            accounts={robot.accounts ?? []}
            brokerLabel={robot.brokerLabel ?? robot.broker_label ?? null}
            busy={busyId === robot.id}
            actionsMenuOpen={actionsMenuId === robot.id}
            onActionsMenuOpenChange={open => setActionsMenuId(open ? robot.id : null)}
            onStart={r => void onStart(r)}
            onStop={r => void onStop(r)}
            onTogglePortfolio={r => void onTogglePortfolio(r)}
            onClone={r => void onClone(r)}
            onDelete={onDelete}
        />
    )

    const createMenuItems = (
        <DropdownMenu.Panel className="robots-fleet-create-menu">
            <DropdownMenu.Item onClick={() => navigate('/robots/new?kind=portfolio')}>
                Опросник портфеля
            </DropdownMenu.Item>
            <DropdownMenu.Divider />
            <DropdownMenu.Item onClick={() => navigate('/robots/new?kind=trading')}>
                Торговый робот
            </DropdownMenu.Item>
        </DropdownMenu.Panel>
    )

    const createFab = (
        <DropdownMenu
            open={createMenuOpen}
            onOpenChange={setCreateMenuOpen}
            placement="above"
            portaled
            className="robots-create-fab"
        >
            <DropdownMenu.Trigger asChild aria-label="Создать робота">
                <Button type="button" variant="ghost" className="robots-create-fab__btn">
                    <svg viewBox="0 0 24 24" aria-hidden>
                        <path
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.7"
                            strokeLinecap="round"
                            d="M12 5v14M5 12h14"
                        />
                    </svg>
                </Button>
            </DropdownMenu.Trigger>
            {createMenuItems}
        </DropdownMenu>
    )

    if (loading && robots.length === 0 && !error) {
        return (
            <div className="page" data-page="robots" data-robots-view="fleet">
                <FleetSkeleton />
            </div>
        )
    }

    return (
        <div className="page" data-page="robots" data-robots-view="fleet" data-create="fab">
            <div className="dashboard-layout robots-v2-fleet">
                <h1 className="dash-sr-only">Роботы</h1>

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
                    <>
                        {tradingRobots.length > 0 ? (
                            <section className="robots-v2-fleet-section" aria-label="Торговые роботы">
                                <div className="robots-v2-fleet-section-label">
                                    Торговые роботы <span>{tradingRobots.length}</span>
                                </div>
                                <div className="robots-v2-fleet-stack">
                                    {tradingRobots.map(renderRobotCard)}
                                </div>
                            </section>
                        ) : null}

                        {portfolioRobots.length > 0 ? (
                            <section className="robots-v2-fleet-section" aria-label="Опросники портфеля">
                                <div className="robots-v2-fleet-section-label">
                                    Опросники портфеля <span>{portfolioRobots.length}</span>
                                </div>
                                <div className="robots-v2-fleet-stack">
                                    {portfolioRobots.map(renderRobotCard)}
                                </div>
                            </section>
                        ) : null}
                    </>
                )}
            </div>

            {createFab}

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
        </div>
    )
}
