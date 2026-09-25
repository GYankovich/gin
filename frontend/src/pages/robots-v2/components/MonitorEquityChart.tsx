import React from 'react'
import { Card } from '@/components/ui/Card'
import { Chart } from '@/components/ui/Chart'
import type { IChartApi } from '@/components/ui/Chart'

type MonitorEquityChartProps = {
    onReady: (chart: IChartApi | null) => void
}

export function MonitorEquityChart({ onReady }: MonitorEquityChartProps) {
    return (
        <Card className="dashboard-assets-card robots-v2-monitor-chart">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">График equity</h3>
            </div>
            <Chart height={280} onReady={onReady} />
        </Card>
    )
}
