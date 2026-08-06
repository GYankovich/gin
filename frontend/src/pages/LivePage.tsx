import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Select } from '@/components/ui/Select'
import { Toggle } from '@/components/ui/Toggle'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Skeleton } from '@/components/ui/Skeleton'
import { Chart, type IChartApi, type Time } from '@/components/ui/Chart'
import { CandlestickSeries, LineSeries } from 'lightweight-charts'
import cyberHero from '@/assets/dashboard/cyber-hero.png'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAuthStore } from '@/stores/authStore'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'
import { useToast } from '@/components/ui/Toast'
import { formatDmsUniverseReason } from '@/utils/dmsUniverseDisplay'
import { universeModeLabel, CRYPTO_UNIVERSE_MODE_OPTIONS, normalizeCryptoUniverseMode } from '@/utils/universeMode'
import { deriveMarketProfile, resolveBybitEnvironment } from '@/modules/robots/config/resolveProfile'
import { buildTickerByFigiMap, instrumentTitle, tickerFromFigi } from '@/utils/instrumentLabel'
import { buildLiveWsUrl } from '@/utils/liveWsUrl'
import {
    buildPipelineFromSnapshot,
    buildSignalSummaryRows,
    upsertPipelineFromOrder,
    upsertPipelineFromSignal,
    type TradePipelineItem,
} from '@/pages/live/tradePipeline'
import { buildCryptoScreeningRecommendations } from '@/modules/robots/live/cryptoScreeningRecommendations'
import {
    formatCryptoScreeningToggleLabel,
    isCryptoScreeningInProgress,
} from '@/modules/robots/live/cryptoScreeningStatus'
import { buildLiveCandidates } from '@/modules/robots/live/buildLiveCandidates'
import type { LiveCandidateRow } from '@/modules/robots/live/buildLiveCandidates'
import type { RobotCryptoScreeningStatus } from '@/types/robot'
import { analyticsService } from '@/services/analyticsService'
import type { AccountSummary } from '@/types/api'
import { PortfolioComposition } from '@/components/portfolio/PortfolioComposition'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import {
    isBybitPortfolioAccount,
    matchPortfolioAccountByBrokerId,
} from '@/utils/portfolioFormat'

///@EPIC Frontend.ITEM LiveMonitoring.TOPIC Realtime Robot Screen [1]
///@ Экран live-мониторинга: WebSocket события, статус робота, поток сигналов/ордеров,
///@ графики и управляющие действия для оперативного контроля торговли.
const SERIES_COLORS = [
    '#00ffff', '#ff00ff', '#00ffaa', '#ffaa00', '#aa00ff',
    '#ff3366', '#66ffcc', '#ff9900', '#33ccff', '#ff66cc',
]
const MAX_PRICE_POINTS = 3000
const MAX_TARGET_POINTS = 1000
const MAX_CANDLE_POINTS = 1000
/** Сколько последних событий держим в live-side-card «Лента». */
const FEED_LIMIT = 30

function isUniverseAccepted(row: { filter_result?: string }): boolean {
    const v = String(row.filter_result || '').toLowerCase()
    return v === 'accept' || v === 'accepted'
}

function isUniverseRejected(row: { filter_result?: string }): boolean {
    const v = String(row.filter_result || '').toLowerCase()
    return v === 'reject' || v === 'rejected'
}

interface LogLine {
    id: number
    level: string
    text: string
    time: string
    backendId?: number
}

interface LiveSnapshotState {
    robot_id: number
    status: number
    broker_type: string
    strategy: string
    account_id?: string | null
    active_positions: any[]
    portfolio_positions: any[]
    portfolio_summary: Record<string, any>
    portfolio_fetch_error?: string | null
    portfolio_source?: string | null
    recent_signals: any[]
    recent_orders: any[]
    open_orders?: any[]
    order_history?: any[]
    recent_logs?: any[]
    stream_health: Record<string, any>
}

/** Дата + время для live-side-card / ленты / консоли. */
function formatLiveTs(value?: string | number | Date | null): string {
    const opts: Intl.DateTimeFormatOptions = {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    }
    if (value == null || value === '') {
        return new Date().toLocaleString('ru-RU', opts)
    }
    if (value instanceof Date) {
        return Number.isNaN(value.getTime()) ? '—' : value.toLocaleString('ru-RU', opts)
    }
    if (typeof value === 'number') {
        const d = new Date(value)
        return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('ru-RU', opts)
    }
    const raw = String(value).trim()
    const d = new Date(raw)
    if (!Number.isNaN(d.getTime())) {
        return d.toLocaleString('ru-RU', opts)
    }
    // Уже отформатированная строка (например только время) — оставляем как есть.
    return raw || '—'
}

function pushLogLine(
    prev: LogLine[],
    line: Omit<LogLine, 'id'> & { id?: number },
    nextId: () => number,
): LogLine[] {
    if (line.backendId != null && prev.some(l => l.backendId === line.backendId)) {
        return prev
    }
    return [{ id: line.id ?? nextId(), level: line.level, text: line.text, time: line.time, backendId: line.backendId }, ...prev].slice(0, 500)
}

function extractApiErrorMessage(error: unknown, fallback: string): string {
    const e = error as { response?: { data?: { detail?: unknown; message?: unknown } }; message?: unknown }
    const detail = e?.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail.trim()
    const message = e?.response?.data?.message
    if (typeof message === 'string' && message.trim()) return message.trim()
    if (typeof e?.message === 'string' && e.message.trim()) return e.message.trim()
    return fallback
}

