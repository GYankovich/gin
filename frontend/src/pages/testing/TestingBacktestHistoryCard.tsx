import React from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { DataTable } from '@/components/ui/DataTable'
import { TestingSectionState } from '@/pages/testing/TestingSectionState'
import { RunComparePanel } from '@/pages/testing/refactored/components/analysis/RunComparePanel'
import type { RobotBacktestHistoryItem } from '@/types/robot'
import { getStrategyMeta } from '@/pages/testing/strategyPresets'

function resolveRunStrategy(r: RobotBacktestHistoryItem): string | null {
    const fromRun = String(r.strategy ?? '').trim().toLowerCase()
    if (fromRun) return fromRun
    const fromPayload = String(
        (r.result_payload as { strategy?: string } | undefined)?.strategy ?? '',
    ).trim().toLowerCase()
    return fromPayload || null
}

function strategyDisplayName(r: RobotBacktestHistoryItem): string {
    const titled = String(r.strategy_title ?? '').trim()
    if (titled) return titled
    const key = resolveRunStrategy(r)
    if (!key) return '—'
    return getStrategyMeta(key).title
}

function runCompareLabel(r: RobotBacktestHistoryItem): string {
    const strat = strategyDisplayName(r)
    const st = String(r.status ?? '').toUpperCase()
    const stTag = st && st !== 'SUCCESS' ? ` • ${st}` : ''
    return `#${r.id} • ${strat}${stTag} • ${new Date(r.created_at).toLocaleString('ru-RU')}`
}

function statusLabel(r: RobotBacktestHistoryItem): string {
    const st = String(r.status ?? '').toUpperCase() || '—'
    if (st === 'RUNNING' || st === 'QUEUED' || st === 'FETCHING') {
        const phase = String(r.run_phase ?? '').trim()
        return phase ? `${st} (${phase})` : st
    }
    return st
}

function marketLabel(r: RobotBacktestHistoryItem): string {
    const mp = String(r.market_profile ?? '').toLowerCase()
    if (mp === 'crypto') return 'Crypto'
    if (mp === 'moex') return 'MOEX'
    const bt = String(r.broker_type ?? '').toLowerCase()
    if (bt === 'bybit') return 'Crypto'
    return 'MOEX'
}

export type TestingBacktestHistoryCardProps = {
    historyLoading: boolean
    historyError?: string | null
    onRefresh: () => void | Promise<void>
    historyRuns: RobotBacktestHistoryItem[]
    filteredHistoryRuns: RobotBacktestHistoryItem[]
    historySearch: string
    onHistorySearchChange: (v: string) => void
    historyMinReturn: number | null
    onHistoryMinReturnChange: (v: number | null) => void
    historyMarketFilter?: 'all' | 'tinvest' | 'bybit'
    onHistoryMarketFilterChange?: (v: 'all' | 'tinvest' | 'bybit') => void
    historyStatusFilter?: 'all' | 'SUCCESS' | 'FAILED'
    onHistoryStatusFilterChange?: (v: 'all' | 'SUCCESS' | 'FAILED') => void
    compareLeftId: number | null
    onCompareLeftIdChange: (id: number | null) => void
    compareRightId: number | null
    onCompareRightIdChange: (id: number | null) => void
    onOpenRun: (r: RobotBacktestHistoryItem) => void | Promise<void>
    embedded?: boolean
    showCompare?: boolean
}

