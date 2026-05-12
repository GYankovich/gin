import React, { type Dispatch, type SetStateAction } from 'react'
import { Card } from '@/components/ui/Card'
import { DataTable, type Column } from '@/components/ui/DataTable'
import type { Time } from '@/components/ui/Chart'
import type { Robot, RobotHistoryBacktestResult, RobotHistoryBacktestTrade } from '@/types/robot'
import { TestingBacktestEquityChart } from '@/pages/testing/TestingBacktestEquityChart'

const TRADE_COLUMNS: Column<RobotHistoryBacktestTrade>[] = [
    { key: 'bar_time', header: 'Бар', render: r => r.bar_time ?? '—' },
    { key: 'figi', header: 'Тикер' },
    {
        key: 'side',
        header: 'Сторона',
        render: r => <span className={r.side === 'buy' ? 'color-up' : 'color-down'}>{r.side.toUpperCase()}</span>,
    },
    { key: 'price', header: 'Цена', align: 'right', render: r => r.price.toLocaleString('ru-RU', { maximumFractionDigits: 4 }) },
    { key: 'quantity', header: 'Лоты', align: 'right' },
    { key: 'commission', header: 'Комиссия', align: 'right', render: r => r.commission.toFixed(2) },
]

export type TestingBacktestResultPanelProps = {
    result: RobotHistoryBacktestResult
    priceCurve: Array<{ time: Time; value: number }>
    fromDate: string
    selectedRobot: Robot | null
    interval: string
    chartLegend: { time: string; equity?: number; price?: number }
    setChartLegend: Dispatch<SetStateAction<{ time: string; equity?: number; price?: number }>>
    runSignals: Array<Record<string, unknown>>
    runOrders: Array<Record<string, unknown>>
    runPortfolioSnapshots: Array<Record<string, unknown>>
    activeDetailsTab: 'trades' | 'signals' | 'orders' | 'portfolio'
    setActiveDetailsTab: Dispatch<SetStateAction<'trades' | 'signals' | 'orders' | 'portfolio'>>
}