export default function LivePage() {
    const toast = useToast()
    const [searchParams, setSearchParams] = useSearchParams()
    const [robots, setRobots] = useState<Robot[]>([])
    const [selectedRobot, setSelectedRobot] = useState<number | null>(() => {
        const raw = searchParams.get('robotId')
        const parsed = raw ? Number(raw) : null
        return parsed && Number.isFinite(parsed) && parsed > 0 ? parsed : null
    })
    const selectedRobotRef = useRef<number | null>(null)
    selectedRobotRef.current = selectedRobot
    const robotsRef = useRef(robots)
    robotsRef.current = robots
    const [selectedBroker, setSelectedBroker] = useState<string>('tinvest')
    const [loading, setLoading] = useState(true)
    const [softLoading, setSoftLoading] = useState(false)
    /** True from robot select until first full snapshot + universe settle. */
    const [robotHydrating, setRobotHydrating] = useState(false)
    const [pipeline, setPipeline] = useState<TradePipelineItem[]>([])
    const [prices, setPrices] = useState<Record<string, { price: number; change: number; time: string }>>({})
    const [signalMeta, setSignalMeta] = useState<Record<string, { targetPrice?: number; indicators?: Record<string, number>; signalType?: string }>>({})
    const [lastPriceEventAt, setLastPriceEventAt] = useState<number | null>(null)
    const [lastHeartbeatAt, setLastHeartbeatAt] = useState<number | null>(null)
    const [nowTs, setNowTs] = useState<number>(() => Date.now())
    const [logs, setLogs] = useState<LogLine[]>([])
    const [snapshot, setSnapshot] = useState<LiveSnapshotState | null>(null)
    const [dmsSubscriptions, setDmsSubscriptions] = useState<any[]>([])
    const [dmsSnapshots, setDmsSnapshots] = useState<any[]>([])
    const [dailyUniverse, setDailyUniverse] = useState<any[]>([])
    const [logFilter, setLogFilter] = useState('ALL')
    const [chartMode, setChartMode] = useState<'candles' | 'lines' | 'both'>('both')
    const [portfolioOpen, setPortfolioOpen] = useState(true)
    const [compositionPositions, setCompositionPositions] = useState<any[]>([])
    const [compositionLoading, setCompositionLoading] = useState(false)
    const [portfolioAccounts, setPortfolioAccounts] = useState<AccountSummary[]>([])
    const [matchedPortfolioAccount, setMatchedPortfolioAccount] = useState<AccountSummary | null>(null)
    const [ordersOpen, setOrdersOpen] = useState(true)
    const [universeOpen, setUniverseOpen] = useState(false)
    const [candidatesOpen, setCandidatesOpen] = useState(true)
    const [cryptoScreeningStatus, setCryptoScreeningStatus] = useState<RobotCryptoScreeningStatus | null>(null)
    const [cryptoScreeningStarting, setCryptoScreeningStarting] = useState(false)
    const [logsOpen, setLogsOpen] = useState(true)
    const [ordersActiveOnly, setOrdersActiveOnly] = useState(true)
    const [ordersSyncing, setOrdersSyncing] = useState(false)
    const [liveIssue, setLiveIssue] = useState<string | null>(null)
    const logIdRef = useRef(0)

    const [manualFigi, setManualFigi] = useState('')
    const [manualSide, setManualSide] = useState<'BUY' | 'SELL'>('BUY')
    const [manualPrice, setManualPrice] = useState('')
    const [manualSizeMode, setManualSizeMode] = useState<'qty' | 'notional'>('notional')
    const [manualSize, setManualSize] = useState('')
    const [manualReduceOnly, setManualReduceOnly] = useState(false)
    const [manualSubmitting, setManualSubmitting] = useState(false)

    const [availableFigis, setAvailableFigis] = useState<string[]>([])
    const [selectedFigis, setSelectedFigis] = useState<string[]>([])
    const selectedFigisRef = useRef<string[]>([])
    const pricesRef = useRef<Record<string, { price: number; change: number; time: string }>>({})
    selectedFigisRef.current = selectedFigis
    pricesRef.current = prices
    const chartRef = useRef<IChartApi | null>(null)
    const seriesMapRef = useRef<Map<string, any>>(new Map())
    const candleSeriesMapRef = useRef<Map<string, any>>(new Map())
    const targetSeriesMapRef = useRef<Map<string, any>>(new Map())
    const priceHistoryRef = useRef<Map<string, { time: Time; value: number }[]>>(new Map())
    const candleHistoryRef = useRef<Map<string, { time: Time; open: number; high: number; low: number; close: number }[]>>(new Map())
    const candleCurrentRef = useRef<Map<string, { time: Time; open: number; high: number; low: number; close: number }>>(new Map())
    const targetHistoryRef = useRef<Map<string, { time: Time; value: number }[]>>(new Map())
    const initialPricesRef = useRef<Map<string, number>>(new Map())
    const lastPriceTsByFigiRef = useRef<Map<string, number>>(new Map())
    const tickerByFigiRef = useRef<Map<string, string>>(new Map())
    const figiColorIndexRef = useRef<Map<string, number>>(new Map())

    const token = useAuthStore(s => s.token)

    const loadRobots = useCallback(async () => {
        try {
            const r = await robotService.list()
            const trading = r.items.filter(rb => rb.type === 2)
            setRobots(trading)
            const currentId = selectedRobotRef.current
            if (currentId && !trading.some(x => x.id === currentId)) {
                setSelectedRobot(null)
            }
        } catch {
            toast.show('Не удалось загрузить список роботов', 'error')
        } finally {
            setLoading(false)
        }
    }, [toast])

    useEffect(() => {
        void loadRobots()
        // Mount-only: list is for the robot picker; avoid re-fetch on selection/toast identity churn.
        // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional
    }, [])

    useEffect(() => {
        if (!selectedRobot) return
        const robot = robots.find(r => r.id === selectedRobot)
        const broker = String((robot?.config as Record<string, unknown> | undefined)?.broker_type || 'tinvest')
        setSelectedBroker(broker)
        // Do not seed figi bar from config allowed_symbols (full universe).
    }, [selectedRobot, robots])

    const clearRobotScopedState = useCallback(() => {
        setSnapshot(null)
        setDmsSubscriptions([])
        setDmsSnapshots([])
        setDailyUniverse([])
        setCryptoScreeningStatus(null)
        setLiveIssue(null)
    }, [])

    const loadDms = useCallback(async (options?: { processQueue?: boolean }) => {
        if (!selectedRobot) {
            setDmsSubscriptions([])
            setDmsSnapshots([])
            setDailyUniverse([])
            return
        }
        const robot = robots.find(r => r.id === selectedRobot)
        const isCrypto = robot ? deriveMarketProfile(robot) === 'crypto' : false
        const tradeDate = new Date().toISOString().slice(0, 10)
        try {
            if (isCrypto) {
                const universe = await robotService.listUniverseDaily(selectedRobot, { trade_date: tradeDate })
                setDmsSubscriptions([])
                setDmsSnapshots([])
                setDailyUniverse(Array.isArray(universe?.items) ? universe.items : [])
                return
            }
            if (options?.processQueue) {
                try {
                    await robotService.processDmsQueue()
                } catch {
                    // очередь может быть пустой — всё равно обновляем списки
                }
            }
            const [subs, snaps, universe] = await Promise.all([
                robotService.listDmsSubscriptions(),
                robotService.listDmsSnapshots('TQBR'),
                robotService.listDailyUniverse({ robot_id: selectedRobot, trade_date: tradeDate }),
            ])
            setDmsSubscriptions(Array.isArray(subs) ? subs : [])
            setDmsSnapshots(Array.isArray(snaps) ? snaps : [])
            setDailyUniverse(Array.isArray(universe?.items) ? universe.items : [])
        } catch {
            setDmsSubscriptions([])
            setDmsSnapshots([])
            setDailyUniverse([])
        }
    }, [selectedRobot, robots])

    useEffect(() => {
        // Initial empty-state clear when list callback identity changes without a robot.
        if (!selectedRobot) {
            setDmsSubscriptions([])
            setDmsSnapshots([])
            setDailyUniverse([])
        }
    }, [selectedRobot])

    useEffect(() => {
        const timer = window.setInterval(() => setNowTs(Date.now()), 1000)
        return () => window.clearInterval(timer)
    }, [])

    const resetChartState = useCallback(() => {
        setPipeline([])
        setPrices({})
        setSignalMeta({})
        setLastPriceEventAt(null)
        setLastHeartbeatAt(null)
        setLogs([])
        setSelectedBroker('tinvest')
        setAvailableFigis([])
        setSelectedFigis([])
        priceHistoryRef.current.clear()
        candleHistoryRef.current.clear()
        candleCurrentRef.current.clear()
        initialPricesRef.current.clear()
        seriesMapRef.current.clear()
        candleSeriesMapRef.current.clear()
        targetSeriesMapRef.current.clear()
        targetHistoryRef.current.clear()
        lastPriceTsByFigiRef.current.clear()
        // chartRef is owned by <Chart onReady> — do not null here (avoids missed ticks mid-remount)
    }, [])

    const wsUrl = useMemo(() => {
        if (!selectedRobot || !token) return ''
        return buildLiveWsUrl(selectedRobot, token)
    }, [selectedRobot, token])

    const normalizeLineHistory = useCallback((points: { time: Time; value: number }[]) => {
        const byTime = new Map<number, number>()
        for (const p of points) {
            const t = Number(p.time)
            if (!Number.isFinite(t)) continue
            byTime.set(t, p.value)
        }
        return Array.from(byTime.entries())
            .sort((a, b) => a[0] - b[0])
            .map(([time, value]) => ({ time: time as Time, value }))
    }, [])

    const normalizeCandleHistory = useCallback((candles: { time: Time; open: number; high: number; low: number; close: number }[]) => {
        const byTime = new Map<number, { time: Time; open: number; high: number; low: number; close: number }>()
        for (const c of candles) {
            const t = Number(c.time)
            if (!Number.isFinite(t)) continue
            const existing = byTime.get(t)
            if (!existing) {
                byTime.set(t, { ...c, time: t as Time })
            } else {
                existing.high = Math.max(existing.high, c.high)
                existing.low = Math.min(existing.low, c.low)
                existing.close = c.close
            }
        }
        return Array.from(byTime.values()).sort((a, b) => Number(a.time) - Number(b.time))
    }, [])

    const ensurePriceSeries = useCallback((figi: string) => {
        if (!chartRef.current) return null
        const existing = seriesMapRef.current.get(figi)
        if (existing) return existing
        const idx = figiColorIndexRef.current.get(figi) ?? seriesMapRef.current.size
        const color = SERIES_COLORS[idx % SERIES_COLORS.length]
        const series = chartRef.current.addSeries(LineSeries, {
            color,
            lineWidth: 2,
            title: tickerFromFigi(figi, tickerByFigiRef.current),
            priceScaleId: 'right',
        })
        const hist = normalizeLineHistory(priceHistoryRef.current.get(figi) ?? [])
        if (hist.length > 0) {
            series.setData(hist)
        }
        series.applyOptions({ visible: chartMode === 'lines' || chartMode === 'both' })
        seriesMapRef.current.set(figi, series)
        return series
    }, [chartMode, normalizeLineHistory])

    const ensureTargetSeries = useCallback((figi: string) => {
        if (!chartRef.current) return null
        if (targetSeriesMapRef.current.has(figi)) return targetSeriesMapRef.current.get(figi)!
        const idx = figiColorIndexRef.current.get(figi) ?? targetSeriesMapRef.current.size
        const base = SERIES_COLORS[idx % SERIES_COLORS.length]
        const targetSeries = chartRef.current.addSeries(LineSeries, {
            color: base,
            lineWidth: 1,
            lineStyle: 2,
            title: `${tickerFromFigi(figi, tickerByFigiRef.current)} target`,
            priceScaleId: 'right',
        })
        const hist = normalizeLineHistory(targetHistoryRef.current.get(figi) ?? [])
        if (hist.length > 0) {
            targetSeries.setData(hist)
        }
        targetSeries.applyOptions({ visible: chartMode === 'lines' || chartMode === 'both' })
        targetSeriesMapRef.current.set(figi, targetSeries)
        return targetSeries
    }, [chartMode, normalizeLineHistory])

    const ensureCandleSeries = useCallback((figi: string) => {
        if (!chartRef.current) return null
        if (candleSeriesMapRef.current.has(figi)) return candleSeriesMapRef.current.get(figi)!
        const candleSeries = chartRef.current.addSeries(CandlestickSeries, {
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
            priceScaleId: 'right',
        })
        const hist = normalizeCandleHistory(candleHistoryRef.current.get(figi) ?? [])
        if (hist.length > 0) {
            candleSeries.setData(hist)
        }
        candleSeries.applyOptions({ visible: chartMode === 'candles' || chartMode === 'both' })
        candleSeriesMapRef.current.set(figi, candleSeries)
        return candleSeries
    }, [chartMode, normalizeCandleHistory])

    const appendPriceToChart = useCallback((figi: string, price: number, eventTime?: string) => {
        const now = Math.floor(Date.now() / 1000) as Time
        const parsed = eventTime ? Math.floor(new Date(eventTime).getTime() / 1000) : Number(now)
        const candidateTs = Number.isFinite(parsed) ? parsed : Number(now)
        const prevTs = lastPriceTsByFigiRef.current.get(figi) ?? 0
        const normalizedTs = candidateTs <= prevTs ? prevTs + 1 : candidateTs
        lastPriceTsByFigiRef.current.set(figi, normalizedTs)
        const pointTime = normalizedTs as Time
        const point = { time: pointTime, value: price }

        if (!priceHistoryRef.current.has(figi)) {
            priceHistoryRef.current.set(figi, [])
        }
        const hist = priceHistoryRef.current.get(figi)!
        hist.push(point)
        if (hist.length > MAX_PRICE_POINTS) {
            hist.splice(0, hist.length - MAX_PRICE_POINTS)
        }

        const candleTime = (Math.floor(Number(pointTime) / 60) * 60) as Time
        const current = candleCurrentRef.current.get(figi)
        if (!current || Number(current.time) !== Number(candleTime)) {
            const nextCandle = { time: candleTime, open: price, high: price, low: price, close: price }
            candleCurrentRef.current.set(figi, nextCandle)
            if (!candleHistoryRef.current.has(figi)) {
                candleHistoryRef.current.set(figi, [])
            }
            const candleHist = candleHistoryRef.current.get(figi)!
            candleHist.push(nextCandle)
            if (candleHist.length > MAX_CANDLE_POINTS) {
                candleHist.splice(0, candleHist.length - MAX_CANDLE_POINTS)
            }
        } else {
            current.high = Math.max(current.high, price)
            current.low = Math.min(current.low, price)
            current.close = price
        }

        if (!initialPricesRef.current.has(figi)) {
            initialPricesRef.current.set(figi, price)
        }

        if (!chartRef.current) return
        if (!selectedFigisRef.current.includes(figi)) return

        try {
            const series = ensurePriceSeries(figi)
            series?.update(point)
            const candleSeries = ensureCandleSeries(figi)
            const candle = candleCurrentRef.current.get(figi)
            if (candle) candleSeries?.update(candle)
        } catch {
            // Chart may have been disposed between tick and update (StrictMode / remount).
        }
    }, [ensurePriceSeries, ensureCandleSeries])

    const appendTargetToChart = useCallback((figi: string, targetPrice: number) => {
        const now = Math.floor(Date.now() / 1000) as Time
        const point = { time: now, value: targetPrice }
        if (!targetHistoryRef.current.has(figi)) {
            targetHistoryRef.current.set(figi, [])
        }
        const hist = targetHistoryRef.current.get(figi)!
        hist.push(point)
        if (hist.length > MAX_TARGET_POINTS) {
            hist.splice(0, hist.length - MAX_TARGET_POINTS)
        }
        if (!chartRef.current) return
        if (!selectedFigisRef.current.includes(figi)) return
        const series = ensureTargetSeries(figi)
        series?.update(point)
    }, [ensureTargetSeries])

    const seedHistoryFromLatestPrice = useCallback((figi: string) => {
        const row = pricesRef.current[figi]
        const price = row?.price
        if (price == null || !Number.isFinite(price)) return
        if ((priceHistoryRef.current.get(figi) ?? []).length > 0) return
        const now = Math.floor(Date.now() / 1000) as Time
        priceHistoryRef.current.set(figi, [{ time: now, value: price }])
        lastPriceTsByFigiRef.current.set(figi, Number(now))
        const candleTime = (Math.floor(Number(now) / 60) * 60) as Time
        const candle = { time: candleTime, open: price, high: price, low: price, close: price }
        candleCurrentRef.current.set(figi, candle)
        candleHistoryRef.current.set(figi, [candle])
    }, [])

    const syncChartToSelection = useCallback(() => {
        if (!chartRef.current) return
        const chart = chartRef.current
        const selected = new Set(selectedFigisRef.current)

        for (const [figi, series] of [...seriesMapRef.current.entries()]) {
            if (selected.has(figi)) continue
            try {
                chart.removeSeries(series)
            } catch {
                // series may already be detached
            }
            seriesMapRef.current.delete(figi)
        }
        for (const [figi, series] of [...candleSeriesMapRef.current.entries()]) {
            if (selected.has(figi)) continue
            try {
                chart.removeSeries(series)
            } catch {
                // ignore
            }
            candleSeriesMapRef.current.delete(figi)
        }
        for (const [figi, series] of [...targetSeriesMapRef.current.entries()]) {
            if (selected.has(figi)) continue
            try {
                chart.removeSeries(series)
            } catch {
                // ignore
            }
            targetSeriesMapRef.current.delete(figi)
        }

        for (const figi of selectedFigisRef.current) {
            seedHistoryFromLatestPrice(figi)
            const lineSeries = ensurePriceSeries(figi)
            const lineHist = normalizeLineHistory(priceHistoryRef.current.get(figi) ?? [])
            if (lineSeries) {
                lineSeries.setData(lineHist)
            }
            const candleSeries = ensureCandleSeries(figi)
            const candleHist = normalizeCandleHistory(candleHistoryRef.current.get(figi) ?? [])
            if (candleSeries) {
                candleSeries.setData(candleHist)
            }
            const targetSeries = ensureTargetSeries(figi)
            const targetHist = normalizeLineHistory(targetHistoryRef.current.get(figi) ?? [])
            if (targetSeries) {
                targetSeries.setData(targetHist)
            }
        }

        for (const [figi, series] of seriesMapRef.current.entries()) {
            series.applyOptions({
                visible: selected.has(figi) && (chartMode === 'lines' || chartMode === 'both'),
            })
        }
        for (const [figi, series] of candleSeriesMapRef.current.entries()) {
            series.applyOptions({
                visible: selected.has(figi) && (chartMode === 'candles' || chartMode === 'both'),
            })
        }
        for (const [figi, series] of targetSeriesMapRef.current.entries()) {
            series.applyOptions({
                visible: selected.has(figi) && (chartMode === 'lines' || chartMode === 'both'),
            })
        }

        if (selectedFigisRef.current.length > 0) {
            try {
                chart.timeScale().fitContent()
            } catch {
                // no data yet
            }
            try {
                chart.timeScale().scrollToRealTime()
            } catch {
                // no realtime anchor yet
            }
        }
    }, [
        chartMode,
        ensurePriceSeries,
        ensureCandleSeries,
        ensureTargetSeries,
        normalizeLineHistory,
        normalizeCandleHistory,
        seedHistoryFromLatestPrice,
    ])

    const syncChartToSelectionRef = useRef(syncChartToSelection)
    syncChartToSelectionRef.current = syncChartToSelection

    const onWsMessage = useCallback((data: any) => {
        if (!data || !data.type) return

        const tickerOf = (figi: string) => tickerFromFigi(figi, tickerByFigiRef.current)

        if (data.type === 'init') {
            const instruments: string[] = (data.instruments ?? data.figis ?? [])
                .map((x: unknown) => String(x || '').trim().toUpperCase())
                .filter(Boolean)
            setAvailableFigis(instruments)
            // Keep prior selection across reconnects; default = all (toggle «Все символы» on).
            const keep = selectedFigisRef.current.filter(f => instruments.includes(f))
            const next = keep.length > 0 ? keep : instruments
            setSelectedFigis(next)
            selectedFigisRef.current = next
            setSelectedBroker(data.broker_type || 'tinvest')
            setSoftLoading(false)
            setLiveIssue(null)
            queueMicrotask(() => syncChartToSelectionRef.current())
            return
        }

        if (data.type === 'ping') {
            setLastHeartbeatAt(Date.now())
            return
        }

        if (data.type === 'price') {
            const figi = String(data.figi || '').trim().toUpperCase()
            if (!figi) return
            const rawPrice = typeof data.price === 'number' ? data.price : Number(data.price)
            if (!Number.isFinite(rawPrice)) return
            const price = rawPrice
            const ts = formatLiveTs(data.time)

            setPrices(prev => {
                const prevPrice = prev[figi]?.price ?? price
                const change = prevPrice > 0 ? ((price - prevPrice) / prevPrice) * 100 : 0
                return { ...prev, [figi]: { price, change, time: ts } }
            })
            setLastPriceEventAt(Date.now())

            appendPriceToChart(figi, price, data.time)
        }

        if (data.type === 'signal') {
            const side = (data.signal_type || data.side || '').toLowerCase()
            const tk = data.figi ? tickerFromFigi(String(data.figi), tickerByFigiRef.current) : '—'
            const ts = formatLiveTs(data.time)
            if (data.figi) {
                setSignalMeta(prev => ({
                    ...prev,
                    [data.figi]: {
                        targetPrice: typeof data.target_price === 'number' ? data.target_price : prev[data.figi]?.targetPrice,
                        indicators: data.indicators || prev[data.figi]?.indicators || {},
                        signalType: side || prev[data.figi]?.signalType,
                    },
                }))
                if (typeof data.target_price === 'number') {
                    appendTargetToChart(data.figi, data.target_price)
                }
            }
            const signalText = `${tk} @ ${data.price}${data.target_price ? ` в†’ target ${data.target_price}` : ''}`
            setPipeline(prev => upsertPipelineFromSignal(prev, data, tickerOf, formatLiveTs, FEED_LIMIT))
            setLogs(prev => pushLogLine(prev, {
                level: 'INFO',
                text: `[SIGNAL] ${(side || 'info').toUpperCase()} ${signalText}`,
                time: ts,
            }, () => ++logIdRef.current))
        }

        if (data.type === 'order') {
            const tk = data.figi ? tickerFromFigi(String(data.figi), tickerByFigiRef.current) : '—'
            const ts = formatLiveTs(data.time)
            const orderText = `${data.side?.toUpperCase()} ${tk} x${data.quantity} — ${data.status}`
            setPipeline(prev => upsertPipelineFromOrder(prev, data, tickerOf, formatLiveTs, FEED_LIMIT, false))
            setLogs(prev => pushLogLine(prev, {
                level: 'INFO',
                text: `[ORDER] ${orderText}`,
                time: ts,
            }, () => ++logIdRef.current))
        }

        if (data.type === 'orders_snapshot') {
            setSnapshot(prev => {
                if (!prev) {
                    return {
                        robot_id: Number(data.robot_id) || 0,
                        status: 0,
                        broker_type: String(data.broker_type || 'tinvest'),
                        strategy: '',
                        active_positions: [],
                        portfolio_positions: [],
                        portfolio_summary: {},
                        recent_signals: [],
                        recent_orders: [],
                        open_orders: Array.isArray(data.open_orders) ? data.open_orders : [],
                        order_history: Array.isArray(data.order_history) ? data.order_history : [],
                        stream_health: {},
                    }
                }
                return {
                    ...prev,
                    open_orders: Array.isArray(data.open_orders) ? data.open_orders : prev.open_orders,
                    order_history: Array.isArray(data.order_history) ? data.order_history : prev.order_history,
                }
            })
        }

        if (data.type === 'skipped') {
            const tk = data.figi ? tickerFromFigi(String(data.figi), tickerByFigiRef.current) : '—'
            const reason = String(data.reason || data.status || 'UNKNOWN_REASON')
            const ts = formatLiveTs(data.time)
            setPipeline(prev => upsertPipelineFromOrder(prev, data, tickerOf, formatLiveTs, FEED_LIMIT, true))
            setLogs(prev => pushLogLine(prev, {
                level: 'INFO',
                text: `[SIGNAL_SKIPPED] ${tk} — ${reason}`,
                time: ts,
            }, () => ++logIdRef.current))
        }

        if (data.type === 'log') {
            const ts = formatLiveTs(data.time)
            const msg = String(data.message ?? JSON.stringify(data))
            const backendId = data.id != null && Number.isFinite(Number(data.id)) ? Number(data.id) : undefined
            setLogs(prev => pushLogLine(prev, {
                level: data.level ?? 'INFO',
                text: msg,
                time: ts,
                backendId,
            }, () => ++logIdRef.current))
        }

        if (data.type === 'error') {
            const message = String(data.message || 'Unknown error')
            setSoftLoading(false)
            setLiveIssue(message)
            setLogs(prev => pushLogLine(prev, {
                level: 'ERROR',
                text: message,
                time: formatLiveTs(null),
            }, () => ++logIdRef.current))
        }
    }, [appendPriceToChart, appendTargetToChart])

    const { connected, send } = useWebSocket({
        url: wsUrl,
        onMessage: onWsMessage,
        enabled: !!selectedRobot && !!token && !!wsUrl,
    })

    useEffect(() => {
        if (connected) {
            setLiveIssue(null)
            setSoftLoading(false)
        }
    }, [connected])

    useEffect(() => {
        if (!selectedRobot || !softLoading) return
        const timer = window.setTimeout(() => {
            setSoftLoading(false)
            setLiveIssue(prev => prev || (
                !token
                    ? 'Нужна авторизация в UI для Live-мониторинга. Торговый WS робота при этом работает в фоне по расписанию (heavy worker).'
                    : connected
                        ? 'Мониторинг WS подключён, но init не получен — проверьте allowed_symbols / universe робота'
                        : `Мониторинг WS не подключился (${wsUrl || '—'}). Нужны: run.py ws (:8001) и перезапуск Vite (proxy /ws). Открой UI как http://localhost:5173 — WS должен идти на тот же host, не напрямую на :8001.`
            ))
        }, 12000)
        return () => window.clearTimeout(timer)
    }, [selectedRobot, softLoading, connected, token, wsUrl])

    const handleRobotChange = (val: string) => {
        const num = val ? Number(val) : null
        const nextId = num && Number.isFinite(num) && num > 0 ? num : null
        resetChartState()
        setSoftLoading(!!nextId)
        setLiveIssue(null)
        clearRobotScopedState()
        setRobotHydrating(!!nextId)
        setSelectedRobot(nextId)
        setSearchParams(
            (prev) => {
                const next = new URLSearchParams(prev)
                if (nextId != null) next.set('robotId', String(nextId))
                else next.delete('robotId')
                return next
            },
            { replace: true },
        )
    }

    // Browser back/forward or shared link → restore robot from URL
    useEffect(() => {
        const raw = searchParams.get('robotId')
        const fromUrl = raw ? Number(raw) : null
        const nextId = fromUrl && Number.isFinite(fromUrl) && fromUrl > 0 ? fromUrl : null
        if (nextId === selectedRobotRef.current) return
        resetChartState()
        setSoftLoading(!!nextId)
        setLiveIssue(null)
        clearRobotScopedState()
        setRobotHydrating(!!nextId)
        setSelectedRobot(nextId)
    }, [searchParams, clearRobotScopedState, resetChartState])

    const mergeRecentLogsFromSnapshot = useCallback((snap: LiveSnapshotState | null | undefined) => {
        const seededLogs = (snap?.recent_logs || []).slice(-150).map((x: any) => ({
            id: ++logIdRef.current,
            level: String(x.level || 'INFO'),
            text: String(x.message || ''),
            time: formatLiveTs(x.time || x.created_at),
            backendId: x.id != null && Number.isFinite(Number(x.id)) ? Number(x.id) : undefined,
        }))
        if (!seededLogs.length) return
        setLogs(prev => {
            const known = new Set(prev.map(l => l.backendId).filter((id): id is number => id != null))
            const fresh = seededLogs.filter(l => l.backendId == null || !known.has(l.backendId))
            if (!fresh.length) return prev
            // recent_logs уже oldest→newest; в консоли newest сверху
            return [...[...fresh].reverse(), ...prev].slice(0, 500)
        })
    }, [])

    const applyFeedFromSnapshot = useCallback((snap: LiveSnapshotState | null | undefined) => {
        if (!snap) return
        setPipeline(buildPipelineFromSnapshot(
            snap.recent_signals,
            snap.recent_orders,
            (figi) => tickerFromFigi(figi, tickerByFigiRef.current),
            formatLiveTs,
            FEED_LIMIT,
        ))
    }, [])

    const loadSnapshot = useCallback(async (opts?: {
        mergeLogs?: boolean
        mergeFeed?: boolean
        mode?: 'ops' | 'full'
    }) => {
        if (!selectedRobot) {
            setSnapshot(null)
            return null
        }
        const mode = opts?.mode ?? 'full'
        try {
            const snap = await robotService.getLiveSnapshot(selectedRobot, { mode })
            setSnapshot(prev => {
                const next = snap as LiveSnapshotState
                if (mode === 'ops' && prev) {
                    return {
                        ...next,
                        portfolio_positions: prev.portfolio_positions?.length
                            ? prev.portfolio_positions
                            : next.portfolio_positions,
                        portfolio_summary: Object.keys(prev.portfolio_summary || {}).length
                            ? prev.portfolio_summary
                            : next.portfolio_summary,
                        portfolio_fetch_error: prev.portfolio_fetch_error ?? next.portfolio_fetch_error,
                        portfolio_source: prev.portfolio_source ?? next.portfolio_source,
                        account_id: next.account_id || prev.account_id,
                    }
                }
                if (
                    (!next.portfolio_positions || next.portfolio_positions.length === 0)
                    && prev?.portfolio_positions?.length
                    && next.portfolio_fetch_error
                ) {
                    return { ...next, portfolio_positions: prev.portfolio_positions }
                }
                return next
            })
            setSelectedBroker(snap.broker_type || 'tinvest')
            setLiveIssue(null)
            const typed = snap as LiveSnapshotState
            if (opts?.mergeLogs) {
                mergeRecentLogsFromSnapshot(typed)
            }
            if (opts?.mergeFeed) {
                applyFeedFromSnapshot(typed)
            }
            return typed
        } catch (error) {
            setLiveIssue(extractApiErrorMessage(error, 'Не удалось загрузить snapshot робота'))
            return null
        }
    }, [selectedRobot, mergeRecentLogsFromSnapshot, applyFeedFromSnapshot])

    const refreshFullLive = useCallback(async (options?: { processQueue?: boolean }) => {
        await loadSnapshot({ mode: 'full', mergeLogs: true, mergeFeed: true })
        await loadDms(
            options?.processQueue
                ? { processQueue: true }
                : undefined,
        )
    }, [loadSnapshot, loadDms])

    useEffect(() => {
        if (!selectedRobot) {
            setRobotHydrating(false)
            return
        }
        let cancelled = false
        setRobotHydrating(true)
        const robot = robotsRef.current.find(r => r.id === selectedRobot)
        const isCrypto = robot ? deriveMarketProfile(robot) === 'crypto' : false
        ;(async () => {
            try {
                await Promise.all([
                    loadSnapshot({ mode: 'full', mergeLogs: true, mergeFeed: true }),
                    loadDms(isCrypto ? undefined : { processQueue: true }),
                ])
            } catch {
                // hydrate best-effort; skeleton clears in finally
            } finally {
                if (!cancelled) setRobotHydrating(false)
            }
        })()
        return () => {
            cancelled = true
        }
    }, [selectedRobot, loadSnapshot, loadDms])

    useEffect(() => {
        if (!selectedRobot) return
        const timer = window.setInterval(() => {
            void loadSnapshot({ mode: 'ops', mergeLogs: true, mergeFeed: true })
        }, 15000)
        return () => window.clearInterval(timer)
    }, [selectedRobot, loadSnapshot])

    useEffect(() => {
        if (!selectedRobot) return
        const timer = window.setInterval(() => {
            void refreshFullLive({ processQueue: true })
        }, 5 * 60 * 1000)
        return () => window.clearInterval(timer)
    }, [selectedRobot, refreshFullLive])

    const handleSyncOrders = async () => {
        if (!selectedRobot || ordersSyncing) return
        setOrdersSyncing(true)
        try {
            const res = await robotService.syncLiveOrders(selectedRobot)
            toast.show(
                `Заявки: +${res.imported} импорт · ${res.upserted} upsert · `
                + `${res.cancelled} закрыто · hist ${res.history_updated}`
                + ((res.healed_open || res.healed_closed)
                    ? ` · seed ${res.healed_open}/${res.healed_closed}`
                    : ''),
                'success',
            )
            await loadSnapshot({ mode: 'full', mergeLogs: true, mergeFeed: true })
        } catch {
            toast.show('Не удалось синхронизировать заявки с брокером', 'error')
        } finally {
            setOrdersSyncing(false)
        }
    }

    const handleManualOrder = async () => {
        if (!selectedRobot || manualSubmitting) return
        const figi = String(manualFigi || '').trim().toUpperCase()
        const price = Number(String(manualPrice).replace(',', '.'))
        const size = Number(String(manualSize).replace(',', '.'))
        if (!figi) {
            toast.show('Выберите символ', 'error')
            return
        }
        if (!Number.isFinite(price) || price <= 0) {
            toast.show('Укажите лимит-цену > 0', 'error')
            return
        }
        if (!Number.isFinite(size) || size <= 0) {
            toast.show(manualSizeMode === 'qty' ? 'Укажите количество > 0' : 'Укажите сумму USDT > 0', 'error')
            return
        }
        const approxQty = manualSizeMode === 'notional' ? size / price : size
        const confirmText = manualSizeMode === 'notional'
            ? `Сумма ${size} USDT → ≈${approxQty.toPrecision(6)} ${figi} @ ${price}`
            : `Qty ${size} ${figi} @ ${price} (в‰€${(size * price).toFixed(4)} USDT)`
        const ok = window.confirm(
            `Выставить лимит ${manualSide} ${figi}?\n${confirmText}`
            + `${manualReduceOnly ? '\nreduce-only' : ''}\n\nЗаявка уйдёт напрямую брокеру.`,
        )
        if (!ok) return
        setManualSubmitting(true)
        try {
            // Explicit fields only — never send both quantity and notional.
            const payload: {
                robotId: number
                figi: string
                side: 'BUY' | 'SELL'
                price: number
                quantity?: number
                notional?: number
                reduceOnly?: boolean
            } = {
                robotId: selectedRobot,
                figi,
                side: manualSide,
                price,
                reduceOnly: manualReduceOnly,
            }
            if (manualSizeMode === 'notional') {
                payload.notional = size
            } else {
                payload.quantity = size
            }
            const result = await robotService.placeManualOrder(payload)
            const placed = result.quantity != null ? ` qty=${result.quantity}` : ''
            const notion = result.notional != null ? ` sum=${result.notional}USDT` : ''
            toast.show(
                `Заявка ${result.side} ${result.figi}:${notion}${placed} — ${result.order_id || result.status}`,
                'success',
            )
            setManualSize('')
            void loadSnapshot({ mode: 'ops', mergeLogs: true, mergeFeed: true })
        } catch (err: unknown) {
            let msg = ''
            if (err && typeof err === 'object' && 'response' in err) {
                const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
                if (typeof detail === 'string') msg = detail
                else if (Array.isArray(detail) && detail[0]?.msg) msg = String(detail[0].msg)
            }
            if (!msg && err instanceof Error) msg = err.message
            toast.show(msg || 'Не удалось выставить заявку', 'error')
        } finally {
            setManualSubmitting(false)
        }
    }

    const toggleFigi = (figi: string) => {
        setSelectedFigis(prev => {
            const next = prev.includes(figi)
                ? prev.filter(f => f !== figi)
                : [...prev, figi]
            selectedFigisRef.current = next
            if (connected) {
                send({ action: prev.includes(figi) ? 'unsubscribe' : 'subscribe', figi })
            }
            queueMicrotask(() => syncChartToSelectionRef.current())
            return next
        })
    }

    const applyBulkFigiSelection = useCallback((next: string[]) => {
        setSelectedFigis(prev => {
            if (connected) {
                const nextSet = new Set(next)
                const toSubscribe = next.filter(f => !prev.includes(f))
                const toUnsubscribe = prev.filter(f => !nextSet.has(f))
                if (toSubscribe.length > 0) {
                    send(toSubscribe.length === 1
                        ? { action: 'subscribe', figi: toSubscribe[0] }
                        : { action: 'subscribe', figis: toSubscribe })
                }
                if (toUnsubscribe.length > 0) {
                    send(toUnsubscribe.length === 1
                        ? { action: 'unsubscribe', figi: toUnsubscribe[0] }
                        : { action: 'unsubscribe', figis: toUnsubscribe })
                }
            }
            selectedFigisRef.current = next
            queueMicrotask(() => syncChartToSelectionRef.current())
            return next
        })
    }, [connected, send])

    const resetChartSeriesMaps = useCallback(() => {
        seriesMapRef.current.clear()
        candleSeriesMapRef.current.clear()
        targetSeriesMapRef.current.clear()
    }, [])

    const onChartReady = useCallback((chart: IChartApi | null) => {
        if (!chart) {
            chartRef.current = null
            resetChartSeriesMaps()
            return
        }
        chartRef.current = chart
        resetChartSeriesMaps()
        chart.timeScale().applyOptions({
            timeVisible: true,
            secondsVisible: true,
            rightOffset: 5,
        })
        syncChartToSelection()
    }, [resetChartSeriesMaps, syncChartToSelection])

    useEffect(() => {
        syncChartToSelection()
    }, [selectedFigis, chartMode, syncChartToSelection])

    const portfolioRows = useMemo(() => {
        const moneyNum = (v: unknown): number | null => {
            if (v == null) return null
            if (typeof v === 'number' && Number.isFinite(v)) return v
            if (typeof v === 'object' && v !== null && 'decimal' in v) {
                const d = Number((v as { decimal?: unknown }).decimal)
                return Number.isFinite(d) ? d : null
            }
            const n = Number(v)
            return Number.isFinite(n) ? n : null
        }

        const snapRows = (snapshot?.portfolio_positions || []).filter(
            (row) => Math.abs(Number((row as { quantity?: number }).quantity) || 0) > 1e-9,
        )
        const source = snapRows.length > 0 ? snapRows : compositionPositions.filter(
            (row) => Math.abs(Number((row as { quantity?: number }).quantity) || 0) > 1e-9,
        )

        return source.map((row) => {
            const figi = String((row as { figi?: string }).figi || '').trim().toUpperCase()
            const qty = Number((row as { quantity?: number }).quantity ?? 0)
            const avg =
                moneyNum((row as { avg_price?: unknown }).avg_price)
                ?? moneyNum((row as { average_position_price?: unknown }).average_position_price)
                ?? 0
            const live = figi ? prices[figi] : undefined
            const current =
                (live && Number.isFinite(live.price) ? live.price : null)
                ?? moneyNum((row as { current_price?: unknown }).current_price)
                ?? 0
            const expected =
                live && Number.isFinite(avg) && avg > 0
                    ? (current - avg) * qty
                    : moneyNum((row as { expected_yield?: unknown }).expected_yield)
            const total =
                moneyNum((row as { total_value?: unknown }).total_value)
                ?? (current * Math.abs(qty))
            return {
                figi,
                ticker: String((row as { ticker?: string }).ticker || figi),
                ticker_name: String((row as { ticker_name?: string }).ticker_name || '').trim() || null,
                instrument_type: String((row as { instrument_type?: string }).instrument_type || ''),
                type_name: String(
                    (row as { type_name?: string }).type_name
                    || (row as { instrument_type?: string }).instrument_type
                    || '',
                ) || null,
                quantity: qty,
                avg_price: avg,
                current_price: current,
                expected_yield: expected,
                total_value: total,
            }
        })
    }, [compositionPositions, prices, snapshot?.portfolio_positions])

    const loadCompositionPositions = useCallback(async (accountPk: number | null) => {
        if (!accountPk) {
            setCompositionPositions([])
            return
        }
        setCompositionLoading(true)
        try {
            const pos = await analyticsService.getAccountPositions(accountPk)
            setCompositionPositions(Array.isArray(pos) ? pos : [])
        } catch {
            setCompositionPositions([])
        } finally {
            setCompositionLoading(false)
        }
    }, [])

    useEffect(() => {
        if (!selectedRobot) {
            setPortfolioAccounts([])
            return
        }
        let cancelled = false
        ;(async () => {
            try {
                const summary = await analyticsService.getSummary(true)
                if (!cancelled) setPortfolioAccounts(summary.accounts ?? [])
            } catch {
                if (!cancelled) setPortfolioAccounts([])
            }
        })()
        return () => {
            cancelled = true
        }
    }, [selectedRobot])

    const openOrderRows = useMemo(() => snapshot?.open_orders || [], [snapshot?.open_orders])
    const filledOrderRows = useMemo(() => snapshot?.order_history || [], [snapshot?.order_history])
    const selectedRobotEntity = useMemo(
        () => robots.find(r => r.id === selectedRobot) ?? null,
        [robots, selectedRobot],
    )

    useEffect(() => {
        if (!selectedRobot) {
            setMatchedPortfolioAccount(null)
            setCompositionPositions([])
            return
        }
        const brokerId =
            snapshot?.account_id
            || String((selectedRobotEntity?.config as { account_id?: string } | undefined)?.account_id || '')
            || null
        const matched = matchPortfolioAccountByBrokerId(portfolioAccounts, brokerId)
        setMatchedPortfolioAccount(matched)
        void loadCompositionPositions(matched?.id ?? null)
    }, [
        selectedRobot,
        snapshot?.account_id,
        selectedRobotEntity?.config,
        portfolioAccounts,
        loadCompositionPositions,
    ])

    const isCryptoRobot = useMemo(
        () => (selectedRobotEntity ? deriveMarketProfile(selectedRobotEntity) === 'crypto' : false),
        [selectedRobotEntity],
    )
    const universeModeText = useMemo(() => {
        if (!selectedRobotEntity?.config) return null
        const cfg = selectedRobotEntity.config as Record<string, unknown>
        if (isCryptoRobot) {
            const cu = (cfg.crypto_universe ?? {}) as Record<string, unknown>
            const mode = normalizeCryptoUniverseMode(cu.universe_mode ?? cfg.universe_mode)
            return CRYPTO_UNIVERSE_MODE_OPTIONS.find(o => o.value === mode)?.label ?? mode
        }
        return cfg.universe_mode ? universeModeLabel(String(cfg.universe_mode)) : null
    }, [selectedRobotEntity, isCryptoRobot])
    const bybitEnvironment = useMemo(
        () =>
            resolveBybitEnvironment(
                selectedRobotEntity?.config as { broker_type?: string; bybit?: { testnet?: boolean } } | null,
            ),
        [selectedRobotEntity?.config],
    )

    const tickerByFigi = useMemo(() => {
        const cfg = (selectedRobotEntity?.config ?? {}) as Record<string, unknown>
        const im = (cfg.instrument_map ?? {}) as Record<string, unknown>
        const fromPortfolio = new Map<string, string>()
        for (const p of [...(snapshot?.portfolio_positions || []), ...compositionPositions]) {
            const fg = String((p as { figi?: string }).figi || '').trim().toUpperCase()
            const tk = String((p as { ticker?: string }).ticker || '').trim().toUpperCase()
            if (fg && tk) fromPortfolio.set(fg, tk)
        }
        const fromFigiByTicker = new Map<string, string>()
        const fbt = im.figi_by_ticker
        if (fbt && typeof fbt === 'object' && !Array.isArray(fbt)) {
            for (const [ticker, figi] of Object.entries(fbt as Record<string, unknown>)) {
                const fg = String(figi || '').trim().toUpperCase()
                const tk = String(ticker || '').trim().toUpperCase()
                if (fg && tk) fromFigiByTicker.set(fg, tk)
            }
        }
        return buildTickerByFigiMap(
            (im.ticker_by_figi as Record<string, unknown> | undefined) ?? undefined,
            fromFigiByTicker,
            fromPortfolio,
        )
    }, [selectedRobotEntity, snapshot?.portfolio_positions, compositionPositions])
    tickerByFigiRef.current = tickerByFigi

    const wsInstrumentUnion = useMemo(() => {
        const ids: string[] = []
        const seen = new Set<string>()
        const add = (value: unknown) => {
            const s = String(value || '').trim().toUpperCase()
            if (!s || seen.has(s)) return
            seen.add(s)
            ids.push(s)
        }
        for (const p of [...(snapshot?.portfolio_positions || []), ...compositionPositions]) {
            const row = p as { figi?: string; ticker?: string }
            add(row.figi || row.ticker)
        }
        const cfg = (selectedRobotEntity?.config ?? {}) as Record<string, unknown>
        const im = (cfg.instrument_map ?? {}) as Record<string, unknown>
        const figiByTicker =
            im.figi_by_ticker && typeof im.figi_by_ticker === 'object' && !Array.isArray(im.figi_by_ticker)
                ? (im.figi_by_ticker as Record<string, unknown>)
                : {}
        for (const row of dailyUniverse) {
            if (!isUniverseAccepted(row)) continue
            const item = row as { figi?: string; ticker?: string }
            const figi = String(item.figi || '').trim().toUpperCase()
            const ticker = String(item.ticker || '').trim().toUpperCase()
            if (figi) {
                add(figi)
                continue
            }
            if (!ticker) continue
            const mapped = String(
                figiByTicker[ticker] || figiByTicker[ticker.toLowerCase()] || '',
            ).trim().toUpperCase()
            add(mapped || ticker)
        }
        return ids
    }, [
        snapshot?.portfolio_positions,
        compositionPositions,
        dailyUniverse,
        selectedRobotEntity,
    ])

    useEffect(() => {
        if (wsInstrumentUnion.length === 0) return
        setAvailableFigis(wsInstrumentUnion)
        const unionSet = new Set(wsInstrumentUnion)
        const prev = selectedFigisRef.current
        const keep = prev.filter((f) => unionSet.has(f))
        const next = keep.length > 0 ? keep : wsInstrumentUnion
        const same =
            next.length === prev.length
            && next.every((f, i) => f === prev[i])
        if (same) return
        applyBulkFigiSelection(next)
    }, [wsInstrumentUnion, applyBulkFigiSelection])

    const instrLabel = (figi: string) => tickerFromFigi(figi, tickerByFigi)

    const sortedAvailableFigis = useMemo(
        () => [...availableFigis].sort((a, b) => {
            const cmp = instrLabel(a).localeCompare(instrLabel(b), 'ru', { sensitivity: 'base' })
            return cmp !== 0 ? cmp : a.localeCompare(b)
        }),
        [availableFigis, tickerByFigi],
    )

    useEffect(() => {
        if (sortedAvailableFigis.length === 0) {
            setManualFigi('')
            return
        }
        setManualFigi(prev => (
            prev && sortedAvailableFigis.includes(prev)
                ? prev
                : (selectedFigis.find(f => sortedAvailableFigis.includes(f)) || sortedAvailableFigis[0])
        ))
    }, [sortedAvailableFigis, selectedFigis])

    useEffect(() => {
        if (!manualFigi) return
        const livePx = prices[manualFigi]?.price
        if (livePx != null && Number.isFinite(livePx) && livePx > 0) {
            setManualPrice(prev => (prev.trim() ? prev : String(livePx)))
        }
    }, [manualFigi, prices])

    const figiColorIndex = useMemo(() => {
        const m = new Map<string, number>()
        sortedAvailableFigis.forEach((figi, idx) => m.set(figi, idx))
        return m
    }, [sortedAvailableFigis])
    figiColorIndexRef.current = figiColorIndex

    const selectAllFigis = useCallback(() => {
        applyBulkFigiSelection([...sortedAvailableFigis])
    }, [applyBulkFigiSelection, sortedAvailableFigis])

    const deselectAllFigis = useCallback(() => {
        applyBulkFigiSelection([])
    }, [applyBulkFigiSelection])

    const allFigisSelected = sortedAvailableFigis.length > 0
        && sortedAvailableFigis.every(f => selectedFigis.includes(f))

    const priceRows = sortedAvailableFigis.length > 0
        ? sortedAvailableFigis.map((figi) => {
        const d = prices[figi]
        return {
            figi,
            price: d?.price ?? null,
            change: d?.change ?? 0,
            time: d?.time ?? '—',
        }
    })
        : Object.keys(prices).map((figi) => {
            const d = prices[figi]
            return {
                figi,
                price: d?.price ?? null,
                change: d?.change ?? 0,
                time: d?.time ?? '—',
            }
        })
    const priceColumns: Column<any>[] = [
        {
            key: 'figi', header: 'Тикер',
            render: r => {
                const idx = figiColorIndex.get(r.figi) ?? availableFigis.indexOf(r.figi)
                const color = SERIES_COLORS[(idx >= 0 ? idx : 0) % SERIES_COLORS.length]
                return (
                    <span className="live-figi-cell" title={instrumentTitle(r.figi, tickerByFigi)}>
                        <span className="live-figi-cell__dot" style={{ background: color }} />
                        <span className="mono">{instrLabel(r.figi)}</span>
                    </span>
                )
            },
        },
        { key: 'price', header: 'Цена', align: 'right' as const, render: r => <span className="mono">{r.price == null ? '—' : r.price.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</span> },
        {
            key: 'change', header: 'Изм. %', align: 'right' as const,
            render: r => <span className={r.price == null ? '' : (r.change >= 0 ? 'color-up' : 'color-down')}>{r.price == null ? '—' : `${r.change >= 0 ? '+' : ''}${r.change?.toFixed(4)}%`}</span>,
        },
        { key: 'time', header: 'Дата / время', render: r => <span className="mono">{r.time}</span> },
    ]

    const signalSummaryRows = useMemo(() => buildSignalSummaryRows(pipeline), [pipeline])

    const brokerOrderColumns: Column<any>[] = [
        {
            key: 'figi',
            header: 'Символ',
            render: r => instrLabel(String(r.figi || r.symbol || '')),
        },
        {
            key: 'source',
            header: 'Источник',
            render: r => String(r.source_name || r.source || r.order_type || '—'),
        },
        {
            key: 'reason',
            header: 'Причина',
            render: r => String(r.reason_name || r.reason || '—'),
        },
        {
            key: 'side',
            header: 'Сторона',
            render: r => String(r.side_name || r.side || '—'),
        },
        {
            key: 'quantity',
            header: 'Кол-во',
            align: 'right',
            render: r => Number(r.quantity || 0).toLocaleString('ru-RU'),
        },
        {
            key: 'filled_qty',
            header: 'Исполн.',
            align: 'right',
            render: r => (r.filled_qty != null ? Number(r.filled_qty).toLocaleString('ru-RU') : '—'),
        },
        {
            key: 'price',
            header: 'Цена',
            align: 'right',
            render: r => (Number(r.price || 0) > 0 ? Number(r.price).toLocaleString('ru-RU') : '—'),
        },
        {
            key: 'status',
            header: 'Статус',
            render: r => String(r.status_name || r.status || '—'),
        },
        {
            key: 'order_id',
            header: 'Order ID',
            render: r => (
                <span className="mono" style={{ fontSize: '0.85em' }} title={String(r.order_id || '')}>
                    {r.order_id ? String(r.order_id).slice(0, 10) : '—'}
                </span>
            ),
        },
        {
            key: 'created_at',
            header: 'Время',
            render: r => (r.created_at ? formatLiveTs(r.created_at) : '—'),
        },
    ]

    const candidateColumns: Column<LiveCandidateRow>[] = [
        {
            key: 'ticker',
            header: 'Символ',
            sortable: true,
            render: r => (
                <span className="mono" title={instrumentTitle(r.figi, tickerByFigi)}>
                    {r.ticker || instrLabel(r.figi)}
                    {r.hasOpenOrder ? (
                        <span className="live-candidate-order-dot" title="Есть открытая заявка"> · ord</span>
                    ) : null}
                </span>
            ),
        },
        {
            key: 'sourceLabel',
            header: 'Откуда',
            sortable: true,
            render: r => <span style={{ opacity: 0.85 }}>{r.sourceLabel}</span>,
        },
        {
            key: '_sortTs',
            header: 'Дата сигнала',
            sortable: true,
            render: r => <span className="mono">{r.signalAtLabel}</span>,
        },
        {
            key: 'lastSignalLabel',
            header: 'Последний сигнал',
            sortable: true,
            render: r => (
                <span
                    className={
                        r.lastKind === 'filled' || r.lastKind === 'open' || r.lastKind === 'partial'
                            ? 'color-up'
                            : r.lastKind === 'failed' || r.lastKind === 'rejected' || r.lastKind === 'error'
                                ? 'color-down'
                                : ''
                    }
                    style={r.lastKind === 'none' ? { opacity: 0.65 } : undefined}
                    title={r.lastReason || undefined}
                >
                    {r.lastSignalLabel}
                </span>
            ),
        },
        {
            key: 'lastReason',
            header: 'Причина / описание',
            sortable: true,
            render: r => (
                <span
                    title={r.lastReason}
                    style={{
                        display: 'inline-block',
                        maxWidth: 360,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        opacity: 0.85,
                    }}
                >
                    {r.lastReason || '—'}
                </span>
            ),
        },
    ]

    const filteredLogs = logFilter === 'ALL' ? logs : logs.filter(l => l.level === logFilter)
    const secondsSinceLastPrice = lastPriceEventAt ? Math.floor((nowTs - lastPriceEventAt) / 1000) : null
    const streamState: 'offline' | 'fresh' | 'stale' = !connected
        ? 'offline'
        : (secondsSinceLastPrice == null || secondsSinceLastPrice <= 5 ? 'fresh' : 'stale')
    const streamVariant = streamState === 'offline' ? 'neutral' : (streamState === 'fresh' ? 'up' : 'down')
    const lastPriceText = lastPriceEventAt
        ? formatLiveTs(lastPriceEventAt)
        : '—'
    const lastHeartbeatText = lastHeartbeatAt
        ? formatLiveTs(lastHeartbeatAt)
        : '—'
    const tradingSessionActive = Boolean(snapshot?.stream_health?.trading_session_active)
    const tradingSessionStatus = String(snapshot?.stream_health?.trading_session_status || '')
    const robotLiveHint = tradingSessionActive
        ? (tradingSessionStatus === 'queued' ? 'QUEUE' : 'LIVE')
        : (snapshot?.status === 1 ? 'ON' : 'OFF')

    const downloadLog = () => {
        const text = [...logs].reverse().map(l => `[${l.time}] [${l.level}] ${l.text}`).join('\n')
        const blob = new Blob([text], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = 'live-log.txt'; a.click()
        URL.revokeObjectURL(url)
    }

    const clearLogs = () => setLogs([])

    const robotSnapshotRows = useMemo(() => {
        if (!selectedRobot) return []
        return dmsSubscriptions
            .filter((sub: { robot_id?: number }) => Number(sub.robot_id) === selectedRobot)
            .map((sub: { id: number; snapshot_id?: number | null; status?: string; requested_at?: string; board?: string }) => {
                const snap = dmsSnapshots.find((s: { id?: number }) => s.id === sub.snapshot_id)
                return {
                    id: sub.id,
                    snapshot_id: sub.snapshot_id,
                    board: sub.board || snap?.board,
                    sub_status: sub.status,
                    snap_status: snap?.status,
                    requested_at: sub.requested_at,
                    snapshot_time: snap?.snapshot_time,
                    securities_count: snap?.securities_count ?? 0,
                }
            })
    }, [dmsSubscriptions, dmsSnapshots, selectedRobot])

    const universeAccepted = useMemo(
        () => dailyUniverse.filter(isUniverseAccepted),
        [dailyUniverse],
    )
    const universeRejected = useMemo(
        () => dailyUniverse.filter(isUniverseRejected),
        [dailyUniverse],
    )
    const candidateRows = useMemo(
        () =>
            buildLiveCandidates({
                acceptedUniverse: universeAccepted,
                portfolio: portfolioRows,
                signalSummary: signalSummaryRows,
                recentSignals: snapshot?.recent_signals,
                openOrders: openOrderRows,
            }),
        [universeAccepted, portfolioRows, signalSummaryRows, snapshot?.recent_signals, openOrderRows],
    )

    const positionCount = selectedRobot
        ? portfolioRows.filter(
            (p: { quantity?: number }) => Math.abs(Number(p.quantity) || 0) > 1e-9,
        ).length
        : 0

    const showRobotSkeleton = Boolean(selectedRobot && robotHydrating)

    const cryptoScreeningTips = useMemo(() => {
        if (!isCryptoRobot) return []
        const cfg = (selectedRobotEntity?.config ?? {}) as Record<string, unknown>
        const cu = (cfg.crypto_universe && typeof cfg.crypto_universe === 'object')
            ? (cfg.crypto_universe as Record<string, unknown>)
            : {}
        return buildCryptoScreeningRecommendations(dailyUniverse, cu)
    }, [isCryptoRobot, selectedRobotEntity, dailyUniverse])

    const cryptoScreeningToggleLabel = useMemo(
        () => (isCryptoRobot ? formatCryptoScreeningToggleLabel(cryptoScreeningStatus) : null),
        [isCryptoRobot, cryptoScreeningStatus],
    )
    const cryptoScreeningBusy = isCryptoScreeningInProgress(cryptoScreeningStatus) || cryptoScreeningStarting

    const cryptoScreeningWasBusyRef = useRef(false)

    const refreshCryptoScreeningStatus = useCallback(async () => {
        if (!selectedRobot) {
            setCryptoScreeningStatus(null)
            return null
        }
        try {
            const st = await robotService.getCryptoScreeningStatus(selectedRobot)
            setCryptoScreeningStatus(st)
            return st
        } catch {
            return null
        }
    }, [selectedRobot])

    useEffect(() => {
        if (!selectedRobot || !isCryptoRobot) {
            setCryptoScreeningStatus(null)
            cryptoScreeningWasBusyRef.current = false
            return
        }
        let cancelled = false
        const tick = async () => {
            if (cancelled) return
            const st = await refreshCryptoScreeningStatus()
            if (cancelled || !st) return
            const busy = isCryptoScreeningInProgress(st)
            if (cryptoScreeningWasBusyRef.current && !busy) {
                if (st.status === 'failed') {
                    toast.show(st.error || st.message || 'Crypto-screening завершился с ошибкой', 'error')
                } else {
                    toast.show(st.message || 'Crypto-screening завершён', 'success')
                }
                await loadDms()
            }
            cryptoScreeningWasBusyRef.current = busy
        }
        void tick()
        const inProgress = isCryptoScreeningInProgress(cryptoScreeningStatus)
        const timer = window.setInterval(() => { void tick() }, inProgress ? 4000 : 20000)
        return () => {
            cancelled = true
            window.clearInterval(timer)
        }
    }, [
        selectedRobot,
        isCryptoRobot,
        refreshCryptoScreeningStatus,
        cryptoScreeningStatus?.status,
        loadDms,
        toast,
    ])

    if (loading) {
        return (
            <div className="page" data-page="live">
                <LiveHero />
                <Skeleton height="400px" />
            </div>
        )
    }

    const dailyUniverseColumns: Column<any>[] = [
        { key: 'ticker', header: 'Тикер', sortable: true },
        { key: 'source', header: 'Источник', sortable: true },
        { key: 'filter_result', header: 'Статус', sortable: true },
        {
            key: 'reject_reason',
            header: 'Причина',
            sortable: true,
            render: r => formatDmsUniverseReason(r),
        },
        {
            key: 'created_at',
            header: 'Дата / время',
            sortable: true,
            render: r => r.created_at ? formatLiveTs(r.created_at) : '—',
        },
    ]
    const robotSnapshotColumns: Column<any>[] = [
        { key: 'snapshot_id', header: 'Снимок', render: r => r.snapshot_id ? `#${r.snapshot_id}` : '—' },
        { key: 'board', header: 'Board' },
        { key: 'sub_status', header: 'Подписка' },
        { key: 'snap_status', header: 'Снимок', render: r => r.snap_status || '—' },
        { key: 'securities_count', header: 'Бумаг', align: 'right', render: r => Number(r.securities_count || 0).toLocaleString('ru-RU') },
        { key: 'requested_at', header: 'Запрошено', render: r => r.requested_at ? new Date(r.requested_at).toLocaleString('ru-RU') : '—' },
        { key: 'snapshot_time', header: 'Время снимка', render: r => r.snapshot_time ? new Date(r.snapshot_time).toLocaleString('ru-RU') : '—' },
    ]

    const displayLogs = selectedRobot ? filteredLogs : []

    return (
        <div className="page" data-page="live">
            <LiveHero
                meta={
                    selectedRobot && snapshot ? (
                        <p className="live-page-meta dashboard-hero__sub">
                            <span className="mono">#{selectedRobot}</span>
                            {snapshot.strategy && <span>{snapshot.strategy}</span>}
                            {universeModeText && <span>{universeModeText}</span>}
                            <span>{selectedBroker}</span>
                            {bybitEnvironment && (
                                <Badge variant={bybitEnvironment === 'testnet' ? 'warn' : 'cyan'}>
                                    {bybitEnvironment === 'testnet' ? 'Testnet' : 'Mainnet'}
                                </Badge>
                            )}
                            {snapshot.account_id && <span className="mono">счёт {snapshot.account_id}</span>}
                            <span>поз. {positionCount}</span>
                            <span>сигн. {(snapshot.recent_signals || []).length}</span>
                        </p>
                    ) : undefined
                }
            />
            {softLoading && <div className="soft-loading-bar" />}

            <div className="live-toolbar">
                <div className="live-toolbar__primary">
                    <Select
                        className="live-toolbar__robot"
                        size="sm"
                        options={[{ value: '', label: 'Робот…' }, ...robots.map(r => ({ value: String(r.id), label: r.name }))]}
                        value={selectedRobot != null ? String(selectedRobot) : ''}
                        onChange={handleRobotChange}
                        placeholder="Робот"
                    />
                    <span title="Фоновая торговая сессия (Stage2/ByBit WS). Не зависит от логина в UI.">
                        <Badge variant={tradingSessionActive ? 'up' : (snapshot?.status === 1 ? 'warn' : 'neutral')}>
                            Робот {robotLiveHint}
                        </Badge>
                    </span>
                    <span title="Мониторинг UI → /ws/live (:8001). Нужна авторизация в браузере.">
                        <Badge variant={connected ? 'up' : 'neutral'}>
                            <span className={`status-dot status-dot--${connected ? 'active' : 'inactive'}`} />
                            {connected ? 'Monitor' : 'Monitor —'}
                        </Badge>
                    </span>
                    <Badge variant={streamVariant}>{streamState === 'fresh' ? 'OK' : streamState === 'stale' ? 'LAG' : 'OFF'}</Badge>
                    <span className="live-toolbar__meta mono">
                        {lastPriceText} · ping {lastHeartbeatText}
                    </span>
                </div>
            </div>

            {robots.length === 0 && (
                <Card className="live-empty-card">
                    <div className="event-feed__empty">Нет торговых роботов (тип 2)</div>
                </Card>
            )}

            {!selectedRobot && (
                <Card className="live-compact-grid live-compact-grid--empty">
                    <div className="event-feed__empty">Выберите робота для графика и цен</div>
                </Card>
            )}

            {selectedRobot && showRobotSkeleton && (
                <div className="live-boot-skeleton" aria-busy="true" aria-label="Загрузка данных робота">
                    <Skeleton height="56px" borderRadius="10px" />
                    <div className="live-compact-grid">
                        <Skeleton height="280px" borderRadius="12px" />
                        <Skeleton height="280px" borderRadius="12px" />
                    </div>
                    <Skeleton height="140px" borderRadius="12px" />
                    <Skeleton height="120px" borderRadius="12px" count={3} />
                </div>
            )}

            {selectedRobot && !showRobotSkeleton && (
                <>
                <div className="live-manual-order" data-testid="live-manual-order">
                    <span className="live-manual-order__label">Ручная заявка</span>
                    <Select
                        className="live-manual-order__symbol"
                        size="sm"
                        options={[
                            { value: '', label: 'Символ…' },
                            ...sortedAvailableFigis.map(f => ({
                                value: f,
                                label: instrLabel(f),
                            })),
                        ]}
                        value={manualFigi}
                        onChange={(v) => {
                            setManualFigi(v)
                            setManualPrice('')
                        }}
                        placeholder="Символ"
                    />
                    <div className="ios-segment ios-segment--sm">
                        {(['BUY', 'SELL'] as const).map(side => (
                            <button
                                key={side}
                                type="button"
                                className={`ios-segment__btn ${manualSide === side ? 'ios-segment__btn--active' : ''}`}
                                onClick={() => setManualSide(side)}
                            >
                                {side}
                            </button>
                        ))}
                    </div>
                    <input
                        className="form-input cyber-input live-manual-order__input"
                        type="text"
                        inputMode="decimal"
                        placeholder="Лимит-цена"
                        value={manualPrice}
                        onChange={(e) => setManualPrice(e.target.value)}
                        aria-label="Лимит-цена"
                    />
                    <div className="ios-segment ios-segment--sm">
                        <button
                            type="button"
                            className={`ios-segment__btn ${manualSizeMode === 'notional' ? 'ios-segment__btn--active' : ''}`}
                            onClick={() => setManualSizeMode('notional')}
                        >
                            USDT
                        </button>
                        <button
                            type="button"
                            className={`ios-segment__btn ${manualSizeMode === 'qty' ? 'ios-segment__btn--active' : ''}`}
                            onClick={() => setManualSizeMode('qty')}
                        >
                            Qty
                        </button>
                    </div>
                    <input
                        className="form-input cyber-input live-manual-order__input"
                        type="text"
                        inputMode="decimal"
                        placeholder={manualSizeMode === 'qty' ? 'Кол-во монет' : 'Сумма USDT'}
                        value={manualSize}
                        onChange={(e) => setManualSize(e.target.value)}
                        aria-label={manualSizeMode === 'qty' ? 'Количество монет' : 'Сумма USDT'}
                    />
                    <label className="live-manual-order__reduce">
                        <input
                            type="checkbox"
                            checked={manualReduceOnly}
                            onChange={(e) => setManualReduceOnly(e.target.checked)}
                        />
                        reduce-only
                    </label>
                    <Button
                        variant="primary"
                        size="sm"
                        onClick={() => void handleManualOrder()}
                        disabled={!selectedRobot || manualSubmitting || !manualFigi}
                    >
                        {manualSubmitting ? '…' : 'Выставить'}
                    </Button>
                </div>

            {liveIssue && (
                <Card className="live-empty-card">
                    <div className="event-feed__empty">
                        {liveIssue.startsWith('HALT')
                            ? liveIssue
                            : `Не удалось отобразить live-данные: ${liveIssue}`}
                    </div>
                </Card>
            )}

            {sortedAvailableFigis.length > 1 && (
                <div className="live-figi-bar-wrap">
                    <div className="live-figi-bar__head">
                        <span className="live-figi-bar__meta">
                            Выбрано {selectedFigis.length} / {sortedAvailableFigis.length}
                        </span>
                        <div className="live-figi-bar__actions">
                            <Toggle
                                checked={allFigisSelected}
                                onChange={(on) => {
                                    if (on) selectAllFigis()
                                    else deselectAllFigis()
                                }}
                                label={allFigisSelected ? 'Все символы' : 'Выбрать все'}
                                title="Вкл — все символы на графике; выкл — снять выделение"
                                aria-label="Выбрать все символы"
                            />
                        </div>
                    </div>
                    <div className="live-figi-bar">
                    {sortedAvailableFigis.map((figi) => {
                        const idx = figiColorIndex.get(figi) ?? 0
                        const color = SERIES_COLORS[idx % SERIES_COLORS.length]
                        const active = selectedFigis.includes(figi)
                        const label = instrLabel(figi)
                        return (
                            <button
                                key={figi}
                                type="button"
                                className={`tag ${active ? 'tag--active' : ''}`}
                                style={{
                                    borderColor: color,
                                    opacity: active ? 1 : 0.45,
                                    cursor: 'pointer',
                                }}
                                title={instrumentTitle(figi, tickerByFigi)}
                                onClick={() => toggleFigi(figi)}
                            >
                                <span
                                    style={{
                                        display: 'inline-block',
                                        width: 8,
                                        height: 8,
                                        borderRadius: '50%',
                                        background: color,
                                        marginRight: 6,
                                    }}
                                />
                                {label}
                            </button>
                        )
                    })}
                    </div>
                </div>
            )}

            <div className="live-compact-grid">
                    <Card className="live-chart-card">
                        <div className="live-chart-card__toolbar">
                            <div className="ios-segment ios-segment--sm">
                                {(['candles', 'lines', 'both'] as const).map(mode => (
                                    <button
                                        key={mode}
                                        type="button"
                                        className={`ios-segment__btn ${chartMode === mode ? 'ios-segment__btn--active' : ''}`}
                                        onClick={() => setChartMode(mode)}
                                    >
                                        {mode === 'candles' ? 'Свечи' : mode === 'lines' ? 'Линии' : 'Оба'}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <Chart height={280} onReady={onChartReady} key={selectedRobot ?? 'empty'} />
                    </Card>

                    <Card className="live-side-card">
                        <h4 className="card__section-title">Цены ({priceRows.length})</h4>
                        <div className="live-side-panel">
                            <DataTable
                                columns={priceColumns}
                                data={priceRows}
                                keyField="figi"
                                emptyText="Ожидание…"
                                maxHeight={260}
                            />
                        </div>
                    </Card>
                </div>

            <PortfolioComposition
                positions={portfolioRows}
                loading={Boolean(selectedRobot) && compositionLoading}
                currency={matchedPortfolioAccount?.currency || (isCryptoRobot ? 'USDT' : 'RUB')}
                bybitAccount={
                    matchedPortfolioAccount
                        ? isBybitPortfolioAccount(matchedPortfolioAccount)
                        : isCryptoRobot
                }
                open={portfolioOpen}
                onOpenChange={setPortfolioOpen}
                emptyText={
                    !selectedRobot
                        ? 'Выберите робота'
                        : matchedPortfolioAccount
                            ? 'Нет позиций'
                            : 'Нет счёта портфеля для этого робота — дождитесь снимка portfolio updater'
                }
            />

            <CollapsibleSection
                className="portfolio-collapse"
                title={
                    isCryptoRobot
                        ? 'Результаты crypto-screening (сегодня)'
                        : 'Результаты отбора DMS (сегодня)'
                }
                badge={
                    <span className="portfolio-collapse__count">
                        ✓{universeAccepted.length} / ✗{universeRejected.length}
                    </span>
                }
                headerEnd={
                    cryptoScreeningToggleLabel ? (
                        <span
                            className={
                                cryptoScreeningBusy
                                    ? 'portfolio-collapse__count live-screening-status live-screening-status--busy'
                                    : 'portfolio-collapse__count live-screening-status'
                            }
                        >
                            {cryptoScreeningToggleLabel}
                        </span>
                    ) : null
                }
                open={universeOpen}
                onOpenChange={setUniverseOpen}
            >
                    <>
                        <div className="portfolio-collapse__actions">
                            {!isCryptoRobot && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={async () => {
                                        try {
                                            await robotService.subscribeDms({
                                                robot_id: selectedRobot,
                                                board: 'TQBR',
                                                ttl_minutes: 5,
                                            })
                                            toast.show('Подписка DMS создана', 'success')
                                            await refreshFullLive({ processQueue: true })
                                        } catch {
                                            toast.show('Не удалось создать подписку DMS', 'error')
                                        }
                                    }}
                                >
                                    Подписать DMS
                                </Button>
                            )}
                            {isCryptoRobot && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    disabled={!selectedRobot || cryptoScreeningBusy}
                                    onClick={async () => {
                                        if (!selectedRobot || cryptoScreeningBusy) return
                                        setCryptoScreeningStarting(true)
                                        try {
                                            const res = await robotService.runCryptoScreening(selectedRobot)
                                            const nextStatus: RobotCryptoScreeningStatus = {
                                                robot_id: selectedRobot,
                                                status: res.status || 'queued',
                                                job_id: res.job_id,
                                                started_at: res.started_at,
                                                message: res.message,
                                            }
                                            setCryptoScreeningStatus(nextStatus)
                                            cryptoScreeningWasBusyRef.current = true
                                            toast.show(
                                                res.message || 'Crypto-screening поставлен в очередь',
                                                'info',
                                            )
                                        } catch {
                                            toast.show('Не удалось запустить crypto-screening', 'error')
                                        } finally {
                                            setCryptoScreeningStarting(false)
                                        }
                                    }}
                                >
                                    {cryptoScreeningBusy ? 'Screening…' : 'Запустить crypto-screening'}
                                </Button>
                            )}
                            <Button
                                variant="ghost"
                                size="sm"
                                disabled={!selectedRobot}
                                title={
                                    isCryptoRobot
                                        ? 'Прогнать screening по текущим фильтрам crypto_universe и записать accepted в allowed_symbols конфига робота'
                                        : 'Пересчитать daily_universe за сегодня и записать accepted FIGI в allowed_figis конфига робота'
                                }
                                onClick={async () => {
                                    if (!selectedRobot) return
                                    try {
                                        const res = await robotService.syncUniverse(selectedRobot)
                                        toast.show(
                                            isCryptoRobot
                                                ? `Universe пересобран: ${res.accepted_tickers.length} символов`
                                                : `Universe пересобран: ${res.accepted_tickers.length} тикеров → ${res.allowed_figis.length} FIGI в конфиге`,
                                            'success',
                                        )
                                        await refreshFullLive(
                                            isCryptoRobot ? undefined : { processQueue: true },
                                        )
                                    } catch {
                                        toast.show('Не удалось пересобрать universe', 'error')
                                    }
                                }}
                            >
                                Пересобрать universe
                            </Button>
                            <Button
                                variant="ghost"
                                size="sm"
                                title={
                                    isCryptoRobot
                                        ? 'Только обновить UI: полный snapshot + таблица screening за сегодня (без пересчёта фильтров)'
                                        : 'Обновить UI: snapshot + строки daily_universe; для MOEX ещё process DMS queue'
                                }
                                onClick={() => void refreshFullLive(
                                    isCryptoRobot ? undefined : { processQueue: true },
                                )}
                            >
                                Обновить
                            </Button>
                        </div>
                        {isCryptoRobot && cryptoScreeningTips.length > 0 && (
                            <div className="live-dms-info live-screening-tips">
                                <strong>Рекомендации: какие поля ослабить</strong>
                                <ol>
                                    {cryptoScreeningTips.map((tip) => (
                                        <li key={tip.id}>
                                            <span className="live-screening-tips__title">{tip.title}</span>
                                            {tip.rejectCount != null && tip.rejectCount > 0 && (
                                                <span className="live-screening-tips__count">
                                                    {' '}· {tip.rejectCount} reject
                                                </span>
                                            )}
                                            <div className="live-screening-tips__change mono">{tip.change}</div>
                                            <div className="live-screening-tips__detail">
                                                Зачем: {tip.why}
                                            </div>
                                        </li>
                                    ))}
                                </ol>
                                <p className="live-screening-tips__footer">
                                    Правки в настройках робота → screening / <code>crypto_universe</code>,
                                    затем «Запустить crypto-screening» или «Пересобрать universe».
                                </p>
                            </div>
                        )}
                        <DataTable
                            columns={dailyUniverseColumns}
                            data={dailyUniverse}
                            keyField="id"
                            defaultSortKey="filter_result"
                            defaultSortDir="asc"
                            secondarySortKey="ticker"
                            emptyText={
                                isCryptoRobot
                                    ? 'Нет данных за сегодня — запустите crypto-screening или пересоберите universe'
                                    : 'Нет данных за сегодня — нажмите «Подписать DMS» и дождитесь обработки очереди'
                            }
                            maxHeight={380}
                        />
                        {!isCryptoRobot && (
                            <>
                                <h4 className="card__section-title">Подписки и снимки робота</h4>
                                <DataTable
                                    columns={robotSnapshotColumns}
                                    data={robotSnapshotRows}
                                    keyField="id"
                                    emptyText="Нет подписок DMS для этого робота"
                                    maxHeight={160}
                                />
                            </>
                        )}
                    </>
            </CollapsibleSection>

            <CollapsibleSection
                className="portfolio-collapse"
                title="Кандидаты"
                badge={
                    <span className="portfolio-collapse__count">{candidateRows.length}</span>
                }
                open={candidatesOpen}
                onOpenChange={setCandidatesOpen}
            >
                <DataTable
                    columns={candidateColumns}
                    data={candidateRows}
                    keyField="key"
                    defaultSortKey="_sortTs"
                    defaultSortDir="desc"
                    secondarySortKey="ticker"
                    emptyText={
                        selectedRobot
                            ? 'Нет accepted screening и позиций в портфеле'
                            : 'Выберите робота'
                    }
                    maxHeight={280}
                />
            </CollapsibleSection>

            <CollapsibleSection
                className="portfolio-collapse"
                title="Заявки"
                badge={
                    <span className="portfolio-collapse__count">
                        {ordersActiveOnly ? openOrderRows.length : filledOrderRows.length}
                    </span>
                }
                headerEnd={
                    <Toggle
                        checked={ordersActiveOnly}
                        onChange={setOrdersActiveOnly}
                        label="Только активные"
                        aria-label="Только активные заявки"
                    />
                }
                open={ordersOpen}
                onOpenChange={setOrdersOpen}
            >
                    <>
                        {/* <div className="portfolio-collapse__actions">
                            <Button
                                variant="ghost"
                                size="sm"
                                disabled={ordersSyncing}
                                onClick={() => void handleSyncOrders()}
                            >
                                {ordersSyncing ? 'Синхронизация…' : 'Синхронизировать'}
                            </Button>
                        </div> */}
                        <DataTable
                            columns={brokerOrderColumns}
                            data={ordersActiveOnly ? openOrderRows : filledOrderRows}
                            keyField="id"
                            emptyText={
                                ordersActiveOnly
                                    ? 'Нет активных заявок'
                                    : 'Нет исполненных / отменённых заявок'
                            }
                            maxHeight={220}
                        />
                    </>
            </CollapsibleSection>

            <CollapsibleSection
                className="portfolio-collapse"
                title="Консоль логов"
                badge={
                    <span className="portfolio-collapse__count">{displayLogs.length}</span>
                }
                open={logsOpen}
                onOpenChange={setLogsOpen}
            >
                    <>
                        <div className="portfolio-collapse__actions">
                            {['ALL', 'INFO', 'ERROR', 'DEBUG'].map(f => (
                                <button
                                    key={f}
                                    type="button"
                                    className={`tf-btn tf-btn--sm ${f === logFilter ? 'tf-btn--active' : ''}`}
                                    onClick={() => setLogFilter(f)}
                                >
                                    {f}
                                </button>
                            ))}
                            <Button variant="ghost" size="sm" onClick={clearLogs}>
                                Очистить
                            </Button>
                            <Button variant="ghost" size="sm" onClick={downloadLog}>
                                Скачать
                            </Button>
                        </div>
                        <div className="log-console log-console--compact">
                            {displayLogs.length === 0 && (
                                <div className="log-console__empty">
                                    {connected
                                        ? 'Пока нет строк — дождитесь цикла сессии или переподключите WS'
                                        : 'Нет соединения WS — логи появятся после подключения'}
                                </div>
                            )}
                            {displayLogs.map(l => (
                                <div key={l.id} className={`log-console__line--${l.level.toLowerCase()}`}>
                                    [{l.time}] [{l.level}] {l.text}
                                </div>
                            ))}
                        </div>
                    </>
            </CollapsibleSection>
                </>
            )}
        </div>
    )
}

function LiveHero({ meta }: { meta?: React.ReactNode }) {
    return (
        <header className="dashboard-hero">
            <div className="dashboard-hero__bg" style={{ backgroundImage: `url(${cyberHero})` }} aria-hidden />
            <div className="dashboard-hero__veil" aria-hidden />
            <div className="dashboard-hero__content">
                <p className="dashboard-hero__eyebrow">GIN // LIVE NODE</p>
                <h1 className="dashboard-hero__title">
                    <span className="dashboard-hero__title-glitch" data-text="LIVE">LIVE</span>
                </h1>
                {meta ?? <p className="dashboard-hero__sub">Мониторинг · сигналы · ордера</p>}
            </div>
        </header>
    )
}
