import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { DataTable, type Column } from '@/components/ui/DataTable'
import type { OrderDisplayRow } from '@/pages/robots-v2/monitorUtils'

type MonitorOrdersCardProps = {
    rows: OrderDisplayRow[]
    openOrderCount: number
}

export function MonitorOrdersCard({ rows, openOrderCount }: MonitorOrdersCardProps) {
    const columns = useMemo<Column<OrderDisplayRow>[]>(() => [
        {
            key: 'ticker',
            header: 'Тикер',
            sortable: true,
            render: r => <strong>{r.ticker}</strong>,
        },
        {
            key: 'dateMs',
            header: 'Время покупки',
            sortable: true,
            render: r => <span className="mono">{r.buyAtLabel}</span>,
        },
        {
            key: 'buyPriceLabel',
            header: 'Цена покупки',
            render: r => <span className="mono">{r.buyPriceLabel}</span>,
        },
        {
            key: 'sellAtLabel',
            header: 'Время продажи',
            render: r => <span className="mono">{r.sellAtLabel}</span>,
        },
        {
            key: 'sellListedLabel',
            header: 'Цена продажи выст.',
            render: r => <span className="mono">{r.sellListedLabel}</span>,
        },
        {
            key: 'sellFillLabel',
            header: 'Цена продажи факт',
            render: r => <span className="mono">{r.sellFillLabel}</span>,
        },
        {
            key: 'statusRank',
            header: 'Статус',
            sortable: true,
            render: r => r.statusLabel,
        },
        {
            key: 'pocket',
            header: 'В карман',
            sortable: true,
            render: r => (
                <span className={`mono robots-v2-pnl--${r.pocketTone}`} title={r.pocketTitle}>
                    {r.pocketText}
                </span>
            ),
        },
        {
            key: 'reasonLabel',
            header: 'Причина',
            render: r => r.reasonLabel,
        },
    ], [])

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-orders">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Заявки</h3>
                {rows.length > 0 ? (
                    <span className="robots-v2-hint">
                        {openOrderCount > 0 ? `${openOrderCount} открытых · ` : ''}
                        {rows.length}
                    </span>
                ) : null}
            </div>
            <p className="robots-v2-hint robots-v2-universe-caption">
                Сделки: покупка → продажа. «Цена продажи выставленная» — лимит TP; «факт» — исполнение.
            </p>
            <DataTable
                columns={columns}
                data={rows}
                keyField="id"
                emptyText="Пока нет сделок"
                maxHeight={360}
                defaultSortKey="dateMs"
                defaultSortDir="desc"
                secondarySortKey="ticker"
                mobilePrimary={r => (
                    <div className="portfolio-mobile-split">
                        <strong>{r.ticker}</strong>
                        <span className={`mono robots-v2-pnl--${r.pocketTone}`}>{r.pocketText}</span>
                    </div>
                )}
                mobileDetails={r => (
                    <div className="portfolio-mobile-stack">
                        <span>{r.statusLabel} · {r.buyAtLabel}</span>
                        <span className="mono">{r.buyPriceLabel} → {r.sellFillLabel}</span>
                        <span>{r.reasonLabel}</span>
                    </div>
                )}
            />
        </Card>
    )
}
