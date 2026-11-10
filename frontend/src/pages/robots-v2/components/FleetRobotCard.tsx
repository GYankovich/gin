import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
    faClone,
    faEllipsisVertical,
    faPencil,
    faPlay,
    faStop,
    faTrashCan,
} from '@fortawesome/free-solid-svg-icons'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DropdownMenu } from '@/components/ui/DropdownMenu'
import { MobileDockDropdown } from '@/components/ui/MobileDockDropdown'
import {
    fmtMoney,
    fmtSyncAge,
    sessionStateLabel,
} from '@/pages/robots-v2/formatters'
import { ARCHETYPE_CARDS } from '@/pages/robots-v2/wizardDraft'
import type { RobotV2FleetAccount } from '@/services/robotV2Service'
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

function archetypeTitle(robot: RobotV2): string | null {
    const id = String(strategyOf(robot).archetype || '').trim()
    if (!id) return null
    return ARCHETYPE_CARDS.find(card => card.id === id)?.title || id
}

function formatSyncFact(iso: string | null, now: number): string {
    if (!iso) return '—'
    const t = new Date(iso).getTime()
    if (Number.isNaN(t)) return '—'
    const sameDay = new Date(t).toDateString() === new Date(now).toDateString()
    if (sameDay) {
        return new Date(t).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    }
    return new Date(t).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    })
}

function accountDisplayName(account: RobotV2FleetAccount): string | null {
    const name = String(account.accountName ?? account.account_name ?? '').trim()
    if (name) return name
    const id = String(account.accountId ?? account.account_id ?? '').trim()
    return id || null
}

function formatAccountsLabel(accounts: RobotV2FleetAccount[]): string | null {
    const names = accounts.map(accountDisplayName).filter(Boolean) as string[]
    if (names.length === 0) return null
    if (names.length === 1) return names[0]
    return names[0]
}

