import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '@/services/api'
import {
    marketService,
    type CandleLoadJobStatus,
    type MoexCacheInterval,
} from '@/services/marketService'
import type { Robot } from '@/types/robot'
import { buildPipelineFiltersPayload, suggestedMoexIntervalForSignal } from '@/pages/testing/testingPipeline'
import { clampDateToToday, fmtErr, parseTickers, toApiDate } from '@/pages/testing/testingUtils'

type ToastLike = {
    show: (message: string, variant?: 'success' | 'error' | 'info' | 'warning', durationMs?: number) => void
}

export type PipelineFiltersPayload = ReturnType<typeof buildPipelineFiltersPayload>

export function useMoexCandleJobState(opts: {
    fromDate: string
    toDate: string
    signalInterval: string
    selectedRobot: Robot | null
    pipelinePayload: PipelineFiltersPayload
    pipelineMode: 'ALL' | 'ANY'
    toast: ToastLike
}) {
    const { fromDate, toDate, signalInterval, selectedRobot, pipelinePayload, pipelineMode, toast } = opts

    const [moexTickers, setMoexTickers] = useState('')
    const [moexBoard, setMoexBoard] = useState('TQBR')
    const [moexInterval, setMoexInterval] = useState<MoexCacheInterval>('10m')
    const [moexJobId, setMoexJobId] = useState<string | null>(null)
    const [moexJobStatus, setMoexJobStatus] = useState<CandleLoadJobStatus | null>(null)
    const [moexJobSubmitting, setMoexJobSubmitting] = useState(false)
    const [moexJobError, setMoexJobError] = useState<string | null>(null)
    const [moexPreviewLoading, setMoexPreviewLoading] = useState(false)
    const [moexPreview, setMoexPreview] = useState<{ bars: number; gaps: number } | null>(null)

    useEffect(() => {
        if (!moexJobId) return
        let cancelled = false
        const pollOnce = async (): Promise<string> => {
            try {
                const st = await marketService.getCandleLoadJob(moexJobId)
                if (!cancelled) {
                    setMoexJobStatus(st)
                    setMoexJobError(null)
                }
                return st.status
            } catch (e: unknown) {
                if (!cancelled) setMoexJobError(fmtErr(e))
                return 'failed'
            }
        }
        void (async () => {
            let status = await pollOnce()
            while (!cancelled && (status === 'queued' || status === 'running')) {
                await new Promise(r => setTimeout(r, 2000))
                if (cancelled) break
                status = await pollOnce()
            }
        })()
        return () => {
            cancelled = true
        }
    }, [moexJobId])

    const suggestedMoexForSignal = useMemo(() => suggestedMoexIntervalForSignal(signalInterval), [signalInterval])
    const moexIntervalMismatch = moexInterval !== suggestedMoexForSignal

    const resolveMoexTickersAuto = useCallback(async (): Promise<string[]> => {
        if (!selectedRobot) {
            throw new Error('NO_ROBOT')
        }
        const { data } = await api.post<{ sample?: Array<{ ticker?: string; result?: string }> }>('/dms/pipeline/preview', {
            robot_id: selectedRobot.id,
            board: moexBoard.trim().toUpperCase() || 'TQBR',
            filters: pipelinePayload,
            mode: pipelineMode,
        })
        const sample = Array.isArray(data?.sample) ? data.sample : []
        const acc = new Set<string>()
        for (const row of sample) {
            if (String(row?.result || '').toUpperCase() === 'ACCEPT' && row?.ticker) {
                acc.add(String(row.ticker).trim().toUpperCase())
            }
        }
        return [...acc].sort()
    }, [selectedRobot, moexBoard, pipelineMode, pipelinePayload])

    const resolveMoexTickersForJob = useCallback(async (): Promise<{ tickers: string[]; auto: boolean }> => {
        const manual = parseTickers(moexTickers)
        if (manual.length) {
            return { tickers: manual, auto: false }
        }
        const auto = await resolveMoexTickersAuto()
        return { tickers: auto, auto: true }
    }, [moexTickers, resolveMoexTickersAuto])

    const startMoexCandleLoad = useCallback(async () => {
        setMoexJobSubmitting(true)
        setMoexJobError(null)
        setMoexPreview(null)
        try {
            if (!fromDate || !toDate) {
                toast.show('Выберите период тестирования (блок параметров робота ниже)', 'error', 4500)
                return
            }
            let tickers: string[] = []
            let usedAuto = false
            try {
                const r = await resolveMoexTickersForJob()
                tickers = r.tickers
                usedAuto = r.auto
            } catch (e: unknown) {
                if (fmtErr(e).includes('NO_ROBOT') || (e as Error)?.message === 'NO_ROBOT') {
                    toast.show('Для автоподбора выберите робота в блоке «Параметры робота»', 'error', 5000)
                    return
                }
                throw e
            }
            if (!tickers.length) {
                toast.show(
                    usedAuto
                        ? 'Автоподбор не вернул ни одной бумаги (ACCEPT). Ослабьте фильтры конвейера или укажите тикеры вручную.'
                        : 'Укажите хотя бы один тикер или включите автоподбор (очистите поле)',
                    'error',
                    5500,
                )
                return
            }
            const fromIso = `${toApiDate(clampDateToToday(fromDate))}T00:00:00.000Z`
            const toIso = `${toApiDate(clampDateToToday(toDate))}T23:59:59.999Z`
            const idemKey = usedAuto
                ? `moex|auto|robot=${selectedRobot?.id ?? 0}|${moexBoard}|${moexInterval}|${fromIso}|${toIso}|${[...tickers].sort().join(',')}`.slice(0, 220)
                : `moex|${[...tickers].sort().join(',')}|${moexBoard}|${moexInterval}|${fromIso}|${toIso}`.slice(0, 220)
            const res = await marketService.createCandleLoadJob(
                {
                    tickers,
                    board: moexBoard.trim().toUpperCase() || 'TQBR',
                    interval: moexInterval,
                    from: fromIso,
                    to: toIso,
                },
                { idempotencyKey: idemKey },
            )
            setMoexJobId(res.job_id)
            setMoexJobStatus(null)
            toast.show(
                usedAuto
                    ? `Задача загрузки создана (автоподбор: ${tickers.length} тикеров по DMS)`
                    : 'Задача загрузки в общий кеш создана',
                'success',
                4000,
            )
        } catch (e: unknown) {
            const m = fmtErr(e)
            setMoexJobError(m)
            toast.show(m, 'error', 5000)
        } finally {
            setMoexJobSubmitting(false)
        }
    }, [
        moexTickers,
        moexBoard,
        moexInterval,
        fromDate,
        toDate,
        toast,
        resolveMoexTickersForJob,
        selectedRobot?.id,
    ])

    const clearMoexCandleJob = useCallback(() => {
        setMoexJobId(null)
        setMoexJobStatus(null)
        setMoexJobError(null)
        setMoexPreview(null)
    }, [])

    const previewMoexCache = useCallback(async () => {
        setMoexPreviewLoading(true)
        setMoexPreview(null)
        setMoexJobError(null)
        try {
            if (!fromDate || !toDate) {
                toast.show('Выберите период тестирования', 'error', 4000)
                return
            }
            let tickers: string[] = []
            let usedAuto = false
            try {
                const r = await resolveMoexTickersForJob()
                tickers = r.tickers
                usedAuto = r.auto
            } catch (e: unknown) {
                if (fmtErr(e).includes('NO_ROBOT') || (e as Error)?.message === 'NO_ROBOT') {
                    toast.show('Для автоподбора выберите робота в блоке «Параметры робота»', 'error', 5000)
                    return
                }
                throw e
            }
            if (!tickers.length) {
                toast.show(
                    usedAuto
                        ? 'Автоподбор не вернул бумаг — скорректируйте фильтры или введите тикеры вручную.'
                        : 'Укажите тикеры или очистите поле для автоподбора по роботу',
                    'error',
                    5000,
                )
                return
            }
            const fromIso = `${toApiDate(clampDateToToday(fromDate))}T00:00:00.000Z`
            const toIso = `${toApiDate(clampDateToToday(toDate))}T23:59:59.999Z`
            const data = await marketService.getSharedCandles({
                tickers,
                board: moexBoard.trim().toUpperCase() || 'TQBR',
                interval: moexInterval,
                from: fromIso,
                to: toIso,
            })
            setMoexPreview({ bars: data.candles.length, gaps: data.gaps?.length ?? 0 })
            if (data.gaps?.length) {
                toast.show(
                    `В кеше есть пробелы (${data.gaps.length}) — запустите загрузку MOEX${usedAuto ? ` (${tickers.length} тикеров, автоподбор)` : ''}`,
                    'error',
                    5000,
                )
            } else {
                toast.show(
                    `В кеше ${data.candles.length} баров${usedAuto ? ` (${tickers.length} тикеров, автоподбор)` : ''}`,
                    'success',
                    4000,
                )
            }
        } catch (e: unknown) {
            const m = fmtErr(e)
            setMoexJobError(m)
            toast.show(m, 'error', 5000)
        } finally {
            setMoexPreviewLoading(false)
        }
    }, [moexTickers, moexBoard, moexInterval, fromDate, toDate, toast, resolveMoexTickersForJob])

    const alignMoexIntervalToSignal = useCallback(() => {
        setMoexInterval(suggestedMoexForSignal)
    }, [suggestedMoexForSignal])

    return {
        moexTickers,
        setMoexTickers,
        moexBoard,
        setMoexBoard,
        moexInterval,
        setMoexInterval,
        moexJobId,
        moexJobStatus,
        moexJobError,
        moexJobSubmitting,
        moexPreviewLoading,
        moexPreview,
        suggestedMoexForSignal,
        moexIntervalMismatch,
        alignMoexIntervalToSignal,
        startMoexCandleLoad,
        previewMoexCache,
        clearMoexCandleJob,
    }
}

export type MoexCandleJobState = ReturnType<typeof useMoexCandleJobState>
