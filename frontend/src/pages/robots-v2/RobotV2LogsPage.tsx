import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { RobotPageChrome } from '@/pages/robots-v2/components/RobotPageChrome'
import { fmtErr, fmtNum, fmtPrice } from '@/pages/robots-v2/formatters'
import { todayMoscowDayKey } from '@/pages/robots-v2/monitorUtils'
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

const PERIOD_PRESETS = [
    { id: '1', label: 'Сегодня', days: 1 },
    { id: '7', label: '7 дней', days: 7 },
    { id: '30', label: '30 дней', days: 30 },
    { id: '90', label: '90 дней', days: 90 },
] as const

const HISTORY_LIMIT = 500

function shiftMoscowDate(dayKey: string, deltaDays: number): string {
    const [year, month, day] = dayKey.split('-').map(Number)
    const utc = new Date(Date.UTC(year, month - 1, day))
    utc.setUTCDate(utc.getUTCDate() + deltaDays)
    return utc.toISOString().slice(0, 10)
}

/** Inclusive Moscow calendar days → half-open UTC window [from, to). */
function moscowPeriodToUtc(fromDate: string, toDate: string): { from: string; to: string } {
    const from = new Date(`${fromDate}T00:00:00+03:00`).toISOString()
    const end = new Date(`${toDate}T00:00:00+03:00`)
    end.setUTCDate(end.getUTCDate() + 1)
    return { from, to: end.toISOString() }
}

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

function shownCount(shown: number, total: number): string {
    if (total > shown) return `${shown} из ${total}`
    return String(total)
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
    const todayKey = todayMoscowDayKey()
    const [fromDate, setFromDate] = useState(() => shiftMoscowDate(todayMoscowDayKey(), -29))
    const [toDate, setToDate] = useState(() => todayMoscowDayKey())

    const loadAudit = useCallback(async () => {
        if (!Number.isFinite(robotId) || !fromDate || !toDate) return
        setAuditLoading(true)
        try {
            const start = fromDate <= toDate ? fromDate : toDate
            const end = fromDate <= toDate ? toDate : fromDate
            const range = moscowPeriodToUtc(start, end)
            const data = await robotV2Service.fetchAudit({
                robotId,
                limit: HISTORY_LIMIT,
                types: [view],
                from: range.from,
                to: range.to,
            })
            setAudit(data)
        } catch (e) {
            toast.show(fmtErr(e), 'error')
            setAudit(null)
        } finally {
            setAuditLoading(false)
        }
    }, [robotId, view, fromDate, toDate, toast])

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
                eyebrow="ИСТОРИЯ"
                title="История"
                robotId={robotId}
                active="logs"
                subtitle="Сохранённые исполнения, заявки и циклы за выбранный период. Лайв показывает только сегодня."
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
                        aria-label="Раздел истории"
                        options={VIEW_OPTIONS}
                        value={view}
                        onChange={v => setView(v as ViewMode)}
                    />
                    <div className="robots-v2-lab-period" aria-label="Период истории">
                        <SegmentedControl
                            className="portfolio-period-control"
                            aria-label="Пресет периода"
                            options={[
                                ...PERIOD_PRESETS.map(p => ({ value: p.id, label: p.label })),
                                { value: 'custom', label: 'Свой' },
                            ]}
                            value={
                                PERIOD_PRESETS.find(
                                    p => fromDate === shiftMoscowDate(todayKey, -(p.days - 1)) && toDate === todayKey,
                                )?.id ?? 'custom'
                            }
                            onChange={id => {
                                const preset = PERIOD_PRESETS.find(p => p.id === id)
                                if (!preset) return
                                setFromDate(shiftMoscowDate(todayKey, -(preset.days - 1)))
                                setToDate(todayKey)
                            }}
                        />
                        <DateRangePicker
                            variant="fields"
                            showLabel={false}
                            fromValue={fromDate ? `${fromDate}T00:00` : ''}
                            toValue={toDate ? `${toDate}T00:00` : ''}
                            onFromChange={v => setFromDate(v ? v.slice(0, 10) : '')}
                            onToChange={v => setToDate(v ? v.slice(0, 10) : '')}
                        />
                    </div>
                </Card>

                {view === 'fills' && (
                    <Card className="dashboard-assets-card robots-v2-logs-card portfolio-history-zone">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Исполнения</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{shownCount(fills.length, auditCount)}</span> : null}
                        </div>
                        {showSkeleton ? (
                            <AuditTableSkeleton />
                        ) : (
                            <DataTable
                                columns={fillColumns}
                                data={fillRows}
                                keyField="id"
                                emptyText="Нет исполнений за период"
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
                            <h3 className="dashboard-panel-title">Заявки</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{shownCount(orders.length, auditCount)}</span> : null}
                        </div>
                        {showSkeleton ? (
                            <AuditTableSkeleton />
                        ) : (
                            <DataTable
                                columns={orderColumns}
                                data={orderRows}
                                keyField="id"
                                emptyText="Нет заявок за период"
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
                            <h3 className="dashboard-panel-title">Циклы</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{shownCount(cycles.length, auditCount)}</span> : null}
                        </div>
                        {showSkeleton ? (
                            <AuditTableSkeleton />
                        ) : (
                            <DataTable
                                columns={cycleColumns}
                                data={cycleRows}
                                keyField="id"
                                emptyText="Нет циклов за период"
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