export function TestingBacktestResultPanel({
    result,
    priceCurve,
    fromDate,
    selectedRobot,
    interval,
    chartLegend,
    setChartLegend,
    runSignals,
    runOrders,
    runPortfolioSnapshots,
    activeDetailsTab,
    setActiveDetailsTab,
}: TestingBacktestResultPanelProps) {
    return (
        <>
            <div className="grid-kpi mb-6">
                <div className="kpi-tile">
                    <span className="kpi-tile__label">Доходность</span>
                    <span className={`kpi-tile__value mono ${Number(result.total_return_percent || 0) >= 0 ? 'color-up' : 'color-down'}`}>
                        {Number(result.total_return_percent || 0).toFixed(2)}%
                    </span>
                </div>
                <div className="kpi-tile">
                    <span className="kpi-tile__label">Итоговый капитал</span>
                    <span className="kpi-tile__value mono">
                        {Number(result.final_equity || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                    </span>
                </div>
                <div className="kpi-tile">
                    <span className="kpi-tile__label">Max drawdown</span>
                    <span className="kpi-tile__value mono">
                        {result.max_drawdown_percent != null ? `${Number(result.max_drawdown_percent).toFixed(2)}%` : '—'}
                    </span>
                </div>
                <div className="kpi-tile">
                    <span className="kpi-tile__label">Сделок</span>
                    <span className="kpi-tile__value mono">{result.trades.length}</span>
                </div>
            </div>
            {result.history_stats && (
                <div className="grid-kpi mb-6">
                    <div className="kpi-tile">
                        <span className="kpi-tile__label">Торговых дат</span>
                        <span className="kpi-tile__value mono">{result.history_stats.total_trade_dates}</span>
                    </div>
                    <div className="kpi-tile">
                        <span className="kpi-tile__label">Обработано</span>
                        <span className="kpi-tile__value mono color-up">{result.history_stats.processed}</span>
                    </div>
                    <div className="kpi-tile">
                        <span className="kpi-tile__label">Пропуск (fetch)</span>
                        <span className="kpi-tile__value mono color-down">{result.history_stats.skipped_fetch}</span>
                    </div>
                    <div className="kpi-tile">
                        <span className="kpi-tile__label">Пропуск (empty)</span>
                        <span className="kpi-tile__value mono">{result.history_stats.skipped_empty}</span>
                    </div>
                </div>
            )}
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
            <Card className="cyber-form-card testing-cyber-card">
                <h3 className="card__section-title pipeline-title">
                    <span className="cyber-bracket">[</span>
                    ДЕТАЛИ ПРОГОНА
                    <span className="cyber-bracket">]</span>
                </h3>
                <div className="tabs testing-details-tabs">
                    <button
                        type="button"
                        className={`tab-btn ${activeDetailsTab === 'trades' ? 'tab-btn--active' : ''}`}
                        onClick={() => setActiveDetailsTab('trades')}
                    >
                        Сделки
                    </button>
                    <button
                        type="button"
                        className={`tab-btn ${activeDetailsTab === 'signals' ? 'tab-btn--active' : ''}`}
                        onClick={() => setActiveDetailsTab('signals')}
                    >
                        Сигналы
                    </button>
                    <button
                        type="button"
                        className={`tab-btn ${activeDetailsTab === 'orders' ? 'tab-btn--active' : ''}`}
                        onClick={() => setActiveDetailsTab('orders')}
                    >
                        Ордера
                    </button>
                    <button
                        type="button"
                        className={`tab-btn ${activeDetailsTab === 'portfolio' ? 'tab-btn--active' : ''}`}
                        onClick={() => setActiveDetailsTab('portfolio')}
                    >
                        Портфель
                    </button>
                </div>
                {activeDetailsTab === 'trades' && (
                    <DataTable columns={TRADE_COLUMNS} data={result.trades} keyField="id" emptyText="Нет сделок" />
                )}
                {activeDetailsTab === 'signals' && (
                    <DataTable
                        columns={[
                            {
                                key: 'signal_time',
                                header: 'Время',
                                render: (r: Record<string, unknown>) =>
                                    r.signal_time ? new Date(String(r.signal_time)).toLocaleString('ru-RU') : '—',
                            },
                            { key: 'figi', header: 'Тикер' },
                            { key: 'signal_type', header: 'Сигнал' },
                            {
                                key: 'price',
                                header: 'Цена',
                                align: 'right',
                                render: (r: Record<string, unknown>) => (r.price != null ? Number(r.price).toFixed(4) : '—'),
                            },
                            {
                                key: 'was_executed',
                                header: 'Исполнен',
                                render: (r: Record<string, unknown>) => (r.was_executed ? 'Да' : 'Нет'),
                            },
                        ]}
                        data={runSignals}
                        keyField="id"
                        emptyText="Нет сигналов"
                    />
                )}
                {activeDetailsTab === 'orders' && (
                    <DataTable
                        columns={[
                            {
                                key: 'signal_time',
                                header: 'Время',
                                render: (r: Record<string, unknown>) =>
                                    r.signal_time ? new Date(String(r.signal_time)).toLocaleString('ru-RU') : '—',
                            },
                            { key: 'figi', header: 'Тикер' },
                            {
                                key: 'side',
                                header: 'Сторона',
                                render: (r: Record<string, unknown>) => String(r.side || '').toUpperCase(),
                            },
                            { key: 'status', header: 'Статус' },
                            {
                                key: 'quantity',
                                header: 'Кол-во',
                                align: 'right',
                                render: (r: Record<string, unknown>) => Number(r.quantity || 0).toFixed(2),
                            },
                            {
                                key: 'executed_price',
                                header: 'Цена',
                                align: 'right',
                                render: (r: Record<string, unknown>) =>
                                    r.executed_price != null ? Number(r.executed_price).toFixed(4) : '—',
                            },
                            {
                                key: 'pnl_net',
                                header: 'P&L',
                                align: 'right',
                                render: (r: Record<string, unknown>) => (r.pnl_net != null ? Number(r.pnl_net).toFixed(2) : '—'),
                            },
                        ]}
                        data={runOrders}
                        keyField="id"
                        emptyText="Нет ордеров"
                    />
                )}
                {activeDetailsTab === 'portfolio' && (
                    <DataTable
                        columns={[
                            {
                                key: 'snapshot_time',
                                header: 'Время',
                                render: (r: Record<string, unknown>) =>
                                    r.snapshot_time ? new Date(String(r.snapshot_time)).toLocaleString('ru-RU') : '—',
                            },
                            {
                                key: 'cash_balance',
                                header: 'Деньги',
                                align: 'right',
                                render: (r: Record<string, unknown>) =>
                                    Number(r.cash_balance || 0).toLocaleString('ru-RU', { maximumFractionDigits: 2 }),
                            },
                            {
                                key: 'equity',
                                header: 'Equity',
                                align: 'right',
                                render: (r: Record<string, unknown>) =>
                                    Number(r.equity || 0).toLocaleString('ru-RU', { maximumFractionDigits: 2 }),
                            },
                        ]}
                        data={runPortfolioSnapshots}
                        keyField="id"
                        emptyText="Нет снимков портфеля"
                    />
                )}
            </Card>
        </>
    )
}
