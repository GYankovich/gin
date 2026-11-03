import React, { useEffect, useState } from 'react'
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
import {
    fmtMoney,
    fmtSyncAge,
    sessionStateLabel,
} from '@/pages/robots-v2/formatters'
import { ARCHETYPE_CARDS } from '@/pages/robots-v2/wizardDraft'
import type { RobotV2, RobotV2Status } from '@/types/robotV2'

function isSessionActive(state: string | null | undefined): boolean {
    const s = String(state || '').toUpperCase()
    return s === 'RUNNING' || s === 'BOOTSTRAP' || s === 'STOPPING'
}

export function fleetStatusBadge(
    robot: RobotV2,
    sessionState: string | null | undefined,
): { label: string; tone: 'ok' | 'warn' | 'bad' | 'idle' } {
    const statusName = robot.statusName || robot.status_name
    if (robot.type === 1) {
        if (robot.status === 1) return { label: 'Включён', tone: 'ok' }
        if (robot.status === 2) return { label: 'Выключен', tone: 'idle' }
        return { label: statusName || 'Удалён', tone: 'bad' }
    }
    const s = String(sessionState || '').toUpperCase()
    if (s === 'ERROR' || s === 'FAILED' || robot.status === 3) {
        return { label: 'Ошибка', tone: 'bad' }
    }
    if (isSessionActive(sessionState)) {
        if (s === 'BOOTSTRAP') return { label: 'Синхронизация', tone: 'ok' }
        if (s === 'STOPPING') return { label: 'Остановка', tone: 'warn' }
        return { label: 'Работает', tone: 'ok' }
    }
    if (s === 'STOPPED' || robot.status === 2) return { label: 'Приостановлен', tone: 'warn' }
    if (robot.status === 1) return { label: statusName || 'Включён', tone: 'warn' }
    return { label: sessionStateLabel(sessionState) || statusName || '—', tone: 'idle' }
}

function strategyOf(robot: RobotV2): Record<string, unknown> {
    return (robot.config?.strategy || {}) as Record<string, unknown>
}

function coreOf(robot: RobotV2): Record<string, unknown> {
    return (robot.config?.core || {}) as Record<string, unknown>
}

function riskOf(robot: RobotV2): Record<string, unknown> {
    return (robot.config?.risk || {}) as Record<string, unknown>
}

function archetypeTitle(robot: RobotV2): string {
    const id = String(strategyOf(robot).archetype || '')
    return ARCHETYPE_CARDS.find(card => card.id === id)?.title || id || 'Стратегия'
}

function modeOf(robot: RobotV2): string {
    return String(coreOf(robot).mode || 'paper')
}

function modeLabel(mode: string): string {
    if (mode === 'live') return 'Боевой'
    if (mode === 'paper') return 'Бумага'
    return mode
}

function isCrypto(robot: RobotV2): boolean {
    const raw = String(coreOf(robot).instrumentType || '')
    return raw === 'perpetual' || raw === 'coin_futures'
}

function sessionStateOf(robot: RobotV2, snapshot?: RobotV2Status | null): string | null {
    return (
        snapshot?.sessionState
        ?? snapshot?.session_state
        ?? robot.sessionState
        ?? robot.session_state
        ?? null
    ) as string | null
}

function syncIso(robot: RobotV2, snapshot: RobotV2Status | null | undefined, isPortfolio: boolean): string | null {
    if (isPortfolio) {
        return (robot.lastStarted || robot.last_started || robot.updatedAt || robot.updated_at || null) as string | null
    }
    return (
        snapshot?.lastCycleAt
        ?? snapshot?.last_cycle_at
        ?? snapshot?.balanceAsOf
        ?? snapshot?.balance_as_of
        ?? snapshot?.positionsUpdatedAt
        ?? snapshot?.positions_updated_at
        ?? robot.lastStarted
        ?? robot.last_started
        ?? robot.updatedAt
        ?? robot.updated_at
        ?? null
    ) as string | null
}

function positionsCount(snapshot: RobotV2Status | null | undefined): number | null {
    const positions = snapshot?.openPositions ?? snapshot?.open_positions
    if (!Array.isArray(positions)) return null
    return positions.length
}

function equitySeries(snapshot: RobotV2Status | null | undefined): number[] {
    const raw = snapshot?.equityCurve ?? snapshot?.equity_curve
    if (!Array.isArray(raw)) return []
    return raw
        .map(point => Number(point?.equity))
        .filter(value => Number.isFinite(value))
}

