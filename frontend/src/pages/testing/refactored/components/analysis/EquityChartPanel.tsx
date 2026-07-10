import React, { type Dispatch, type SetStateAction } from 'react'
import type { Time } from '@/components/ui/Chart'
import type { Robot, RobotHistoryBacktestResult } from '@/types/robot'
import { TestingBacktestEquityChart } from '@/pages/testing/TestingBacktestEquityChart'

export type EquityChartPanelProps = {
    result: RobotHistoryBacktestResult
    priceCurve: Array<{ time: Time; value: number }>
    fromDate: string
    selectedRobot: Robot | null
    interval: string
    chartLegend: { time: string; equity?: number; price?: number }
    setChartLegend: Dispatch<SetStateAction<{ time: string; equity?: number; price?: number }>>
}

/** T4.2 — equity chart wrapper. */
export function EquityChartPanel(props: EquityChartPanelProps) {
    const { result, priceCurve, fromDate, selectedRobot, interval, chartLegend, setChartLegend } = props
    return (
        <TestingBacktestEquityChart
            key={`bt-${result.final_equity}-${result.equity_curve.length}-${priceCurve.length}`}
            result={result}
            fromDate={fromDate}
            priceCurve={priceCurve}
            selectedRobot={selectedRobot}
            interval={interval}
            chartLegend={chartLegend}
            setChartLegend={setChartLegend}
        />
    )
}
