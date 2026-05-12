import React from 'react'
import { TestingBacktestHistoryCard } from '@/pages/testing/TestingBacktestHistoryCard'
import { TestingBacktestResultPanel } from '@/pages/testing/TestingBacktestResultPanel'
import { TestingBacktestRunSection } from '@/pages/testing/TestingBacktestRunSection'
import { TestingMoexCacheCard } from '@/pages/testing/TestingMoexCacheCard'
import { TestingRobotParamsCard } from '@/pages/testing/TestingRobotParamsCard'
import { TestingRiskParamsCard } from '@/pages/testing/TestingRiskParamsCard'
import { TestingPipelineCard } from '@/pages/testing/TestingPipelineCard'
import type { TestingPageController } from '@/pages/testing/hooks/useTestingPage'

export function TestingPageContent({ form, backtest, moexJob }: TestingPageController) {
    return (
        <div className="page" data-page="testing">
            <h1 className="page__title">Тестирование</h1>

            <TestingMoexCacheCard moex={moexJob} />

            <TestingRobotParamsCard
                robots={form.robots}
                robotId={form.robotId}
                onRobotIdChange={form.setRobotId}
                strategyOptions={form.strategyOptions}
                strategy={form.strategy}
                onStrategyChange={form.setStrategy}
                brokerType={form.brokerType}
                onBrokerTypeChange={form.setBrokerType}
                pollValue={form.pollValue}
                onPollValueChange={form.setPollValue}
                pollUnit={form.pollUnit}
                onPollUnitChange={form.setPollUnit}
                invalidPeriod={!!form.invalid.period}
                fromDate={form.fromDate}
                toDate={form.toDate}
                onFromDateChange={form.setFromDate}
                onToDateChange={form.setToDate}
                interval={form.interval}
                onIntervalChange={form.setInterval}
                onConfigDirty={() => form.setConfigDirty(true)}
            />

            <TestingRiskParamsCard
                capital={form.capital}
                onCapitalChange={form.setCapital}
                brokerCommissionPct={form.brokerCommissionPct}
                onBrokerCommissionPctChange={form.setBrokerCommissionPct}
                ndflPct={form.ndflPct}
                onNdflPctChange={form.setNdflPct}
                stopLossPct={form.stopLossPct}
                onStopLossPctChange={form.setStopLossPct}
                takeProfitPct={form.takeProfitPct}
                onTakeProfitPctChange={form.setTakeProfitPct}
                maxPositionPct={form.maxPositionPct}
                onMaxPositionPctChange={form.setMaxPositionPct}
                maxPositionRub={form.maxPositionRub}
                onMaxPositionRubChange={form.setMaxPositionRub}
                onConfigDirty={() => form.setConfigDirty(true)}
            />

            <TestingPipelineCard
                pipelineMode={form.pipelineMode}
                onPipelineModeChange={mode => {
                    form.setPipelineMode(mode)
                    form.setConfigDirty(true)
                }}
                filters={form.filters}
                setFilters={form.setFilters}
                onAddFilter={form.addFilter}
                onRemoveFilter={form.removeFilter}
                onConfigDirty={() => form.setConfigDirty(true)}
            />

            <TestingBacktestRunSection running={backtest.running} onRunBacktest={backtest.runBacktest} statusWindow={backtest.statusWindow} />

            {form.selectedRobot && (
                <TestingBacktestHistoryCard
                    historyLoading={backtest.historyLoading}
                    onRefresh={backtest.refreshHistoryBacktests}
                    historyRuns={backtest.historyRuns}
                    filteredHistoryRuns={backtest.filteredHistoryRuns}
                    historySearch={backtest.historySearch}
                    onHistorySearchChange={backtest.setHistorySearch}
                    historyMinReturn={backtest.historyMinReturn}
                    onHistoryMinReturnChange={backtest.setHistoryMinReturn}
                    compareLeftId={backtest.compareLeftId}
                    onCompareLeftIdChange={backtest.setCompareLeftId}
                    compareRightId={backtest.compareRightId}
                    onCompareRightIdChange={backtest.setCompareRightId}
                    onOpenRun={backtest.openHistoryBacktestRun}
                />
            )}

            {backtest.result && (
                <TestingBacktestResultPanel
                    result={backtest.result}
                    priceCurve={backtest.priceCurve}
                    fromDate={form.fromDate}
                    selectedRobot={form.selectedRobot}
                    interval={form.interval}
                    chartLegend={backtest.chartLegend}
                    setChartLegend={backtest.setChartLegend}
                    runSignals={backtest.runSignals}
                    runOrders={backtest.runOrders}
                    runPortfolioSnapshots={backtest.runPortfolioSnapshots}
                    activeDetailsTab={backtest.activeDetailsTab}
                    setActiveDetailsTab={backtest.setActiveDetailsTab}
                />
            )}
        </div>
    )
}
