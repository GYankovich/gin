import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CandlestickSeries, createSeriesMarkers } from 'lightweight-charts'
import type { ISeriesApi, ISeriesMarkersPluginApi, SeriesMarker, Time } from 'lightweight-charts'
import { Chart } from '@/components/ui/Chart'
import type { IChartApi } from '@/components/ui/Chart'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Skeleton } from '@/components/ui/Skeleton'
import { robotV2Service } from '@/services/robotV2Service'
import type { BacktestPriceCandle, BacktestPriceWindowResponse } from '@/types/robot'

export type PriceBarsPreset = 20 | 50 | 100

type Props = {
    runId: number
    ticker: string
    /** Anchor timestamp for fetch (selection / lifecycle jump). */
    around: string
    bars: PriceBarsPreset
    onBarsChange: (bars: PriceBarsPreset) => void
    /** Playhead moved within loaded window — does not refetch. */
    onPlayheadChange: (iso: string, sec: number) => void
    chartHeight?: number
}

function toCandleTime(raw: unknown): number | null {
    const sec = Math.floor(new Date(String(raw)).getTime() / 1000)
    return Number.isFinite(sec) ? sec : null
}

function toChartCandles(rows: BacktestPriceCandle[]): Array<{
    time: Time
    open: number
    high: number
    low: number
    close: number
}> {
    const out: Array<{ time: Time; open: number; high: number; low: number; close: number }> = []
    for (const r of rows) {
        const t = toCandleTime(r.time)
        if (t == null) continue
        const open = Number(r.open)
        const high = Number(r.high)
        const low = Number(r.low)
        const close = Number(r.close)
        if (![open, high, low, close].every(Number.isFinite)) continue
        out.push({ time: t as Time, open, high, low, close })
    }
    out.sort((a, b) => Number(a.time) - Number(b.time))
    return out
}

