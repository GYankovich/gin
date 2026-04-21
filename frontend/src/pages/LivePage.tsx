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
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAuthStore } from '@/stores/authStore'
import { robotService } from '@/services/robotService'
import type { Robot } from '@/types/robot'
import { useToast } from '@/components/ui/Toast'

const SERIES_COLORS = [
    '#00ffff', '#ff00ff', '#00ffaa', '#ffaa00', '#aa00ff',
    '#ff3366', '#66ffcc', '#ff9900', '#33ccff', '#ff66cc',
]
const MAX_PRICE_POINTS = 3000
const MAX_TARGET_POINTS = 1000
const MAX_CANDLE_POINTS = 1000

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
    recent_signals: any[]
    recent_orders: any[]
    stream_health: Record<string, any>
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
    const [lastPriceEventAt, setLastPriceEventAt] = useState<number | null>(null)
    const [lastHeartbeatAt, setLastHeartbeatAt] = useState<number | null>(null)
    const [nowTs, setNowTs] = useState<number>(() => Date.now())
    const [logs, setLogs] = useState<LogLine[]>([])
    const [snapshot, setSnapshot] = useState<LiveSnapshotState | null>(null)
    const [dmsSubscriptions, setDmsSubscriptions] = useState<any[]>([])
    const [dmsSnapshots, setDmsSnapshots] = useState<any[]>([])
    const [dailyUniverse, setDailyUniverse] = useState<any[]>([])
    const [filterLog, setFilterLog] = useState<any[]>([])
    const [filterLogStats, setFilterLogStats] = useState({ total_checked: 0, passed: 0, rejected: 0 })
    const [snapshotOpen, setSnapshotOpen] = useState(false)
    const [logFilter, setLogFilter] = useState('ALL')
    const [chartMode, setChartMode] = useState<'candles' | 'lines' | 'both'>('both')
    const logIdRef = useRef(0)
    const signalIdRef = useRef(0)

    const [availableFigis, setAvailableFigis] = useState<string[]>([])
    const [selectedFigis, setSelectedFigis] = useState<string[]>([])
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

    const loadDms = useCallback(async () => {
        try {
            const [subs, snaps, universe] = await Promise.all([
                robotService.listDmsSubscriptions(),
                robotService.listDmsSnapshots('TQBR'),
                robotService.listDailyUniverse(selectedRobot ? { robot_id: selectedRobot } : undefined),
            ])
            setDmsSubscriptions(Array.isArray(subs) ? subs : [])
            setDmsSnapshots(Array.isArray(snaps) ? snaps : [])
            setDailyUniverse(Array.isArray(universe?.items) ? universe.items : [])
            const log = await robotService.getDmsFilterLog(selectedRobot ? { robot_id: selectedRobot, limit: 300 } : { limit: 300 })
            setFilterLog(Array.isArray(log?.items) ? log.items : [])
            setFilterLogStats({
                total_checked: Number(log?.total_checked || 0),
                passed: Number(log?.passed || 0),
                rejected: Number(log?.rejected || 0),
            })
        } catch {
            // best effort
        }
    }, [selectedRobot])

    useEffect(() => {
        loadDms()
    }, [loadDms])

    useEffect(() => {
        const timer = window.setInterval(() => setNowTs(Date.now()), 1000)
        return () => window.clearInterval(timer)
    }, [])

    const resetChartState = useCallback(() => {
        setSignals([])
        setOrders([])
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
        if (seriesMapRef.current.has(figi)) return seriesMapRef.current.get(figi)!
        const idx = availableFigis.indexOf(figi)
        const color = SERIES_COLORS[idx >= 0 ? idx % SERIES_COLORS.length : seriesMapRef.current.size % SERIES_COLORS.length]
        const series = chartRef.current.addSeries(LineSeries, {
            color,
            lineWidth: 2,
            title: figi.slice(-4),
            priceScaleId: 'right',
        })
        const hist = normalizeLineHistory(priceHistoryRef.current.get(figi) ?? [])
        if (hist.length > 0) {
            series.setData(hist)
        }
        series.applyOptions({ visible: chartMode === 'lines' || chartMode === 'both' })
        seriesMapRef.current.set(figi, series)
        return series
    }, [availableFigis, chartMode, normalizeLineHistory])

    const ensureTargetSeries = useCallback((figi: string) => {
        if (!chartRef.current) return null
        if (targetSeriesMapRef.current.has(figi)) return targetSeriesMapRef.current.get(figi)!
        const idx = availableFigis.indexOf(figi)
        const base = SERIES_COLORS[idx >= 0 ? idx % SERIES_COLORS.length : targetSeriesMapRef.current.size % SERIES_COLORS.length]
        const targetSeries = chartRef.current.addSeries(LineSeries, {
            color: base,
            lineWidth: 1,
            lineStyle: 2,
            title: `${figi.slice(-4)} target`,
            priceScaleId: 'right',
        })
        const hist = normalizeLineHistory(targetHistoryRef.current.get(figi) ?? [])
        if (hist.length > 0) {
            targetSeries.setData(hist)
        }
        targetSeries.applyOptions({ visible: chartMode === 'lines' || chartMode === 'both' })
        targetSeriesMapRef.current.set(figi, targetSeries)
        return targetSeries
    }, [availableFigis, chartMode, normalizeLineHistory])

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
        if (!selectedFigis.includes(figi) && selectedFigis.length > 0) return

        const series = ensurePriceSeries(figi)
        series?.update(point)
        const candleSeries = ensureCandleSeries(figi)
        candleSeries?.update(candleCurrentRef.current.get(figi)!)
    }, [ensurePriceSeries, ensureCandleSeries, selectedFigis])

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
        if (!selectedFigis.includes(figi) && selectedFigis.length > 0) return
        const series = ensureTargetSeries(figi)
        series?.update(point)
    }, [ensureTargetSeries, selectedFigis])

    const onWsMessage = useCallback((data: any) => {
        if (!data || !data.type) return

        if (data.type === 'init') {
            const figis: string[] = data.figis ?? []
            setAvailableFigis(figis)
            setSelectedFigis(prev => {
                if (prev.length === 0) return figis
                const available = new Set(figis)
                const filtered = prev.filter(f => available.has(f))
                return filtered.length > 0 ? filtered : figis
            })
            setSelectedBroker(data.broker_type || 'tinvest')
            setSoftLoading(false)
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
            setSignals(prev => [{
                id: ++signalIdRef.current,
                type: (side === 'buy' ? 'buy' : side === 'sell' ? 'sell' : 'info') as FeedEvent['type'],
                text: `${data.figi} @ ${data.price}${data.target_price ? ` → target ${data.target_price}` : ''}`,
                time: data.time ?? new Date().toLocaleTimeString('ru-RU'),
            }, ...prev].slice(0, 100))
        }

        if (data.type === 'order') {
            setOrders(prev => [{
                id: ++signalIdRef.current,
                type: (data.status === 'filled' ? 'buy' : 'info') as FeedEvent['type'],
                text: `${data.side?.toUpperCase()} ${data.figi} x${data.quantity} — ${data.status}`,
                time: data.time ?? new Date().toLocaleTimeString('ru-RU'),
            }, ...prev].slice(0, 100))
        }

        if (data.type === 'skipped') {
            setOrders(prev => [{
                id: ++signalIdRef.current,
                type: 'info' as FeedEvent['type'],
                text: `SKIPPED ${data.figi} — ${data.reason || data.status}`,
                time: data.time ?? new Date().toLocaleTimeString('ru-RU'),
            }, ...prev].slice(0, 100))
        }

        if (data.type === 'log') {
            setLogs(prev => [...prev, {
                id: ++logIdRef.current,
                level: data.level ?? 'INFO',
                text: data.message ?? JSON.stringify(data),
                time: data.time ?? new Date().toLocaleTimeString('ru-RU'),
            }].slice(-500))
        }

        if (data.type === 'error') {
            setSoftLoading(false)
            setLogs(prev => [...prev, {
                id: ++logIdRef.current,
                level: 'ERROR',
                text: data.message ?? 'Unknown error',
                time: new Date().toLocaleTimeString('ru-RU'),
            }].slice(-500))
        }
    }, [appendPriceToChart, appendTargetToChart])

    const { connected, send } = useWebSocket({ url: wsUrl, onMessage: onWsMessage, enabled: !!selectedRobot })

    const handleRobotChange = (val: string) => {
        const num = val ? Number(val) : null
        resetChartState()
        setSoftLoading(!!num)
        setSelectedRobot(num)
    }

    useEffect(() => {
        const hydrate = async () => {
            if (!selectedRobot) return
            try {
                const snap = await robotService.getLiveSnapshot(selectedRobot)
                setSnapshot(snap as LiveSnapshotState)
                setSelectedBroker(snap.broker_type || 'tinvest')
                const nextSignals: FeedEvent[] = (snap.recent_signals || []).slice(0, 100).map((x: any) => ({
                    id: x.id,
                    type: String(x.signal_type || '').toLowerCase() === 'buy' ? 'buy' : String(x.signal_type || '').toLowerCase() === 'sell' ? 'sell' : 'info',
                    text: `${x.figi} @ ${Number(x.price_at_signal || 0).toLocaleString('ru-RU', { maximumFractionDigits: 4 })}`,
                    time: x.created_at ? new Date(x.created_at).toLocaleTimeString('ru-RU') : '—',
                }))
                const nextOrders: FeedEvent[] = (snap.recent_orders || []).slice(0, 100).map((x: any) => ({
                    id: x.id,
                    type: String(x.side || '').toLowerCase() === 'buy' ? 'buy' : 'info',
                    text: `${String(x.side || '').toUpperCase()} ${x.figi} x${x.quantity} — ${x.status}`,
                    time: x.created_at ? new Date(x.created_at).toLocaleTimeString('ru-RU') : '—',
                }))
                setSignals(nextSignals)
                setOrders(nextOrders)
            } catch {
                // best effort hydration
                setSnapshot(null)
            }
        }
        hydrate()
    }, [selectedRobot])

    useEffect(() => {
        if (!selectedRobot) return
        const timer = window.setInterval(async () => {
            try {
                const snap = await robotService.getLiveSnapshot(selectedRobot)
                setSnapshot(snap as LiveSnapshotState)
            } catch {
                // ignore periodic refresh errors
            }
        }, 15000)
        return () => window.clearInterval(timer)
    }, [selectedRobot])

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
            if (prev.includes(figi) && prev.length === 1) {
                return prev
            }
            const next = prev.includes(figi)
                ? prev.filter(f => f !== figi)
                : [...prev, figi]
            const wasSelected = prev.includes(figi)
            if (connected) {
                send({ action: wasSelected ? 'unsubscribe' : 'subscribe', figi })
            }

            const chart = chartRef.current
            if (chart) {
                for (const [f, series] of seriesMapRef.current.entries()) {
                    series.applyOptions({ visible: next.includes(f) && (chartMode === 'lines' || chartMode === 'both') })
                }
                for (const [f, series] of candleSeriesMapRef.current.entries()) {
                    series.applyOptions({ visible: next.includes(f) && (chartMode === 'candles' || chartMode === 'both') })
                }
                for (const [f, series] of targetSeriesMapRef.current.entries()) {
                    series.applyOptions({ visible: next.includes(f) && (chartMode === 'lines' || chartMode === 'both') })
                }
            }
            return next
        })
    }

    const onChartReady = useCallback((chart: IChartApi) => {
        chartRef.current = chart
        chart.timeScale().applyOptions({
            timeVisible: true,
            secondsVisible: true,
            rightOffset: 5,
        })
        const figisToRender = selectedFigis.length > 0 ? selectedFigis : availableFigis
        for (const figi of figisToRender) {
            ensurePriceSeries(figi)
            ensureCandleSeries(figi)
            ensureTargetSeries(figi)
        }
    }, [availableFigis, ensurePriceSeries, ensureCandleSeries, ensureTargetSeries, selectedFigis])

    useEffect(() => {
        if (!chartRef.current) return
        const figisToRender = selectedFigis.length > 0 ? selectedFigis : availableFigis
        for (const figi of figisToRender) {
            ensurePriceSeries(figi)
            ensureCandleSeries(figi)
            ensureTargetSeries(figi)
        }
    }, [availableFigis, selectedFigis, ensurePriceSeries, ensureCandleSeries, ensureTargetSeries])

    useEffect(() => {
        const selected = new Set(selectedFigis)
        for (const [figi, series] of seriesMapRef.current.entries()) {
            series.applyOptions({ visible: selected.has(figi) && (chartMode === 'lines' || chartMode === 'both') })
        }
        for (const [figi, series] of candleSeriesMapRef.current.entries()) {
            series.applyOptions({ visible: selected.has(figi) && (chartMode === 'candles' || chartMode === 'both') })
        }
        for (const [figi, series] of targetSeriesMapRef.current.entries()) {
            series.applyOptions({ visible: selected.has(figi) && (chartMode === 'lines' || chartMode === 'both') })
        }
    }, [chartMode, selectedFigis])

    const priceRows = (availableFigis.length > 0 ? availableFigis : Object.keys(prices)).map((figi) => {
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
            key: 'figi', header: 'FIGI',
            render: r => {
                const idx = availableFigis.indexOf(r.figi)
                const color = SERIES_COLORS[idx >= 0 ? idx % SERIES_COLORS.length : 0]
                return <span style={{ borderLeft: `3px solid ${color}`, paddingLeft: 6 }}>{r.figi}</span>
            },
        },
        { key: 'price', header: 'Цена', align: 'right' as const, render: r => <span className="mono">{r.price == null ? '—' : r.price.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</span> },
        {
            key: 'change', header: 'Изм. %', align: 'right' as const,
            render: r => <span className={r.price == null ? '' : (r.change >= 0 ? 'color-up' : 'color-down')}>{r.price == null ? '—' : `${r.change >= 0 ? '+' : ''}${r.change?.toFixed(4)}%`}</span>,
        },
        { key: 'time', header: 'Время', render: r => <span className="mono">{r.time}</span> },
    ]

    const indicatorRows = (availableFigis.length > 0 ? availableFigis : Object.keys(signalMeta)).map((figi) => {
        const m = signalMeta[figi] || {}
        return {
            figi,
            signal: (m.signalType || '—').toUpperCase(),
            target: m.targetPrice ?? null,
            indicators: m.indicators || {},
        }
    })
    const indicatorColumns: Column<any>[] = [
        { key: 'figi', header: 'FIGI' },
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
        { key: 'figi', header: 'FIGI' },
        { key: 'side', header: 'Сторона', render: r => String(r.side || '').toUpperCase() },
        { key: 'quantity', header: 'Кол-во', align: 'right', render: r => Number(r.quantity || 0).toLocaleString('ru-RU') },
        { key: 'entry_price', header: 'Вход', align: 'right', render: r => Number(r.entry_price || 0).toLocaleString('ru-RU', { maximumFractionDigits: 4 }) },
        { key: 'status', header: 'Статус' },
    ]

    const filteredLogs = logFilter === 'ALL' ? logs : logs.filter(l => l.level === logFilter)
    const secondsSinceLastPrice = lastPriceEventAt ? Math.floor((nowTs - lastPriceEventAt) / 1000) : null
    const streamState: 'offline' | 'fresh' | 'stale' = !connected
        ? 'offline'
        : (secondsSinceLastPrice == null || secondsSinceLastPrice <= 5 ? 'fresh' : 'stale')
    const streamLabel = streamState === 'offline'
        ? 'Поток: оффлайн'
        : streamState === 'fresh'
            ? `Поток: свежий (${secondsSinceLastPrice ?? 0}с)`
            : `Поток: задержка (${secondsSinceLastPrice ?? 0}с)`
    const streamVariant = streamState === 'offline' ? 'neutral' : (streamState === 'fresh' ? 'up' : 'down')
    const lastPriceText = lastPriceEventAt
        ? new Date(lastPriceEventAt).toLocaleTimeString('ru-RU')
        : '—'
    const lastHeartbeatText = lastHeartbeatAt
        ? new Date(lastHeartbeatAt).toLocaleTimeString('ru-RU')
        : '—'

    const downloadLog = () => {
        const text = logs.map(l => `[${l.time}] [${l.level}] ${l.text}`).join('\n')
        const blob = new Blob([text], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = 'live-log.txt'; a.click()
        URL.revokeObjectURL(url)
    }

    if (loading) return <div className="page"><h1 className="page__title">Live</h1><Skeleton height="400px" /></div>

    const dmsSubscriptionColumns: Column<any>[] = [
        { key: 'id', header: 'ID', render: r => <span className="mono">#{r.id}</span> },
        { key: 'robot_id', header: 'Робот', render: r => <span className="mono">#{r.robot_id}</span> },
        { key: 'board', header: 'Board' },
        { key: 'status', header: 'Статус' },
        { key: 'requested_at', header: 'Запрошено', render: r => r.requested_at ? new Date(r.requested_at).toLocaleString('ru-RU') : '—' },
        { key: 'snapshot_id', header: 'Снимок', render: r => r.snapshot_id ? `#${r.snapshot_id}` : '—' },
    ]

    const dmsSnapshotColumns: Column<any>[] = [
        { key: 'id', header: 'ID', render: r => <span className="mono">#{r.id}</span> },
        { key: 'snapshot_time', header: 'Время', render: r => r.snapshot_time ? new Date(r.snapshot_time).toLocaleString('ru-RU') : '—' },
        { key: 'board', header: 'Board' },
        { key: 'status', header: 'Статус' },
        { key: 'securities_count', header: 'Бумаг', align: 'right', render: r => Number(r.securities_count || 0).toLocaleString('ru-RU') },
    ]

    const dailyUniverseColumns: Column<any>[] = [
        { key: 'ticker', header: 'Тикер' },
        { key: 'source', header: 'Источник' },
        { key: 'filter_result', header: 'Статус' },
        { key: 'reject_reason', header: 'Причина', render: r => r.reject_reason || '—' },
        { key: 'created_at', header: 'Время', render: r => r.created_at ? new Date(r.created_at).toLocaleTimeString('ru-RU') : '—' },
    ]
    const filterLogColumns: Column<any>[] = [
        { key: 'created_at', header: 'Время', render: r => r.created_at ? new Date(r.created_at).toLocaleTimeString('ru-RU') : '—' },
        { key: 'ticker', header: 'Тикер' },
        { key: 'filter_result', header: 'Результат' },
        { key: 'reject_reason', header: 'Причина', render: r => r.reject_reason || '—' },
        {
            key: 'applied_filters',
            header: 'Фильтры',
            render: r => {
                const arr = Array.isArray(r.applied_filters) ? r.applied_filters : []
                if (arr.length === 0) return '—'
                return arr.map((x: any) => String(x?.type || '?')).join(', ')
            },
        },
    ]

    return (
        <div className="page">
            <h1 className="page__title">Live-режим</h1>
            {softLoading && <div className="soft-loading-bar" />}

            <div className="portfolio-toolbar">
                <Select
                    options={[{ value: '', label: 'Выберите робота' }, ...robots.map(r => ({ value: String(r.id), label: r.name }))]}
                    value={selectedRobot != null ? String(selectedRobot) : ''}
                    onChange={handleRobotChange}
                    placeholder="Выберите робота"
                />
                <Badge variant={connected ? 'up' : 'neutral'}>
                    <span className={`status-dot status-dot--${connected ? 'active' : 'inactive'}`} />
                    {connected ? 'Онлайн' : 'Оффлайн'}
                </Badge>
                <Badge variant={streamVariant}>
                    {streamLabel}
                </Badge>
                <Badge variant="neutral">
                    Last price: {lastPriceText}
                </Badge>
                <Badge variant="neutral">
                    Last ping: {lastHeartbeatText}
                </Badge>
                <Badge variant="neutral">Брокер: {selectedBroker}</Badge>
                {snapshot?.strategy && <Badge variant="neutral">Стратегия: {snapshot.strategy}</Badge>}
                {snapshot?.account_id && <Badge variant="neutral">Счёт: {snapshot.account_id}</Badge>}
                <div style={{ display: 'inline-flex', gap: '6px', marginLeft: '6px' }}>
                    <Button variant={chartMode === 'candles' ? 'primary' : 'ghost'} size="sm" onClick={() => setChartMode('candles')}>Свечи</Button>
                    <Button variant={chartMode === 'lines' ? 'primary' : 'ghost'} size="sm" onClick={() => setChartMode('lines')}>Линии</Button>
                    <Button variant={chartMode === 'both' ? 'primary' : 'ghost'} size="sm" onClick={() => setChartMode('both')}>Оба</Button>
                </div>
                <Button variant="primary" size="sm" onClick={handleStart} disabled={!selectedRobot}>Старт</Button>
                <Button variant="danger" size="sm" onClick={handleStop} disabled={!selectedRobot}>Стоп</Button>
                <Button variant="secondary" size="sm" onClick={() => setSnapshotOpen(true)} disabled={!snapshot}>Детали snapshot</Button>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={async () => {
                        if (!selectedRobot) return
                        try {
                            await robotService.subscribeDms({ robot_id: selectedRobot, board: 'TQBR', ttl_minutes: 5 })
                            toast.show('Подписка DMS создана', 'success')
                            await loadDms()
                        } catch {
                            toast.show('Не удалось создать подписку DMS', 'error')
                        }
                    }}
                    disabled={!selectedRobot}
                >
                    Подписать DMS
                </Button>
            </div>

            {snapshot && (
                <div className="grid-kpi mb-6">
                    <div className="kpi-tile">
                        <span className="kpi-tile__label">Snapshot: позиции</span>
                        <span className="kpi-tile__value mono">{(snapshot.active_positions || []).length}</span>
                    </div>
                    <div className="kpi-tile">
                        <span className="kpi-tile__label">Snapshot: сигналы</span>
                        <span className="kpi-tile__value mono">{(snapshot.recent_signals || []).length}</span>
                    </div>
                    <div className="kpi-tile">
                        <span className="kpi-tile__label">Snapshot: ордера</span>
                        <span className="kpi-tile__value mono">{(snapshot.recent_orders || []).length}</span>
                    </div>
                    <div className="kpi-tile">
                        <span className="kpi-tile__label">Health: last event</span>
                        <span className="kpi-tile__value mono">
                            {snapshot.stream_health?.last_event_at
                                ? new Date(snapshot.stream_health.last_event_at).toLocaleString('ru-RU')
                                : '—'}
                        </span>
                    </div>
                </div>
            )}

            {availableFigis.length > 1 && (
                <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginBottom: 'var(--space-4)' }}>
                    {availableFigis.map((figi, idx) => {
                        const color = SERIES_COLORS[idx % SERIES_COLORS.length]
                        const active = selectedFigis.includes(figi)
                        return (
                            <button
                                key={figi}
                                className="tag"
                                style={{
                                    borderColor: color,
                                    opacity: active ? 1 : 0.4,
                                    cursor: 'pointer',
                                }}
                                onClick={() => toggleFigi(figi)}
                            >
                                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: color, marginRight: 6 }} />
                                {figi}
                            </button>
                        )
                    })}
                </div>
            )}

            {robots.length === 0 && (
                <Card>
                    <div className="event-feed__empty">Нет активных торговых роботов (тип 2, статус: включён)</div>
                </Card>
            )}

            <div className="live-grid">
                <div className="live-grid__chart">
                    <Card>
                        <h3 className="card__section-title">График цен</h3>
                        <Chart height={420} onReady={onChartReady} key={selectedRobot ?? 'empty'} />
                    </Card>
                </div>

                <div className="live-grid__feeds">
                    <Card>
                        <h3 className="card__section-title">Цены</h3>
                        <DataTable columns={priceColumns} data={priceRows} keyField="figi" emptyText="Ожидание данных..." />
                    </Card>

                    <Card>
                        <h3 className="card__section-title">Сигналы</h3>
                        <EventFeed events={signals} maxHeight="200px" />
                    </Card>

                    <Card>
                        <h3 className="card__section-title">Target и индикаторы</h3>
                        <DataTable columns={indicatorColumns} data={indicatorRows} keyField="figi" emptyText="Нет индикаторных данных" />
                    </Card>

                    <Card>
                        <h3 className="card__section-title">Заявки</h3>
                        <EventFeed events={orders} maxHeight="200px" />
                    </Card>

                    <Card>
                        <h3 className="card__section-title">Открытые позиции (snapshot)</h3>
                        <DataTable
                            columns={snapshotPositionColumns}
                            data={snapshot?.active_positions || []}
                            keyField="id"
                            emptyText="Нет открытых позиций"
                            maxHeight={260}
                        />
                    </Card>
                </div>
            </div>

            <Card className="mt-6">
                <div className="card__header">
                    <h3>DMS / Дневная выборка</h3>
                    <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={async () => {
                                try {
                                    const res = await robotService.createDmsSnapshot({ board: 'TQBR', ttl_minutes: 5, is_manual: true })
                                    toast.show(`Снимок создан: #${res.snapshot_id}`, 'success')
                                    await loadDms()
                                } catch {
                                    toast.show('Не удалось создать снимок DMS', 'error')
                                }
                            }}
                        >
                            Новый снимок
                        </Button>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={async () => {
                                try {
                                    const res = await robotService.processDmsQueue()
                                    toast.show(
                                        `Очередь: подписок ${res.processed_subscriptions}, снимков ${res.created_snapshots}`,
                                        'success',
                                    )
                                    await loadDms()
                                } catch {
                                    toast.show('Не удалось обработать очередь DMS', 'error')
                                }
                            }}
                        >
                            Обработать очередь
                        </Button>
                        <Button variant="ghost" size="sm" onClick={loadDms}>Обновить</Button>
                    </div>
                </div>
                <div className="mb-4">
                    <h4 className="card__section-title">Активные подписки</h4>
                    <DataTable columns={dmsSubscriptionColumns} data={dmsSubscriptions} keyField="id" emptyText="Подписок пока нет" maxHeight={220} />
                </div>
                <div className="mb-4">
                    <h4 className="card__section-title">Последние снимки</h4>
                    <DataTable columns={dmsSnapshotColumns} data={dmsSnapshots} keyField="id" emptyText="Снимков пока нет" maxHeight={220} />
                </div>
                <div>
                    <h4 className="card__section-title">Daily universe (за сегодня)</h4>
                    <DataTable columns={dailyUniverseColumns} data={dailyUniverse} keyField="id" emptyText="Пока пусто" maxHeight={260} />
                </div>
            </Card>

            <Card className="mt-6">
                <div className="card__header">
                    <h3>Журнал фильтрации</h3>
                    <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                        <Badge variant="neutral">Проверено: {filterLogStats.total_checked}</Badge>
                        <Badge variant="up">Прошли: {filterLogStats.passed}</Badge>
                        <Badge variant="down">Отклонено: {filterLogStats.rejected}</Badge>
                    </div>
                </div>
                <DataTable columns={filterLogColumns} data={filterLog} keyField="id" emptyText="Логов пока нет" maxHeight={320} />
            </Card>

            <Card className="mt-6">
                <div className="card__header">
                    <h3>Консоль логов</h3>
                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                        {['ALL', 'INFO', 'ERROR', 'DEBUG'].map(f => (
                            <button key={f} className={`tf-btn ${f === logFilter ? 'tf-btn--active' : ''}`} onClick={() => setLogFilter(f)}>{f}</button>
                        ))}
                        <Button variant="ghost" size="sm" onClick={downloadLog}>Скачать</Button>
                    </div>
                </div>
                <div className="log-console" style={{ maxHeight: '320px' }}>
                    {filteredLogs.length === 0 && <div style={{ color: 'var(--text-muted)' }}>Логи пусты</div>}
                    {filteredLogs.map(l => (
                        <div key={l.id} className={`log-console__line--${l.level.toLowerCase()}`}>
                            [{l.time}] [{l.level}] {l.text}
                        </div>
                    ))}
                </div>
            </Card>

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
                                    { key: 'figi', header: 'FIGI' },
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
                                    { key: 'figi', header: 'FIGI' },
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
