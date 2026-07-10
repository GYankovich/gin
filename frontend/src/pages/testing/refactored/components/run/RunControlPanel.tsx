import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import {
    deriveRunControlState,
    runControlStateLabel,
    runControlSystemLabel,
    type RunControlState,
} from '@/pages/testing/refactored/components/run/runControlState'

export type RunControlPanelProps = {
    running: boolean
    hasResult: boolean
    error?: string | null
    onRunBacktest: () => void
    configDirty: boolean
    canRunBacktest: boolean
    invalidPeriod: boolean
    onRefreshHistory?: () => void
    historyLoading?: boolean
    pollingRunId?: number | null
    cancellingRun?: boolean
    onCancelBacktest?: () => void | Promise<void>
    runProgress?: {
        percent: number
        etaLabel: string | null
        phaseLabel: string | null
    } | null
    onBackToSetup?: () => void
    statusLogCount?: number
    sticky?: boolean
    className?: string
}

function badgeClass(state: RunControlState): string {
    if (state === 'running') return 'badge--cyan'
    if (state === 'success') return 'badge--up'
    if (state === 'error') return 'badge--down'
    return 'badge--neutral'
}

function dotClass(state: RunControlState): string {
    if (state === 'running') return 'status-dot--active status-dot--pulse'
    if (state === 'success') return 'status-dot--active'
    if (state === 'error') return 'status-dot--inactive'
    return 'status-dot--inactive'
}

/** T3.2 — sticky run control: IDLE / RUNNING / terminal (success | error). */
export function RunControlPanel({
    running,
    hasResult,
    error = null,
    onRunBacktest,
    configDirty,
    canRunBacktest,
    invalidPeriod,
    onRefreshHistory,
    historyLoading = false,
    pollingRunId = null,
    cancellingRun = false,
    onCancelBacktest,
    runProgress = null,
    onBackToSetup,
    statusLogCount = 0,
    sticky = true,
    className = '',
}: RunControlPanelProps) {
    const state = useMemo(
        () => deriveRunControlState({ running, hasResult, error }),
        [running, hasResult, error],
    )
    const runBlocked = running || invalidPeriod || !canRunBacktest
    const canCancel = Boolean(running && pollingRunId != null && onCancelBacktest)
    const lastUpdate = new Date().toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    })

    return (
        <>
            <Card
                className={`mb-6 cyber-form-card testing-cyber-card testing-state-card testing-run-control-panel testing-runbar${sticky ? ' testing-runbar--sticky' : ''} ${className}`.trim()}
                data-run-state={state}
            >
                <div className="testing-runbar__top">
                    <div className="testing-runbar__status-block">
                        <div className="testing-runbar__system-title">
                            <span className={`status-dot ${dotClass(state)}`} aria-hidden />
                            {runControlSystemLabel(state)}
                        </div>
                        <div className="testing-runbar__meta-text">
                            Обновлено: {lastUpdate}
                            {statusLogCount > 0 ? ` · ${statusLogCount} шаг(ов) в логе` : ''}
                        </div>
                        <div className="testing-runbar__meta">
                            <span className={`badge ${badgeClass(state)}`}>{runControlStateLabel(state)}</span>
                            {configDirty && (
                                <span className="form-hint color-warn">Параметры изменены после последнего запуска</span>
                            )}
                            {state === 'error' && error && (
                                <span className="form-hint color-down">{error}</span>
                            )}
                            {!canRunBacktest && state === 'idle' && !invalidPeriod && (
                                <span className="form-hint color-down">
                                    Укажите период тестирования (с / по). Если робот не выбран — в теле запроса уходит
                                    пресет риска `RobotRisk` (BRD-ARCH-03 §7). При выборе робота нужен type=2.
                                </span>
                            )}
                            {invalidPeriod && <span className="form-hint color-down">Проверьте интервал тестирования</span>}
                        </div>
                    </div>
                    <div className="testing-runbar__actions">
                        {onBackToSetup && !running && (
                            <Button size="sm" variant="ghost" onClick={onBackToSetup}>
                                ← Настройка
                            </Button>
                        )}
                        {onRefreshHistory && (
                            <Button
                                size="sm"
                                variant="ghost"
                                className="pipeline-action-btn pipeline-action-btn--reset"
                                loading={historyLoading}
                                onClick={onRefreshHistory}
                            >
                                Обновить историю
                            </Button>
                        )}
                        {canCancel && (
                            <Button
                                size="sm"
                                variant="danger"
                                loading={cancellingRun}
                                onClick={() => void onCancelBacktest?.()}
                            >
                                ■ Стоп
                            </Button>
                        )}
                        <Button
                            variant="primary"
                            glow
                            onClick={onRunBacktest}
                            loading={running}
                            disabled={runBlocked}
                        >
                            ⚡ {running ? 'Выполняется…' : 'Запустить бэктест'}
                        </Button>
                    </div>
                </div>
                {running && runProgress && (
                    <div
                        className="testing-backtest-progress"
                        role="progressbar"
                        aria-valuenow={runProgress.percent}
                        aria-valuemin={0}
                        aria-valuemax={100}
                    >
                        <div className="testing-backtest-progress__meta">
                            <span>
                                {runProgress.phaseLabel ? `${runProgress.phaseLabel}` : 'Выполняется'}
                                {runProgress.percent > 0 ? ` · ${runProgress.percent.toFixed(0)}%` : ''}
                            </span>
                            {runProgress.etaLabel ? (
                                <span className="testing-backtest-progress__eta">осталось {runProgress.etaLabel}</span>
                            ) : (
                                <span className="testing-backtest-progress__eta testing-backtest-progress__eta--muted">
                                    оцениваем время…
                                </span>
                            )}
                        </div>
                        <div className="testing-moex-job-progress testing-backtest-progress__track">
                            <div
                                className="testing-moex-job-progress__bar testing-backtest-progress__bar"
                                style={{
                                    width: `${Math.min(100, Math.max(runProgress.percent > 0 ? 4 : 0, runProgress.percent))}%`,
                                }}
                            />
                        </div>
                    </div>
                )}
            </Card>
            {sticky && <div className="testing-runbar-mobile-spacer" aria-hidden />}
        </>
    )
}
