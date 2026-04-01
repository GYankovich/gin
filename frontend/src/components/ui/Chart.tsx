import React, { useRef, useEffect } from 'react'
import { createChart, IChartApi, DeepPartial, ChartOptions, ISeriesApi, Time } from 'lightweight-charts'

interface ChartProps {
    height?: number
    className?: string
    onReady?: (chart: IChartApi) => void
}

export function Chart({ height = 360, className = '', onReady }: ChartProps) {
    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi | null>(null)

    useEffect(() => {
        if (!containerRef.current) return

        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'

        const chart = createChart(containerRef.current, {
            height,
            layout: {
                background: { color: 'transparent' },
                textColor: isDark ? '#888888' : '#666666',
                fontFamily: "'Inter', sans-serif",
            },
            grid: {
                vertLines: { color: isDark ? 'rgba(0,255,255,0.06)' : 'rgba(0,0,0,0.06)' },
                horzLines: { color: isDark ? 'rgba(0,255,255,0.06)' : 'rgba(0,0,0,0.06)' },
            },
            crosshair: { mode: 0 },
            rightPriceScale: { borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)' },
            timeScale: { borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)' },
        } as DeepPartial<ChartOptions>)

        chartRef.current = chart
        onReady?.(chart)

        const ro = new ResizeObserver(() => {
            if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
        })
        ro.observe(containerRef.current)

        return () => {
            ro.disconnect()
            chart.remove()
        }
    }, [height, onReady])

    return <div ref={containerRef} className={`chart-container ${className}`} />
}

export type { IChartApi, ISeriesApi, Time }
