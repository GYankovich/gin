import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { useToast } from '@/components/ui/Toast'
import { RobotPageChrome } from '@/pages/robots-v2/components/RobotPageChrome'
import { fmtErr, fmtNum, fmtPrice } from '@/pages/robots-v2/formatters'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'
import { robotV2Service } from '@/services/robotV2Service'
import type {
    AuditDataType,
    RobotV2AuditResponse,
    RobotV2Cycle,
    RobotV2Fill,
    RobotV2Order,
} from '@/types/robotV2'

type ViewMode = 'stream' | AuditDataType

const VIEW_OPTIONS: Array<{ value: ViewMode; label: string }> = [
    { value: 'stream', label: 'Поток' },
    { value: 'fills', label: 'Исполнения' },
    { value: 'orders', label: 'Заявки' },
    { value: 'cycles', label: 'Циклы' },
]

const STREAM_FILTERS: Array<{ value: string; label: string }> = [
    { value: '', label: 'Все' },
    { value: 'cycle', label: 'Цикл' },
    { value: 'stage', label: 'Этап' },
    { value: 'signal', label: 'Сигнал' },
    { value: 'order', label: 'Заявка' },
    { value: 'decision', label: 'Решение' },
    { value: 'health', label: 'Health' },
]

function pickField<T>(row: Record<string, unknown>, camel: string, snake: string): T | undefined {
    return (row[camel] ?? row[snake]) as T | undefined
}

function fmtTimeShort(ts: string | null | undefined): string {
    if (!ts) return '—'
    const d = new Date(ts)
    if (!Number.isFinite(d.getTime())) return '—'
    return d.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    })
}

function orderStatusLabel(status: string): string {
    switch (String(status || '').toLowerCase()) {
        case 'closed':
            return 'Закрыта'
        case 'open':
            return 'Открыта'
        case 'resting':
            return 'В рынке'
        case 'filled':
            return 'Исполнено'
        case 'cancelled':
        case 'canceled':
            return 'Отменена'
        case 'rejected':
            return 'Отклонена'
        default:
            return status || '—'
    }
}

function cycleStatusLabel(status: string): string {
    switch (String(status || '').toLowerCase()) {
        case 'completed':
            return 'Завершён'
        case 'skipped':
            return 'Пропущен'
        case 'failed':
            return 'Ошибка'
        case 'running':
            return 'В работе'
        default:
            return status || '—'
    }
}

function streamSummary(ev: Record<string, unknown>): string {
    const code = ev.code ?? ev.stage ?? ev.ticker ?? ev.message
    if (code != null && String(code).trim()) return String(code)
    const keys = Object.keys(ev).filter(k => !['ts', 'type', 'robotId', 'robot_id'].includes(k))
    if (keys.length === 0) return '—'
    try {
        return JSON.stringify(
            Object.fromEntries(keys.slice(0, 4).map(k => [k, ev[k]])),
        ).slice(0, 120)
    } catch {
        return '—'
    }
}

