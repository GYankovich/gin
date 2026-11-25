import React, {
    Suspense,
    createContext,
    useCallback,
    useContext,
    useLayoutEffect,
    useMemo,
    useState,
    type DependencyList,
} from 'react'
import { Outlet, useLocation, useParams } from 'react-router-dom'
import {
    RobotsQuietChrome,
    type RobotLiveStage,
    type RobotsQuietChromeActive,
} from '@/pages/robots/components/RobotsQuietChrome'
import type { TradingRobot, TradingRobotStatus } from '@/types/robots'

type QuietChromeSlot = {
    setActions: (node: React.ReactNode) => void
    setLiveStage: (stage: RobotLiveStage | null) => void
    setStreamConnected: (connected: boolean | undefined) => void
    setPhaseNote: (note: string | null) => void
    setMonitorSnapshot: (snap: {
        robot: TradingRobot | null
        status: TradingRobotStatus | null
        statusLoaded: boolean
    } | null) => void
}

const QuietChromeContext = createContext<QuietChromeSlot | null>(null)

/** Register header actions for the persistent quiet chrome (Live / History). */
export function useQuietChromeActions(
    factory: () => React.ReactNode,
    deps: DependencyList,
) {
    const ctx = useContext(QuietChromeContext)
    useLayoutEffect(() => {
        if (!ctx) return
        ctx.setActions(factory())
        return () => ctx.setActions(null)
        // eslint-disable-next-line react-hooks/exhaustive-deps -- caller supplies deps
    }, deps)
}

/** Push live WS stage into the persistent quiet chrome (monitor only). */
export function useQuietChromeLive(
    liveStage: RobotLiveStage | null,
    streamConnected?: boolean,
) {
    const ctx = useContext(QuietChromeContext)
    useLayoutEffect(() => {
        if (!ctx) return
        ctx.setLiveStage(liveStage)
        return () => ctx.setLiveStage(null)
    }, [ctx, liveStage])
    useLayoutEffect(() => {
        if (!ctx) return
        ctx.setStreamConnected(streamConnected)
        return () => ctx.setStreamConnected(undefined)
    }, [ctx, streamConnected])
}

/** Footnote under the phase track (balance honesty line from monitor). */
export function useQuietChromePhaseNote(note: string | null) {
    const ctx = useContext(QuietChromeContext)
    useLayoutEffect(() => {
        if (!ctx) return
        ctx.setPhaseNote(note)
        return () => ctx.setPhaseNote(null)
    }, [ctx, note])
}

/** Push Live page robot/status into the persistent chrome (single source of truth). */
export function useQuietChromeMonitorSnapshot(
    robot: TradingRobot | null,
    status: TradingRobotStatus | null,
    statusLoaded: boolean,
) {
    const ctx = useContext(QuietChromeContext)
    useLayoutEffect(() => {
        if (!ctx) return
        ctx.setMonitorSnapshot({ robot, status, statusLoaded })
        return () => ctx.setMonitorSnapshot(null)
    }, [ctx, robot, status, statusLoaded])
}

function ShellFallback() {
    return (
        <div className="page-loader" aria-busy="true">
            <div className="page-loader__spinner" />
        </div>
    )
}

/**
 * Persistent shell for /robots/:id/monitor|logs.
 * Quiet chrome stays mounted across tab switches; only the Outlet content swaps.
 */
export default function RobotQuietShell() {
    const { id } = useParams()
    const robotId = Number(id)
    const { pathname } = useLocation()
    const active: RobotsQuietChromeActive = pathname.includes('/logs') ? 'logs' : 'monitor'

    const [actions, setActions] = useState<React.ReactNode>(null)
    const [liveStage, setLiveStage] = useState<RobotLiveStage | null>(null)
    const [streamConnected, setStreamConnected] = useState<boolean | undefined>(undefined)
    const [phaseNote, setPhaseNote] = useState<string | null>(null)
    const [monitorSnap, setMonitorSnap] = useState<{
        robot: TradingRobot | null
        status: TradingRobotStatus | null
        statusLoaded: boolean
    } | null>(null)

    const setActionsStable = useCallback((node: React.ReactNode) => {
        setActions(node)
    }, [])
    const setLiveStageStable = useCallback((stage: RobotLiveStage | null) => {
        setLiveStage(stage)
    }, [])
    const setStreamConnectedStable = useCallback((connected: boolean | undefined) => {
        setStreamConnected(connected)
    }, [])
    const setPhaseNoteStable = useCallback((note: string | null) => {
        setPhaseNote(note)
    }, [])
    const setMonitorSnapshotStable = useCallback((
        snap: {
            robot: TradingRobot | null
            status: TradingRobotStatus | null
            statusLoaded: boolean
        } | null,
    ) => {
        setMonitorSnap(snap)
    }, [])

    const slot = useMemo<QuietChromeSlot>(() => ({
        setActions: setActionsStable,
        setLiveStage: setLiveStageStable,
        setStreamConnected: setStreamConnectedStable,
        setPhaseNote: setPhaseNoteStable,
        setMonitorSnapshot: setMonitorSnapshotStable,
    }), [
        setActionsStable,
        setLiveStageStable,
        setStreamConnectedStable,
        setPhaseNoteStable,
        setMonitorSnapshotStable,
    ])

    if (!Number.isFinite(robotId)) {
        return <ShellFallback />
    }

    return (
        <QuietChromeContext.Provider value={slot}>
            <div className="page" data-page="robots" data-robots-view={active}>
                <RobotsQuietChrome
                    robotId={robotId}
                    active={active}
                    actions={actions}
                    robot={monitorSnap ? monitorSnap.robot : undefined}
                    status={monitorSnap ? monitorSnap.status : undefined}
                    statusLoaded={monitorSnap ? monitorSnap.statusLoaded : undefined}
                    liveStage={liveStage}
                    streamConnected={streamConnected}
                    phaseNote={phaseNote}
                />
                <Suspense fallback={<ShellFallback />}>
                    <Outlet />
                </Suspense>
            </div>
        </QuietChromeContext.Provider>
    )
}