function accountsCountLabel(count: number): string {
    const mod10 = count % 10
    const mod100 = count % 100
    if (mod10 === 1 && mod100 !== 11) return `${count} счёт`
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} счёта`
    return `${count} счетов`
}

function AccountsDisclosure({
    accounts,
    className,
    emptyLabel = 'Счёт не выбран',
}: {
    accounts: RobotV2FleetAccount[]
    className?: string
    emptyLabel?: string
}) {
    const [open, setOpen] = useState(false)
    const label = formatAccountsLabel(accounts)

    if (accounts.length <= 1) {
        return <span className={className}>{label || emptyLabel}</span>
    }

    return (
        <span
            className="robots-v2-fleet-accounts-wrap"
            onClick={event => event.stopPropagation()}
            onKeyDown={event => event.stopPropagation()}
        >
            <DropdownMenu
                open={open}
                onOpenChange={setOpen}
                placement="below"
                portaled
                className="robots-v2-fleet-accounts"
            >
                <DropdownMenu.Trigger
                    aria-label={`Все счета робота: ${accounts.length}`}
                    aria-expanded={open}
                    className={[
                        'robots-v2-fleet-accounts__trigger',
                        open ? 'is-open' : '',
                        className,
                    ].filter(Boolean).join(' ')}
                >
                    <span className="robots-v2-fleet-accounts__label">
                        {accountsCountLabel(accounts.length)}
                    </span>
                    <span className="robots-v2-fleet-accounts__chev" aria-hidden>
                        ▾
                    </span>
                </DropdownMenu.Trigger>
                <DropdownMenu.Panel className="robots-v2-fleet-accounts-menu">
                    <div className="robots-v2-fleet-accounts-menu__title">Счета робота</div>
                    <ul className="robots-v2-fleet-accounts-menu__list">
                        {accounts.map((acc, index) => {
                            const name = accountDisplayName(acc)
                            const id = String(acc.accountId ?? acc.account_id ?? '').trim()
                            return (
                                <li
                                    key={id || `${name || 'account'}-${index}`}
                                    className="robots-v2-fleet-accounts-menu__item"
                                >
                                    <span className="robots-v2-fleet-accounts-menu__name">
                                        {name || id || '—'}
                                    </span>
                                    {id && name && name !== id ? (
                                        <span className="robots-v2-fleet-accounts-menu__id">{id}</span>
                                    ) : null}
                                </li>
                            )
                        })}
                    </ul>
                </DropdownMenu.Panel>
            </DropdownMenu>
        </span>
    )
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

function finiteNumber(raw: unknown): number | null {
    if (typeof raw !== 'number' || !Number.isFinite(raw)) return null
    return raw
}

function signedAmount(value: number | null, crypto: boolean): string {
    if (value == null) return '—'
    const text = formatAmount(Math.abs(value), crypto)
    if (value > 0) return `+${text}`
    if (value < 0) return `-${text}`
    return text
}

function winLossOf(snapshot: RobotV2Status | null | undefined): string | null {
    const wins = snapshot?.wins
    const losses = snapshot?.losses
    if (typeof wins !== 'number' || typeof losses !== 'number') return null
    if (!Number.isFinite(wins) || !Number.isFinite(losses) || wins < 0 || losses < 0) return null
    return `${Math.trunc(wins)}/${Math.trunc(losses)}`
}

function statsPeriodLabel(
    snapshot: RobotV2Status | null | undefined,
    sessionState: string | null | undefined,
): string {
    const raw = String(snapshot?.statsPeriod ?? snapshot?.stats_period ?? '').trim().toLowerCase()
    if (raw === 'week') return 'За неделю'
    if (raw === 'month') return 'За месяц'
    if (raw === 'all') return 'За всё время'
    if (raw === 'session') return 'За сессию'
    if (isSessionActive(sessionState)) return 'За сессию'
    return 'За неделю'
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

function sparkPoints(series: number[], width = 160, height = 48, pad = 2): string | null {
    if (series.length < 2) return null
    const min = Math.min(...series)
    const max = Math.max(...series)
    const span = max - min || 1
    return series
        .map((value, index) => {
            const x = pad + (index / (series.length - 1)) * (width - pad * 2)
            const y = height - pad - ((value - min) / span) * (height - pad * 2)
            return `${x.toFixed(1)},${y.toFixed(1)}`
        })
        .join(' ')
}

const EQUITY_SCALE_MIN = 0.55
const EQUITY_SCALE_STEP = 0.04

function fitEquityStackScale(stack: HTMLElement, valueEl: HTMLElement) {
    stack.style.setProperty('--equity-scale', '1')
    let scale = 1
    // Allow layout to settle at full size before measuring overflow.
    while (
        scale > EQUITY_SCALE_MIN
        && valueEl.scrollWidth > valueEl.clientWidth + 0.5
    ) {
        scale = Math.max(EQUITY_SCALE_MIN, +(scale - EQUITY_SCALE_STEP).toFixed(2))
        stack.style.setProperty('--equity-scale', String(scale))
    }
}

export type FleetRobotCardProps = {
    robot: RobotV2
    busy: boolean
    snapshot?: RobotV2Status | null
    accounts?: RobotV2FleetAccount[]
    brokerLabel?: string | null
    actionsMenuOpen: boolean
    onActionsMenuOpenChange: (open: boolean) => void
    onStart: (robot: RobotV2) => void
    onStop: (robot: RobotV2) => void
    onTogglePortfolio: (robot: RobotV2) => void
    onClone: (robot: RobotV2) => void
    onDelete: (robot: RobotV2) => void
}

export function FleetRobotCard({
    robot,
    busy,
    snapshot = null,
    accounts = [],
    brokerLabel = null,
    actionsMenuOpen,
    onActionsMenuOpenChange,
    onStart,
    onStop,
    onTogglePortfolio,
    onClone,
    onDelete,
}: FleetRobotCardProps) {
    const navigate = useNavigate()
    const equityStackRef = useRef<HTMLDivElement>(null)
    const equityValueRef = useRef<HTMLElement>(null)
    const [now, setNow] = useState(() => Date.now())
    useEffect(() => {
        const timer = window.setInterval(() => setNow(Date.now()), 1000)
        return () => window.clearInterval(timer)
    }, [])

    const isPortfolio = robot.type === 1
    const sessionState = sessionStateOf(robot, snapshot)
    const badge = fleetStatusBadge(robot, sessionState)
    const syncAt = syncIso(robot, snapshot, isPortfolio)
    const sync = syncParts(syncAt, now)
    const equityRaw = snapshot?.equity
    const equity = equityRaw != null && Number.isFinite(Number(equityRaw)) ? Number(equityRaw) : null
    const capitalRaw = Number(riskOf(robot).capital)
    const capital = Number.isFinite(capitalRaw) && capitalRaw > 0 ? capitalRaw : null
    const series = equitySeries(snapshot)
    const periodDelta = finiteNumber(snapshot?.periodDelta ?? snapshot?.period_delta)
    const priceDelta = finiteNumber(snapshot?.priceDelta ?? snapshot?.price_delta)
    const ownFunds = finiteNumber(snapshot?.ownFunds ?? snapshot?.own_funds)
    const curveDelta = series.length >= 2 ? series[series.length - 1] - series[0] : null
    const pnl = periodDelta != null
        ? periodDelta
        : curveDelta != null && Number.isFinite(curveDelta)
            ? curveDelta
            : equity != null && capital != null
                ? equity - capital
                : null
    const posCount = positionsCount(snapshot)
    const winLoss = winLossOf(snapshot)
    const periodLabel = statsPeriodLabel(snapshot, sessionState)
    const crypto = isCrypto(robot)
    const errorText = badge.tone === 'bad'
        ? (snapshot?.message || 'Ошибка синхронизации или исполнения')
        : null
    const account = formatAccountsLabel(accounts)
    const accountsCount = accounts.length
    const strategy = archetypeTitle(robot)
    const broker = brokerLabel || null
    const syncFact = formatSyncFact(syncAt, now)
    const active = isSessionActive(sessionState)
    const spark = sparkPoints(series)
    const sparkTone = priceDelta == null ? 'idle' : priceDelta >= 0 ? 'up' : 'down'
    const equityDisplay = equity ?? capital

    useLayoutEffect(() => {
        const stack = equityStackRef.current
        const valueEl = equityValueRef.current
        if (!stack || !valueEl) return

        const run = () => fitEquityStackScale(stack, valueEl)
        run()

        if (typeof ResizeObserver === 'undefined') return undefined
        const ro = new ResizeObserver(run)
        ro.observe(stack)
        return () => {
            ro.disconnect()
            stack.style.removeProperty('--equity-scale')
        }
    }, [equityDisplay, ownFunds, priceDelta, crypto])

    const openRobot = () => navigate(
        isPortfolio ? `/robots/edit/${robot.id}` : `/robots/${robot.id}/monitor`,
    )

    const stopActions = (event: React.SyntheticEvent) => {
        event.stopPropagation()
    }

    const statusBadge = (
        <span className={`robots-v2-fleet-card__status robots-v2-fleet-card__status--${badge.tone}`}>
            {badge.label}
        </span>
    )

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
                    robot.status === 1 ? (
                        <MobileDockDropdown.Item
                            variant="alert"
                            icon={<FontAwesomeIcon icon={faStop} className="mobile-dock__dropdown-icon" />}
                            disabled={busy}
                            onClick={() => onTogglePortfolio(robot)}
                        >
                            Остановить
                        </MobileDockDropdown.Item>
                    ) : (
                        <MobileDockDropdown.Item
                            icon={<FontAwesomeIcon icon={faPlay} className="mobile-dock__dropdown-icon" />}
                            disabled={busy}
                            onClick={() => onTogglePortfolio(robot)}
                        >
                            Включить
                        </MobileDockDropdown.Item>
                    )
                ) : active ? (
                    <MobileDockDropdown.Item
                        variant="alert"
                        icon={<FontAwesomeIcon icon={faStop} className="mobile-dock__dropdown-icon" />}
                        disabled={busy}
                        onClick={() => onStop(robot)}
                    >
                        Остановить
                    </MobileDockDropdown.Item>
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

    if (isPortfolio) {
        return (
            <Card
                className={[
                    'robots-v2-fleet-card',
                    `robots-v2-fleet-card--${badge.tone}`,
                    'robots-v2-fleet-card--portfolio',
                ].join(' ')}
                onClick={openRobot}
            >
                <div className="robots-v2-fleet-card__main robots-v2-fleet-card__main--portfolio">
                    <div className="robots-v2-fleet-card__identity">
                        <div className="robots-v2-fleet-card__name-line">
                            <span className="robots-v2-fleet-card__name">{robot.name}</span>
                            <span className="robots-v2-fleet-card__id">#{robot.id}</span>
                        </div>
                    </div>
                    <div className="robots-v2-fleet-card__metric robots-v2-fleet-card__metric--sync">
                        <div className="robots-v2-fleet-card__metric-label">Синхрон</div>
                        <div className="robots-v2-fleet-card__metric-value">{sync.value}</div>
                        {sync.sub ? (
                            <div className="robots-v2-fleet-card__metric-sub">{sync.sub}</div>
                        ) : (
                            <div className="robots-v2-fleet-card__metric-sub">Последнее обновление</div>
                        )}
                    </div>
                    <div
                        className="robots-v2-fleet-card__metric robots-v2-fleet-card__metric--accounts"
                        onClick={accountsCount > 1 ? stopActions : undefined}
                        onKeyDown={accountsCount > 1 ? stopActions : undefined}
                    >
                        <div className="robots-v2-fleet-card__metric-label">
                            {accountsCount > 1 ? 'Брокерские аккаунты' : 'Брокерский аккаунт'}
                        </div>
                        <AccountsDisclosure
                            accounts={accounts}
                            className="robots-v2-fleet-card__metric-value robots-v2-fleet-accounts__trigger--metric"
                        />
                        <div className="robots-v2-fleet-card__metric-sub">
                            {broker
                                || (accountsCount > 1
                                    ? 'Подключены'
                                    : account
                                        ? 'Подключён'
                                        : 'Не выбран')}
                        </div>
                    </div>
                    <div className="robots-v2-fleet-card__facts" aria-label="Сводка">
                        <span className="robots-v2-fleet-card__fact robots-v2-fleet-card__fact--primary">
                            {broker ? (
                                <>
                                    <span className="robots-v2-fleet-card__fact-broker">{broker}</span>
                                    <span className="robots-v2-fleet-card__fact-sep" aria-hidden>·</span>
                                </>
                            ) : null}
                            <AccountsDisclosure
                                accounts={accounts}
                                className="robots-v2-fleet-accounts__trigger--fact"
                            />
                        </span>
                        <span className="robots-v2-fleet-card__fact robots-v2-fleet-card__fact--sync">
                            {syncFact}
                        </span>
                    </div>
                    <div
                        className="robots-v2-fleet-card__actions"
                        onClick={stopActions}
                        onKeyDown={stopActions}
                    >
                        {statusBadge}
                        {menu}
                    </div>
                </div>
            </Card>
        )
    }

    return (
        <Card
            className={[
                'robots-v2-fleet-card',
                'robots-v2-fleet-card--trading',
                `robots-v2-fleet-card--${badge.tone}`,
            ].join(' ')}
            onClick={openRobot}
        >
            <div className="robots-v2-fleet-card__main robots-v2-fleet-card__main--trading">
                <div className="robots-v2-fleet-card__identity">
                    <div className="robots-v2-fleet-card__name-line">
                        <span className="robots-v2-fleet-card__name">{robot.name}</span>
                        <span className="robots-v2-fleet-card__id">#{robot.id}</span>
                    </div>
                    <div className="robots-v2-fleet-card__meta">
                        {strategy || '—'}
                    </div>
                </div>

                <div className="robots-v2-fleet-card__metric robots-v2-fleet-card__metric--sync">
                    <div className="robots-v2-fleet-card__metric-label">Синхрон</div>
                    <div className="robots-v2-fleet-card__metric-value">{sync.value}</div>
                    {sync.sub ? (
                        <div className="robots-v2-fleet-card__metric-sub">{sync.sub}</div>
                    ) : (
                        <div className="robots-v2-fleet-card__metric-sub">Последнее обновление</div>
                    )}
                </div>
                <div
                    className="robots-v2-fleet-card__metric robots-v2-fleet-card__metric--accounts"
                    onClick={accountsCount > 1 ? stopActions : undefined}
                    onKeyDown={accountsCount > 1 ? stopActions : undefined}
                >
                    <div className="robots-v2-fleet-card__metric-label">
                        {accountsCount > 1 ? 'Брокерские аккаунты' : 'Брокерский аккаунт'}
                    </div>
                    <AccountsDisclosure
                        accounts={accounts}
                        className="robots-v2-fleet-card__metric-value robots-v2-fleet-accounts__trigger--metric"
                    />
                    <div className="robots-v2-fleet-card__metric-sub">
                        {broker
                            || (accountsCount > 1
                                ? 'Подключены'
                                : account
                                    ? 'Подключён'
                                    : 'Не выбран')}
                    </div>
                </div>

                <div className="robots-v2-fleet-card__facts" aria-label="Сводка">
                    <span className="robots-v2-fleet-card__fact robots-v2-fleet-card__fact--primary">
                        <AccountsDisclosure
                            accounts={accounts}
                            className="robots-v2-fleet-accounts__trigger--fact"
                        />
                    </span>
                    <span className="robots-v2-fleet-card__fact robots-v2-fleet-card__fact--sync">
                        {syncFact}
                    </span>
                </div>

                <div className="robots-v2-fleet-card__equity">
                    <div className="robots-v2-fleet-card__equity-primary">
                        <div
                            ref={equityStackRef}
                            className="robots-v2-fleet-card__equity-stack"
                        >
                            <div className="robots-v2-fleet-card__equity-hero">
                                <div className="robots-v2-fleet-card__equity-hero-head">
                                    <span className="robots-v2-fleet-card__equity-label">Текущая</span>
                                    <span
                                        className={[
                                            'robots-v2-fleet-card__equity-meta-item',
                                            'robots-v2-fleet-card__pnl',
                                            priceDelta == null ? 'is-idle' : priceDelta >= 0 ? 'is-up' : 'is-down',
                                        ].join(' ')}
                                    >
                                        <strong className="robots-v2-fleet-card__equity-meta-value">
                                            {signedAmount(priceDelta, crypto)}
                                        </strong>
                                    </span>
                                </div>
                                <strong
                                    ref={equityValueRef}
                                    className="robots-v2-fleet-card__equity-value"
                                >
                                    {equityDisplay != null ? formatAmount(equityDisplay, crypto) : '—'}
                                </strong>
                            </div>
                            <div className="robots-v2-fleet-card__equity-meta">
                                <span className="robots-v2-fleet-card__equity-meta-item">
                                    <span className="robots-v2-fleet-card__equity-meta-label">Свои</span>
                                    <strong className="robots-v2-fleet-card__equity-meta-value">
                                        {ownFunds != null ? formatAmount(ownFunds, crypto) : '—'}
                                    </strong>
                                </span>
                            </div>
                        </div>
                        {spark ? (
                            <div className="robots-v2-fleet-card__equity-side">
                                <svg
                                    className={`robots-v2-fleet-card__spark robots-v2-fleet-card__spark--${sparkTone}`}
                                    viewBox="0 0 160 48"
                                    preserveAspectRatio="none"
                                    aria-hidden
                                >
                                    <polyline
                                        fill="none"
                                        stroke="currentColor"
                                        strokeWidth="2"
                                        strokeLinejoin="round"
                                        strokeLinecap="round"
                                        points={spark}
                                    />
                                </svg>
                            </div>
                        ) : null}
                    </div>
                    <div
                        className="robots-v2-fleet-card__equity-secondary"
                        aria-label={`Статистика: ${periodLabel}`}
                    >
                        <span className="robots-v2-fleet-card__equity-period">{periodLabel}</span>
                        <div className="robots-v2-fleet-card__equity-stats">
                            <div className="robots-v2-fleet-card__equity-stat">
                                <span className="robots-v2-fleet-card__equity-stat-label">
                                    <span className="robots-v2-fleet-card__equity-stat-label-full">Позиции</span>
                                    <span className="robots-v2-fleet-card__equity-stat-label-short">Поз.</span>
                                </span>
                                <strong className="robots-v2-fleet-card__equity-stat-value">
                                    {posCount != null ? String(posCount) : '—'}
                                </strong>
                            </div>
                            <div className="robots-v2-fleet-card__equity-stat">
                                <span className="robots-v2-fleet-card__equity-stat-label">P&L</span>
                                <strong
                                    className={[
                                        'robots-v2-fleet-card__equity-stat-value',
                                        pnl == null ? 'is-idle' : pnl >= 0 ? 'is-up' : 'is-down',
                                    ].join(' ')}
                                >
                                    {signedAmount(pnl, crypto)}
                                </strong>
                            </div>
                            <div className="robots-v2-fleet-card__equity-stat">
                                <span className="robots-v2-fleet-card__equity-stat-label">
                                    <span className="robots-v2-fleet-card__equity-stat-label-full">Win/Loss</span>
                                    <span className="robots-v2-fleet-card__equity-stat-label-short">W/L</span>
                                </span>
                                <strong className="robots-v2-fleet-card__equity-stat-value">
                                    {winLoss || '—'}
                                </strong>
                            </div>
                        </div>
                    </div>
                </div>

                {errorText ? (
                    <div
                        className="robots-v2-fleet-card__inline-alert"
                        onClick={stopActions}
                    >
                        <span>ⓘ {errorText}</span>
                        <button
                            type="button"
                            className="robots-v2-fleet-card__link"
                            onClick={() => navigate(`/robots/${robot.id}/logs`)}
                        >
                            Логи →
                        </button>
                    </div>
                ) : null}

                <div
                    className="robots-v2-fleet-card__actions"
                    onClick={stopActions}
                    onKeyDown={stopActions}
                >
                    {statusBadge}
                    {menu}
                </div>
            </div>
        </Card>
    )
}
