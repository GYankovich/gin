import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Select } from '@/components/ui/Select'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { EventFeed, type FeedEvent } from '@/components/ui/EventFeed'
import { Skeleton } from '@/components/ui/Skeleton'
import { Modal } from '@/components/ui/Modal'
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
    stream_health: Record<string, any>
}

function instrumentsFromRobotConfig(robot: Robot | null | undefined): string[] {
    if (!robot?.config || typeof robot.config !== 'object') return []
    const cfg = robot.config as Record<string, unknown>
    const broker = String(cfg.broker_type || 'tinvest').trim().toLowerCase()
    const strategyParams = cfg.strategy_params
    const strategyFigis = strategyParams && typeof strategyParams === 'object'
        ? (strategyParams as Record<string, unknown>).figis
        : undefined
    const raw = broker === 'bybit'
        ? (cfg.allowed_symbols ?? cfg.instruments)
        : (cfg.allowed_figis ?? cfg.figis ?? strategyFigis)
    if (!Array.isArray(raw)) return []
    return raw.map(x => String(x).trim().toUpperCase()).filter(Boolean)
}

function formatPortfolioMoney(value: unknown): string {
    if (value == null) return '—'
    if (typeof value === 'number' && Number.isFinite(value)) {
        return value.toLocaleString('ru-RU', { maximumFractionDigits: 4 })
    }
    if (typeof value === 'object' && value !== null && 'decimal' in value) {
        const d = Number((value as { decimal?: unknown }).decimal)
        if (Number.isFinite(d)) {
            return d.toLocaleString('ru-RU', { maximumFractionDigits: 4 })
        }
    }
    return '—'
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

function parseSignalResultFromLogMessage(message: string): { figi: string; status: 'SIGNAL' | 'SKIPPED'; reason: string } | null {
    const text = String(message || '').trim()
    if (!text) return null
    let m = text.match(/Сигнала нет:\s*([A-Z0-9_]+)\s*[—-]\s*(.+)$/i)
    if (m) {
        return { figi: String(m[1]).toUpperCase(), status: 'SKIPPED', reason: String(m[2]).trim() }
    }
    m = text.match(/\[SIGNAL_SKIPPED\]\s*([A-Z0-9_]+)\s*[—-]\s*(.+)$/i)
    if (m) {
        return { figi: String(m[1]).toUpperCase(), status: 'SKIPPED', reason: String(m[2]).trim() }
    }
    m = text.match(/\[REVERSION_TO_MA\]\s*([A-Z0-9_]+)\s+raw_signal=(BUY|SELL|NONE)\s+reason=(.+)$/i)
    if (m) {
        const side = String(m[2]).toUpperCase()
        return {
            figi: String(m[1]).toUpperCase(),
            status: side === 'NONE' ? 'SKIPPED' : 'SIGNAL',
            reason: String(m[3]).trim(),
        }
    }
    return null
}

export default function LivePage() {
    const toast = useToast()
    const [robots, setRobots] = useState<Robot[]>([])
    const [selectedRobot, setSelectedRobot] = useState<number | null>(null)
    const [selectedBroker, setSelectedBroker] = useState<string>('tinvest')
    const [loading, setLoading] = useState(true)
    const [softLoading, setSoftLoading] = useState(false)
    const [signals, setSignals] = useState<FeedEvent[]>([])
    const [orders, setOrders] = useState<FeedEvent[]>([])
    const [prices, setPrices] = useState<Record<string, { price: number; change: number; time: string }>>({})
    const [signalMeta, setSignalMeta] = useState<Record<string, { targetPrice?: number; indicators?: Record<string, number>; signalType?: string }>>({})
    const [signalResultByFigi, setSignalResultByFigi] = useState<Record<string, { status: 'SIGNAL' | 'SKIPPED'; reason: string; time: string }>>({})
    const [lastPriceEventAt, setLastPriceEventAt] = useState<number | null>(null)
    const [lastHeartbeatAt, setLastHeartbeatAt] = useState<number | null>(null)
    const [nowTs, setNowTs] = useState<number>(() => Date.now())
    const [logs, setLogs] = useState<LogLine[]>([])
    const [snapshot, setSnapshot] = useState<LiveSnapshotState | null>(null)
    const [dmsSubscriptions, setDmsSubscriptions] = useState<any[]>([])
    const [dmsSnapshots, setDmsSnapshots] = useState<any[]>([])
    const [dailyUniverse, setDailyUniverse] = useState<any[]>([])
    const [snapshotOpen, setSnapshotOpen] = useState(false)
    const [logFilter, setLogFilter] = useState('ALL')
    const [chartMode, setChartMode] = useState<'candles' | 'lines' | 'both'>('both')
    const [sidePanel, setSidePanel] = useState<'prices' | 'feed'>('prices')
    const [dmsOpen, setDmsOpen] = useState(true)
    const [logsOpen, setLogsOpen] = useState(true)
    const [liveIssue, setLiveIssue] = useState<string | null>(null)
    const logIdRef = useRef(0)

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
            if (selectedRobot && !trading.some(x => x.id === selectedRobot)) {
                setSelectedRobot(null)
            }
        } catch {
            toast.show('Не удалось загрузить список роботов', 'error')
        } finally {
            setLoading(false)
        }
    }, [selectedRobot, toast])

    useEffect(() => {
        loadRobots()
    }, [loadRobots])

    useEffect(() => {
        if (!selectedRobot) return
        const robot = robots.find(r => r.id === selectedRobot)
        const instruments = instrumentsFromRobotConfig(robot)
        if (instruments.length === 0) return
        setAvailableFigis(prev => (prev.length > 0 ? prev : instruments))
        setSelectedFigis(prev => (prev.length > 0 ? prev : instruments))
        const broker = String((robot?.config as Record<string, unknown> | undefined)?.broker_type || 'tinvest')
        setSelectedBroker(broker)
    }, [selectedRobot, robots])

    const clearRobotScopedState = useCallback(() => {
        setSnapshot(null)
        setDmsSubscriptions([])
        setDmsSnapshots([])
        setDailyUniverse([])
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
        void loadDms({ processQueue: true })
    }, [loadDms])

    useEffect(() => {
        if (!selectedRobot || !dmsOpen) return
        const timer = window.setInterval(() => {
            void loadDms({ processQueue: true })
        }, 20000)
        return () => window.clearInterval(timer)
    }, [selectedRobot, dmsOpen, loadDms])

    useEffect(() => {
        const timer = window.setInterval(() => setNowTs(Date.now()), 1000)
        return () => window.clearInterval(timer)
    }, [])

    const resetChartState = useCallback(() => {
        setSignals([])
        setOrders([])
        setPrices({})
        setSignalMeta({})
        setSignalResultByFigi({})
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
        chartRef.current = null
    }, [])

    const wsUrl = useMemo(() => {
        if (!selectedRobot || !token) return ''
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        return `${proto}://${window.location.host}/ws/live?robot_id=${selectedRobot}&token=${encodeURIComponent(token)}`
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

        const series = ensurePriceSeries(figi)
        series?.update(point)
        const candleSeries = ensureCandleSeries(figi)
        candleSeries?.update(candleCurrentRef.current.get(figi)!)
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

        const envelopeEventKey = (kind: 'signal' | 'order' | 'skipped', payload: any): string => {
            const eventId = payload?.event_id != null ? String(payload.event_id) : ''
            const runId = payload?.run_id != null ? String(payload.run_id) : ''
            const cycleId = payload?.cycle_id != null ? String(payload.cycle_id) : ''
            const decisionId = payload?.decision_id != null ? String(payload.decision_id) : ''
            if (eventId) {
                return `${kind}:${runId}:${cycleId}:${decisionId}:${eventId}`
            }
            // Защита от некорректного/старого payload без envelope полей.
            const figi = String(payload?.figi || '')
            const ts = String(payload?.time || Date.now())
            return `${kind}:${runId}:${cycleId}:${decisionId}:${figi}:${ts}`
        }

        if (data.type === 'init') {
            const instruments: string[] = data.instruments ?? data.figis ?? []
            setAvailableFigis(instruments)
            // Reset selection on every init to avoid stale single-figi selection
            // after reconnects or backend/ws process restarts.
            setSelectedFigis(instruments)
            selectedFigisRef.current = instruments
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
            const figi = data.figi as string
            const rawPrice = typeof data.price === 'number' ? data.price : Number(data.price)
            if (!Number.isFinite(rawPrice)) return
            const price = rawPrice
            const ts = data.time
                ? new Date(data.time).toLocaleTimeString('ru-RU')
                : new Date().toLocaleTimeString('ru-RU')

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
            const ts = data.time ?? new Date().toLocaleTimeString('ru-RU')
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
                const reason = side
                    ? `${side.toUpperCase()} @ ${data.price}${data.target_price ? ` -> target ${data.target_price}` : ''}`
                    : `@ ${data.price}${data.target_price ? ` -> target ${data.target_price}` : ''}`
                setSignalResultByFigi(prev => ({
                    ...prev,
                    [String(data.figi)]: { status: 'SIGNAL', reason, time: ts },
                }))
            }
            setSignals(prev => [{
                id: envelopeEventKey('signal', data),
                type: (side === 'buy' ? 'buy' : side === 'sell' ? 'sell' : 'info') as FeedEvent['type'],
                text: `${tk} @ ${data.price}${data.target_price ? ` → target ${data.target_price}` : ''}`,
                time: ts,
            }, ...prev].slice(0, 100))
        }

        if (data.type === 'order') {
            const tk = data.figi ? tickerFromFigi(String(data.figi), tickerByFigiRef.current) : '—'
            setOrders(prev => [{
                id: envelopeEventKey('order', data),
                type: (data.status === 'filled' ? 'buy' : 'info') as FeedEvent['type'],
                text: `${data.side?.toUpperCase()} ${tk} x${data.quantity} — ${data.status}`,
                time: data.time ?? new Date().toLocaleTimeString('ru-RU'),
            }, ...prev].slice(0, 100))
        }

        if (data.type === 'skipped') {
            const tk = data.figi ? tickerFromFigi(String(data.figi), tickerByFigiRef.current) : '—'
            const reason = String(data.reason || data.status || 'UNKNOWN_REASON')
            const ts = data.time ?? new Date().toLocaleTimeString('ru-RU')
            if (data.figi) {
                setSignalResultByFigi(prev => ({
                    ...prev,
                    [String(data.figi)]: { status: 'SKIPPED', reason, time: ts },
                }))
            }
            setOrders(prev => [{
                id: envelopeEventKey('skipped', data),
                type: 'info' as FeedEvent['type'],
                text: `SKIPPED ${tk} — ${reason}`,
                time: ts,
            }, ...prev].slice(0, 100))
            setLogs(prev => [{
                id: ++logIdRef.current,
                level: 'INFO',
                text: `[SIGNAL_SKIPPED] ${tk} — ${reason}`,
                time: ts,
            }, ...prev].slice(0, 500))
        }

        if (data.type === 'log') {
            const ts = data.time ?? new Date().toLocaleTimeString('ru-RU')
            const msg = String(data.message ?? JSON.stringify(data))
            const parsed = parseSignalResultFromLogMessage(msg)
            if (parsed) {
                setSignalResultByFigi(prev => ({
                    ...prev,
                    [parsed.figi]: { status: parsed.status, reason: parsed.reason, time: ts },
                }))
            }
            setLogs(prev => [{
                id: ++logIdRef.current,
                level: data.level ?? 'INFO',
                text: msg,
                time: ts,
            }, ...prev].slice(0, 500))
        }

        if (data.type === 'error') {
            const message = String(data.message || 'Unknown error')
            setSoftLoading(false)
            setLiveIssue(message)
            setLogs(prev => [{
                id: ++logIdRef.current,
                level: 'ERROR',
                text: message,
                time: new Date().toLocaleTimeString('ru-RU'),
            }, ...prev].slice(0, 500))
        }
    }, [appendPriceToChart, appendTargetToChart])

    const { connected, send } = useWebSocket({ url: wsUrl, onMessage: onWsMessage, enabled: !!selectedRobot })

    useEffect(() => {
        if (!selectedRobot || !softLoading) return
        const timer = window.setTimeout(() => {
            setSoftLoading(false)
            setLiveIssue(prev => prev || (
                connected
                    ? 'Live WebSocket подключён, но init не получен — проверьте allowed_symbols / universe робота'
                    : 'Live WebSocket не подключился — перезапустите backend (run.py server) и dev-сервер Vite'
            ))
        }, 12000)
        return () => window.clearTimeout(timer)
    }, [selectedRobot, softLoading, connected])

    const handleRobotChange = (val: string) => {
        const num = val ? Number(val) : null
        resetChartState()
        setSoftLoading(!!num)
        setLiveIssue(null)
        setSelectedRobot(num)
        if (!num) {
            clearRobotScopedState()
        }
    }

    const loadSnapshot = useCallback(async () => {
        if (!selectedRobot) {
            setSnapshot(null)
            return null
        }
        try {
            const snap = await robotService.getLiveSnapshot(selectedRobot)
            setSnapshot(prev => {
                const next = snap as LiveSnapshotState
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
            return snap as LiveSnapshotState
        } catch (error) {
            setLiveIssue(extractApiErrorMessage(error, 'Не удалось загрузить snapshot робота'))
            return null
        }
    }, [selectedRobot])

    useEffect(() => {
        const hydrate = async () => {
            if (!selectedRobot) return
            try {
                const snap = await loadSnapshot()
                if (!snap) {
                    setSnapshot(null)
                    return
                }
                const nextSignals: FeedEvent[] = (snap.recent_signals || []).slice(0, 100).map((x: any) => ({
                    id: x.id,
                    type: String(x.signal_type || '').toLowerCase() === 'buy' ? 'buy' : String(x.signal_type || '').toLowerCase() === 'sell' ? 'sell' : 'info',
                    text: `${tickerFromFigi(String(x.figi || ''), tickerByFigiRef.current)} @ ${Number(x.price_at_signal || 0).toLocaleString('ru-RU', { maximumFractionDigits: 4 })}`,
                    time: x.created_at ? new Date(x.created_at).toLocaleTimeString('ru-RU') : '—',
                }))
                const nextOrders: FeedEvent[] = (snap.recent_orders || []).slice(0, 100).map((x: any) => ({
                    id: x.id,
                    type: String(x.side || '').toLowerCase() === 'buy' ? 'buy' : 'info',
                    text: `${String(x.side || '').toUpperCase()} ${tickerFromFigi(String(x.figi || ''), tickerByFigiRef.current)} x${x.quantity} — ${x.status}`,
                    time: x.created_at ? new Date(x.created_at).toLocaleTimeString('ru-RU') : '—',
                }))
                setSignals(nextSignals)
                setOrders(nextOrders)
                setSignalResultByFigi(() => {
                    const next: Record<string, { status: 'SIGNAL' | 'SKIPPED'; reason: string; time: string }> = {}
                    for (const s of (snap.recent_signals || [])) {
                        const figi = String(s?.figi || '').toUpperCase()
                        if (!figi) continue
                        const side = String(s?.signal_type || '').toUpperCase() || 'SIGNAL'
                        next[figi] = {
                            status: 'SIGNAL',
                            reason: `${side} @ ${s?.price_at_signal ?? '—'}`,
                            time: s?.created_at ? new Date(s.created_at).toLocaleTimeString('ru-RU') : '—',
                        }
                    }
                    for (const o of (snap.recent_orders || [])) {
                        const status = String(o?.status || '').toLowerCase()
                        if (status !== 'skipped') continue
                        const figi = String(o?.figi || '').toUpperCase()
                        if (!figi) continue
                        next[figi] = {
                            status: 'SKIPPED',
                            reason: String(o?.error || o?.reason || o?.status || 'skipped'),
                            time: o?.created_at ? new Date(o.created_at).toLocaleTimeString('ru-RU') : '—',
                        }
                    }
                    return next
                })
            } catch {
                // best effort hydration
                setSnapshot(null)
            }
        }
        hydrate()
    }, [selectedRobot, loadSnapshot])

    useEffect(() => {
        if (!selectedRobot) return
        const timer = window.setInterval(() => {
            void loadSnapshot()
        }, 15000)
        return () => window.clearInterval(timer)
    }, [selectedRobot, loadSnapshot])

    useEffect(() => {
        if (!selectedRobot || !dmsOpen) return
        void loadSnapshot()
    }, [selectedRobot, dmsOpen, loadSnapshot])

    const handleStart = async () => {
        if (!selectedRobot) return
        try {
            await robotService.changeStatus(selectedRobot, 1)
            toast.show('Робот запущен', 'success')
            await loadRobots()
        } catch {
            toast.show('Не удалось запустить робота', 'error')
        }
    }

    const handleStop = async () => {
        if (!selectedRobot) return
        try {
            await robotService.changeStatus(selectedRobot, 2)
            toast.show('Робот остановлен', 'success')
            await loadRobots()
        } catch {
            toast.show('Не удалось остановить робота', 'error')
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

    const onChartReady = useCallback((chart: IChartApi) => {
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
        const rows = snapshot?.portfolio_positions || []
        return rows.map((row) => {
            const figi = String((row as { figi?: string }).figi || '').trim().toUpperCase()
            const live = figi ? prices[figi] : undefined
            if (!live || !Number.isFinite(live.price)) {
                return row
            }
            return {
                ...row,
                current_price: { decimal: live.price, currency: 'USDT' },
                current_price_live: true,
                current_price_time: live.time,
            }
        })
    }, [snapshot?.portfolio_positions, prices])
    const selectedRobotEntity = useMemo(
        () => robots.find(r => r.id === selectedRobot) ?? null,
        [robots, selectedRobot],
    )
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
        for (const p of snapshot?.portfolio_positions || []) {
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
    }, [selectedRobotEntity, snapshot?.portfolio_positions])
    tickerByFigiRef.current = tickerByFigi

    const instrLabel = (figi: string) => tickerFromFigi(figi, tickerByFigi)

    const sortedAvailableFigis = useMemo(
        () => [...availableFigis].sort((a, b) => {
            const cmp = instrLabel(a).localeCompare(instrLabel(b), 'ru', { sensitivity: 'base' })
            return cmp !== 0 ? cmp : a.localeCompare(b)
        }),
        [availableFigis, tickerByFigi],
    )

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
    const noFigisSelected = selectedFigis.length === 0

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
        { key: 'time', header: 'Время', render: r => <span className="mono">{r.time}</span> },
    ]

    const indicatorRows = (sortedAvailableFigis.length > 0 ? sortedAvailableFigis : Object.keys(signalMeta)).map((figi) => {
        const m = signalMeta[figi] || {}
        return {
            figi,
            signal: (m.signalType || '—').toUpperCase(),
            target: m.targetPrice ?? null,
            indicators: m.indicators || {},
        }
    })
    const indicatorColumns: Column<any>[] = [
        {
            key: 'figi',
            header: 'Тикер',
            render: r => (
                <span className="mono" title={instrumentTitle(r.figi, tickerByFigi)}>
                    {instrLabel(r.figi)}
                </span>
            ),
        },
        { key: 'signal', header: 'Сигнал' },
        { key: 'target', header: 'Target', align: 'right' as const, render: r => r.target == null ? '—' : r.target.toLocaleString('ru-RU', { maximumFractionDigits: 4 }) },
        {
            key: 'indicators',
            header: 'Индикаторы',
            render: r => {
                const items = Object.entries(r.indicators || {}) as [string, any][]
                if (items.length === 0) return '—'
                return items.slice(0, 4).map(([k, v]) => `${k}=${Number(v).toFixed(4)}`).join(' | ')
            },
        },
    ]

    const snapshotPositionColumns: Column<any>[] = [
        {
            key: 'ticker',
            header: 'Тикер',
            render: r => r.ticker || instrLabel(String(r.figi || '')),
        },
        {
            key: 'figi',
            header: 'FIGI',
            render: r => (
                <span className="mono" style={{ opacity: 0.65, fontSize: '0.85em' }} title={String(r.figi || '')}>
                    {r.figi ? String(r.figi).slice(-8) : '—'}
                </span>
            ),
        },
        { key: 'instrument_type', header: 'Тип', render: r => r.instrument_type || '—' },
        { key: 'quantity', header: 'Кол-во', align: 'right', render: r => Number(r.quantity || 0).toLocaleString('ru-RU') },
        {
            key: 'average_position_price',
            header: 'Средняя',
            align: 'right',
            render: r => formatPortfolioMoney(r.average_position_price),
        },
        {
            key: 'current_price',
            header: 'Текущая',
            align: 'right',
            render: r => {
                const live = Boolean((r as { current_price_live?: boolean }).current_price_live)
                const liveTime = (r as { current_price_time?: string }).current_price_time
                const formatted = formatPortfolioMoney(r.current_price)
                if (!live) return formatted
                return (
                    <span title={liveTime ? `live WS · ${liveTime}` : 'live WS'}>
                        {formatted}
                        <span className="mono" style={{ opacity: 0.55, fontSize: '0.75em', marginLeft: 4 }}>live</span>
                    </span>
                )
            },
        },
        { key: 'blocked', header: 'Блок', render: r => r.blocked ? 'да' : '—' },
    ]

    const filteredLogs = logFilter === 'ALL' ? logs : logs.filter(l => l.level === logFilter)
    const secondsSinceLastPrice = lastPriceEventAt ? Math.floor((nowTs - lastPriceEventAt) / 1000) : null
    const streamState: 'offline' | 'fresh' | 'stale' = !connected
        ? 'offline'
        : (secondsSinceLastPrice == null || secondsSinceLastPrice <= 5 ? 'fresh' : 'stale')
    const streamVariant = streamState === 'offline' ? 'neutral' : (streamState === 'fresh' ? 'up' : 'down')
    const lastPriceText = lastPriceEventAt
        ? new Date(lastPriceEventAt).toLocaleTimeString('ru-RU')
        : '—'
    const lastHeartbeatText = lastHeartbeatAt
        ? new Date(lastHeartbeatAt).toLocaleTimeString('ru-RU')
        : '—'

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

    const positionCount = selectedRobot
        ? portfolioRows.filter(
            (p: { quantity?: number }) => Math.abs(Number(p.quantity) || 0) > 1e-9,
        ).length
        : 0

    if (loading) {
        return (
            <div className="page" data-page="live">
                <LiveHero />
                <Skeleton height="400px" />
            </div>
        )
    }

    const dailyUniverseColumns: Column<any>[] = [
        { key: 'ticker', header: 'Тикер' },
        { key: 'source', header: 'Источник' },
        { key: 'filter_result', header: 'Статус' },
        {
            key: 'reason',
            header: 'Причина',
            render: r => formatDmsUniverseReason(r),
        },
        { key: 'created_at', header: 'Время', render: r => r.created_at ? new Date(r.created_at).toLocaleTimeString('ru-RU') : '—' },
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

    const hasIndicatorData = selectedRobot && indicatorRows.some(r => Object.keys(r.indicators || {}).length > 0)
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
                    <Badge variant={connected ? 'up' : 'neutral'}>
                        <span className={`status-dot status-dot--${connected ? 'active' : 'inactive'}`} />
                        {connected ? 'WS' : '—'}
                    </Badge>
                    <Badge variant={streamVariant}>{streamState === 'fresh' ? 'OK' : streamState === 'stale' ? 'LAG' : 'OFF'}</Badge>
                    <span className="live-toolbar__meta mono">
                        {lastPriceText} · ping {lastHeartbeatText}
                    </span>
                </div>
                <div className="live-toolbar__actions">
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
                    <Button variant="primary" size="sm" onClick={handleStart} disabled={!selectedRobot}>Старт</Button>
                    <Button variant="danger" size="sm" onClick={handleStop} disabled={!selectedRobot}>Стоп</Button>
                    <Button variant="ghost" size="sm" onClick={() => setSnapshotOpen(true)} disabled={!snapshot} title="Snapshot">
                        Snapshot
                    </Button>
                </div>
            </div>

            {selectedRobot && liveIssue && (
                <Card className="live-empty-card">
                    <div className="event-feed__empty">
                        Не удалось отобразить live-данные: {liveIssue}
                    </div>
                </Card>
            )}

            {selectedRobot && sortedAvailableFigis.length > 1 && (
                <div className="live-figi-bar-wrap">
                    <div className="live-figi-bar__head">
                        <span className="live-figi-bar__meta">
                            Выбрано {selectedFigis.length} / {sortedAvailableFigis.length}
                        </span>
                        <div className="live-figi-bar__actions">
                            <Button
                                variant="ghost"
                                size="sm"
                                disabled={allFigisSelected}
                                onClick={selectAllFigis}
                            >
                                Выделить все
                            </Button>
                            <Button
                                variant="ghost"
                                size="sm"
                                disabled={noFigisSelected}
                                onClick={deselectAllFigis}
                            >
                                Снять все
                            </Button>
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

            {robots.length === 0 && (
                <Card className="live-empty-card">
                    <div className="event-feed__empty">Нет торговых роботов (тип 2)</div>
                </Card>
            )}

            {!selectedRobot && (
                <Card className="live-compact-grid live-compact-grid--empty">
                    <div className="event-feed__empty">Выберите робота для графика, цен и ленты событий</div>
                </Card>
            )}

            {selectedRobot && (
                <div className="live-compact-grid">
                    <Card className="live-chart-card">
                        <Chart height={280} onReady={onChartReady} key={selectedRobot ?? 'empty'} />
                    </Card>

                    <Card className="live-side-card">
                        <div className="live-side-tabs">
                            {([
                                ['prices', `Цены (${priceRows.length})`],
                                ['feed', `Лента (${signals.length + orders.length})`],
                            ] as const).map(([id, label]) => (
                                <button
                                    key={id}
                                    type="button"
                                    className={`live-side-tabs__btn ${sidePanel === id ? 'live-side-tabs__btn--active' : ''}`}
                                    onClick={() => setSidePanel(id)}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>

                        <div className="live-side-panel">
                            {sidePanel === 'prices' && (
                                <DataTable
                                    columns={priceColumns}
                                    data={priceRows}
                                    keyField="figi"
                                    emptyText="Ожидание…"
                                    maxHeight={220}
                                />
                            )}
                            {sidePanel === 'feed' && (
                                <div className="live-feed-split">
                                    <div className="live-feed-split__col">
                                        <span className="live-feed-split__label">Сигналы</span>
                                        <EventFeed events={signals} maxHeight="140px" />
                                    </div>
                                    <div className="live-feed-split__col">
                                        <span className="live-feed-split__label">Заявки</span>
                                        <EventFeed events={orders} maxHeight="140px" />
                                    </div>
                                    {hasIndicatorData && (
                                        <div className="live-feed-split__indicators">
                                            <DataTable
                                                columns={indicatorColumns}
                                                data={indicatorRows}
                                                keyField="figi"
                                                emptyText="—"
                                                maxHeight={100}
                                            />
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </Card>
                </div>
            )}

            <details
                className="live-accordion"
                open={dmsOpen}
                onToggle={e => setDmsOpen((e.target as HTMLDetailsElement).open)}
            >
                <summary className="live-accordion__summary">
                    <span>{isCryptoRobot ? 'Universe / screening' : 'DMS / выборка'}</span>
                    <span className="live-accordion__hint mono">
                        {selectedRobot
                            ? isCryptoRobot
                                ? `поз. ${positionCount} · ✓${universeAccepted.length} / ✗${universeRejected.length}`
                                : `поз. ${positionCount} · ✓${universeAccepted.length} / ✗${universeRejected.length} · снимки ${robotSnapshotRows.length}`
                            : 'робот не выбран'}
                    </span>
                </summary>
                <Card className="live-accordion__body">
                    {!selectedRobot ? (
                        <div className="event-feed__empty">Выберите робота</div>
                    ) : (
                        <>
                            <div className="live-dms-info">
                                <strong>Как формируется блок</strong>
                                {isCryptoRobot ? (
                                    <ol>
                                        <li>
                                            Режим universe — в{' '}
                                            <span className="mono">Настройки робота → Отбор монет</span>: auto-screening
                                            ByBit или фиксированный список символов.
                                        </li>
                                        <li>
                                            <span className="mono">Запустить crypto-screening</span> — отбор пар →{' '}
                                            <span className="mono">crypto_universe_daily</span>.
                                        </li>
                                        <li>
                                            <span className="mono">Пересобрать universe</span> —{' '}
                                            <span className="mono">allowed_symbols</span> в конфиге.
                                        </li>
                                        <li>
                                            <em>Портфель</em> — позиции ByBit-счёта (не universe).
                                        </li>
                                    </ol>
                                ) : (
                                    <ol>
                                        <li>
                                            Режим universe задаётся в{' '}
                                            <span className="mono">Настройки робота → Отбор бумаг</span>: фиксированный список,
                                            DMS pipeline или вся TQBR.
                                        </li>
                                        <li>
                                            <span className="mono">Подписать DMS</span> → snapshot MOEX и пересчёт{' '}
                                            <span className="mono">daily_universe</span> по выбранному режиму.
                                        </li>
                                        <li>
                                            <span className="mono">Пересобрать universe</span> — обновление{' '}
                                            <span className="mono">allowed_figis</span> в конфиге (live подхватит за ~10 с).
                                        </li>
                                        <li>
                                            <em>Портфель</em> — позиции брокерского счёта (не universe).
                                        </li>
                                    </ol>
                                )}
                            </div>
                            <div className="live-accordion__toolbar live-accordion__toolbar--end">
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
                                                await loadDms({ processQueue: true })
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
                                        onClick={async () => {
                                            if (!selectedRobot) return
                                            try {
                                                const res = await robotService.runCryptoScreening(selectedRobot)
                                                toast.show(
                                                    res.message
                                                    || `Screening: ${res.accepted} из ${res.scanned} символов`,
                                                    'success',
                                                )
                                                await loadDms()
                                            } catch {
                                                toast.show('Не удалось запустить crypto-screening', 'error')
                                            }
                                        }}
                                    >
                                        Запустить crypto-screening
                                    </Button>
                                )}
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    disabled={!selectedRobot}
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
                                            await loadDms(isCryptoRobot ? undefined : { processQueue: true })
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
                                    onClick={() => void loadDms(isCryptoRobot ? undefined : { processQueue: true })}
                                >
                                    Обновить
                                </Button>
                            </div>
                            <h4 className="card__section-title">
                                Портфель (все позиции)
                                {selectedRobot && (
                                    <span className="live-dms-section-hint">
                                        {' '}· {positionCount} на счёте
                                        {snapshot?.portfolio_source ? ` · ${snapshot.portfolio_source}` : ''}
                                    </span>
                                )}
                            </h4>
                            {snapshot?.portfolio_fetch_error && (
                                <p className="live-dms-section-hint">
                                    Портфель брокера: {snapshot.portfolio_fetch_error}
                                    {!isCryptoRobot && !snapshot.account_id
                                        ? ' · укажите токен T-Invest и счёт в настройках робота'
                                        : ''}
                                    {isCryptoRobot && !snapshot.account_id
                                        ? ' · укажите токен ByBit в настройках робота'
                                        : ''}
                                </p>
                            )}
                            <div className="live-accordion__toolbar live-accordion__toolbar--end">
                                <Button variant="ghost" size="sm" onClick={() => void loadSnapshot()}>
                                    Обновить портфель
                                </Button>
                            </div>
                            <DataTable
                                columns={snapshotPositionColumns}
                                data={portfolioRows}
                                keyField="id"
                                emptyText={
                                    snapshot?.account_id
                                        ? 'Нет позиций на счёте'
                                        : 'Нет данных — счёт подберётся автоматически при обновлении'
                                }
                                maxHeight={220}
                            />
                            <h4 className="card__section-title">
                                {isCryptoRobot ? 'Результаты crypto-screening (сегодня)' : 'Результаты отбора DMS (сегодня)'}
                            </h4>
                            <p className="live-dms-section-hint">
                                Принято: {universeAccepted.length} · отклонено: {universeRejected.length}
                                {!isCryptoRobot && dailyUniverse[0]?.snapshot_id != null && (
                                    <> · snapshot #{dailyUniverse[0].snapshot_id}</>
                                )}
                            </p>
                            <DataTable
                                columns={dailyUniverseColumns}
                                data={dailyUniverse}
                                keyField="id"
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
                    )}
                </Card>
            </details>

            <details
                className="live-accordion"
                open={logsOpen}
                onToggle={e => setLogsOpen((e.target as HTMLDetailsElement).open)}
            >
                <summary className="live-accordion__summary">
                    <span>Консоль логов</span>
                    <span className="live-accordion__hint mono">
                        {selectedRobot ? `${displayLogs.length} строк` : 'робот не выбран'}
                    </span>
                </summary>
                <Card className="live-accordion__body">
                    {!selectedRobot ? (
                        <div className="event-feed__empty">Выберите робота</div>
                    ) : (
                        <>
                            <div className="live-accordion__toolbar live-accordion__toolbar--end">
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
                            <h4 className="card__section-title">Результат генерации сигналов</h4>
                            <div className="live-signal-results">
                                {(sortedAvailableFigis.length > 0 ? sortedAvailableFigis : Object.keys(signalResultByFigi)).map((figi) => {
                                    const row = signalResultByFigi[figi]
                                    const tk = instrLabel(figi)
                                    if (!row) {
                                        return (
                                            <div key={figi} className="live-signal-results__row">
                                                <span className="mono">{tk}</span>
                                                <span className="live-signal-results__status live-signal-results__status--wait">WAIT</span>
                                                <span className="live-signal-results__reason">нет решения</span>
                                            </div>
                                        )
                                    }
                                    const isSkipped = row.status === 'SKIPPED'
                                    return (
                                        <div key={figi} className="live-signal-results__row">
                                            <span className="mono">{tk}</span>
                                            <span className={`live-signal-results__status ${isSkipped ? 'live-signal-results__status--skip' : 'live-signal-results__status--ok'}`}>
                                                {row.status}
                                            </span>
                                            <span className="live-signal-results__reason">{row.reason}</span>
                                            <span className="live-signal-results__time mono">{row.time}</span>
                                        </div>
                                    )
                                })}
                            </div>
                            <div className="log-console log-console--compact">
                                {displayLogs.length === 0 && (
                                    <div className="log-console__empty">Пусто — события WS появятся при работе сессии</div>
                                )}
                                {displayLogs.map(l => (
                                    <div key={l.id} className={`log-console__line--${l.level.toLowerCase()}`}>
                                        [{l.time}] [{l.level}] {l.text}
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </Card>
            </details>

            <Modal
                open={snapshotOpen}
                onClose={() => setSnapshotOpen(false)}
                title="Snapshot робота"
                width="900px"
            >
                {!snapshot ? (
                    <div className="event-feed__empty">Нет snapshot-данных</div>
                ) : (
                    <>
                        <div className="grid-kpi mb-6">
                            <div className="kpi-tile"><span className="kpi-tile__label">Робот</span><span className="kpi-tile__value mono">#{snapshot.robot_id}</span></div>
                            <div className="kpi-tile"><span className="kpi-tile__label">Статус</span><span className="kpi-tile__value mono">{snapshot.status}</span></div>
                            <div className="kpi-tile"><span className="kpi-tile__label">Брокер</span><span className="kpi-tile__value mono">{snapshot.broker_type}</span></div>
                            <div className="kpi-tile"><span className="kpi-tile__label">Стратегия</span><span className="kpi-tile__value mono">{snapshot.strategy}</span></div>
                        </div>
                        <Card className="mb-6">
                            <h3 className="card__section-title">Открытые позиции</h3>
                            <DataTable
                                columns={snapshotPositionColumns}
                                data={snapshot.active_positions || []}
                                keyField="id"
                                emptyText="Нет открытых позиций"
                                maxHeight={260}
                            />
                        </Card>
                        <Card className="mb-6">
                            <h3 className="card__section-title">Последние сигналы (snapshot)</h3>
                            <DataTable
                                columns={[
                                    { key: 'created_at', header: 'Время', render: r => r.created_at ? new Date(r.created_at).toLocaleString('ru-RU') : '—' },
                                    {
                                        key: 'figi',
                                        header: 'Тикер',
                                        render: r => (
                                            <span className="mono" title={instrumentTitle(String(r.figi || ''), tickerByFigi)}>
                                                {instrLabel(String(r.figi || ''))}
                                            </span>
                                        ),
                                    },
                                    { key: 'signal_type', header: 'Сигнал' },
                                    { key: 'price_at_signal', header: 'Цена', align: 'right', render: r => Number(r.price_at_signal || 0).toLocaleString('ru-RU', { maximumFractionDigits: 4 }) },
                                    { key: 'was_executed', header: 'Исполнен', render: r => Number(r.was_executed || 0) === 1 ? 'Да' : 'Нет' },
                                ]}
                                data={snapshot.recent_signals || []}
                                keyField="id"
                                emptyText="Нет сигналов"
                                maxHeight={260}
                            />
                        </Card>
                        <Card>
                            <h3 className="card__section-title">Последние ордера (snapshot)</h3>
                            <DataTable
                                columns={[
                                    { key: 'created_at', header: 'Время', render: r => r.created_at ? new Date(r.created_at).toLocaleString('ru-RU') : '—' },
                                    {
                                        key: 'figi',
                                        header: 'Тикер',
                                        render: r => (
                                            <span className="mono" title={instrumentTitle(String(r.figi || ''), tickerByFigi)}>
                                                {instrLabel(String(r.figi || ''))}
                                            </span>
                                        ),
                                    },
                                    { key: 'side', header: 'Сторона' },
                                    { key: 'quantity', header: 'Кол-во', align: 'right', render: r => Number(r.quantity || 0).toLocaleString('ru-RU') },
                                    { key: 'price', header: 'Цена', align: 'right', render: r => Number(r.price || 0).toLocaleString('ru-RU', { maximumFractionDigits: 4 }) },
                                    { key: 'status', header: 'Статус' },
                                ]}
                                data={snapshot.recent_orders || []}
                                keyField="id"
                                emptyText="Нет ордеров"
                                maxHeight={260}
                            />
                        </Card>
                    </>
                )}
            </Modal>
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
