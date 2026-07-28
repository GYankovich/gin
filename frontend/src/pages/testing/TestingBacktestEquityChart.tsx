import React, { useCallback, useEffect, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Chart, type IChartApi, type ISeriesApi, type Time } from '@/components/ui/Chart'
import { LineSeries } from 'lightweight-charts'
import type { Robot, RobotHistoryBacktestResult, RobotHistoryBacktestTrade } from '@/types/robot'
import { normalizeSignalInterval, toChartTime } from '@/pages/testing/testingPipeline'

function normalizeSeriesByTime<T extends { time: Time }>(rows: T[]): T[] {
    const map = new Map<string, T>()
    for (const row of rows) map.set(String(row.time), row)
    return Array.from(map.values()).sort((a, b) => Number(a.time) - Number(b.time))
}

type Props = {
    result: RobotHistoryBacktestResult
    fromDate: string
    priceCurve: Array<{ time: Time; value: number }>
    selectedRobot: Robot | null
    interval: string
    chartLegend: { time: string; equity?: number; price?: number }
    setChartLegend: React.Dispatch<React.SetStateAction<{ time: string; equity?: number; price?: number }>>
}

function useAnalysisChartHeight(): number {
    const [height, setHeight] = useState(440)
    useEffect(() => {
        const update = () => {
            setHeight(Math.min(560, Math.max(400, Math.round(window.innerHeight * 0.46))))
        }
        update()
        window.addEventListener('resize', update)
        return () => window.removeEventListener('resize', update)
    }, [])
    return height
}

