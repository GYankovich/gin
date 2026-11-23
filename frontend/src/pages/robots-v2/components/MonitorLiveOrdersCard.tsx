import React, { useMemo, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { fmtOrderClock, fmtPrice } from '@/pages/robots-v2/monitorUtils'

type OrderFilter = 'all' | 'buy' | 'sell' | 'error'

export type LiveOrderRow = {
    id: string
    ticker: string
    side: string
    sideLabel: string
    detailLabel: string
    kindLabel: string
    statusKey: string
    statusLabel: string
    timeLabel: string
    isError: boolean
    isBuy: boolean
    isSell: boolean
}

type MonitorLiveOrdersCardProps = {
    orders: Array<Record<string, unknown>>
}

function sideLabelOf(side: string): string {
    const s = side.toUpperCase()
    if (s === 'BUY' || s === 'LONG') return 'Купить'
    if (s === 'SELL' || s === 'SHORT' || s === 'CLOSE') return 'Продать'
    return side || '—'
}

function statusLabelOf(status: string): string {
    const s = status.toLowerCase()
    if (s === 'resting' || s === 'submitted' || s === 'new' || s === 'active') return 'Активна'
    if (s === 'partial' || s === 'partially_filled') return 'Частично'
    if (s === 'rejected' || s === 'reject') return 'Отклонена'
    if (s === 'cancelled' || s === 'canceled') return 'Отменена'
    if (s === 'filled') return 'Исполнена'
    return status || '—'
}

function toLiveOrderRow(o: Record<string, unknown>, index: number): LiveOrderRow {
    const ticker = String(o.ticker || o.secid || '—').toUpperCase()
    const side = String(o.side || '')
    const statusKey = String(o.status || '').toLowerCase()
    const qty = Number(o.quantity ?? o.qty)
    const price = o.price != null ? Number(o.price) : null
    const qtyLabel = Number.isFinite(qty) && qty > 0
        ? qty.toLocaleString('ru-RU', { maximumFractionDigits: 4 })
        : '—'
    const priceLabel = price != null && Number.isFinite(price) && price > 0 ? fmtPrice(price) : null
    const detailLabel = priceLabel
        ? `${qtyLabel} шт по ${priceLabel}`
        : `${qtyLabel} шт`
    const orderType = String(o.orderType || o.order_type || 'LIMIT').toUpperCase()
    const kind = String(o.kind || o.reason || '').trim()
    const kindLabel = [orderType, kind].filter(Boolean).join(' · ') || orderType
    const submitted = o.submittedAt ?? o.submitted_at ?? o.createdAt ?? o.created_at
    const isError = statusKey === 'rejected' || statusKey === 'reject'
    const sideU = side.toUpperCase()
    return {
        id: String(o.brokerOrderId || o.broker_order_id || o.id || `${ticker}-${index}`),
        ticker,
        side,
        sideLabel: sideLabelOf(side),
        detailLabel,
        kindLabel,
        statusKey,
        statusLabel: statusLabelOf(statusKey),
        timeLabel: fmtOrderClock(submitted != null ? String(submitted) : null),
        isError,
        isBuy: sideU === 'BUY' || sideU === 'LONG',
        isSell: sideU === 'SELL' || sideU === 'SHORT' || sideU === 'CLOSE',
    }
}

/**
 * Active broker / resting orders — what is in flight now.
 */
export function MonitorLiveOrdersCard({ orders }: MonitorLiveOrdersCardProps) {
    const [filter, setFilter] = useState<OrderFilter>('all')
    const rows = useMemo(
        () => orders.map((o, i) => toLiveOrderRow(o, i)),
        [orders],
    )
    const filtered = useMemo(() => {
        if (filter === 'buy') return rows.filter(r => r.isBuy)
        if (filter === 'sell') return rows.filter(r => r.isSell)
        if (filter === 'error') return rows.filter(r => r.isError)
        return rows
    }, [rows, filter])

    const chips: Array<{ key: OrderFilter; label: string }> = [
        { key: 'all', label: 'Все' },
        { key: 'buy', label: 'Покупки' },
        { key: 'sell', label: 'Продажи' },
        { key: 'error', label: 'Ошибки' },
    ]

    return (
        <Card className="dashboard-assets-card robots-monitor-day-trades robots-monitor-live-orders">
            <div className="dashboard-assets-card__head robots-monitor-orders__head">
                <h3 className="dashboard-panel-title">
                    Заявки
                    {rows.length > 0 ? (
                        <span className="robots-v2-hint"> · {rows.length}</span>
                    ) : null}
                </h3>
            </div>
            {rows.length > 0 ? (
                <div className="robots-monitor-live-orders__chips robots-monitor-pool__row">
                    {chips.map(c => (
                        <button
                            key={c.key}
                            type="button"
                            className={`robots-monitor-pill${filter === c.key ? ' robots-monitor-pill--on' : ''}`}
                            onClick={() => setFilter(c.key)}
                        >
                            {c.label}
                        </button>
                    ))}
                </div>
            ) : null}
            {filtered.length === 0 ? (
                <p className="dashboard-empty">
                    {rows.length === 0 ? 'Нет активных заявок' : 'Нет заявок в этом фильтре'}
                </p>
            ) : (
                <div className="robots-monitor-day-trades__scroll">
                    <table className="robots-monitor-day-trades__table" aria-label="Активные заявки">
                        <thead>
                            <tr>
                                <th>Тикер</th>
                                <th>Ордер</th>
                                <th>Статус</th>
                                <th>Время</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map(row => (
                                <tr key={row.id}>
                                    <td>
                                        <b className="robots-monitor-day-trades__tk">{row.ticker}</b>
                                        <div className="robots-monitor-day-trades__muted">{row.sideLabel}</div>
                                    </td>
                                    <td>
                                        <span className="mono">{row.detailLabel}</span>
                                        <div className="robots-monitor-day-trades__muted">{row.kindLabel}</div>
                                    </td>
                                    <td className="robots-monitor-day-trades__muted">{row.statusLabel}</td>
                                    <td className="mono robots-monitor-day-trades__muted">{row.timeLabel}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            {rows.length > 0 ? (
                <p className="robots-v2-hint robots-monitor-live-orders__cap">
                    Лимитные заявки могут висеть до исполнения или таймаута.
                </p>
            ) : null}
        </Card>
    )
}
