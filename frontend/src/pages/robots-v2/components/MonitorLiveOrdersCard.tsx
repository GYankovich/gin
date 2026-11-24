import React, { useMemo, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { MonitorContextPanel } from '@/pages/robots-v2/components/MonitorContextPanel'
import { MonitorTableViewport } from '@/pages/robots-v2/components/MonitorTableViewport'
import { fmtNum, fmtPrice } from '@/pages/robots-v2/formatters'
import { fmtOrderClock, fmtOrderClockSeconds } from '@/pages/robots-v2/monitorUtils'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'

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

export type HistoryOrderRow = {
    id: string
    time: string
    ticker: string
    sideLabel: string
    kind: string
    statusLabel: string
    submitted: string
    replySummary: string
    replyPayload: Record<string, unknown>
    cycleId: string
    mode: string
    orderType: string
}

type MonitorLiveOrdersCardProps = {
    orders: Array<Record<string, unknown>>
    /** live = monitor blotter; history = audit with submit/reply + inspector */
    mode?: 'live' | 'history'
    title?: string | null
    emptyTitle?: string
    emptySub?: string
    ariaLabel?: string
    bare?: boolean
    footnote?: string | null
    className?: string
}

function sideLabelOf(side: string): string {
    const s = side.toUpperCase()
    if (s === 'BUY' || s === 'LONG') return 'Купить'
    if (s === 'SELL' || s === 'SHORT' || s === 'CLOSE') return 'Продать'
    return side || '—'
}

function statusLabelOf(status: string, opts: { history?: boolean } = {}): string {
    const history = Boolean(opts.history)
    const s = status.toLowerCase()
    if (s === 'resting' || s === 'submitted' || s === 'new' || s === 'active') {
        return history ? 'В рынке' : 'Активна'
    }
    if (s === 'partial' || s === 'partially_filled') return 'Частично'
    if (s === 'rejected' || s === 'reject') return 'Отклонена'
    if (s === 'cancelled' || s === 'canceled') return 'Отменена'
    if (s === 'filled') return history ? 'Исполнено' : 'Исполнена'
    if (s === 'closed') return 'Закрыта'
    if (s === 'open') return 'Открыта'
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

function toHistoryOrderRow(o: Record<string, unknown>, index: number): HistoryOrderRow {
    const ticker = String(o.ticker || o.secid || '—').toUpperCase() || '—'
    const side = String(o.side || '')
    const statusRaw = String(o.status || '')
    const statusLabel = statusLabelOf(statusRaw, { history: true })
    const orderType = String(o.orderType || o.order_type || 'MARKET').toUpperCase()
    const kind = tradeReasonLabel(o.kind || o.reason)
    const qty = Number(o.quantity ?? o.qty)
    const qtyLabel = Number.isFinite(qty) ? fmtNum(qty, 4) : '—'
    const price = o.price != null ? Number(o.price) : null
    const priceLabel = price != null && Number.isFinite(price) && price > 0
        ? fmtPrice(price, 4)
        : '—'
    const submittedParts = [
        orderType,
        sideLabelOf(side),
        priceLabel !== '—' ? `${qtyLabel} шт по ${priceLabel}` : `${qtyLabel} шт`,
        kind && kind !== '—' ? kind : null,
    ].filter(Boolean)
    const submitted = submittedParts.join(' · ')
    const brokerOrderId = o.brokerOrderId ?? o.broker_order_id
    const brokerId = brokerOrderId != null && String(brokerOrderId) ? String(brokerOrderId) : null
    const rejectRaw = o.rejectReason ?? o.reject_reason
    const reject = rejectRaw != null && String(rejectRaw) ? String(rejectRaw) : null
    const replyPayload: Record<string, unknown> = {
        status: statusRaw || null,
        brokerOrderId: brokerId,
        rejectReason: reject,
    }
    const replyBits = [statusLabel]
    if (brokerId) replyBits.push(`id ${brokerId}`)
    if (reject) replyBits.push(reject)
    const submittedAt = o.submittedAt ?? o.submitted_at ?? o.createdAt ?? o.created_at
    return {
        id: String(o.id || brokerId || `${ticker}-${index}`),
        time: fmtOrderClockSeconds(submittedAt != null ? String(submittedAt) : null),
        ticker,
        sideLabel: sideLabelOf(side),
        kind,
        statusLabel,
        submitted,
        replySummary: replyBits.filter(Boolean).join(' · ') || '—',
        replyPayload,
        cycleId: String(o.cycleId ?? o.cycle_id ?? ''),
        mode: String(o.mode || ''),
        orderType,
    }
}

/**
 * Orders blotter — live on монитор, history (submit/reply) on История.
 */
export function MonitorLiveOrdersCard({
    orders,
    mode = 'live',
    title = 'Заявки',
    emptyTitle,
    emptySub,
    ariaLabel,
    bare = false,
    footnote = 'Лимитные заявки могут висеть до исполнения или таймаута.',
    className = '',
}: MonitorLiveOrdersCardProps) {
    const [filter, setFilter] = useState<OrderFilter>('all')
    const [selectedId, setSelectedId] = useState<string | null>(null)

    const liveRows = useMemo(
        () => (mode === 'live' ? orders.map((o, i) => toLiveOrderRow(o, i)) : []),
        [orders, mode],
    )
    const historyRows = useMemo(
        () => (mode === 'history' ? orders.map((o, i) => toHistoryOrderRow(o, i)) : []),
        [orders, mode],
    )

    const filteredLive = useMemo(() => {
        if (filter === 'buy') return liveRows.filter(r => r.isBuy)
        if (filter === 'sell') return liveRows.filter(r => r.isSell)
        if (filter === 'error') return liveRows.filter(r => r.isError)
        return liveRows
    }, [liveRows, filter])

    const selectedHistory = useMemo(
        () => historyRows.find(r => r.id === selectedId) ?? null,
        [historyRows, selectedId],
    )

    const chips: Array<{ key: OrderFilter; label: string }> = [
        { key: 'all', label: 'Все' },
        { key: 'buy', label: 'Покупки' },
        { key: 'sell', label: 'Продажи' },
        { key: 'error', label: 'Ошибки' },
    ]

    const resolvedEmptyTitle = emptyTitle
        ?? (mode === 'history'
            ? 'Нет заявок за период'
            : 'Сейчас пусто — лимиты появятся, когда робот выставит вход или TP/SL.')
    const resolvedEmptySub = emptySub
        ?? (mode === 'history'
            ? 'Сдвиньте даты или дождитесь выставления ордеров роботом.'
            : undefined)
    const resolvedAria = ariaLabel ?? (mode === 'history' ? 'История заявок' : 'Активные заявки')

    let body: React.ReactNode

    if (mode === 'history') {
        body = historyRows.length === 0 ? (
            <div className="robots-monitor-empty">
                <p className="robots-monitor-empty__sub"><b>{resolvedEmptyTitle}</b></p>
                {resolvedEmptySub ? (
                    <p className="robots-monitor-empty__sub">{resolvedEmptySub}</p>
                ) : null}
            </div>
        ) : (
            <div className={`robots-v2-logs-split${selectedHistory ? ' robots-v2-logs-split--open' : ''}`}>
                <div className="robots-v2-logs-split__table">
                    <MonitorTableViewport
                        ariaLabel={resolvedAria}
                        syncKey={historyRows.map(r => r.id).join('|')}
                        renderHead={() => (
                            <tr>
                                <th>Время</th>
                                <th>Тикер</th>
                                <th>Выставили</th>
                                <th>Ответ брокера</th>
                            </tr>
                        )}
                        bodyRows={historyRows.map(row => (
                            <tr
                                key={row.id}
                                className={selectedId === row.id ? 'robots-v2-table__row--active' : undefined}
                                onClick={() => setSelectedId(selectedId === row.id ? null : row.id)}
                                style={{ cursor: 'pointer' }}
                            >
                                <td className="mono">{row.time}</td>
                                <td>
                                    <b className="robots-monitor-day-trades__tk">{row.ticker}</b>
                                    <div className="robots-monitor-day-trades__muted">{row.sideLabel}</div>
                                </td>
                                <td title={row.submitted}>{row.submitted}</td>
                                <td className="robots-monitor-day-trades__muted" title={row.replySummary}>
                                    {row.replySummary}
                                </td>
                            </tr>
                        ))}
                    />
                </div>
                {selectedHistory ? (
                    <MonitorContextPanel
                        title={`${selectedHistory.ticker} · ${selectedHistory.statusLabel}`}
                        onClose={() => setSelectedId(null)}
                        meta={[
                            { label: 'Время', value: <span className="mono">{selectedHistory.time}</span> },
                            {
                                label: 'Тип / режим',
                                value: `${selectedHistory.orderType}${selectedHistory.mode ? ` · ${selectedHistory.mode}` : ''}`,
                            },
                            {
                                label: 'Цикл',
                                value: selectedHistory.cycleId
                                    ? <span className="mono">{selectedHistory.cycleId}</span>
                                    : '—',
                            },
                        ]}
                        blocks={[
                            {
                                label: 'Выставили',
                                body: <pre className="robots-v2-log-payload">{selectedHistory.submitted}</pre>,
                            },
                            {
                                label: 'Ответ брокера',
                                body: (
                                    <pre className="robots-v2-log-payload">
                                        {JSON.stringify(selectedHistory.replyPayload, null, 2)}
                                    </pre>
                                ),
                            },
                        ]}
                    />
                ) : null}
            </div>
        )
    } else {
        body = (
            <>
                {liveRows.length > 0 ? (
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
                {filteredLive.length === 0 ? (
                    <div className="robots-monitor-empty">
                        <p className="robots-monitor-empty__sub">
                            {liveRows.length === 0
                                ? resolvedEmptyTitle
                                : 'В этом фильтре пусто — сбросьте фильтр или дождитесь заявок этого типа.'}
                        </p>
                    </div>
                ) : (
                    <MonitorTableViewport
                        ariaLabel={resolvedAria}
                        syncKey={`${filter}:${filteredLive.map(r => r.id).join('|')}`}
                        renderHead={() => (
                            <tr>
                                <th>Тикер</th>
                                <th>Ордер</th>
                                <th>Статус</th>
                                <th>Время</th>
                            </tr>
                        )}
                        bodyRows={filteredLive.map(row => (
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
                    />
                )}
                {liveRows.length > 0 && footnote ? (
                    <p className="robots-v2-hint robots-monitor-live-orders__cap">{footnote}</p>
                ) : null}
            </>
        )
    }

    if (bare) {
        return (
            <div className={`robots-monitor-day-trades robots-monitor-live-orders ${className}`.trim()}>
                {body}
            </div>
        )
    }

    return (
        <Card className={`dashboard-assets-card robots-monitor-day-trades robots-monitor-live-orders ${className}`.trim()}>
            {title != null ? (
                <div className="dashboard-assets-card__head robots-monitor-orders__head">
                    <h3 className="dashboard-panel-title">
                        {title}
                        {(mode === 'live' ? liveRows : historyRows).length > 0 ? (
                            <span className="robots-v2-hint">
                                {' '}· {(mode === 'live' ? liveRows : historyRows).length}
                            </span>
                        ) : null}
                    </h3>
                </div>
            ) : null}
            {body}
        </Card>
    )
}
