import React, { type Dispatch, type SetStateAction } from 'react'
import type { Time } from '@/components/ui/Chart'
import type { Robot, RobotHistoryBacktestResult } from '@/types/robot'
import { ResultsDashboard } from '@/pages/testing/refactored/components/analysis/ResultsDashboard'
import { EquityChartPanel } from '@/pages/testing/refactored/components/analysis/EquityChartPanel'
import { ResultDetailsTabs } from '@/pages/testing/refactored/components/analysis/ResultDetailsTabs'
import { ResultExportActions } from '@/pages/testing/refactored/components/analysis/ResultExportActions'
import { resolveResultCurrencyLabel } from '@/pages/testing/refactored/components/analysis/resultCurrency'

export type TestingAnalysisPanelProps = {
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

/** T4 — Analysis stage: KPI, chart, tabs, export. */
export function TestingAnalysisPanel({
    result,
    priceCurve,
    fromDate,
    selectedRobot,
    interval,
    isCrypto = false,
    chartLegend,
    setChartLegend,
    runSignals,
    runOrders,
    runPortfolioSnapshots,
    activeDetailsTab,
    setActiveDetailsTab,
    onExportToast,
}: TestingAnalysisPanelProps) {
    const currencyLabel = resolveResultCurrencyLabel(isCrypto)

    return (
        <div className="testing-analysis-panel">
            <div className="testing-analysis-panel__toolbar">
                <ResultExportActions
                    result={result}
                    onCopied={() => onExportToast?.('JSON скопирован в буфер')}
                    onDownloaded={() => onExportToast?.('JSON сохранён')}
                />
                <span className="form-hint testing-analysis-panel__currency">Валюта KPI: {currencyLabel}</span>
            </div>
            <ResultsDashboard result={result} currencyLabel={currencyLabel} isCrypto={isCrypto} />
            <EquityChartPanel
                result={result}
                priceCurve={priceCurve}
                fromDate={fromDate}
                selectedRobot={selectedRobot}
                interval={interval}
                chartLegend={chartLegend}
                setChartLegend={setChartLegend}
            />
            <ResultDetailsTabs
                result={result}
                isCrypto={isCrypto}
                runSignals={runSignals}
                runOrders={runOrders}
                runPortfolioSnapshots={runPortfolioSnapshots}
                activeDetailsTab={activeDetailsTab}
                setActiveDetailsTab={setActiveDetailsTab}
            />
        </div>
    )
}
