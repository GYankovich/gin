import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faTowerBroadcast } from '@fortawesome/free-solid-svg-icons'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { PageHero } from '@/components/ui/PageHero'
import { useToast } from '@/components/ui/Toast'
import { robotV2Service } from '@/services/robotV2Service'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'
import type {
    AuditDataType,
    RobotV2AuditResponse,
    RobotV2Cycle,
    RobotV2Fill,
    RobotV2Order,
} from '@/types/robotV2'

function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    return err?.message || 'Ошибка'
}

type ViewMode = 'stream' | AuditDataType

const AUDIT_TABS: Array<{ id: AuditDataType; label: string }> = [
    { id: 'fills', label: 'Исполнения' },
    { id: 'orders', label: 'Заявки' },
    { id: 'cycles', label: 'Циклы' },
]

function pickField<T>(row: Record<string, unknown>, camel: string, snake: string): T | undefined {
    return (row[camel] ?? row[snake]) as T | undefined
}

function fmtTime(ts: string | null | undefined): string {
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

function fmtPrice(v: unknown): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return '—'
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 4 })
}

function fmtNum(v: unknown, digits = 2): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return '—'
    return n.toLocaleString('ru-RU', { maximumFractionDigits: digits })
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

export default function RobotV2LogsPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const navigate = useNavigate()
    const toast = useToast()
    const [view, setView] = useState<ViewMode>('stream')
    const [items, setItems] = useState<Array<Record<string, unknown>>>([])
    const [filter, setFilter] = useState('')
    const [loading, setLoading] = useState(true)
    const [audit, setAudit] = useState<RobotV2AuditResponse | null>(null)
    const [auditLoading, setAuditLoading] = useState(false)

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

    return (
        <div className="page" data-page="robots-v2">
            <PageHero
                eyebrow="AUDIT NODE"
                title={`ЛОГИ #${robotId}`}
                subtitle="Поток сессии · audit DB (исполнения, заявки, циклы)"
                actions={
                    <>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate('/robots-v2')}
                        >
                            Флот
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate(`/robots-v2/${robotId}/monitor`)}
                        >
                            <FontAwesomeIcon icon={faTowerBroadcast} />
                            Лайв
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-hero__cfg"
                            onClick={() => navigate(`/robots-v2/${robotId}/backtest`)}
                        >
                            Бэктест
                        </Button>
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
                    <div className="robots-v2-chip-row robots-v2-logs-tabs" role="tablist" aria-label="Источник данных">
                        <button
                            type="button"
                            role="tab"
                            aria-selected={view === 'stream'}
                            className={`dashboard-sticky-chip${view === 'stream' ? ' dashboard-sticky-chip--active' : ''}`}
                            onClick={() => setView('stream')}
                        >
                            <span className="dashboard-sticky-chip__cur">Поток</span>
                        </button>
                        {AUDIT_TABS.map(tab => (
                            <button
                                key={tab.id}
                                type="button"
                                role="tab"
                                aria-selected={view === tab.id}
                                className={`dashboard-sticky-chip${view === tab.id ? ' dashboard-sticky-chip--active' : ''}`}
                                onClick={() => setView(tab.id)}
                            >
                                <span className="dashboard-sticky-chip__cur">{tab.label}</span>
                            </button>
                        ))}
                    </div>
                </Card>

                {view === 'stream' && (
                    <Card className="portfolio-toolbar robots-v2-toolbar robots-v2-logs-toolbar">
                        <div className="robots-v2-chip-row robots-v2-logs-tabs" role="tablist" aria-label="Тип события">
                            {[
                                { id: '', label: 'Все' },
                                { id: 'cycle', label: 'Цикл' },
                                { id: 'stage', label: 'Этап' },
                                { id: 'signal', label: 'Сигнал' },
                                { id: 'order', label: 'Заявка' },
                                { id: 'decision', label: 'Решение' },
                                { id: 'health', label: 'Health' },
                            ].map(t => (
                                <button
                                    key={t.id || 'all'}
                                    type="button"
                                    role="tab"
                                    aria-selected={filter === t.id}
                                    className={`dashboard-sticky-chip${filter === t.id ? ' dashboard-sticky-chip--active' : ''}`}
                                    onClick={() => setFilter(t.id)}
                                >
                                    <span className="dashboard-sticky-chip__cur">{t.label}</span>
                                </button>
                            ))}
                        </div>
                    </Card>
                )}

                {view === 'stream' && (
                    <>
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
                                        const rest = { ...ev }
                                        delete rest.ts
                                        delete rest.type
                                        delete rest.robotId
                                        return (
                                            <li key={`${ts}-${i}`}>
                                                <span className="mono">{ts ? new Date(ts).toLocaleString('ru-RU') : '—'}</span>{' '}
                                                <Badge variant="cyan">{type}</Badge>{' '}
                                                <code className="robots-v2-log-payload">{JSON.stringify(rest)}</code>
                                            </li>
                                        )
                                    })}
                                </ul>
                            )}
                        </Card>
                    </>
                )}

                {view === 'fills' && (
                    <Card className="dashboard-assets-card robots-v2-logs-card">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Исполнения (audit)</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{auditCount}</span> : null}
                        </div>
                        {auditLoading && fills.length === 0 ? (
                            <p className="dashboard-empty">Загрузка…</p>
                        ) : fills.length === 0 ? (
                            <p className="dashboard-empty">Нет исполнений в audit</p>
                        ) : (
                            <div className="robots-v2-scan-table-wrap">
                                <table className="robots-v2-table robots-v2-scan-table">
                                    <thead>
                                        <tr>
                                            <th>Время</th>
                                            <th>Тикер</th>
                                            <th>Сторона</th>
                                            <th>Кол-во</th>
                                            <th>Цена</th>
                                            <th>Комиссия</th>
                                            <th>В карман</th>
                                            <th>Тип</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {fills.map((row: RobotV2Fill) => {
                                            const raw = row as unknown as Record<string, unknown>
                                            const netPnl = pickField<number | null>(raw, 'netPnl', 'net_pnl')
                                            const tone =
                                                netPnl == null ? 'neutral' : netPnl >= 0 ? 'up' : 'down'
                                            return (
                                                <tr key={row.id}>
                                                    <td className="mono">{fmtTime(row.filledAt ?? pickField(raw, 'filledAt', 'filled_at'))}</td>
                                                    <td><strong>{row.ticker}</strong></td>
                                                    <td>{row.side}</td>
                                                    <td className="mono">{fmtNum(row.quantity, 4)}</td>
                                                    <td className="mono">{fmtPrice(row.price)}</td>
                                                    <td className="mono">{fmtNum(row.commission)}</td>
                                                    <td className={`mono robots-v2-pnl--${tone}`}>
                                                        {netPnl == null ? '—' : `${fmtNum(netPnl)} ₽`}
                                                    </td>
                                                    <td>{tradeReasonLabel(row.kind)}</td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </Card>
                )}

                {view === 'orders' && (
                    <Card className="dashboard-assets-card robots-v2-logs-card">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Заявки (audit)</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{auditCount}</span> : null}
                        </div>
                        {auditLoading && orders.length === 0 ? (
                            <p className="dashboard-empty">Загрузка…</p>
                        ) : orders.length === 0 ? (
                            <p className="dashboard-empty">Нет заявок в audit</p>
                        ) : (
                            <div className="robots-v2-scan-table-wrap robots-v2-orders-table-wrap">
                                <table className="robots-v2-table robots-v2-scan-table">
                                    <thead>
                                        <tr>
                                            <th>Время</th>
                                            <th>Тикер</th>
                                            <th>Сторона</th>
                                            <th>Тип</th>
                                            <th>Кол-во</th>
                                            <th>Цена</th>
                                            <th>Статус</th>
                                            <th>Отказ</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {orders.map((row: RobotV2Order) => {
                                            const raw = row as unknown as Record<string, unknown>
                                            const submitted = row.submittedAt ?? pickField<string>(raw, 'submittedAt', 'submitted_at')
                                            const reject = row.rejectReason ?? pickField<string | null>(raw, 'rejectReason', 'reject_reason')
                                            return (
                                                <tr key={row.id}>
                                                    <td className="mono">{fmtTime(submitted)}</td>
                                                    <td><strong>{row.ticker}</strong></td>
                                                    <td>{row.side}</td>
                                                    <td>{tradeReasonLabel(row.kind)}</td>
                                                    <td className="mono">{fmtNum(row.quantity, 4)}</td>
                                                    <td className="mono">{fmtPrice(row.price)}</td>
                                                    <td>{orderStatusLabel(row.status)}</td>
                                                    <td className="robots-v2-scan-reason">{reject || '—'}</td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </Card>
                )}

                {view === 'cycles' && (
                    <Card className="dashboard-assets-card robots-v2-logs-card">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Циклы (audit)</h3>
                            {auditCount > 0 ? <span className="robots-v2-hint">{auditCount}</span> : null}
                        </div>
                        {auditLoading && cycles.length === 0 ? (
                            <p className="dashboard-empty">Загрузка…</p>
                        ) : cycles.length === 0 ? (
                            <p className="dashboard-empty">Нет циклов в audit</p>
                        ) : (
                            <div className="robots-v2-scan-table-wrap">
                                <table className="robots-v2-table robots-v2-scan-table">
                                    <thead>
                                        <tr>
                                            <th>#</th>
                                            <th>Wake</th>
                                            <th>Начало</th>
                                            <th>Конец</th>
                                            <th>Статус</th>
                                            <th>Skip</th>
                                            <th>Equity</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {cycles.map((row: RobotV2Cycle) => {
                                            const raw = row as unknown as Record<string, unknown>
                                            return (
                                                <tr key={row.id}>
                                                    <td className="mono">{row.cycleNumber ?? pickField(raw, 'cycleNumber', 'cycle_number')}</td>
                                                    <td className="mono">{row.triggeredBy ?? pickField(raw, 'triggeredBy', 'triggered_by')}</td>
                                                    <td className="mono">{fmtTime(row.startedAt ?? pickField(raw, 'startedAt', 'started_at'))}</td>
                                                    <td className="mono">{fmtTime(row.finishedAt ?? pickField(raw, 'finishedAt', 'finished_at'))}</td>
                                                    <td>{cycleStatusLabel(row.status)}</td>
                                                    <td className="robots-v2-scan-reason">
                                                        {row.skipReason ?? pickField(raw, 'skipReason', 'skip_reason') ?? '—'}
                                                    </td>
                                                    <td className="mono">{fmtNum(row.equity, 0)}</td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </Card>
                )}
            </div>
        </div>
    )
}
