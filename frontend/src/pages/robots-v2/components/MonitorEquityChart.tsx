import React from 'react'
import { Card } from '@/components/ui/Card'
import { Chart } from '@/components/ui/Chart'
import type { IChartApi } from '@/components/ui/Chart'

type MonitorEquityChartProps = {
    onReady: (chart: IChartApi | null) => void
}

export function MonitorEquityChart({ onReady }: MonitorEquityChartProps) {
    return (
        <Card className="dashboard-assets-card robots-v2-monitor-chart robots-v2-cockpit-chart-card">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Equity сессии</h3>
            </div>
            <div className="robots-v2-cockpit-chart-card__body">
                <Chart height={188} onReady={onReady} />
            </div>
        </Card>
    )
}
