import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Skeleton } from '@/components/ui/Skeleton'
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

type ViewMode = AuditDataType

const VIEW_OPTIONS: Array<{ value: ViewMode; label: string }> = [
    { value: 'fills', label: 'Исполнения' },
    { value: 'orders', label: 'Заявки' },
    { value: 'cycles', label: 'Циклы' },
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

function AuditTableSkeleton({ rows = 6 }: { rows?: number }) {
    return (
        <div className="robots-v2-audit-skeleton" aria-busy="true" aria-label="Загрузка таблицы">
            <Skeleton width="100%" height="28px" borderRadius="4px" />
            {Array.from({ length: rows }).map((_, i) => (
                <div key={i} style={{ marginTop: 'var(--space-2)' }}>
                    <Skeleton width="100%" height="36px" borderRadius="4px" />
                </div>
            ))}
        </div>
    )
}

export default function RobotV2LogsPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const toast = useToast()
    const [view, setView] = useState<ViewMode>('fills')
    const [audit, setAudit] = useState<RobotV2AuditResponse | null>(null)
    const [auditLoading, setAuditLoading] = useState(false)

    const loadAudit = useCallback(async () => {
        if (!Number.isFinite(robotId)) return
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
        void loadAudit()
        const t = window.setInterval(() => void loadAudit(), 8000)
        return () => window.clearInterval(t)
    }, [loadAudit])

    const exportJson = () => {
        const payload = audit?.[view as keyof RobotV2AuditResponse]
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
            trigger: String(row.triggeredBy ?? pickField(raw, 'triggeredBy', 'triggered_by') ?? '—'),
            started: fmtTimeShort(row.startedAt ?? pickField(raw, 'startedAt', 'started_at')),
            finished: fmtTimeShort(row.finishedAt ?? pickField(raw, 'finishedAt', 'finished_at')),
            status: cycleStatusLabel(row.status),
            skip: String(row.skipReason ?? pickField(raw, 'skipReason', 'skip_reason') ?? '—'),
            equity: fmtNum(row.equity, 0),
        }
    }), [cycles])

    const cycleColumns = useMemo<Column<(typeof cycleRows)[number]>[]>(() => [
        { key: 'cycleNumber', header: '#', sortable: true, render: r => <span className="mono">{r.cycleNumber}</span> },
        { key: 'trigger', header: 'Триггер', render: r => <span className="mono">{r.trigger}</span> },
        { key: 'started', header: 'Начало', render: r => <span className="mono">{r.started}</span> },
        { key: 'finished', header: 'Конец', render: r => <span className="mono">{r.finished}</span> },
        { key: 'status', header: 'Статус' },
        { key: 'skip', header: 'Skip', render: r => <span className="robots-v2-scan-reason">{r.skip}</span> },
        { key: 'equity', header: 'Equity', render: r => <span className="mono">{r.equity}</span> },
    ], [])

    const showSkeleton =
        auditLoading
        && ((view === 'fills' && fills.length === 0)
            || (view === 'orders' && orders.length === 0)
            || (view === 'cycles' && cycles.length === 0))

    return (
        <div className="page" data-page="robots">
            <RobotPageChrome
                eyebrow="AUDIT NODE"
                title={`AUDIT #${robotId}`}
                robotId={robotId}
                active="logs"
                subtitle="Только persisted: исполнения · заявки · циклы. Живой поток — на Лайве."
                actions={
                    <>
                        <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            onClick={exportJson}
                            disabled={auditCount === 0}
                        >
                            Экспорт JSON
                        </Button>
                        <Button
                            type="button"
                            size="sm"
                            onClick={() => void loadAudit()}
                            loading={auditLoading}
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
                        aria-label="Источник audit"
                        options={VIEW_OPTIONS}
                        value={view}
                        onChange={v => setView(v as ViewMode)}
                    />
                    <p className="robots-v2-banner robots-v2-banner--warn robots-v2-audit-live-banner" role="note">
                        Живой поток — на вкладке{' '}
                        <Link to={`/robots/${robotId}/monitor`}>Лайв</Link>
                    </p>
                </Card>

                {view === 'fills' && (
                    <Card className="dashboard-assets-card robots-v2-logs-card portfolio-history-zone">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Исполнения (audit)</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{auditCount}</span> : null}
                        </div>
                        {showSkeleton ? (
                            <AuditTableSkeleton />
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
                        {showSkeleton ? (
                            <AuditTableSkeleton />
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
                        {showSkeleton ? (
                            <AuditTableSkeleton />
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
