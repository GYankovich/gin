import React, { useEffect, useMemo, useState } from 'react'
import { Select } from '@/components/ui/Select'
import { TestingSectionState } from '@/pages/testing/TestingSectionState'
import { resolveHistoryRunCurrencyLabel } from '@/pages/testing/refactored/components/analysis/resultCurrency'
import { robotService } from '@/services/robotService'
import type { RobotBacktestCompareResponse, RobotBacktestHistoryItem } from '@/types/robot'
import { fmtErr } from '@/pages/testing/testingUtils'

export type RunComparePanelProps = {
    historyRuns: RobotBacktestHistoryItem[]
    compareLeftId: number | null
    onCompareLeftIdChange: (id: number | null) => void
    compareRightId: number | null
    onCompareRightIdChange: (id: number | null) => void
    runCompareLabel: (r: RobotBacktestHistoryItem) => string
}

function fmtDelta(v: number | null | undefined, suffix = ''): string {
    if (v == null || !Number.isFinite(v)) return '—'
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(2)}${suffix}`
}

/** T4.6 — compare two runs via POST /history-backtest/compare. */
export function RunComparePanel({
    historyRuns,
    compareLeftId,
    onCompareLeftIdChange,
    compareRightId,
    onCompareRightIdChange,
    runCompareLabel,
}: RunComparePanelProps) {
    const [compareData, setCompareData] = useState<RobotBacktestCompareResponse | null>(null)
    const [compareLoading, setCompareLoading] = useState(false)
    const [compareError, setCompareError] = useState<string | null>(null)

    const leftRun = useMemo(
        () => historyRuns.find(x => x.id === compareLeftId) ?? null,
        [historyRuns, compareLeftId],
    )
    const rightRun = useMemo(
        () => historyRuns.find(x => x.id === compareRightId) ?? null,
        [historyRuns, compareRightId],
    )
    const compareSelectionValid = Boolean(leftRun && rightRun && leftRun.id !== rightRun.id)

    useEffect(() => {
        if (!compareSelectionValid || !leftRun || !rightRun) {
            setCompareData(null)
            setCompareError(null)
            return
        }

        let cancelled = false
        setCompareLoading(true)
        setCompareError(null)
        void robotService
            .compareHistoryBacktestRuns(leftRun.id, rightRun.id)
            .then(data => {
                if (!cancelled) setCompareData(data)
            })
            .catch((e: unknown) => {
                if (!cancelled) {
                    setCompareData(null)
                    setCompareError(fmtErr(e))
                }
            })
            .finally(() => {
                if (!cancelled) setCompareLoading(false)
            })

        return () => {
            cancelled = true
        }
    }, [compareSelectionValid, leftRun, rightRun])

    const rightCurrency = rightRun ? resolveHistoryRunCurrencyLabel(rightRun) : '₽'
    const diff = compareData?.metrics_diff

    return (
        <div className="testing-history-compare">
            <h4 className="testing-history-compare__title">Сравнение прогонов</h4>
            <div className="form-row testing-history-compare__selectors">
                <div className="form-group testing-history-compare__select">
                    <label className="form-label">Базовый</label>
                    <Select
                        options={[
                            { value: '', label: '—' },
                            ...historyRuns.map(r => ({ value: String(r.id), label: runCompareLabel(r) })),
                        ]}
                        value={compareLeftId != null ? String(compareLeftId) : ''}
                        onChange={v => onCompareLeftIdChange(v ? Number(v) : null)}
                    />
                </div>
                <div className="form-group testing-history-compare__select">
                    <label className="form-label">Сравниваемый</label>
                    <Select
                        options={[
                            { value: '', label: '—' },
                            ...historyRuns.map(r => ({ value: String(r.id), label: runCompareLabel(r) })),
                        ]}
                        value={compareRightId != null ? String(compareRightId) : ''}
                        onChange={v => onCompareRightIdChange(v ? Number(v) : null)}
                    />
                </div>
            </div>
            {leftRun && rightRun && leftRun.id === rightRun.id && (
                <TestingSectionState
                    title="СРАВНЕНИЕ ПРОГОНОВ"
                    message="Выберите два разных прогона: левый и правый run не должны совпадать."
                    variant="partial"
                    compact
                />
            )}
            {compareLoading && (
                <p className="form-hint testing-history-compare__loading">Загрузка сравнения…</p>
            )}
            {compareError && (
                <TestingSectionState title="СРАВНЕНИЕ" message={compareError} variant="error" compact />
            )}
            {compareSelectionValid && compareData && diff && (
                <>
                    <div className="grid-kpi testing-history-compare__kpi">
                        <div className="kpi-tile">
                            <span className="kpi-tile__label">Δ Доходность</span>
                            <span
                                className={`kpi-tile__value mono ${
                                    Number(diff.total_return_percent ?? 0) >= 0 ? 'color-up' : 'color-down'
                                }`}
                            >
                                {fmtDelta(diff.total_return_percent as number, '%')}
                            </span>
                        </div>
                        <div className="kpi-tile">
                            <span className="kpi-tile__label">Δ Max DD</span>
                            <span className="kpi-tile__value mono">
                                {fmtDelta(diff.max_drawdown_percent as number, '%')}
                            </span>
                        </div>
                        <div className="kpi-tile">
                            <span className="kpi-tile__label">Δ Win rate</span>
                            <span className="kpi-tile__value mono">
                                {fmtDelta(diff.win_rate_percent as number, '%')}
                            </span>
                        </div>
                        <div className="kpi-tile">
                            <span className="kpi-tile__label">Δ Итоговый капитал</span>
                            <span
                                className={`kpi-tile__value mono ${
                                    Number(diff.final_equity ?? 0) >= 0 ? 'color-up' : 'color-down'
                                }`}
                            >
                                {Number(diff.final_equity ?? 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 })}{' '}
                                {rightCurrency}
                            </span>
                        </div>
                        <div className="kpi-tile">
                            <span className="kpi-tile__label">Δ Сделок</span>
                            <span className="kpi-tile__value mono">{fmtDelta(diff.trades_total as number, '')}</span>
                        </div>
                    </div>
                    {Object.keys(compareData.config_diff).length > 0 && (
                        <details className="testing-history-compare__config-diff">
                            <summary>Отличия конфигурации ({Object.keys(compareData.config_diff).length})</summary>
                            <pre className="testing-history-compare__config-pre">
                                {JSON.stringify(compareData.config_diff, null, 2)}
                            </pre>
                        </details>
                    )}
                </>
            )}
        </div>
    )
}
