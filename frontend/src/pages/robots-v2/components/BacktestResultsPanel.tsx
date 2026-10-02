import React, { useMemo, useRef } from 'react'
import { LineSeries } from 'lightweight-charts'
import { Card } from '@/components/ui/Card'
import { Chart } from '@/components/ui/Chart'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { StatTile } from '@/components/ui/StatTile'
import { fmtMoney, fmtPct } from '@/pages/robots-v2/formatters'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'
import type { IChartApi, ISeriesApi, Time } from '@/components/ui/Chart'

type TradeRow = Record<string, unknown> & {
    id?: string | number
    bar_time?: string
    figi?: string
    side?: string
    reason?: string
    kind?: string
    price?: number
    quantity?: number
    commission?: number
    pnl_net?: number | null
}

type SignalRow = Record<string, unknown>
type OrderRow = Record<string, unknown>
type DailyRow = Record<string, unknown>

function fmtRatio(v: number | null | undefined): string {
    if (v == null || !Number.isFinite(v)) return '—'
    return v.toFixed(2)
}

type BacktestResultsPanelProps = {
    runId: number | null
    capital: number
    initialCapital: number
    finalEquity: number | null
    totalReturnPercent: number | null
    maxDrawdownPercent: number | null
    winRatePercent?: number | null
    sharpeRatio?: number | null
    sortinoRatio?: number | null
    calmarRatio?: number | null
    stages?: string[]
    trades: TradeRow[]
    chartPoints: Array<{ time: Time; value: number }>
    signals: SignalRow[]
    orders: OrderRow[]
    dailySummary: DailyRow[]
    chartRef: React.MutableRefObject<IChartApi | null>
    seriesRef: React.MutableRefObject<ISeriesApi<'Line'> | null>
}

function fmtTs(raw: unknown): string {
    if (raw == null) return '—'
    const d = new Date(String(raw))
    if (!Number.isFinite(d.getTime())) return '—'
    return d.toLocaleString('ru-RU')
}