export function TestingBacktestHistoryCard({
    historyLoading,
    historyError,
    onRefresh,
    historyRuns,
    filteredHistoryRuns,
    historySearch,
    onHistorySearchChange,
    historyMinReturn,
    onHistoryMinReturnChange,
    historyMarketFilter = 'all',
    onHistoryMarketFilterChange,
    historyStatusFilter = 'all',
    onHistoryStatusFilterChange,
    compareLeftId,
    onCompareLeftIdChange,
    compareRightId,
    onCompareRightIdChange,
    onOpenRun,
    embedded = false,
    showCompare = true,
}: TestingBacktestHistoryCardProps) {
    const hasHistoryData = historyRuns.length > 0
    const hasFilters =
        historySearch.trim().length > 0 ||
        historyMinReturn != null ||
        historyMarketFilter !== 'all' ||
        historyStatusFilter !== 'all'
    const isFilteredEmpty = hasHistoryData && filteredHistoryRuns.length === 0

    const successCount = historyRuns.filter(r => String(r.status ?? '').toUpperCase() === 'SUCCESS').length
    const failedCount = historyRuns.filter(r => String(r.status ?? '').toUpperCase() === 'FAILED').length

    const body = (
        <>
            {historyError && hasHistoryData && (
                <TestingSectionState
                    title="ИСТОРИЯ БЭКТЕСТОВ"
                    message={`Часть данных могла устареть: ${historyError}`}
                    variant="partial"
                    actionLabel="Повторить загрузку"
                    onAction={() => void onRefresh()}
                    compact
                />
            )}
            {historyError && !hasHistoryData && (
                <TestingSectionState
                    title="ИСТОРИЯ БЭКТЕСТОВ"
                    message={`Не удалось загрузить историю: ${historyError}`}
                    variant="error"
                    actionLabel="Повторить загрузку"
                    onAction={() => void onRefresh()}
                    compact
                />
            )}
            <div className="form-row testing-history-filters">
                <div className="form-group testing-history-filters__search">
                    <label className="form-label">Поиск</label>
                    <input
                        className="form-input"
                        value={historySearch}
                        onChange={e => onHistorySearchChange(e.target.value)}
                        placeholder="id, стратегия, дата, доходность"
                    />
                </div>
                <div className="form-group testing-history-filters__min-return">
                    <label className="form-label">Мин. доходность %</label>
                    <input
                        className="form-input"
                        value={historyMinReturn == null ? '' : String(historyMinReturn)}
                        onChange={e => {
                            const raw = e.target.value.trim()
                            if (!raw) {
                                onHistoryMinReturnChange(null)
                                return
                            }
                            const n = Number(raw.replace(',', '.'))
                            onHistoryMinReturnChange(Number.isFinite(n) ? n : null)
                        }}
                        placeholder="например, 5"
                    />
                </div>
                <div className="form-group testing-history-filters__market">
                    <label className="form-label">Рынок</label>
                    <Select
                        options={[
                            { value: 'all', label: 'Все' },
                            { value: 'tinvest', label: 'MOEX' },
                            { value: 'bybit', label: 'Crypto' },
                        ]}
                        value={historyMarketFilter}
                        onChange={v => onHistoryMarketFilterChange?.(v as 'all' | 'tinvest' | 'bybit')}
                    />
                </div>
                <div className="form-group testing-history-filters__status">
                    <label className="form-label">Статус</label>
                    <div className="testing-history-status-chips">
                        {(
                            [
                                { value: 'all' as const, label: `Все (${historyRuns.length})` },
                                { value: 'SUCCESS' as const, label: `Успешные (${successCount})` },
                                { value: 'FAILED' as const, label: `Ошибки (${failedCount})` },
                            ] as const
                        ).map(opt => (
                            <button
                                key={opt.value}
                                type="button"
                                className={`btn btn--sm ${historyStatusFilter === opt.value ? 'btn--primary' : 'btn--ghost'}`}
                                onClick={() => onHistoryStatusFilterChange?.(opt.value)}
                            >
                                {opt.label}
                            </button>
                        ))}
                    </div>
                </div>
                {hasFilters && (
                    <div className="form-group testing-history-filters__reset">
                        <label className="form-label">Фильтры</label>
                        <Button
                            size="sm"
                            variant="ghost"
                            className="pipeline-action-btn pipeline-action-btn--reset"
                            onClick={() => {
                                onHistorySearchChange('')
                                onHistoryMinReturnChange(null)
                                onHistoryMarketFilterChange?.('all')
                                onHistoryStatusFilterChange?.('all')
                            }}
                        >
                            Сбросить
                        </Button>
                    </div>
                )}
            </div>
            {isFilteredEmpty && (
                <TestingSectionState
                    title="ИСТОРИЯ БЭКТЕСТОВ"
                    message="По текущим фильтрам ничего не найдено. Сбросьте фильтры или смягчите порог доходности."
                    variant="partial"
                    compact
                />
            )}
            <DataTable
                columns={[
                    {
                        key: 'created_at',
                        header: 'Запуск',
                        render: (r: RobotBacktestHistoryItem) => new Date(r.created_at).toLocaleString('ru-RU'),
                    },
                    {
                        key: 'status',
                        header: 'Статус',
                        render: (r: RobotBacktestHistoryItem) => (
                            <span
                                className={
                                    String(r.status ?? '').toUpperCase() === 'FAILED'
                                        ? 'color-down'
                                        : String(r.status ?? '').toUpperCase() === 'SUCCESS'
                                          ? 'color-up'
                                          : undefined
                                }
                                title={r.error_message ?? undefined}
                            >
                                {statusLabel(r)}
                            </span>
                        ),
                    },
                    {
                        key: 'market',
                        header: 'Рынок',
                        render: (r: RobotBacktestHistoryItem) => marketLabel(r),
                    },
                    {
                        key: 'strategy',
                        header: 'Стратегия',
                        render: (r: RobotBacktestHistoryItem) => {
                            const strat = resolveRunStrategy(r)
                            return (
                                <span className="testing-history-strategy" title={strat ?? undefined}>
                                    {strategyDisplayName(r)}
                                </span>
                            )
                        },
                    },
                    {
                        key: 'requested_from',
                        header: 'Период',
                        render: (r: RobotBacktestHistoryItem) =>
                            `${new Date(r.requested_from).toLocaleDateString('ru-RU')} - ${new Date(r.requested_to).toLocaleDateString('ru-RU')}`,
                    },
                    {
                        key: 'total_return_percent',
                        header: 'Доходность',
                        align: 'right',
                        render: (r: RobotBacktestHistoryItem) => {
                            const st = String(r.status ?? '').toUpperCase()
                            if (st && st !== 'SUCCESS') return <span>—</span>
                            return (
                                <span className={r.total_return_percent >= 0 ? 'color-up' : 'color-down'}>
                                    {r.total_return_percent.toFixed(2)}%
                                </span>
                            )
                        },
                    },
                    {
                        key: 'final_equity',
                        header: 'Итог',
                        align: 'right',
                        render: (r: RobotBacktestHistoryItem) =>
                            `${r.final_equity.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽`,
                    },
                    {
                        key: 'open',
                        header: '',
                        render: (r: RobotBacktestHistoryItem) => (
                            <Button size="sm" variant="secondary" onClick={() => void onOpenRun(r)}>
                                Открыть
                            </Button>
                        ),
                    },
                ]}
                data={filteredHistoryRuns}
                keyField="id"
                mobilePrimary={(r: RobotBacktestHistoryItem) =>
                    `#${r.id} • ${strategyDisplayName(r)} • ${r.total_return_percent.toFixed(2)}%`}
                mobileSecondary={(r: RobotBacktestHistoryItem) => new Date(r.created_at).toLocaleString('ru-RU')}
                mobileDetails={(r: RobotBacktestHistoryItem) => (
                    <>
                        <div>Статус: {statusLabel(r)}</div>
                        <div>Стратегия: {strategyDisplayName(r)}</div>
                        {r.error_message ? <div className="color-down">{r.error_message}</div> : null}
                        <div>Период: {new Date(r.requested_from).toLocaleDateString('ru-RU')} - {new Date(r.requested_to).toLocaleDateString('ru-RU')}</div>
                        <div>
                            Итог: {r.final_equity.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                        </div>
                    </>
                )}
                emptyText={historyLoading ? 'Загрузка...' : 'Нет сохраненных прогонов'}
            />
            {showCompare && historyRuns.length > 1 && (
                <RunComparePanel
                    historyRuns={historyRuns}
                    compareLeftId={compareLeftId}
                    onCompareLeftIdChange={onCompareLeftIdChange}
                    compareRightId={compareRightId}
                    onCompareRightIdChange={onCompareRightIdChange}
                    runCompareLabel={runCompareLabel}
                />
            )}
        </>
    )

    if (embedded) {
        return (
            <div className="testing-history-embedded">
                <div className="testing-history-embedded__toolbar">
                    <p className="testing-opt-muted">
                        Успешные и неуспешные прогоны. «Открыть» — полный анализ на вкладке «Анализ».
                    </p>
                    <Button
                        size="sm"
                        variant="ghost"
                        className="pipeline-action-btn pipeline-action-btn--reset"
                        loading={historyLoading}
                        onClick={() => void onRefresh()}
                    >
                        Обновить
                    </Button>
                </div>
                {body}
            </div>
        )
    }

    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card testing-history-card">
            <div className="card__header">
                <h3 className="pipeline-title">
                    <span className="cyber-bracket">[</span>
                    ИСТОРИЯ БЭКТЕСТОВ
                    <span className="cyber-bracket">]</span>
                </h3>
                <Button
                    size="sm"
                    variant="ghost"
                    className="pipeline-action-btn pipeline-action-btn--reset"
                    loading={historyLoading}
                    onClick={() => void onRefresh()}
                >
                    Обновить
                </Button>
            </div>
            {body}
        </Card>
    )
}
