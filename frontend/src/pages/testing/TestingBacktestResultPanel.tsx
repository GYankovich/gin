import React, { type Dispatch, type SetStateAction } from 'react'
import type { Time } from '@/components/ui/Chart'
import type { Robot, RobotHistoryBacktestResult } from '@/types/robot'
import { TestingAnalysisPanel } from '@/pages/testing/refactored/components/analysis/TestingAnalysisPanel'

export type TestingBacktestResultPanelProps = {
    result: RobotHistoryBacktestResult
    priceCurve: Array<{ time: Time; value: number }>
    fromDate: string
    selectedRobot: Robot | null
    interval: string
    isCrypto?: boolean
    chartLegend: { time: string; equity?: number; price?: number }
    setChartLegend: Dispatch<SetStateAction<{ time: string; equity?: number; price?: number }>>
    runSignals: Array<Record<string, unknown>>
    runOrders: Array<Record<string, unknown>>
    runPortfolioSnapshots: Array<Record<string, unknown>>
    activeDetailsTab: 'trades' | 'signals' | 'orders' | 'portfolio'
    setActiveDetailsTab: Dispatch<SetStateAction<'trades' | 'signals' | 'orders' | 'portfolio'>>
    onExportToast?: (message: string) => void
}

/** Legacy alias — delegates to T4 `TestingAnalysisPanel`. */
export function TestingBacktestResultPanel(props: TestingBacktestResultPanelProps) {
    return <TestingAnalysisPanel {...props} />
}
