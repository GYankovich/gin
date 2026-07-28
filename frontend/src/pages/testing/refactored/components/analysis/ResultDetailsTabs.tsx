import React, { type Dispatch, type SetStateAction } from 'react'
import { Card } from '@/components/ui/Card'
import { DataTable, type Column } from '@/components/ui/DataTable'
import type { RobotHistoryBacktestResult, RobotHistoryBacktestTrade } from '@/types/robot'

const tradeColumns = (isCrypto: boolean): Column<RobotHistoryBacktestTrade>[] => [
    { key: 'bar_time', header: 'Бар', render: r => r.bar_time ?? '—' },
    { key: 'figi', header: isCrypto ? 'Symbol' : 'Тикер' },
    {
        key: 'side',
        header: 'Сторона',
        render: r => <span className={r.side === 'buy' ? 'color-up' : 'color-down'}>{r.side.toUpperCase()}</span>,
    },
    { key: 'price', header: 'Цена', align: 'right', render: r => r.price.toLocaleString('ru-RU', { maximumFractionDigits: 4 }) },
    { key: 'quantity', header: 'Лоты', align: 'right' },
    { key: 'commission', header: 'Комиссия', align: 'right', render: r => r.commission.toFixed(2) },
]

export type ResultDetailsTabsProps = {
    result: RobotHistoryBacktestResult
    isCrypto?: boolean
    runSignals: Array<Record<string, unknown>>
    runOrders: Array<Record<string, unknown>>
    runPortfolioSnapshots: Array<Record<string, unknown>>
    activeDetailsTab: 'trades' | 'signals' | 'orders' | 'portfolio'
    setActiveDetailsTab: Dispatch<SetStateAction<'trades' | 'signals' | 'orders' | 'portfolio'>>
}

/** T4.3 — trades / signals / orders / portfolio tabs. */
export function ResultDetailsTabs({
    result,
    isCrypto = false,
    runSignals,
    runOrders,
    runPortfolioSnapshots,
    activeDetailsTab,
    setActiveDetailsTab,
}: ResultDetailsTabsProps) {
    const tradeCols = tradeColumns(isCrypto)

    return (
        <Card className="cyber-form-card testing-cyber-card testing-result-details-tabs">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                ДЕТАЛИ ПРОГОНА
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="tabs testing-details-tabs">
                {(['trades', 'signals', 'orders', 'portfolio'] as const).map(tab => (
                    <button
                        key={tab}
                        type="button"
                        className={`tab-btn ${activeDetailsTab === tab ? 'tab-btn--active' : ''}`}
                        onClick={() => setActiveDetailsTab(tab)}
                    >
                        {tab === 'trades' && 'Сделки'}
                        {tab === 'signals' && 'Сигналы'}
                        {tab === 'orders' && 'Ордера'}
                        {tab === 'portfolio' && 'Портфель'}
                    </button>
                ))}
            </div>
            {activeDetailsTab === 'trades' && (
                <DataTable columns={tradeCols} data={result.trades} keyField="id" emptyText="Нет сделок" />
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
                        { key: 'figi', header: isCrypto ? 'Symbol' : 'Тикер' },
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
                        { key: 'figi', header: isCrypto ? 'Symbol' : 'Тикер' },
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
    )
}