export function BacktestResultsPanel({
    runId,
    capital,
    initialCapital,
    finalEquity,
    totalReturnPercent,
    maxDrawdownPercent,
    winRatePercent,
    sharpeRatio,
    sortinoRatio,
    calmarRatio,
    stages,
    trades,
    chartPoints,
    signals,
    orders,
    dailySummary,
    chartRef,
    seriesRef,
}: BacktestResultsPanelProps) {
    const tradeColumns = useMemo<Column<TradeRow>[]>(() => [
        {
            key: 'bar_time',
            header: 'Время',
            sortable: true,
            render: t => (
                <span className="mono">
                    {t.bar_time ? String(t.bar_time).replace('T', ' ').slice(0, 19) : '—'}
                </span>
            ),
        },
        { key: 'figi', header: 'Тикер', sortable: true },
        { key: 'side', header: 'Сторона' },
        {
            key: 'reason',
            header: 'Причина',
            render: t => (
                <span className="robots-v2-scan-reason">
                    {tradeReasonLabel(t.reason || t.kind)}
                </span>
            ),
        },
        {
            key: 'price',
            header: 'Цена',
            render: t => <span className="mono">{fmtMoney(Number(t.price ?? 0))}</span>,
        },
        {
            key: 'quantity',
            header: 'Кол-во',
            render: t => <span className="mono">{t.quantity}</span>,
        },
        {
            key: 'commission',
            header: 'Комиссия',
            render: t => <span className="mono">{fmtMoney(Number(t.commission ?? 0))}</span>,
        },
        {
            key: 'pnl_net',
            header: 'PnL',
            sortable: true,
            render: t => {
                const pnl = t.pnl_net
                const tone = pnl == null ? 'neutral' : pnl >= 0 ? 'up' : 'down'
                return (
                    <span className={`mono robots-v2-pnl--${tone}`}>
                        {pnl == null ? '—' : fmtMoney(pnl)}
                    </span>
                )
            },
        },
    ], [])

    const signalRows = useMemo(
        () => signals.map((s, i) => ({ ...s, id: String(s.id ?? i) })),
        [signals],
    )
    const signalColumns = useMemo<Column<SignalRow>[]>(() => [
        {
            key: 'signal_time',
            header: 'Время',
            sortable: true,
            render: s => (
                <span className="mono">
                    {s.signal_time
                        ? fmtTs(s.signal_time)
                        : s.created_at
                            ? fmtTs(s.created_at)
                            : '—'}
                </span>
            ),
        },
        {
            key: 'figi',
            header: 'Тикер',
            sortable: true,
            render: s => String(s.figi ?? s.ticker ?? '—'),
        },
        {
            key: 'signal_type',
            header: 'Сигнал',
            render: s => String(s.signal_type ?? s.kind ?? '—'),
        },
        {
            key: 'price',
            header: 'Цена',
            render: s => (
                <span className="mono">
                    {s.price != null ? fmtMoney(Number(s.price)) : '—'}
                </span>
            ),
        },
        {
            key: 'was_executed',
            header: 'Исполнен',
            render: s => (s.was_executed ? 'Да' : 'Нет'),
        },
    ], [])

    const orderRows = useMemo(
        () => orders.map((o, i) => ({ ...o, id: String(o.id ?? i) })),
        [orders],
    )
    const orderColumns = useMemo<Column<OrderRow>[]>(() => [
        {
            key: 'signal_time',
            header: 'Время',
            sortable: true,
            render: o => (
                <span className="mono">
                    {o.signal_time
                        ? fmtTs(o.signal_time)
                        : o.submitted_at
                            ? fmtTs(o.submitted_at)
                            : '—'}
                </span>
            ),
        },
        {
            key: 'figi',
            header: 'Тикер',
            sortable: true,
            render: o => String(o.figi ?? o.ticker ?? '—'),
        },
        {
            key: 'side',
            header: 'Сторона',
            render: o => String(o.side ?? '—').toUpperCase(),
        },
        {
            key: 'status',
            header: 'Статус',
            render: o => String(o.status ?? '—'),
        },
        {
            key: 'quantity',
            header: 'Кол-во',
            render: o => <span className="mono">{Number(o.quantity ?? 0).toFixed(2)}</span>,
        },
        {
            key: 'price',
            header: 'Цена',
            render: o => (
                <span className="mono">
                    {o.executed_price != null
                        ? fmtMoney(Number(o.executed_price))
                        : o.price != null
                            ? fmtMoney(Number(o.price))
                            : '—'}
                </span>
            ),
        },
        {
            key: 'pnl_net',
            header: 'PnL',
            sortable: true,
            render: o => (
                <span className="mono">
                    {o.pnl_net != null ? fmtMoney(Number(o.pnl_net)) : '—'}
                </span>
            ),
        },
    ], [])

    const dailyRows = useMemo(
        () => dailySummary.map((row, i) => ({ ...row, id: String(row.date ?? i) })),
        [dailySummary],
    )
    const dailyColumns = useMemo<Column<DailyRow>[]>(() => [
        {
            key: 'date',
            header: 'Дата',
            sortable: true,
            render: row => <span className="mono">{String(row.date ?? '—')}</span>,
        },
        {
            key: 'signals_total',
            header: 'Сигналы',
            render: row => <span className="mono">{String(row.signals_total ?? '—')}</span>,
        },
        {
            key: 'signals_executed',
            header: 'Исполнено',
            render: row => <span className="mono">{String(row.signals_executed ?? '—')}</span>,
        },
        {
            key: 'trades_total',
            header: 'Сделки',
            render: row => <span className="mono">{String(row.trades_total ?? '—')}</span>,
        },
        {
            key: 'candidates_accept',
            header: 'Accept',
            render: row => <span className="mono">{String(row.candidates_accept ?? '—')}</span>,
        },
        {
            key: 'candidates_reject',
            header: 'Reject',
            render: row => <span className="mono">{String(row.candidates_reject ?? '—')}</span>,
        },
    ], [])

    // Keep refs stable for chart onReady closure freshness without unused warnings
    const pointsRef = useRef(chartPoints)
    pointsRef.current = chartPoints

    return (
        <>
            <Card className="dashboard-totals-card">
                <div className="dashboard-totals-card__head">
                    <h3 className="dashboard-panel-title">Результат #{runId}</h3>
                </div>
                <div className="portfolio-stats-grid dashboard-summary-grid">
                    <StatTile label="Капитал" value={fmtMoney(initialCapital || capital)} />
                    <StatTile
                        label="Equity"
                        value={fmtMoney(finalEquity ?? 0)}
                        valueClassName={
                            (finalEquity ?? 0) >= (initialCapital || capital) ? 'color-up' : 'color-down'
                        }
                    />
                    <StatTile
                        label="Доходность"
                        value={fmtPct(totalReturnPercent)}
                        valueClassName={(totalReturnPercent ?? 0) >= 0 ? 'color-up' : 'color-down'}
                    />
                    <StatTile
                        label="Max DD"
                        value={maxDrawdownPercent == null ? '—' : `${maxDrawdownPercent.toFixed(2)}%`}
                        valueClassName="color-down"
                    />
                    <StatTile
                        label="Win rate"
                        value={
                            winRatePercent == null ? '—' : `${winRatePercent.toFixed(1)}%`
                        }
                    />
                    <StatTile label="Sharpe" value={fmtRatio(sharpeRatio)} />
                    <StatTile label="Sortino" value={fmtRatio(sortinoRatio)} />
                    <StatTile label="Calmar" value={fmtRatio(calmarRatio)} />
                    <StatTile label="Сделки" value={trades.length} />
                </div>
                {stages && stages.length > 0 && (
                    <p className="robots-v2-hint robots-v2-universe-caption">
                        {stages.join(' · ')}
                    </p>
                )}
            </Card>

            <Card className="dashboard-assets-card robots-v2-monitor-chart">
                <div className="dashboard-assets-card__head">
                    <h3 className="dashboard-panel-title">График equity</h3>
                </div>
                {chartPoints.length === 0 ? (
                    <p className="robots-v2-hint">Нет точек equity за выбранный период</p>
                ) : (
                    <Chart
                        height={280}
                        onReady={chart => {
                            if (!chart) {
                                chartRef.current = null
                                seriesRef.current = null
                                return
                            }
                            chartRef.current = chart
                            const series = chart.addSeries(LineSeries, {
                                color: '#3dd68c',
                                lineWidth: 2,
                            })
                            seriesRef.current = series
                            const pts = pointsRef.current
                            if (pts.length) series.setData(pts)
                        }}
                    />
                )}
            </Card>

            <Card className="dashboard-assets-card">
                <div className="dashboard-assets-card__head">
                    <h3 className="dashboard-panel-title">Сделки</h3>
                    <span className="robots-v2-hint">{trades.length}</span>
                </div>
                <DataTable
                    columns={tradeColumns}
                    data={trades as Array<TradeRow & Record<string, unknown>>}
                    keyField="id"
                    emptyText="Сделок не было — проверьте период, расписание и сигналы стратегии"
                    maxHeight={360}
                    mobilePrimary={t => (
                        <div className="portfolio-mobile-split">
                            <strong>{String(t.figi ?? '—')}</strong>
                            <span className="mono">
                                {t.pnl_net == null ? '—' : fmtMoney(t.pnl_net)}
                            </span>
                        </div>
                    )}
                    mobileDetails={t =>
                        `${t.side} · ${t.bar_time ? String(t.bar_time).slice(0, 16) : '—'}`
                    }
                />
            </Card>

            <CollapsibleSection
                title={(
                    <span className="dashboard-collapse__label">
                        <IconSignal />
                        Сигналы
                    </span>
                )}
                badge={
                    signals.length > 0 ? (
                        <span className="robots-v2-hint">{signals.length}</span>
                    ) : undefined
                }
                className="dashboard-assets-card"
            >
                <DataTable
                    columns={signalColumns}
                    data={signalRows}
                    keyField="id"
                    emptyText="Нет сигналов за период"
                    maxHeight={320}
                />
            </CollapsibleSection>

            <CollapsibleSection
                title={(
                    <span className="dashboard-collapse__label">
                        <IconOrders />
                        Ордера
                    </span>
                )}
                badge={
                    orders.length > 0 ? (
                        <span className="robots-v2-hint">{orders.length}</span>
                    ) : undefined
                }
                className="dashboard-assets-card"
            >
                <DataTable
                    columns={orderColumns}
                    data={orderRows}
                    keyField="id"
                    emptyText="Нет ордеров за период"
                    maxHeight={320}
                />
            </CollapsibleSection>

            <CollapsibleSection
                title={(
                    <span className="dashboard-collapse__label">
                        <IconDaily />
                        Дневная сводка
                    </span>
                )}
                badge={
                    dailySummary.length > 0 ? (
                        <span className="robots-v2-hint">{dailySummary.length}</span>
                    ) : undefined
                }
                className="dashboard-assets-card"
            >
                <DataTable
                    columns={dailyColumns}
                    data={dailyRows}
                    keyField="id"
                    emptyText="Нет дневной разбивки"
                    maxHeight={320}
                />
            </CollapsibleSection>
        </>
    )
}

function IconSignal() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M4 18V12M9 18V8M14 18V10M19 18V6" />
        </svg>
    )
}

function IconOrders() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" d="M5 5h14v14H5z" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M8 9h8M8 12h8M8 15h5" />
        </svg>
    )
}

function IconDaily() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <rect x="4" y="5" width="16" height="15" rx="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M8 3.5v3M16 3.5v3M4 9.5h16" />
        </svg>
    )
}