function formatAmount(value: number, crypto: boolean): string {
    const digits = Math.abs(value) >= 1000 ? 0 : 2
    const formatted = fmtMoney(value, digits)
    return crypto ? formatted : `${formatted} ₽`
}

function syncParts(iso: string | null, now: number): { value: string; sub: string } {
    if (!iso) return { value: '—', sub: '' }
    const t = new Date(iso).getTime()
    if (Number.isNaN(t)) return { value: String(iso), sub: '' }
    const age = fmtSyncAge(iso, now)
    const time = new Date(t).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    const day = new Date(t).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
    const sameDay = new Date(t).toDateString() === new Date(now).toDateString()
    if (age.includes('с назад') || age.includes('мин назад') || age.includes('ч назад')) {
        return { value: age, sub: sameDay ? time : day }
    }
    if (sameDay) return { value: 'Сегодня', sub: time }
    return { value: day, sub: time }
}

export type FleetRobotCardProps = {
    robot: RobotV2
    busy: boolean
    snapshot?: RobotV2Status | null
    accountLabel?: string | null
    actionsMenuOpen: boolean
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
    snapshot = null,
    accountLabel = null,
    actionsMenuOpen,
    onActionsMenuOpenChange,
    onStart,
    onStop,
    onTogglePortfolio,
    onClone,
    onDelete,
}: FleetRobotCardProps) {
    const navigate = useNavigate()
    const [now, setNow] = useState(() => Date.now())
    useEffect(() => {
        const timer = window.setInterval(() => setNow(Date.now()), 1000)
        return () => window.clearInterval(timer)
    }, [])

    const isPortfolio = robot.type === 1
    const sessionState = sessionStateOf(robot, snapshot)
    const badge = fleetStatusBadge(robot, sessionState)
    const mode = modeOf(robot)
    const syncAt = syncIso(robot, snapshot, isPortfolio)
    const sync = syncParts(syncAt, now)
    const equityRaw = snapshot?.equity
    const equity = equityRaw != null && Number.isFinite(Number(equityRaw)) ? Number(equityRaw) : null
    const capitalRaw = Number(riskOf(robot).capital)
    const capital = Number.isFinite(capitalRaw) && capitalRaw > 0 ? capitalRaw : null
    const series = equitySeries(snapshot)
    const curveDelta = series.length >= 2 ? series[series.length - 1] - series[0] : null
    const pnl = curveDelta != null && Number.isFinite(curveDelta)
        ? curveDelta
        : equity != null && capital != null
            ? equity - capital
            : null
    const posCount = positionsCount(snapshot)
    const crypto = isCrypto(robot)
    const errorText = badge.tone === 'bad'
        ? (snapshot?.message || 'Ошибка синхронизации или исполнения')
        : null
    const account = accountLabel || (robot.tokenId ? `Ключ #${robot.tokenId}` : 'Счёт не выбран')

    const openRobot = () => navigate(
        isPortfolio ? `/robots/edit/${robot.id}` : `/robots/${robot.id}/monitor`,
    )

    const stopActions = (event: React.SyntheticEvent) => {
        event.stopPropagation()
    }

    const menu = (
        <MobileDockDropdown
            open={actionsMenuOpen}
            onOpenChange={onActionsMenuOpenChange}
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
                {isPortfolio ? (
                    <MobileDockDropdown.Item
                        icon={(
                            <FontAwesomeIcon
                                icon={robot.status === 1 ? faStop : faPlay}
                                className="mobile-dock__dropdown-icon"
                            />
                        )}
                        disabled={busy}
                        onClick={() => onTogglePortfolio(robot)}
                    >
                        {robot.status === 1 ? 'Выключить' : 'Включить'}
                    </MobileDockDropdown.Item>
                ) : isSessionActive(sessionState) ? (
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
                {!isPortfolio ? (
                    <>
                        <MobileDockDropdown.Divider />
                        <MobileDockDropdown.Item
                            icon={<FontAwesomeIcon icon={faPencil} className="mobile-dock__dropdown-icon" />}
                            onClick={() => navigate(`/robots/edit/${robot.id}`)}
                        >
                            Правка
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
                ) : (
                    <MobileDockDropdown.Divider />
                )}
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
    )

    return (
        <Card
            className={[
                'robots-v2-fleet-card',
                `robots-v2-fleet-card--${badge.tone}`,
                isPortfolio ? 'robots-v2-fleet-card--portfolio' : '',
            ].filter(Boolean).join(' ')}
            onClick={openRobot}
        >
            <div className={`robots-v2-fleet-card__main${isPortfolio ? ' robots-v2-fleet-card__main--portfolio' : ''}`}>
                <div className="robots-v2-fleet-card__identity">
                    <div className="robots-v2-fleet-card__name-line">
                        <span className="robots-v2-fleet-card__name">{robot.name}</span>
                        <span className="robots-v2-fleet-card__id">#{robot.id}</span>
                        <span className={`robots-v2-fleet-card__status robots-v2-fleet-card__status--${badge.tone}`}>
                            {badge.label}
                        </span>
                    </div>
                    {!isPortfolio ? (
                        <div className="robots-v2-fleet-card__tags">
                            <span className="robots-v2-fleet-card__tag">{modeLabel(mode)}</span>
                            <span className="robots-v2-fleet-card__tag robots-v2-fleet-card__tag--mode">
                                {archetypeTitle(robot)}
                            </span>
                        </div>
                    ) : null}
                </div>

                {isPortfolio ? (
                    <>
                        <div className="robots-v2-fleet-card__metric">
                            <div className="robots-v2-fleet-card__metric-label">Синхронизация</div>
                            <div className="robots-v2-fleet-card__metric-value">{sync.value}</div>
                            <div className="robots-v2-fleet-card__metric-sub">Последнее обновление</div>
                        </div>
                        <div className="robots-v2-fleet-card__metric">
                            <div className="robots-v2-fleet-card__metric-label">Брокерский аккаунт</div>
                            <div className="robots-v2-fleet-card__metric-value">{account}</div>
                            <div className="robots-v2-fleet-card__metric-sub">Подключён</div>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="robots-v2-fleet-card__metric">
                            <div className="robots-v2-fleet-card__metric-label">PnL</div>
                            <div
                                className={[
                                    'robots-v2-fleet-card__metric-value',
                                    pnl == null ? '' : pnl >= 0 ? 'is-up' : 'is-down',
                                ].filter(Boolean).join(' ')}
                            >
                                {pnl != null
                                    ? `${pnl > 0 ? '+' : ''}${formatAmount(pnl, crypto)}`
                                    : (equity ?? capital) != null
                                        ? formatAmount((equity ?? capital) as number, crypto)
                                        : '—'}
                            </div>
                            <div className="robots-v2-fleet-card__metric-sub">
                                {pnl != null ? 'По кривой' : equity != null ? 'Счёт' : 'Капитал'}
                            </div>
                        </div>
                        <div className="robots-v2-fleet-card__metric">
                            <div className="robots-v2-fleet-card__metric-label">Позиции</div>
                            <div className="robots-v2-fleet-card__metric-value">
                                {posCount != null ? String(posCount) : '—'}
                            </div>
                            <div className="robots-v2-fleet-card__metric-sub">
                                {posCount === 1 ? 'Открытая' : 'Открытых'}
                            </div>
                        </div>
                        <div className="robots-v2-fleet-card__metric">
                            <div className="robots-v2-fleet-card__metric-label">Последняя синхронизация</div>
                            <div className="robots-v2-fleet-card__metric-value">{sync.value}</div>
                            {sync.sub ? (
                                <div className="robots-v2-fleet-card__metric-sub">{sync.sub}</div>
                            ) : null}
                        </div>
                    </>
                )}

                <div
                    className="robots-v2-fleet-card__actions"
                    onClick={stopActions}
                    onKeyDown={stopActions}
                >
                    {!isPortfolio ? (
                        <>
                            <Button
                                type="button"
                                size="sm"
                                variant="primary"
                                className="robots-v2-fleet-card__action-main"
                                onClick={openRobot}
                            >
                                Монитор
                            </Button>
                            <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                className="robots-v2-fleet-card__action-alt"
                                onClick={() => navigate(`/backtest?robot=${robot.id}`)}
                            >
                                Бэктест
                            </Button>
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="robots-v2-fleet-card__icon-btn"
                                aria-label="График"
                                title="График"
                                onClick={() => navigate(`/robots/${robot.id}/monitor`)}
                            >
                                <FontAwesomeIcon icon={faChartLine} />
                            </Button>
                        </>
                    ) : null}
                    {menu}
                </div>
            </div>

            {errorText ? (
                <div className="robots-v2-fleet-card__alert" onClick={stopActions}>
                    <span>ⓘ {errorText}</span>
                    <button
                        type="button"
                        className="robots-v2-fleet-card__link"
                        onClick={() => navigate(`/robots/${robot.id}/logs`)}
                    >
                        Открыть логи →
                    </button>
                </div>
            ) : null}
        </Card>
    )
}
