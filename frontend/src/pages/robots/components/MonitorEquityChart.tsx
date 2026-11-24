import React from 'react'
import { Chart } from '@/components/ui/Chart'
import type { IChartApi } from '@/components/ui/Chart'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { formatPortfolioMoney, formatPortfolioMoneySigned } from '@/utils/portfolioFormat'

export type MonitorChartHover = {
    time: string
    value: number
    delta: number | null
    deltaPct: number | null
}

type MonitorEquityChartProps = {
    onReady: (chart: IChartApi | null) => void
    hover: MonitorChartHover | null
}

export function MonitorEquityChart({ onReady, hover }: MonitorEquityChartProps) {
    const narrow = useMediaQuery('(max-width: 767px)')
    return (
        <div className="robots-monitor-chart">
            <div
                className={`mono portfolio-crosshair-main${hover ? '' : ' portfolio-crosshair-main--idle'}`}
                aria-hidden={!hover}
            >
                {hover ? (
                    <>
                        <span className="portfolio-crosshair-main__value">
                            {formatPortfolioMoney(
                                hover.value,
                                'RUB',
                                Math.round(Math.abs(hover.value) * 100) % 100 !== 0 ? 2 : 0,
                            )}
                        </span>
                        {hover.delta != null ? (
                            <span
                                className={`portfolio-crosshair-main__delta${
                                    hover.delta >= 0 ? ' color-up' : ' color-down'
                                }`}
                            >
                                <span className="portfolio-crosshair-main__delta-abs">
                                    {formatPortfolioMoneySigned(hover.delta, 'RUB')}
                                </span>
                                {hover.deltaPct != null ? (
                                    <span className="portfolio-crosshair-main__delta-pct">
                                        ({hover.deltaPct >= 0 ? '+' : ''}
                                        {hover.deltaPct.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}
                                        %)
                                    </span>
                                ) : null}
                            </span>
                        ) : null}
                        <span className="portfolio-crosshair-main__time">{hover.time}</span>
                    </>
                ) : (
                    <span className="portfolio-crosshair-main__placeholder">&nbsp;</span>
                )}
            </div>
            <Chart height={narrow ? 120 : 220} onReady={onReady} />
        </div>
    )
}
