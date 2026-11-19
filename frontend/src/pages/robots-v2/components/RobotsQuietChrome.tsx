import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowLeft } from '@fortawesome/free-solid-svg-icons'
import { Button } from '@/components/ui/Button'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { sessionStateLabel } from '@/pages/robots-v2/formatters'
import {
    CYCLE_STAGE_ORDER,
    pick,
    stageDetailLabel,
    stageLabel,
    SKIP_LABELS,
} from '@/pages/robots-v2/monitorUtils'
import {
    RobotMobileSubnav,
    type RobotMobileNavItem,
} from '@/pages/robots-v2/components/RobotMobileSubnav'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2, RobotV2Status } from '@/types/robotV2'

export type RobotsQuietChromeActive = 'monitor' | 'logs'

export type RobotLiveStage = {
    stage: string
    label?: string
    progress?: number
    skipReason?: string | null
    triggeredBy?: string | null
    detail?: string | null
}

type StatusTone = 'up' | 'down' | 'cyan' | 'neutral'

type RobotsQuietChromeProps = {
    robotId: number
    active: RobotsQuietChromeActive
    actions?: React.ReactNode
    /** Prefer live monitor state when provided; otherwise chrome polls on its own. */
    robot?: RobotV2 | null
    status?: RobotV2Status | null
    statusLoaded?: boolean
    liveStage?: RobotLiveStage | null
    streamConnected?: boolean
}

function statusBadge(
    status: RobotV2Status | null,
    loaded: boolean,
): { label: string; variant: StatusTone } {
    if (!loaded) return { label: '…', variant: 'neutral' }
    const sessionState = String(pick(status || ({} as RobotV2Status), 'sessionState', 'session_state') || '')
    const sessionUpper = sessionState.toUpperCase()
    const statusStage = pick<string>(status || ({} as RobotV2Status), 'cycleStage', 'cycle_stage')
    const stageLower = String(statusStage || '').toLowerCase()
    const bootstrapReady = Boolean(
        pick<boolean>(status || ({} as RobotV2Status), 'bootstrapReady', 'bootstrap_ready'),
    )
    const isRunning = sessionUpper === 'RUNNING' || sessionUpper === 'BOOTSTRAP'
    const isStopping = sessionUpper === 'STOPPING'
    const isActive = isRunning || isStopping
    const isError = sessionUpper === 'ERROR'
    const isSyncing =
        sessionUpper === 'BOOTSTRAP'
        || (sessionUpper === 'RUNNING' && !bootstrapReady)
        || (isActive && (stageLower === 'bootstrap' || stageLower === 'bootstrap_sync'))

    if (isError) return { label: 'Ошибка', variant: 'down' }
    if (isSyncing || sessionUpper === 'BOOTSTRAP') return { label: 'Синхронизация', variant: 'cyan' }
    if (sessionUpper === 'RUNNING') return { label: 'Работает', variant: 'up' }
    if (isStopping) return { label: 'Остановка', variant: 'neutral' }
    return { label: sessionStateLabel(sessionState), variant: 'neutral' }
}

function PhaseTrack({
    status,
    statusLoaded,
    liveStage,
    streamConnected,
}: {
    status: RobotV2Status | null
    statusLoaded: boolean
    liveStage?: RobotLiveStage | null
    streamConnected?: boolean
}) {
    const sessionState = String(pick(status || ({} as RobotV2Status), 'sessionState', 'session_state') || '')
    const sessionUpper = sessionState.toUpperCase()
    const isRunning = sessionUpper === 'RUNNING' || sessionUpper === 'BOOTSTRAP'
    const isStopping = sessionUpper === 'STOPPING'
    const isActive = isRunning || isStopping
    const statusMode = pick<string>(status || ({} as RobotV2Status), 'mode', 'mode')
    const statusMessage = pick<string>(status || ({} as RobotV2Status), 'message', 'message')
    const statusStage = pick<string>(status || ({} as RobotV2Status), 'cycleStage', 'cycle_stage')
    const cycle = pick<number>(status || ({} as RobotV2Status), 'cycleNumber', 'cycle_number')
    const statusProgress = pick<number>(status || ({} as RobotV2Status), 'cycleProgress', 'cycle_progress')
    const statusDetail = pick<string>(status || ({} as RobotV2Status), 'cycleDetail', 'cycle_detail')
    const statusSkip = pick<string>(status || ({} as RobotV2Status), 'cycleSkipReason', 'cycle_skip_reason')
    const statusTriggered = pick<string>(status || ({} as RobotV2Status), 'lastTriggeredBy', 'last_triggered_by')

    const stageKey = liveStage?.stage || statusStage || (isActive ? 'idle' : null)
    const stageText = liveStage?.label
        || (stageKey ? stageLabel(stageKey) : null)
        || (isActive ? 'Ожидание' : null)
    const stageProgress = Math.max(
        0,
        Math.min(1, Number(
            liveStage?.progress
            ?? statusProgress
            ?? (stageKey === 'done' || stageKey === 'skipped' ? 1 : 0),
        )),
    )
    const stagePct = Math.round(stageProgress * 100)
    const stageDetailText = stageDetailLabel(liveStage?.detail ?? statusDetail ?? null)
    const skipReason = liveStage?.skipReason ?? statusSkip ?? null
    const triggeredBy = liveStage?.triggeredBy ?? statusTriggered ?? null
    const cycleLabel = cycle != null && Number.isFinite(Number(cycle)) ? `цикл ${cycle}` : null
    const detailLine = [
        cycleLabel,
        statusMode || null,
        statusLoaded && streamConnected === false ? 'стрим офлайн' : null,
        stageDetailText,
        triggeredBy ? `триггер: ${triggeredBy}` : null,
        skipReason ? (SKIP_LABELS[skipReason] || skipReason) : null,
        statusMessage || null,
    ].filter(Boolean).join(' · ')
    const show = statusLoaded && Boolean(stageText)
    const stageIndex = CYCLE_STAGE_ORDER.indexOf(stageKey as typeof CYCLE_STAGE_ORDER[number])

    if (!show) return null

    return (
        <div className="robots-monitor-phase">
            <div className="robots-monitor-phase__track">
                {CYCLE_STAGE_ORDER.map((key, index) => {
                    const state = stageIndex < 0
                        ? ''
                        : index < stageIndex
                            ? 'done'
                            : index === stageIndex
                                ? 'now'
                                : ''
                    return (
                        <div
                            key={key}
                            className={`robots-monitor-phase__step${state ? ` robots-monitor-phase__step--${state}` : ''}`}
                        >
                            <div className="robots-monitor-phase__bar" />
                            <span>
                                {stageLabel(key)}
                                {state === 'now' ? ` · ${stagePct}%` : ''}
                            </span>
                        </div>
                    )
                })}
            </div>
            {detailLine ? <p className="robots-monitor-phase__why">{detailLine}</p> : null}
        </div>
    )
}