export function TestingBacktestEquityChart({
    result,
    fromDate,
    priceCurve,
    selectedRobot,
    interval,
    chartLegend,
    setChartLegend,
}: Props) {
    const chartHeight = useAnalysisChartHeight()

    const onChartReady = useCallback(
        (chart: IChartApi | null, containerEl?: HTMLDivElement | null) => {
            if (!chart || !result?.equity_curve?.length) return
            const strategyInterval = normalizeSignalInterval(
                interval || (selectedRobot?.config as { strategy_params?: { interval?: string } })?.strategy_params?.interval || '',
            )
            const isIntraday = strategyInterval.includes('MIN') || strategyInterval.includes('HOUR')
            chart.applyOptions({
                timeScale: {
                    timeVisible: isIntraday,
                    secondsVisible: false,
                },
            } as any)
            const formatLegendTime = (t: Time | number | string): string => {
                const sec = typeof t === 'number' ? t : Number(t)
                if (!Number.isFinite(sec)) return ''
                const d = new Date(sec * 1000)
                const date = d.toLocaleDateString('ru-RU')
                if (!isIntraday) return date
                const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
                return `${date} ${time}`
            }
            const start = new Date(fromDate)
            const eqDataRaw = result.equity_curve.map((p, i) => {
                const pTime = (p as { time?: string }).time
                if (pTime) return { time: toChartTime(pTime), value: p.equity }
                const d = new Date(start)
                d.setUTCDate(d.getUTCDate() + i)
                return { time: toChartTime(d.toISOString()), value: p.equity }
            })
            const eqData = normalizeSeriesByTime(eqDataRaw)
            const eqSeries = chart.addSeries(LineSeries, { color: '#0066cc', lineWidth: 2 })
            eqSeries.setData(eqData)

            const tradePricePoints = normalizeSeriesByTime(
                (result.trades || []).filter(t => !!t.bar_time).map(t => ({ time: toChartTime(t.bar_time), value: t.price })),
            )
            const priceLineData = priceCurve.length > 0 ? normalizeSeriesByTime(priceCurve) : tradePricePoints

            let priceSeries: ISeriesApi<any> | null = null
            if (priceLineData.length > 0) {
                priceSeries = chart.addSeries(LineSeries, { color: '#9b7cff', lineWidth: 1, priceScaleId: 'left' as any } as any)
                priceSeries.setData(priceLineData)
            }

            const buyPointsSeries = chart.addSeries(LineSeries, {
                color: '#00aa66',
                lineVisible: false,
                pointMarkersVisible: true,
                pointMarkersRadius: 4,
                crosshairMarkerVisible: true,
                crosshairMarkerRadius: 5,
                priceScaleId: 'left' as any,
            } as any)
            const sellPointsSeries = chart.addSeries(LineSeries, {
                color: '#cc3333',
                lineVisible: false,
                pointMarkersVisible: true,
                pointMarkersRadius: 4,
                crosshairMarkerVisible: true,
                crosshairMarkerRadius: 5,
                priceScaleId: 'left' as any,
            } as any)
            const buyPoints = (result.trades || [])
                .filter(t => t.side === 'buy' && !!t.bar_time)
                .map(t => ({ time: toChartTime(t.bar_time), value: t.price }))
            const sellPoints = (result.trades || [])
                .filter(t => t.side !== 'buy' && !!t.bar_time)
                .map(t => ({ time: toChartTime(t.bar_time), value: t.price }))
            buyPointsSeries.setData(normalizeSeriesByTime(buyPoints as { time: Time; value: number }[]))
            sellPointsSeries.setData(normalizeSeriesByTime(sellPoints as { time: Time; value: number }[]))

            const markers = (result.trades || [])
                .filter(t => !!t.bar_time)
                .map(t => ({
                    time: toChartTime(t.bar_time),
                    position: t.side === 'buy' ? 'belowBar' : 'aboveBar',
                    color: t.side === 'buy' ? '#00aa66' : '#cc3333',
                    shape: t.side === 'buy' ? 'arrowUp' : 'arrowDown',
                    text: `${t.side.toUpperCase()} ${t.quantity} @ ${t.price.toFixed(2)}`,
                }))
            const markerSeries = priceSeries ?? eqSeries
            ;(markerSeries as { setMarkers?: (m: typeof markers) => void }).setMarkers?.(markers)

            const tooltip = document.createElement('div')
            tooltip.className = 'chart-trade-tooltip'
            tooltip.style.display = 'none'
            tooltip.style.whiteSpace = 'pre-line'
            const container = containerEl ?? null
            if (container) container.appendChild(tooltip)
            const toDayKeyFromSec = (sec: number): string => {
                const d = new Date(sec * 1000)
                const y = d.getUTCFullYear()
                const m = String(d.getUTCMonth() + 1).padStart(2, '0')
                const day = String(d.getUTCDate()).padStart(2, '0')
                return `${y}-${m}-${day}`
            }
            const tradesBySecond = new Map<string, RobotHistoryBacktestTrade[]>()
            const tradesByDay = new Map<string, RobotHistoryBacktestTrade[]>()
            for (const t of result.trades || []) {
                if (!t.bar_time) continue
                const sec = Number(toChartTime(t.bar_time))
                const sk = String(sec)
                const dk = toDayKeyFromSec(sec)
                const a = tradesBySecond.get(sk) ?? []
                a.push(t)
                tradesBySecond.set(sk, a)
                const b = tradesByDay.get(dk) ?? []
                b.push(t)
                tradesByDay.set(dk, b)
            }
            chart.subscribeCrosshairMove((param: any) => {
                if (!param?.time || !param?.point || !container) {
                    tooltip.style.display = 'none'
                    setChartLegend(prev => ({ ...prev, time: '' }))
                    return
                }
                const keySec = typeof param.time === 'number' ? String(param.time) : ''
                const keyDay =
                    typeof param.time === 'object' && param.time && 'year' in param.time
                        ? `${(param.time as { year: number }).year}-${String((param.time as { month: number }).month).padStart(2, '0')}-${String((param.time as { day: number }).day).padStart(2, '0')}`
                        : typeof param.time === 'number'
                          ? toDayKeyFromSec(param.time)
                          : ''
                const seriesData = param.seriesData
                const eqPoint = seriesData?.get?.(eqSeries)
                const pxPoint = priceSeries ? seriesData?.get?.(priceSeries) : undefined
                const equity = eqPoint?.value != null ? Number(eqPoint.value) : undefined
                const price = pxPoint?.value != null ? Number(pxPoint.value) : undefined
                setChartLegend({ time: formatLegendTime(param.time), equity, price })
                const buyPoint = seriesData?.get?.(buyPointsSeries)
                const sellPoint = seriesData?.get?.(sellPointsSeries)
                const sideHint: 'buy' | 'sell' | null =
                    buyPoint?.value != null ? 'buy' : sellPoint?.value != null ? 'sell' : null
                const candidates = (tradesBySecond.get(keySec) ?? tradesByDay.get(keyDay) ?? []).filter(
                    t => !sideHint || t.side === sideHint,
                )
                const trade = candidates[0]
                if (!trade) {
                    tooltip.style.display = 'none'
                    return
                }
                tooltip.style.display = 'block'
                const yOnPrice = (markerSeries as { priceToCoordinate?: (p: number) => number }).priceToCoordinate?.(
                    trade.price,
                )
                const tx = param.point.x + 12
                const ty = Number.isFinite(yOnPrice) ? Number(yOnPrice) - 18 : param.point.y + 12
                tooltip.style.left = `${tx}px`
                tooltip.style.top = `${ty}px`
                const total = trade.price * trade.quantity
                tooltip.textContent =
                    `${trade.side.toUpperCase()} ${formatLegendTime(param.time)}\n` +
                    `Объём: ${trade.quantity} шт\n` +
                    `Цена/ед: ${trade.price.toFixed(2)}\n` +
                    `Сумма: ${total.toFixed(2)}`
            })
            chart.timeScale().fitContent()
        },
        [result, fromDate, priceCurve, selectedRobot, interval, setChartLegend],
    )

    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card testing-equity-chart">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                КРИВАЯ КАПИТАЛА И ЦЕНА АКТИВА
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="form-hint" style={{ marginBottom: 8 }}>
                <span style={{ color: '#0066cc', marginRight: 12 }}>■ Капитал</span>
                <span style={{ color: '#9b7cff', marginRight: 12 }}>■ Цена актива</span>
                <span style={{ color: '#00aa66', marginRight: 12 }}>● Покупка</span>
                <span style={{ color: '#cc3333', marginRight: 12 }}>● Продажа</span>
                {chartLegend.time && (
                    <span style={{ marginLeft: 12 }}>
                        {chartLegend.time}
                        {chartLegend.equity != null ? ` | Капитал: ${chartLegend.equity.toFixed(2)}` : ''}
                        {chartLegend.price != null ? ` | Цена: ${chartLegend.price.toFixed(2)}` : ''}
                    </span>
                )}
            </div>
            <Chart
                height={chartHeight}
                className="testing-equity-chart__canvas"
                onReady={onChartReady}
                key={`bt-${result.final_equity}-${result.equity_curve.length}-${priceCurve.length}`}
            />
        </Card>
    )
}
