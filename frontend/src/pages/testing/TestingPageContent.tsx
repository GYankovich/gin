import React, { useCallback, useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import cyberHero from '@/assets/dashboard/cyber-hero.png'
import { useToast } from '@/components/ui/Toast'
import { robotMatchesMarket, strategyOptionsForMarket } from '@/pages/testing/refactored/market'
import { isCryptoMarket } from '@/pages/testing/refactored/visibility'
import { HistoryPanel } from '@/pages/testing/refactored/components/analysis/HistoryPanel'
import { TestingBacktestResultPanel } from '@/pages/testing/TestingBacktestResultPanel'
import { RunControlPanel } from '@/pages/testing/refactored/components/run/RunControlPanel'
import { RunPhaseStepper } from '@/pages/testing/refactored/components/run/RunPhaseStepper'
import { RunStatusLog } from '@/pages/testing/refactored/components/run/RunStatusLog'
import { TestingSectionState } from '@/pages/testing/TestingSectionState'
import { Button } from '@/components/ui/Button'
import type { TestingPageController } from '@/pages/testing/hooks/useTestingPage'
import { MarketSelector } from '@/pages/testing/refactored/components/MarketSelector'
import { TimeDataPanel } from '@/pages/testing/refactored/components/setup/TimeDataPanel'
import { SignalGenerationPanel } from '@/pages/testing/refactored/components/setup/SignalGenerationPanel'
import { RiskSetupPanel } from '@/pages/testing/refactored/components/setup/RiskSetupPanel'
import { UniverseScreeningPanel } from '@/pages/testing/refactored/components/setup/UniverseScreeningPanel'
import { RecommendationsPanel } from '@/pages/testing/refactored/components/setup/RecommendationsPanel'
import { OptimizationPanel } from '@/pages/testing/refactored/components/setup/OptimizationPanel'
import { SetupValidateBar } from '@/pages/testing/refactored/components/setup/SetupValidateBar'
import { saveTestingConfigSnapshot } from '@/pages/testing/refactored/testingConfigStorage'
import { legacyFormToTestingFormState } from '@/pages/testing/refactored/formAdapter'
import {
    formatValidationIssuesForToast,
    issuesToInvalidFields,
} from '@/pages/testing/refactored/setupValidation'
import { periodSpanDays } from '@/pages/testing/refactored/validation'
import {
    hasBlockingValidationIssues,
    validateTestingFormAsync,
} from '@/pages/testing/refactored/validationAsync'
import { useTestingWizardStep } from '@/pages/testing/refactored/hooks/useTestingWizardStep'
import { useRecommendationActions, buildFormActions } from '@/pages/testing/hooks/useRecommendationActions'
import { TestingWizard } from '@/pages/testing/refactored/components/wizard/TestingWizard'
import { wizardStepSubtitle } from '@/pages/testing/refactored/wizard/types'

export function TestingPageContent({
    form,
    backtest,
    recommendations,
    optimization,
}: TestingPageController) {
    const toast = useToast()
    const recActions = useRecommendationActions(form)
    const isCrypto = isCryptoMarket(form.market)
    const canRunBacktest = useMemo(() => {
        if (!form.fromDate || !form.toDate) return false
        if (form.invalid.period) return false
        if (form.selectedRobot && form.selectedRobot.type !== 2) return false
        if (isCrypto && form.cryptoUniverseMode === 'fixed' && !form.fixedTickersText.trim()) return false
        if (!isCrypto && form.universeMode === 'fixed' && !form.fixedTickersText.trim()) return false
        return true
    }, [form.fromDate, form.toDate, form.invalid.period, form.selectedRobot, isCrypto, form.universeMode, form.cryptoUniverseMode, form.fixedTickersText])

    const hasResult = Boolean(backtest.result)
    const { step, setStep, goRun, goAnalysis, goSetup, goOptimize } = useTestingWizardStep({
        running: backtest.running,
        hasResult,
    })

    const subtitle = wizardStepSubtitle(step)

    const robotsForMarket = useMemo(
        () =>
            form.robots.filter(
                r => r.type !== 2 || robotMatchesMarket(r, form.market),
            ),
        [form.robots, form.market],
    )

    const strategyOptionsForMarketList = useMemo(
        () => strategyOptionsForMarket(form.strategyOptions, form.market),
        [form.strategyOptions, form.market],
    )

    const handleMarketChange = (next: typeof form.market) => {
        const { robotCleared } = form.setMarket(next)
        if (robotCleared) {
            toast.show('Робот снят — выбран другой рынок', 'info', 3500)
        }
    }

    const testingFormState = useMemo(
        () =>
            legacyFormToTestingFormState({
                robotId: form.robotId,
                brokerType: form.brokerType,
                fromDate: form.fromDate,
                toDate: form.toDate,
                capital: form.capital,
                strategy: form.strategy,
                strategyParams: form.strategyParams,
                interval: form.interval,
                stopLossPct: form.stopLossPct,
                takeProfitPct: form.takeProfitPct,
                maxPositionPct: form.maxPositionPct,
                maxPositionRub: form.maxPositionRub,
                maxDailyLoss: form.maxDailyLoss,
                slippagePct: form.slippagePct,
                executionLatencySec: form.executionLatencySec,
                maxDrawdownPct: form.maxDrawdownPct,
                tradingHoursStart: form.tradingHoursStart,
                tradingHoursEnd: form.tradingHoursEnd,
                allowedWeekdays: form.allowedWeekdays,
                brokerCommissionPct: form.brokerCommissionPct,
                ndflPct: form.ndflPct,
                pipelineMode: form.pipelineMode,
                filters: form.filters,
                universeMode: form.universeMode,
                universeRefreshMinutes: form.universeRefreshMinutes,
                fixedTickersText: form.fixedTickersText,
                cryptoUniverseMode: form.cryptoUniverseMode,
                cryptoMinVolume24hUsd: form.cryptoMinVolume24hUsd,
                cryptoMinLastPrice: form.cryptoMinLastPrice,
                cryptoMaxSpreadBps: form.cryptoMaxSpreadBps,
                cryptoMaxFundingRatePct: form.cryptoMaxFundingRatePct,
                cryptoMinFundingRatePct: form.cryptoMinFundingRatePct,
                cryptoMinOpenInterestUsd: form.cryptoMinOpenInterestUsd,
                cryptoMinLsr: form.cryptoMinLsr,
                cryptoMaxLsr: form.cryptoMaxLsr,
                cryptoMinRvol: form.cryptoMinRvol,
                cryptoMinAtrPercent: form.cryptoMinAtrPercent,
                cryptoMaxAtrPercent: form.cryptoMaxAtrPercent,
                cryptoLookbackDays: form.cryptoLookbackDays,
                bybitTestnet: form.bybitTestnet,
                instrumentCategory: form.instrumentCategory,
                leverage: form.leverage,
                makerFeePct: form.makerFeePct,
                takerFeePct: form.takerFeePct,
                fundingMode: form.fundingMode,
                backtestExecution: form.backtestExecution,
                backtestFeeModel: form.backtestFeeModel,
                maintenanceMarginPct: form.maintenanceMarginPct,
                pollValue: form.pollValue,
                pollUnit: form.pollUnit,
            }),
        [
            form.robotId,
            form.brokerType,
            form.fromDate,
            form.toDate,
            form.capital,
            form.strategy,
            form.strategyParams,
            form.interval,
            form.stopLossPct,
            form.takeProfitPct,
            form.maxPositionPct,
            form.maxPositionRub,
            form.maxDailyLoss,
            form.slippagePct,
            form.executionLatencySec,
            form.maxDrawdownPct,
            form.tradingHoursStart,
            form.tradingHoursEnd,
            form.allowedWeekdays,
            form.brokerCommissionPct,
            form.ndflPct,
            form.pipelineMode,
            form.filters,
            form.universeMode,
            form.universeRefreshMinutes,
            form.fixedTickersText,
            form.cryptoUniverseMode,
            form.cryptoMinVolume24hUsd,
            form.cryptoMinLastPrice,
            form.cryptoMaxSpreadBps,
            form.cryptoMaxFundingRatePct,
            form.cryptoMinFundingRatePct,
            form.cryptoMinOpenInterestUsd,
            form.cryptoMinLsr,
            form.cryptoMaxLsr,
            form.cryptoMinRvol,
            form.cryptoMinAtrPercent,
            form.cryptoMaxAtrPercent,
            form.cryptoLookbackDays,
            form.bybitTestnet,
            form.instrumentCategory,
            form.leverage,
            form.makerFeePct,
            form.takerFeePct,
            form.fundingMode,
            form.backtestExecution,
            form.backtestFeeModel,
            form.maintenanceMarginPct,
            form.pollValue,
            form.pollUnit,
        ],
    )

    const handleValidateSetup = useCallback(() => {
        void (async () => {
            const issues = await validateTestingFormAsync(testingFormState, {
                robotType: form.selectedRobot?.type ?? null,
            })
            if (hasBlockingValidationIssues(issues)) {
                form.setInvalid(issuesToInvalidFields(issues.filter(i => i.severity !== 'warning')))
                toast.show(formatValidationIssuesForToast(issues.filter(i => i.severity !== 'warning')), 'error', 7000)
                return
            }
            form.setInvalid({})
            const warnings = issues.filter(i => i.severity === 'warning')
            if (warnings.length > 0) {
                toast.show(formatValidationIssuesForToast(warnings), 'warning', 6000)
            }
            const span = periodSpanDays(form.fromDate, form.toDate)
            const marketLabel = form.market === 'crypto' ? 'Crypto' : 'MOEX'
            toast.show(
                `Конфигурация готова к запуску (${marketLabel}${span != null ? `, ~${span} дн.` : ''})`,
                'success',
                4000,
            )
        })()
    }, [testingFormState, form, toast])

    const handleRunBacktest = useCallback(() => {
        goRun()
        void backtest.runBacktest()
    }, [goRun, backtest])

    const historyPanelProps = useMemo(
        () => ({
            historyLoading: backtest.historyLoading,
            historyError: backtest.historyError,
            onRefresh: backtest.refreshHistoryBacktests,
            historyRuns: backtest.historyRuns,
            filteredHistoryRuns: backtest.filteredHistoryRuns,
            historySearch: backtest.historySearch,
            onHistorySearchChange: backtest.setHistorySearch,
            historyMinReturn: backtest.historyMinReturn,
            onHistoryMinReturnChange: backtest.setHistoryMinReturn,
            historyMarketFilter: backtest.historyMarketFilter,
            onHistoryMarketFilterChange: backtest.setHistoryMarketFilter,
            historyStatusFilter: backtest.historyStatusFilter,
            onHistoryStatusFilterChange: backtest.setHistoryStatusFilter,
            compareLeftId: backtest.compareLeftId,
            onCompareLeftIdChange: backtest.setCompareLeftId,
            compareRightId: backtest.compareRightId,
            onCompareRightIdChange: backtest.setCompareRightId,
            onOpenRun: (r: Parameters<typeof backtest.openHistoryBacktestRun>[0]) => {
                goAnalysis()
                void backtest.openHistoryBacktestRun(r)
            },
        }),
        [backtest, goAnalysis],
    )

    const optimizationPanelProps = useMemo(
        () => ({
            hasBacktestResult: hasResult,
            robotId: form.robotId,
            goal: optimization.goal,
            onGoalChange: (g: typeof optimization.goal) => {
                optimization.setGoal(g)
            },
            rankData: optimization.rankData,
            sessionFailures: optimization.sessionFailures,
            planData: optimization.planData,
            batchData: optimization.batchData,
            loadingRank: optimization.loadingRank,
            loadingPlan: optimization.loadingPlan,
            startingBatch: optimization.startingBatch,
            error: optimization.error,
            onRefreshRank: () => void optimization.refreshRank(),
            onLoadPlan: (mode: 'speed' | 'full') => void optimization.loadPlan(mode),
            onRunBatch: (mode: 'speed' | 'full') => {
                if (!form.robotId) return
                void optimization
                    .runBatch(mode, {
                        fromDate: form.fromDate,
                        toDate: form.toDate,
                        initialCapital: form.capital,
                    })
                    .then(started => {
                        if (started) {
                            toast.show(
                                `Сетка запущена: ${started.enqueued} прогонов (batch #${started.batch_id})`,
                                'success',
                                4000,
                            )
                        }
                    })
            },
            onCancelBatch: () => void optimization.cancelBatch(),
            canRunBatch: canRunBacktest && Boolean(form.robotId),
            formActions: buildFormActions(form),
            onApplied: () => {
                form.setConfigDirty(true)
                toast.show('Параметры применены в форму', 'success', 2500)
            },
            onOpenBacktestRun: (runId: number) => {
                goAnalysis()
                void backtest.openHistoryBacktestRunById(runId)
            },
        }),
        [hasResult, form, optimization, canRunBacktest, toast, backtest, goAnalysis],
    )

    const setupStage = (
        <>
            <MarketSelector
                className="testing-market-selector--page"
                value={form.market}
                onChange={handleMarketChange}
            />
            <TimeDataPanel
                market={form.market}
                testName={form.testName}
                onTestNameChange={form.setTestName}
                robots={robotsForMarket}
                robotId={form.robotId}
                onRobotIdChange={form.setRobotId}
                invalidPeriod={!!form.invalid.period}
                fromDate={form.fromDate}
                toDate={form.toDate}
                onFromDateChange={form.setFromDate}
                onToDateChange={form.setToDate}
                interval={form.interval}
                onIntervalChange={form.setInterval}
                tradingHoursStart={form.tradingHoursStart}
                onTradingHoursStartChange={form.setTradingHoursStart}
                tradingHoursEnd={form.tradingHoursEnd}
                onTradingHoursEndChange={form.setTradingHoursEnd}
                allowedWeekdays={form.allowedWeekdays}
                onAllowedWeekdaysChange={form.setAllowedWeekdays}
                onConfigDirty={() => form.setConfigDirty(true)}
            />
            <UniverseScreeningPanel
                market={form.market}
                filters={form.filters}
                universeMode={form.universeMode}
                onUniverseModeChange={form.setUniverseMode}
                cryptoUniverseMode={form.cryptoUniverseMode}
                onCryptoUniverseModeChange={form.setCryptoUniverseMode}
                fixedTickersText={form.fixedTickersText}
                onFixedTickersTextChange={form.setFixedTickersText}
                universeRefreshMinutes={form.universeRefreshMinutes}
                onUniverseRefreshMinutesChange={form.setUniverseRefreshMinutes}
                onConfigDirty={() => form.setConfigDirty(true)}
                cryptoPipeline={
                    isCrypto && form.cryptoUniverseMode !== 'fixed'
                        ? {
                              filters: form.cryptoFilters,
                              setFilters: form.setCryptoFilters,
                              onAddFilter: form.addCryptoFilter,
                              onRemoveFilter: form.removeCryptoFilter,
                              onConfigDirty: () => form.setConfigDirty(true),
                          }
                        : null
                }
                pipeline={
                    !isCrypto && form.universeMode !== 'fixed'
                        ? {
                              pipelineMode: form.pipelineMode,
                              onPipelineModeChange: mode => {
                                  form.setPipelineMode(mode)
                                  form.setConfigDirty(true)
                              },
                              filters: form.filters,
                              setFilters: form.setFilters,
                              onAddFilter: form.addFilter,
                              onRemoveFilter: form.removeFilter,
                              onConfigDirty: () => form.setConfigDirty(true),
                          }
                        : null
                }
            />
            <SignalGenerationPanel
                market={form.market}
                strategyOptions={strategyOptionsForMarketList}
                strategy={form.strategy}
                onStrategyChange={form.setStrategy}
                params={form.strategyParams}
                onParamChange={form.setStrategyParam}
                onConfigDirty={() => form.setConfigDirty(true)}
                pollValue={form.pollValue}
                onPollValueChange={form.setPollValue}
                pollUnit={form.pollUnit}
                onPollUnitChange={form.setPollUnit}
            />
            <RiskSetupPanel
                market={form.market}
                onConfigDirty={() => form.setConfigDirty(true)}
                risk={{
                    capital: form.capital,
                    onCapitalChange: form.setCapital,
                    brokerCommissionPct: form.brokerCommissionPct,
                    onBrokerCommissionPctChange: form.setBrokerCommissionPct,
                    ndflPct: form.ndflPct,
                    onNdflPctChange: form.setNdflPct,
                    stopLossPct: form.stopLossPct,
                    onStopLossPctChange: form.setStopLossPct,
                    takeProfitPct: form.takeProfitPct,
                    onTakeProfitPctChange: form.setTakeProfitPct,
                    maxPositionPct: form.maxPositionPct,
                    onMaxPositionPctChange: form.setMaxPositionPct,
                    maxPositionRub: form.maxPositionRub,
                    onMaxPositionRubChange: form.setMaxPositionRub,
                maxDailyLoss: form.maxDailyLoss,
                onMaxDailyLossChange: form.setMaxDailyLoss,
                slippagePct: form.slippagePct,
                onSlippagePctChange: form.setSlippagePct,
                executionLatencySec: form.executionLatencySec,
                onExecutionLatencySecChange: form.setExecutionLatencySec,
                maxDrawdownPct: form.maxDrawdownPct,
                onMaxDrawdownPctChange: form.setMaxDrawdownPct,
                    showMinProfitTarget: form.strategy === 'grain_seed' && !isCrypto,
                    minProfitTargetPct:
                        form.strategy === 'grain_seed'
                            ? Number(form.strategyParams.min_profit_target_pct ?? 0.35)
                            : null,
                    onMinProfitTargetPctChange:
                        form.strategy === 'grain_seed'
                            ? v => form.setStrategyParam('min_profit_target_pct', v)
                            : undefined,
                }}
                crypto={
                    isCrypto
                        ? {
                              bybitTestnet: form.bybitTestnet,
                              onBybitTestnetChange: v => form.setBybitTestnet(v),
                              instrumentCategory: form.instrumentCategory,
                              onInstrumentCategoryChange: v => form.setInstrumentCategory(v),
                              leverage: form.leverage,
                              makerFeePct: form.makerFeePct,
                              onMakerFeePctChange: v => form.setMakerFeePct(v),
                              takerFeePct: form.takerFeePct,
                              onTakerFeePctChange: v => form.setTakerFeePct(v),
                              fundingMode: form.fundingMode,
                              onFundingModeChange: v => form.setFundingMode(v),
                              backtestExecution: form.backtestExecution,
                              onBacktestExecutionChange: v => form.setBacktestExecution(v),
                              maintenanceMarginPct: form.maintenanceMarginPct,
                          }
                        : undefined
                }
            />
            <RecommendationsPanel
                robotId={form.robotId}
                data={recommendations.data}
                loading={recommendations.loading}
                error={recommendations.error}
                refresh={recommendations.refresh}
                hasBacktestResult={hasResult}
                recommendations={recActions.filterVisible(recommendations.data?.recommendations)}
                onApply={recActions.applyItem}
                onDismiss={item => recActions.dismiss(item.id)}
                onClearDismissed={recActions.clearDismissed}
                dismissedCount={recActions.dismissedCount}
                canApply={recActions.canApply}
            />
            <SetupValidateBar
                onValidate={handleValidateSetup}
                onSave={() => {
                    saveTestingConfigSnapshot({
                        testName: form.testName,
                        market: form.market,
                        savedAt: new Date().toISOString(),
                        form: testingFormState,
                    })
                    toast.show('Конфигурация сохранена локально', 'success', 2500)
                }}
                onLaunch={handleRunBacktest}
                canLaunch={canRunBacktest}
                launching={backtest.running}
                disabled={backtest.running}
                statusText={
                    form.fromDate && form.toDate
                        ? `Период: ${form.fromDate} — ${form.toDate} · ${form.testName}`
                        : 'Укажите период бэктеста'
                }
            />
        </>
    )

    const runStage = (
        <>
            <RunControlPanel
                running={backtest.running}
                hasResult={hasResult}
                error={backtest.error}
                onRunBacktest={handleRunBacktest}
                configDirty={form.configDirty}
                canRunBacktest={canRunBacktest}
                invalidPeriod={!!form.invalid.period}
                onRefreshHistory={() => void backtest.refreshHistoryBacktests()}
                historyLoading={backtest.historyLoading}
                pollingRunId={backtest.pollingRunId}
                cancellingRun={backtest.cancellingRun}
                onCancelBacktest={backtest.cancelActivePoll}
                runProgress={backtest.runProgress}
                onBackToSetup={goSetup}
                statusLogCount={backtest.statusWindow.length}
                sticky
            />
            <RunPhaseStepper
                runPhase={backtest.runProgress?.runPhase ?? null}
                running={backtest.running}
                hasResult={hasResult}
                phaseUnitsDone={backtest.runProgress?.phaseUnitsDone}
                phaseUnitsTotal={backtest.runProgress?.phaseUnitsTotal}
            />
            {backtest.statusWindow.length > 0 && (
                <Card className="mb-6 cyber-form-card testing-cyber-card testing-run-status-card">
                    <RunStatusLog statusWindow={backtest.statusWindow} />
                </Card>
            )}
        </>
    )

    const analysisStage = (
        <section className="testing-analysis-stage testing-analysis-stage--solo">
            <div className="testing-analysis-stage__result">
                {backtest.result ? (
                    <TestingBacktestResultPanel
                        result={backtest.result}
                        priceCurve={backtest.priceCurve}
                        fromDate={form.fromDate}
                        selectedRobot={form.selectedRobot}
                        interval={form.interval}
                        isCrypto={isCrypto}
                        chartLegend={backtest.chartLegend}
                        setChartLegend={backtest.setChartLegend}
                        runSignals={backtest.runSignals}
                        runOrders={backtest.runOrders}
                        runPortfolioSnapshots={backtest.runPortfolioSnapshots}
                        activeDetailsTab={backtest.activeDetailsTab}
                        setActiveDetailsTab={backtest.setActiveDetailsTab}
                        onExportToast={msg => toast.show(msg, 'success', 2500)}
                    />
                ) : backtest.error ? (
                    <TestingSectionState title="РЕЗУЛЬТАТ БЭКТЕСТА" message={`Ошибка запуска: ${backtest.error}`} variant="error" />
                ) : (
                    <TestingSectionState
                        title="РЕЗУЛЬТАТ БЭКТЕСТА"
                        message="Запустите бэктест или откройте прогон из вкладки «Оптимизация»."
                        actionLabel="К истории прогонов"
                        onAction={goOptimize}
                    />
                )}
            </div>
            {!backtest.result && !backtest.error && (
                <p className="testing-analysis-stage__hint">
                    <Button size="sm" variant="ghost" onClick={goOptimize}>
                        История и сетка параметров → Оптимизация
                    </Button>
                </p>
            )}
        </section>
    )

    const optimizeStage = (
        <section className="testing-optimize-stage">
            <OptimizationPanel {...optimizationPanelProps} />
            <HistoryPanel {...historyPanelProps} />
        </section>
    )

    return (
        <div className="page" data-page="testing">
            <TestingHero subtitle={subtitle} />

            <TestingWizard
                step={step}
                onStepChange={setStep}
                running={backtest.running}
                hasResult={hasResult}
                setup={setupStage}
                run={runStage}
                analysis={analysisStage}
                optimize={optimizeStage}
            />
        </div>
    )
}

function TestingHero({ subtitle }: { subtitle: string }) {
    return (
        <header className="dashboard-hero">
            <div className="dashboard-hero__bg" style={{ backgroundImage: `url(${cyberHero})` }} aria-hidden />
            <div className="dashboard-hero__veil" aria-hidden />
            <div className="dashboard-hero__content">
                <p className="dashboard-hero__eyebrow">GIN // BACKTEST NODE</p>
                <h1 className="dashboard-hero__title">
                    <span className="dashboard-hero__title-glitch" data-text="ТЕСТИРОВАНИЕ">ТЕСТИРОВАНИЕ</span>
                </h1>
                <p className="dashboard-hero__sub">{subtitle}</p>
            </div>
        </header>
    )
}
