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
} from '@/pages/robots-v2/components/RobotsQuietChrome'

type QuietChromeSlot = {
    setActions: (node: React.ReactNode) => void
    setLiveStage: (stage: RobotLiveStage | null) => void
    setStreamConnected: (connected: boolean | undefined) => void
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

    const setActionsStable = useCallback((node: React.ReactNode) => {
        setActions(node)
    }, [])
    const setLiveStageStable = useCallback((stage: RobotLiveStage | null) => {
        setLiveStage(stage)
    }, [])
    const setStreamConnectedStable = useCallback((connected: boolean | undefined) => {
        setStreamConnected(connected)
    }, [])

    const slot = useMemo<QuietChromeSlot>(() => ({
        setActions: setActionsStable,
        setLiveStage: setLiveStageStable,
        setStreamConnected: setStreamConnectedStable,
    }), [setActionsStable, setLiveStageStable, setStreamConnectedStable])

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
                    liveStage={liveStage}
                    streamConnected={streamConnected}
                />
                <Suspense fallback={<ShellFallback />}>
                    <Outlet />
                </Suspense>
            </div>
        </QuietChromeContext.Provider>
    )
}