/**
 * Shared quiet header for robot Live / History.
 * Same shell everywhere: back · name · LED · phase · Лайв/История · actions.
 */
export function RobotsQuietChrome({
    robotId,
    active,
    actions,
    robot: robotProp,
    status: statusProp,
    statusLoaded: statusLoadedProp,
    liveStage,
    streamConnected,
}: RobotsQuietChromeProps) {
    const navigate = useNavigate()
    const isNarrow = useMediaQuery('(max-width: 767px)')
    const controlled = statusProp !== undefined || robotProp !== undefined

    const [robotLocal, setRobotLocal] = useState<RobotV2 | null>(null)
    const [statusLocal, setStatusLocal] = useState<RobotV2Status | null>(null)
    const [loadedLocal, setLoadedLocal] = useState(false)

    const refresh = useCallback(async () => {
        if (!Number.isFinite(robotId) || controlled) return
        try {
            const [r, s] = await Promise.all([
                robotV2Service.getById(robotId),
                robotV2Service.getStatus(robotId),
            ])
            setRobotLocal(r)
            setStatusLocal(s)
        } catch {
            /* keep last good chrome state */
        } finally {
            setLoadedLocal(true)
        }
    }, [controlled, robotId])

    useEffect(() => {
        if (controlled) return
        setLoadedLocal(false)
        void refresh()
        const timer = window.setInterval(() => void refresh(), 5_000)
        return () => window.clearInterval(timer)
    }, [controlled, refresh])

    const robot = robotProp !== undefined ? robotProp : robotLocal
    const status = statusProp !== undefined ? statusProp : statusLocal
    const statusLoaded = statusLoadedProp ?? (controlled ? statusProp != null || robotProp != null : loadedLocal)
    const title = robot?.name || `Робот #${robotId}`
    const badge = statusBadge(status, Boolean(statusLoaded))

    const navItems = useMemo<RobotMobileNavItem[]>(() => {
        if (!Number.isFinite(robotId)) return []
        return [
            { id: 'monitor', label: 'Лайв', path: `/robots/${robotId}/monitor` },
            { id: 'logs', label: 'История', path: `/robots/${robotId}/logs` },
        ]
    }, [robotId])

    const tab = (label: string, path: string, isActive: boolean) => (
        <Button
            type="button"
            variant="ghost"
            size="sm"
            className={`robots-quiet-chrome__tab${isActive ? ' robots-quiet-chrome__tab--active' : ''}`}
            aria-current={isActive ? 'page' : undefined}
            onClick={() => navigate(path)}
        >
            {label}
        </Button>
    )

    return (
        <header className="robots-quiet-chrome">
            <div className="robots-quiet-chrome__top">
                <div className="robots-quiet-chrome__copy">
                    <div className="robots-quiet-chrome__title-row">
                        <button
                            type="button"
                            className="robots-quiet-chrome__back"
                            aria-label="Назад к флоту"
                            title="К флоту"
                            onClick={() => navigate('/robots')}
                        >
                            <FontAwesomeIcon icon={faArrowLeft} />
                        </button>
                        <h1 className="robots-quiet-chrome__title">{title}</h1>
                        <span className={`robots-quiet-chrome__status robots-quiet-chrome__status--${badge.variant}`}>
                            <i className="robots-quiet-chrome__led" aria-hidden />
                            {badge.label}
                        </span>
                    </div>
                </div>
                {actions ? <div className="robots-quiet-chrome__actions">{actions}</div> : null}
            </div>
            <PhaseTrack
                status={status}
                statusLoaded={Boolean(statusLoaded)}
                liveStage={liveStage}
                streamConnected={streamConnected}
            />
            {!isNarrow ? (
                <nav className="robots-quiet-chrome__nav" aria-label="Разделы робота">
                    {tab('Лайв', `/robots/${robotId}/monitor`, active === 'monitor')}
                    {tab('История', `/robots/${robotId}/logs`, active === 'logs')}
                </nav>
            ) : (
                <RobotMobileSubnav items={navItems} active={active} />
            )}
        </header>
    )
}
