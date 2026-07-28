import { useCallback, useEffect, useMemo, useState } from 'react'
import { robotService } from '@/services/robotService'
import type { Dispatch, SetStateAction } from 'react'
import type { Robot } from '@/types/robot'
import {
    hydrateCandidatePool,
    hydrateUniverseJobsState,
} from '@/utils/robotConfigV2'

type ToastLike = {
    show: (message: string, variant?: 'success' | 'error' | 'info' | 'warning', durationMs?: number) => void
}

export type DailyUniverseRow = {
    id?: number
    ticker?: string
    source?: string
    filter_result?: string
    reject_reason?: string | null
    snapshot_id?: number | null
    created_at?: string
}

export function useTestingUniverse(opts: {
    selectedRobot: Robot | null
    toast: ToastLike
    setRobots?: Dispatch<SetStateAction<Robot[]>>
}) {
    const { selectedRobot, toast, setRobots } = opts
    const robotId = selectedRobot?.id ?? null

    const [dailyUniverse, setDailyUniverse] = useState<DailyUniverseRow[]>([])
    const [allowedFigis, setAllowedFigis] = useState<string[]>([])
    const [candidatePoolTickers, setCandidatePoolTickers] = useState<string[]>([])
    const [candidatePoolAsOf, setCandidatePoolAsOf] = useState<string | null>(null)
    const [lastHistoricalRun, setLastHistoricalRun] = useState<string | null>(null)
    const [lastPaperRun, setLastPaperRun] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)
    const [syncing, setSyncing] = useState(false)
    const [histJobLoading, setHistJobLoading] = useState(false)
    const [paperJobLoading, setPaperJobLoading] = useState(false)

    const load = useCallback(async () => {
        if (!robotId) {
            setDailyUniverse([])
            setAllowedFigis([])
            setCandidatePoolTickers([])
            setCandidatePoolAsOf(null)
            setLastHistoricalRun(null)
            setLastPaperRun(null)
            return
        }
        setLoading(true)
        try {
            const tradeDate = new Date().toISOString().slice(0, 10)
            const [universeRes, robot] = await Promise.all([
                robotService.listDailyUniverse({ robot_id: robotId, trade_date: tradeDate }),
                robotService.getById(robotId),
            ])
            setDailyUniverse(Array.isArray(universeRes?.items) ? universeRes.items : [])
            const cfg = (robot.config || {}) as Record<string, unknown>
            const figis = Array.isArray(cfg.allowed_figis) ? (cfg.allowed_figis as string[]) : []
            setAllowedFigis(figis.map(f => String(f).toUpperCase()))
            const pool = hydrateCandidatePool(cfg)
            setCandidatePoolTickers(pool.tickers)
            setCandidatePoolAsOf(pool.asOf)
            const jobs = hydrateUniverseJobsState(cfg)
            setLastHistoricalRun(jobs.lastHistoricalScreeningAt)
            setLastPaperRun(jobs.lastPaperSelectionAt)
        } catch {
            setDailyUniverse([])
            setAllowedFigis([])
            toast.show('Не удалось загрузить universe', 'error')
        } finally {
            setLoading(false)
        }
    }, [robotId, toast])

    useEffect(() => {
        void load()
    }, [load])

    const syncUniverse = useCallback(async () => {
        if (!robotId) return
        setSyncing(true)
        try {
            const res = await robotService.syncUniverse(robotId)
            toast.show(
                `Universe пересобран: ${res.allowed_figis.length} FIGI (ACCEPT: ${res.accepted_tickers.length})`,
                'success',
            )
            setAllowedFigis(res.allowed_figis.map(f => String(f).toUpperCase()))
            if (setRobots) {
                const refreshed = await robotService.getById(robotId)
                setRobots(prev => prev.map(r => (r.id === refreshed.id ? refreshed : r)))
            }
            await load()
        } catch {
            toast.show('Не удалось пересобрать universe', 'error')
        } finally {
            setSyncing(false)
        }
    }, [robotId, load, toast, setRobots])

    const runHistoricalScreening = useCallback(async () => {
        if (!robotId) return
        setHistJobLoading(true)
        try {
            const res = await robotService.runHistoricalScreening(robotId)
            if (res.skipped) {
                toast.show(res.message || 'П1 пропущен', 'info')
            } else {
                toast.show(`П1: ${res.passed}/${res.scanned} → ${res.tickers.length} тикеров`, 'success')
            }
            setCandidatePoolTickers(res.tickers.map(t => String(t).toUpperCase()))
            if (res.as_of) setCandidatePoolAsOf(res.as_of)
            if (setRobots) {
                const refreshed = await robotService.getById(robotId)
                setRobots(prev => prev.map(r => (r.id === refreshed.id ? refreshed : r)))
            }
            await load()
        } catch {
            toast.show('Не удалось запустить П1', 'error')
        } finally {
            setHistJobLoading(false)
        }
    }, [robotId, load, toast, setRobots])

    const runPaperSelection = useCallback(async () => {
        if (!robotId) return
        setPaperJobLoading(true)
        try {
            const res = await robotService.runPaperSelection(robotId)
            toast.show(
                `П2: ${res.accepted_tickers.length} тикеров → ${res.allowed_figis.length} FIGI`,
                'success',
            )
            setAllowedFigis(res.allowed_figis.map(f => String(f).toUpperCase()))
            if (setRobots) {
                const refreshed = await robotService.getById(robotId)
                setRobots(prev => prev.map(r => (r.id === refreshed.id ? refreshed : r)))
            }
            await load()
        } catch {
            toast.show('Не удалось запустить П2', 'error')
        } finally {
            setPaperJobLoading(false)
        }
    }, [robotId, load, toast, setRobots])

    const subscribeDms = useCallback(async () => {
        if (!robotId) return
        try {
            await robotService.subscribeDms({
                robot_id: robotId,
                board: 'TQBR',
                ttl_minutes: 5,
            })
            toast.show('Подписка DMS создана', 'success')
            await load()
        } catch {
            toast.show('Не удалось создать подписку DMS', 'error')
        }
    }, [robotId, load, toast])

    const universeAccepted = useMemo(
        () => dailyUniverse.filter(r => String(r.filter_result || '').toUpperCase() === 'ACCEPT'),
        [dailyUniverse],
    )
    const universeRejected = useMemo(
        () => dailyUniverse.filter(r => String(r.filter_result || '').toUpperCase() === 'REJECT'),
        [dailyUniverse],
    )

    return {
        dailyUniverse,
        allowedFigis,
        candidatePoolTickers,
        candidatePoolAsOf,
        lastHistoricalRun,
        lastPaperRun,
        loading,
        syncing,
        histJobLoading,
        paperJobLoading,
        load,
        syncUniverse,
        runHistoricalScreening,
        runPaperSelection,
        subscribeDms,
        universeAccepted,
        universeRejected,
    }
}