export default function RobotV2LogsPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const toast = useToast()
    const [view, setView] = useState<ViewMode>('stream')
    const [items, setItems] = useState<Array<Record<string, unknown>>>([])
    const [filter, setFilter] = useState('')
    const [loading, setLoading] = useState(true)
    const [audit, setAudit] = useState<RobotV2AuditResponse | null>(null)
    const [auditLoading, setAuditLoading] = useState(false)
    const [expandedStreamKey, setExpandedStreamKey] = useState<string | null>(null)

    const loadStream = useCallback(async () => {
        if (!Number.isFinite(robotId)) return
        setLoading(true)
        try {
            const data = await robotV2Service.getLogs(robotId, {
                limit: 200,
                eventType: filter || undefined,
            })
            setItems(data.items || [])
        } catch (e) {
            toast.show(fmtErr(e), 'error')
            setItems([])
        } finally {
            setLoading(false)
        }
    }, [robotId, filter, toast])

    const loadAudit = useCallback(async () => {
        if (!Number.isFinite(robotId) || view === 'stream') return
        setAuditLoading(true)
        try {
            const data = await robotV2Service.fetchAudit({
                robotId,
                limit: 100,
                types: [view],
            })
            setAudit(data)
        } catch (e) {
            toast.show(fmtErr(e), 'error')
            setAudit(null)
        } finally {
            setAuditLoading(false)
        }
    }, [robotId, view, toast])

    useEffect(() => {
        if (view === 'stream') {
            void loadStream()
            const t = window.setInterval(() => void loadStream(), 4000)
            return () => window.clearInterval(t)
        }
        void loadAudit()
        const t = window.setInterval(() => void loadAudit(), 8000)
        return () => window.clearInterval(t)
    }, [view, loadStream, loadAudit])

    const exportJson = () => {
        const payload =
            view === 'stream'
                ? items
                : audit?.[view as keyof RobotV2AuditResponse]
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `robot-${robotId}-${view}.json`
        a.click()
        URL.revokeObjectURL(url)
    }

    const fills = audit?.fills?.items || []
    const orders = audit?.orders?.items || []
    const cycles = audit?.cycles?.items || []
    const auditCount =
        view === 'fills' ? audit?.fills?.total ?? fills.length
        : view === 'orders' ? audit?.orders?.total ?? orders.length
        : view === 'cycles' ? audit?.cycles?.total ?? cycles.length
        : 0

    const fillRows = useMemo(() => fills.map((row: RobotV2Fill) => {
        const raw = row as unknown as Record<string, unknown>
        const netPnl = pickField<number | null>(raw, 'netPnl', 'net_pnl')
        return {
            id: row.id,
            time: fmtTimeShort(row.filledAt ?? pickField(raw, 'filledAt', 'filled_at')),
            ticker: row.ticker,
            side: row.side,
            quantity: fmtNum(row.quantity, 4),
            price: fmtPrice(row.price, 4),
            commission: fmtNum(row.commission),
            netPnl,
            netPnlLabel: netPnl == null ? '—' : `${fmtNum(netPnl)} ₽`,
            tone: netPnl == null ? 'neutral' : netPnl >= 0 ? 'up' : 'down',
            kind: tradeReasonLabel(row.kind),
        }
    }), [fills])

    const fillColumns = useMemo<Column<(typeof fillRows)[number]>[]>(() => [
        { key: 'time', header: 'Время', render: r => <span className="mono">{r.time}</span> },
        { key: 'ticker', header: 'Тикер', sortable: true, render: r => <strong>{r.ticker}</strong> },
        { key: 'side', header: 'Сторона' },
        { key: 'quantity', header: 'Кол-во', render: r => <span className="mono">{r.quantity}</span> },
        { key: 'price', header: 'Цена', render: r => <span className="mono">{r.price}</span> },
        { key: 'commission', header: 'Комиссия', render: r => <span className="mono">{r.commission}</span> },
        {
            key: 'netPnl',
            header: 'В карман',
            sortable: true,
            render: r => <span className={`mono robots-v2-pnl--${r.tone}`}>{r.netPnlLabel}</span>,
        },
        { key: 'kind', header: 'Тип' },
    ], [])

    const orderRows = useMemo(() => orders.map((row: RobotV2Order) => {
        const raw = row as unknown as Record<string, unknown>
        const submitted = row.submittedAt ?? pickField<string>(raw, 'submittedAt', 'submitted_at')
        const reject = row.rejectReason ?? pickField<string | null>(raw, 'rejectReason', 'reject_reason')
        return {
            id: row.id,
            time: fmtTimeShort(submitted),
            ticker: row.ticker,
            side: row.side,
            kind: tradeReasonLabel(row.kind),
            quantity: fmtNum(row.quantity, 4),
            price: fmtPrice(row.price, 4),
            status: orderStatusLabel(row.status),
            reject: reject || '—',
        }
    }), [orders])

    const orderColumns = useMemo<Column<(typeof orderRows)[number]>[]>(() => [
        { key: 'time', header: 'Время', render: r => <span className="mono">{r.time}</span> },
        { key: 'ticker', header: 'Тикер', sortable: true, render: r => <strong>{r.ticker}</strong> },
        { key: 'side', header: 'Сторона' },
        { key: 'kind', header: 'Тип' },
        { key: 'quantity', header: 'Кол-во', render: r => <span className="mono">{r.quantity}</span> },
        { key: 'price', header: 'Цена', render: r => <span className="mono">{r.price}</span> },
        { key: 'status', header: 'Статус' },
        { key: 'reject', header: 'Отказ', render: r => <span className="robots-v2-scan-reason">{r.reject}</span> },
    ], [])

    const cycleRows = useMemo(() => cycles.map((row: RobotV2Cycle) => {
        const raw = row as unknown as Record<string, unknown>
        return {
            id: row.id,
            cycleNumber: Number(row.cycleNumber ?? pickField(raw, 'cycleNumber', 'cycle_number') ?? 0),
            wake: String(row.triggeredBy ?? pickField(raw, 'triggeredBy', 'triggered_by') ?? '—'),
            started: fmtTimeShort(row.startedAt ?? pickField(raw, 'startedAt', 'started_at')),
            finished: fmtTimeShort(row.finishedAt ?? pickField(raw, 'finishedAt', 'finished_at')),
            status: cycleStatusLabel(row.status),
            skip: String(row.skipReason ?? pickField(raw, 'skipReason', 'skip_reason') ?? '—'),
            equity: fmtNum(row.equity, 0),
        }
    }), [cycles])

    const cycleColumns = useMemo<Column<(typeof cycleRows)[number]>[]>(() => [
        { key: 'cycleNumber', header: '#', sortable: true, render: r => <span className="mono">{r.cycleNumber}</span> },
        { key: 'wake', header: 'Wake', render: r => <span className="mono">{r.wake}</span> },
        { key: 'started', header: 'Начало', render: r => <span className="mono">{r.started}</span> },
        { key: 'finished', header: 'Конец', render: r => <span className="mono">{r.finished}</span> },
        { key: 'status', header: 'Статус' },
        { key: 'skip', header: 'Skip', render: r => <span className="robots-v2-scan-reason">{r.skip}</span> },
        { key: 'equity', header: 'Equity', render: r => <span className="mono">{r.equity}</span> },
    ], [])

    return (
        <div className="page" data-page="robots">
            <RobotPageChrome
                eyebrow="AUDIT NODE"
                title={`ЛОГИ #${robotId}`}
                robotId={robotId}
                active="logs"
                subtitle="Поток сессии · audit DB (исполнения, заявки, циклы)"
                actions={
                    <>
                        <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            onClick={exportJson}
                            disabled={view === 'stream' ? !items.length : auditCount === 0}
                        >
                            Экспорт JSON
                        </Button>
                        <Button
                            type="button"
                            size="sm"
                            onClick={() => void (view === 'stream' ? loadStream() : loadAudit())}
                            loading={view === 'stream' ? loading : auditLoading}
                        >
                            Обновить
                        </Button>
                    </>
                }
            />

            <div className="dashboard-layout">
                <Card className="portfolio-toolbar robots-v2-toolbar robots-v2-logs-toolbar">
                    <SegmentedControl
                        className="portfolio-period-control"
                        aria-label="Источник данных"
                        options={VIEW_OPTIONS}
                        value={view}
                        onChange={v => setView(v as ViewMode)}
                    />
                </Card>

                {view === 'stream' && (
                    <Card className="portfolio-toolbar robots-v2-toolbar robots-v2-logs-toolbar">
                        <SegmentedControl
                            className="portfolio-period-control"
                            aria-label="Тип события"
                            options={STREAM_FILTERS}
                            value={filter}
                            onChange={setFilter}
                        />
                    </Card>
                )}

                {view === 'stream' && (
                    <Card className="dashboard-assets-card robots-v2-logs-card">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">События (память сессии)</h3>
                        </div>
                        {loading && items.length === 0 ? (
                            <p className="dashboard-empty">Загрузка…</p>
                        ) : items.length === 0 ? (
                            <p className="dashboard-empty">Пока нет событий. Запустите робота, чтобы наполнять лог.</p>
                        ) : (
                            <ul className="robots-v2-event-list robots-v2-event-list--dense">
                                {items.map((ev, i) => {
                                    const ts = String(ev.ts || '')
                                    const type = String(ev.type || 'event')
                                    const key = `${ts}-${i}`
                                    const rest = { ...ev }
                                    delete rest.ts
                                    delete rest.type
                                    delete rest.robotId
                                    const expanded = expandedStreamKey === key
                                    return (
                                        <li key={key}>
                                            <button
                                                type="button"
                                                className="robots-v2-log-row"
                                                onClick={() => setExpandedStreamKey(expanded ? null : key)}
                                            >
                                                <span className="mono">
                                                    {ts ? new Date(ts).toLocaleString('ru-RU') : '—'}
                                                </span>{' '}
                                                <Badge variant="cyan">{type}</Badge>{' '}
                                                <span className="robots-v2-log-summary">{streamSummary(rest)}</span>
                                            </button>
                                            {expanded ? (
                                                <pre className="robots-v2-log-payload">{JSON.stringify(rest, null, 2)}</pre>
                                            ) : null}
                                        </li>
                                    )
                                })}
                            </ul>
                        )}
                    </Card>
                )}

                {view === 'fills' && (
                    <Card className="dashboard-assets-card robots-v2-logs-card portfolio-history-zone">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Исполнения (audit)</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{auditCount}</span> : null}
                        </div>
                        {auditLoading && fills.length === 0 ? (
                            <p className="dashboard-empty">Загрузка…</p>
                        ) : (
                            <DataTable
                                columns={fillColumns}
                                data={fillRows}
                                keyField="id"
                                emptyText="Нет исполнений в audit"
                                maxHeight={480}
                                mobilePrimary={r => (
                                    <div className="portfolio-mobile-split">
                                        <strong>{r.ticker}</strong>
                                        <span className={`mono robots-v2-pnl--${r.tone}`}>{r.netPnlLabel}</span>
                                    </div>
                                )}
                                mobileDetails={r => `${r.time} · ${r.side} · ${r.price}`}
                            />
                        )}
                    </Card>
                )}

                {view === 'orders' && (
                    <Card className="dashboard-assets-card robots-v2-logs-card portfolio-history-zone">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Заявки (audit)</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{auditCount}</span> : null}
                        </div>
                        {auditLoading && orders.length === 0 ? (
                            <p className="dashboard-empty">Загрузка…</p>
                        ) : (
                            <DataTable
                                columns={orderColumns}
                                data={orderRows}
                                keyField="id"
                                emptyText="Нет заявок в audit"
                                maxHeight={480}
                                mobilePrimary={r => (
                                    <div className="portfolio-mobile-split">
                                        <strong>{r.ticker}</strong>
                                        <span>{r.status}</span>
                                    </div>
                                )}
                                mobileDetails={r => `${r.time} · ${r.side} · ${r.kind}`}
                            />
                        )}
                    </Card>
                )}

                {view === 'cycles' && (
                    <Card className="dashboard-assets-card robots-v2-logs-card portfolio-history-zone">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Циклы (audit)</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{auditCount}</span> : null}
                        </div>
                        {auditLoading && cycles.length === 0 ? (
                            <p className="dashboard-empty">Загрузка…</p>
                        ) : (
                            <DataTable
                                columns={cycleColumns}
                                data={cycleRows}
                                keyField="id"
                                emptyText="Нет циклов в audit"
                                maxHeight={480}
                                defaultSortKey="cycleNumber"
                                defaultSortDir="desc"
                                mobilePrimary={r => (
                                    <div className="portfolio-mobile-split">
                                        <strong>#{r.cycleNumber}</strong>
                                        <span>{r.status}</span>
                                    </div>
                                )}
                                mobileDetails={r => `${r.started} · equity ${r.equity}`}
                            />
                        )}
                    </Card>
                )}
            </div>
        </div>
    )
}
