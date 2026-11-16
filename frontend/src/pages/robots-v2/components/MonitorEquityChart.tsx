import React from 'react'
import { Chart } from '@/components/ui/Chart'
import type { IChartApi } from '@/components/ui/Chart'
import { useMediaQuery } from '@/hooks/useMediaQuery'

type MonitorEquityChartProps = {
    onReady: (chart: IChartApi | null) => void
}

export function MonitorEquityChart({ onReady }: MonitorEquityChartProps) {
    const narrow = useMediaQuery('(max-width: 767px)')
    return (
        <div className="robots-monitor-chart">
            <Chart height={narrow ? 160 : 220} onReady={onReady} />
        </div>
    )
}
