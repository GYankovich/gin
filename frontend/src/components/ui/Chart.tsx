///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiChart [1]
///@ Исходный модуль `frontend/src/components/ui/Chart.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { useRef, useEffect } from 'react'
import { createChart, IChartApi, DeepPartial, ChartOptions, ISeriesApi, Time } from 'lightweight-charts'

interface ChartProps {
    height?: number
    className?: string
    /** Second argument is the chart container div (for tooltips / overlays). Pass null on unmount. */
    onReady?: (chart: IChartApi | null, container?: HTMLDivElement | null) => void
}

export function Chart({ height = 360, className = '', onReady }: ChartProps) {
    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const onReadyRef = useRef(onReady)

    useEffect(() => {
        onReadyRef.current = onReady
    }, [onReady])

    useEffect(() => {
        if (!containerRef.current) return

        const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        const el = containerRef.current
        const initialWidth = Math.max(el.clientWidth || 0, 1)

        const chart = createChart(el, {
            width: initialWidth,
            height,
            layout: {
                background: { color: 'transparent' },
                textColor: isDark ? '#9ca3af' : '#6b7280',
                fontFamily: "'Inter', sans-serif",
                fontSize: 12,
            },
            grid: {
                vertLines: { color: isDark ? 'rgba(148,163,184,0.09)' : 'rgba(15,23,42,0.06)' },
                horzLines: { color: isDark ? 'rgba(148,163,184,0.09)' : 'rgba(15,23,42,0.06)' },
            },
            crosshair: {
                mode: 0,
                vertLine: {
                    width: 1,
                    color: isDark ? 'rgba(203,213,225,0.45)' : 'rgba(71,85,105,0.45)',
                    style: 2,
                    labelVisible: true,
                },
                horzLine: {
                    width: 1,
                    color: isDark ? 'rgba(203,213,225,0.35)' : 'rgba(71,85,105,0.35)',
                    style: 2,
                    labelVisible: true,
                },
            },
            rightPriceScale: {
                borderColor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)',
                scaleMargins: { top: 0.1, bottom: 0.1 },
            },
            timeScale: {
                borderColor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)',
                timeVisible: true,
                secondsVisible: false,
                minBarSpacing: 4,
                rightOffset: 6,
            },
            handleScroll: {
                mouseWheel: true,
                pressedMouseMove: true,
                horzTouchDrag: true,
                vertTouchDrag: false,
            },
            handleScale: {
                axisPressedMouseMove: true,
                mouseWheel: true,
                pinch: true,
            },
        } as DeepPartial<ChartOptions>)

        chartRef.current = chart
        onReadyRef.current?.(chart, el)

        const ro = new ResizeObserver(() => {
            if (!containerRef.current) return
            const w = containerRef.current.clientWidth
            if (w > 0) chart.applyOptions({ width: w })
        })
        ro.observe(el)
        // Grid/flex parents often report 0 on the first paint — retry once after layout.
        requestAnimationFrame(() => {
            if (!containerRef.current || chartRef.current !== chart) return
            const w = containerRef.current.clientWidth
            if (w > 0) chart.applyOptions({ width: w })
        })

        return () => {
            ro.disconnect()
            onReadyRef.current?.(null, null)
            chart.remove()
            chartRef.current = null
        }
    }, [height])

    return (
        <div
            ref={containerRef}
            className={`chart-container ${className}`}
            style={{ width: '100%', minHeight: height }}
        />
    )
}

export type { IChartApi, ISeriesApi, Time }
