import React, { useEffect, useMemo, useRef } from 'react'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { BacktestResultsPanel } from '@/pages/robots-v2/components/BacktestResultsPanel'
import { BacktestVerdictCard } from '@/pages/robots-v2/components/BacktestVerdictCard'
import { RobotStageCard } from '@/pages/robots-v2/components/RobotStageCard'
import { collectReasonCodes } from '@/pages/robots-v2/backtestGuide'
import { formatBacktestPhaseUnits } from '@/pages/robots-v2/formatBacktestPhaseUnits'
import { toBacktestChartPoints } from '@/pages/robots-v2/backtestLabShared'
import type {
    BacktestFeeSummary,
    BacktestNarrativeStep,
    BacktestObservability,
    BacktestPortfolioSnapshot,
    RobotBacktestRunDetails,
    RobotHistoryBacktestResult,
} from '@/types/robot'
import type { IChartApi, ISeriesApi } from '@/components/ui/Chart'

type Props = {
    runId: number
    status: RobotBacktestRunDetails | null
    opening?: boolean
    error?: string | null
    onSaveAsRobot: () => void
}

export function BacktestRunWorkspace({
    runId,
    status,
    opening = false,
    error = null,
    onSaveAsRobot,
}: Props) {
    const chartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)

    const payload = (status?.result_payload || {}) as Partial<RobotHistoryBacktestResult>
    const equityCurve = payload.equity_curve || []
    const trades = payload.trades || []
    const runSignals = status?.signals ?? []
    const runOrders = status?.orders ?? []
    const dailySummary =
        status?.daily_summary
        ?? (payload as { daily_summary?: Array<Record<string, unknown>> }).daily_summary
        ?? []
    const feeSummary = (
        status?.fee_summary
        ?? payload.fee_summary
        ?? null
    ) as BacktestFeeSummary | null
    const portfolioSnapshots = (status?.portfolio_snapshots || []) as BacktestPortfolioSnapshot[]
    const narrative = (
        status?.narrative
        ?? (payload as { narrative?: BacktestNarrativeStep[] }).narrative
        ?? null
    ) as BacktestNarrativeStep[] | null
    const chartPoints = useMemo(() => toBacktestChartPoints(equityCurve), [equityCurve])

    useEffect(() => {
        const series = seriesRef.current
        if (!series) return
        series.setData(chartPoints)
    }, [chartPoints])

    const runStatus = String(status?.status || '').toUpperCase()
    const isActive = runStatus === 'RUNNING' || runStatus === 'QUEUED'
    const ret = payload.total_return_percent ?? status?.total_return_percent ?? null
    const dd = payload.max_drawdown_percent ?? status?.max_drawdown_percent ?? null
    const finalEq = payload.final_equity ?? status?.final_equity ?? null
    const winRate = payload.win_rate_percent ?? status?.win_rate_percent ?? null
    const sharpe = payload.sharpe_ratio ?? status?.sharpe_ratio ?? null
    const sortino = payload.sortino_ratio ?? status?.sortino_ratio ?? null
    const calmar = payload.calmar_ratio ?? status?.calmar_ratio ?? null
    const progress = Number(status?.progress_percent ?? 0)
    const phaseLabel = status?.phase_label || status?.run_phase || (isActive ? 'Запуск…' : '')
    const capital = Number(payload.initial_capital ?? status?.initial_capital ?? 0)

    if (opening && !status) {
        return (
            <Card className="dashboard-totals-card dashboard-skeleton-card">
                <Skeleton height="280px" />
            </Card>
        )
    }

    return (
        <>
            {(isActive || opening) && (
                <RobotStageCard
                    title={opening && !status ? 'Загрузка прогона…' : (phaseLabel || 'Прогон')}
                    progress={progress}
                    ariaLabel="Прогресс бэктеста"
                    meta={
                        status?.phase_units_total ? (
                            <span className="robots-v2-hint">
                                {formatBacktestPhaseUnits(
                                    status.run_phase,
                                    status.phase_units_done ?? 0,
                                    status.phase_units_total,
                                )}
                            </span>
                        ) : null
                    }
                />
            )}

            {(error || (runStatus === 'FAILED' && !isActive)) && (
                <Card className="dashboard-totals-card dashboard-error-card">
                    <p className="dashboard-empty">
                        {error || status?.error_message || 'Прогон завершился с ошибкой'}
                    </p>
                </Card>
            )}

            {runStatus === 'SUCCESS' && (
                <BacktestVerdictCard
                    totalReturnPercent={ret == null ? null : Number(ret)}
                    maxDrawdownPercent={dd == null ? null : Number(dd)}
                    winRatePercent={winRate == null ? null : Number(winRate)}
                    tradeCount={trades.length}
                    initialCapital={capital}
                    finalEquity={finalEq == null ? null : Number(finalEq)}
                    reasonCodes={collectReasonCodes(trades)}
                    onSaveAsRobot={onSaveAsRobot}
                />
            )}

            {(runStatus === 'SUCCESS'
                || (runStatus === 'CANCELLED' && !isActive && (
                    equityCurve.length > 0 || trades.length > 0 || runSignals.length > 0
                ))) && (
                <BacktestResultsPanel
                    key={runId}
                    runId={runId}
                    runStatus={runStatus}
                    partialResult={status?.partial_result ?? (runStatus === 'CANCELLED' ? true : null)}
                    capital={capital}
                    initialCapital={capital}
                    finalEquity={finalEq}
                    totalReturnPercent={ret}
                    maxDrawdownPercent={dd}
                    winRatePercent={winRate}
                    sharpeRatio={sharpe}
                    sortinoRatio={sortino}
                    calmarRatio={calmar}
                    stages={payload.stages}
                    historyStats={(payload.history_stats || null) as Record<string, unknown> | null}
                    fundingChargesTotal={
                        (payload as { funding_charges_total?: number | null }).funding_charges_total
                        ?? null
                    }
                    observability={
                        status?.observability
                        ?? (payload.observability as BacktestObservability | null | undefined)
                        ?? null
                    }
                    executionModel={
                        status?.execution_model
                        ?? (payload as { execution_model?: unknown }).execution_model
                        ?? null
                    }
                    feeSummary={feeSummary}
                    portfolioSnapshots={portfolioSnapshots}
                    narrative={narrative}
                    requestedFrom={status?.requested_from ?? null}
                    requestedTo={status?.requested_to ?? null}
                    signalsTotal={status?.signals_total ?? null}
                    trades={trades as unknown as Array<Record<string, unknown>>}
                    chartPoints={chartPoints}
                    signals={runSignals as unknown as Array<Record<string, unknown>>}
                    orders={runOrders as unknown as Array<Record<string, unknown>>}
                    dailySummary={dailySummary as unknown as Array<Record<string, unknown>>}
                    chartRef={chartRef}
                    seriesRef={seriesRef}
                />
            )}

            {runStatus === 'CANCELLED' && !isActive
                && equityCurve.length === 0 && trades.length === 0 && runSignals.length === 0 && (
                <Card className="dashboard-totals-card">
                    <p className="dashboard-empty">Прогон отменён — артефактов нет</p>
                </Card>
            )}
        </>
    )
}