/** Zone N — price window + bar scrubber (D submode). */
export function BacktestPriceScrubber({
    runId,
    ticker,
    around,
    bars,
    onBarsChange,
    onPlayheadChange,
    chartHeight = 200,
}: Props) {
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(false)
    const [priceWindow, setPriceWindow] = useState<BacktestPriceWindowResponse | null>(null)
    const [scrubIndex, setScrubIndex] = useState(0)

    const chartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
    const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
    const candlesRef = useRef<ReturnType<typeof toChartCandles>>([])
    const scrubIndexRef = useRef(0)
    const fetchGen = useRef(0)

    const candles = useMemo(() => toChartCandles(priceWindow?.candles || []), [priceWindow])
    candlesRef.current = candles
    scrubIndexRef.current = scrubIndex

    const load = useCallback(async (aroundIso: string, halfBars: number, keepOnFail = false) => {
        const gen = ++fetchGen.current
        setLoading(true)
        setError(false)
        try {
            const res = await robotV2Service.getBacktestPriceWindow(runId, {
                ticker,
                around: aroundIso,
                bars: halfBars,
            })
            if (gen !== fetchGen.current) return
            if (!res) {
                setError(true)
                if (!keepOnFail) setPriceWindow(null)
                return
            }
            setPriceWindow(res)
            const mapped = toChartCandles(res.candles || [])
            const aroundSec = toCandleTime(aroundIso) ?? toCandleTime(res.around)
            let idx = 0
            if (aroundSec != null && mapped.length) {
                let best = 0
                let bestDist = Infinity
                mapped.forEach((c, i) => {
                    const d = Math.abs(Number(c.time) - aroundSec)
                    if (d < bestDist) {
                        bestDist = d
                        best = i
                    }
                })
                idx = best
            }
            setScrubIndex(idx)
            scrubIndexRef.current = idx
        } finally {
            if (gen === fetchGen.current) setLoading(false)
        }
    }, [runId, ticker])

    // Refetch only when selection anchor / ticker / bars change — not on scrub.
    useEffect(() => {
        void load(around, bars)
    }, [around, bars, load])

    const applySeriesData = useCallback((rows: ReturnType<typeof toChartCandles>, playIdx: number) => {
        const series = seriesRef.current
        if (!series) return
        series.setData(rows)
        const play = rows[playIdx]
        const markers: SeriesMarker<Time>[] = []
        if (play) {
            markers.push({
                time: play.time,
                position: 'aboveBar',
                color: '#7dd3fc',
                shape: 'circle',
                id: 'playhead',
                size: 1.5,
            })
        }
        if (!markersRef.current) {
            markersRef.current = createSeriesMarkers(series, markers)
        } else {
            markersRef.current.setMarkers(markers)
        }
        if (play && chartRef.current) {
            try {
                chartRef.current.setCrosshairPosition(play.close, play.time, series)
            } catch {
                /* ignore */
            }
        }
    }, [])

    useEffect(() => {
        applySeriesData(candles, scrubIndex)
    }, [candles, scrubIndex, applySeriesData])

    const onScrub = (idx: number) => {
        const row = candles[idx]
        if (!row) return
        setScrubIndex(idx)
        const iso = new Date(Number(row.time) * 1000).toISOString()
        onPlayheadChange(iso, Number(row.time))
        applySeriesData(candles, idx)
    }

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key !== '[' && e.key !== ']') return
            const t = e.target
            if (t instanceof HTMLElement && t.closest('input, textarea, select, [contenteditable="true"]')) {
                return
            }
            const rows = candlesRef.current
            if (!rows.length) return
            e.preventDefault()
            const delta = e.key === ']' ? 1 : -1
            const next = Math.max(0, Math.min(rows.length - 1, scrubIndexRef.current + delta))
            if (next === scrubIndexRef.current) return
            const row = rows[next]
            scrubIndexRef.current = next
            setScrubIndex(next)
            const iso = new Date(Number(row.time) * 1000).toISOString()
            onPlayheadChange(iso, Number(row.time))
            applySeriesData(rows, next)
        }
        document.addEventListener('keydown', onKey)
        return () => document.removeEventListener('keydown', onKey)
    }, [onPlayheadChange, applySeriesData])

    const gap = priceWindow?.gap
    const empty = !loading && (!priceWindow || candles.length === 0)

    return (
        <div className="robots-v2-glass-price" id="robots-v2-glass-price">
            <div className="robots-v2-glass-price__head">
                <h4 className="robots-v2-glass-price__title">
                    Цена · {ticker}
                    {priceWindow?.interval ? (
                        <span className="robots-v2-hint mono"> · {priceWindow.interval}</span>
                    ) : null}
                </h4>
                <SegmentedControl
                    className="robots-v2-glass-price__bars"
                    aria-label="Окно баров"
                    options={[
                        { value: '20', label: '±20' },
                        { value: '50', label: '±50' },
                        { value: '100', label: '±100' },
                    ]}
                    value={String(bars)}
                    onChange={v => onBarsChange(Number(v) as PriceBarsPreset)}
                />
            </div>

            {loading && candles.length === 0 ? (
                <Skeleton height={`${chartHeight}px`} />
            ) : error && empty ? (
                <div className="robots-v2-glass-price__error">
                    <p className="robots-v2-hint">Не удалось загрузить свечи. Повторить</p>
                    <button
                        type="button"
                        className="robots-v2-chip"
                        onClick={() => void load(around, bars)}
                    >
                        Повторить
                    </button>
                </div>
            ) : empty ? (
                <p className="robots-v2-hint">
                    {gap
                        ? `Нет свечей в кэше (${gap})`
                        : 'Нет свечей для выбранного окна'}
                </p>
            ) : (
                <>
                    {gap ? (
                        <p className="robots-v2-hint robots-v2-glass-price__gap">
                            Частичные данные · {gap}
                        </p>
                    ) : null}
                    <Chart
                        height={chartHeight}
                        className="robots-v2-glass-price__chart"
                        onReady={(chart) => {
                            if (!chart) {
                                chartRef.current = null
                                seriesRef.current = null
                                markersRef.current = null
                                return
                            }
                            chartRef.current = chart
                            const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
                            const series = chart.addSeries(CandlestickSeries, {
                                upColor: isDark ? '#3dd68c' : '#16a34a',
                                downColor: isDark ? '#f07178' : '#dc2626',
                                borderUpColor: isDark ? '#3dd68c' : '#16a34a',
                                borderDownColor: isDark ? '#f07178' : '#dc2626',
                                wickUpColor: isDark ? '#3dd68c' : '#16a34a',
                                wickDownColor: isDark ? '#f07178' : '#dc2626',
                            })
                            seriesRef.current = series
                            applySeriesData(candlesRef.current, scrubIndexRef.current)
                        }}
                    />
                    <div className="robots-v2-glass-price__scrub">
                        <label className="robots-v2-hint" htmlFor="robots-v2-price-scrub">
                            Окно · ±{bars} баров
                        </label>
                        <input
                            id="robots-v2-price-scrub"
                            type="range"
                            min={0}
                            max={Math.max(0, candles.length - 1)}
                            value={Math.min(scrubIndex, Math.max(0, candles.length - 1))}
                            onChange={e => onScrub(Number(e.target.value))}
                            disabled={candles.length < 2}
                        />
                        <span className="robots-v2-hint mono">
                            {candles[scrubIndex]
                                ? new Date(Number(candles[scrubIndex].time) * 1000).toLocaleString('ru-RU')
                                : '—'}
                        </span>
                    </div>
                    {loading ? <p className="robots-v2-hint">Обновление окна…</p> : null}
                </>
            )}
        </div>
    )
}
