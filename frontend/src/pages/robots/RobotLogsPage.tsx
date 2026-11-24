import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { MonitorDecisionsCard } from '@/pages/robots/components/MonitorDecisionsCard'
import { MonitorLiveOrdersCard } from '@/pages/robots/components/MonitorLiveOrdersCard'
import { MonitorOrdersCard } from '@/pages/robots/components/MonitorOrdersCard'
import { useQuietChromeActions } from '@/pages/robots/RobotQuietShell'
import { fmtErr } from '@/pages/robots/formatters'
import {
    fmtNetPnl,
    toOrderDisplayRow,
    todayMoscowDayKey,
} from '@/pages/robots/monitorUtils'
import { robotService } from '@/services/robotService'
import type {
    AuditDataType,
    TradingRobotAuditResponse,
    TradingRobotRoundTrip,
} from '@/types/robots'

type ViewMode = 'orders' | 'roundTrips' | 'decisions'

const VIEW_OPTIONS: Array<{ value: ViewMode; label: string }> = [
    { value: 'orders', label: 'Заявки' },
    { value: 'roundTrips', label: 'Сделки' },
    { value: 'decisions', label: 'Решения' },
]

const PERIOD_PRESETS = [
    { id: '1', label: 'Сегодня', days: 1 },
    { id: '7', label: '7 дней', days: 7 },
    { id: '30', label: '30 дней', days: 30 },
    { id: '90', label: '90 дней', days: 90 },
] as const

/** Per-request page size — must stay within API `limit` max (500 on older servers). */
const AUDIT_PAGE_SIZE = 500
const AUDIT_MAX_PAGES = 20

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

type AuditSectionKey = Exclude<keyof TradingRobotAuditResponse, 'robotId'>

/** Fetch every page for one audit type so history is not truncated at 500. */
async function fetchAuditSection(
    robotId: number,
    type: AuditDataType,
    range: { from: string; to: string },
): Promise<TradingRobotAuditResponse> {
    const key = type as AuditSectionKey
    const items: unknown[] = []
    let total = 0
    let offset = 0

    for (let page = 0; page < AUDIT_MAX_PAGES; page += 1) {
        const data = await robotService.fetchAudit({
            robotId,
            limit: AUDIT_PAGE_SIZE,
            offset,
            types: [type],
            from: range.from,
            to: range.to,
        })
        const section = data[key]
        if (!section) {
            return { robotId, [key]: { items: [], total: 0 } }
        }
        total = section.total
        items.push(...section.items)
        if (items.length >= total || section.items.length === 0) {
            return { robotId: data.robotId, [key]: { items, total } }
        }
        offset += section.items.length
    }

    return { robotId, [key]: { items, total } }
}

function shownCount(shown: number, total: number): string {
    if (total > shown) return `${shown} из ${total}`
    return String(total)
}

function AuditTableSkeleton({ rows = 6 }: { rows?: number }) {
    return (
        <div className="robots-audit-skeleton" aria-busy="true" aria-label="Загрузка таблицы">
            <Skeleton width="100%" height="28px" borderRadius="4px" />
            {Array.from({ length: rows }).map((_, i) => (
                <div key={i} style={{ marginTop: 'var(--space-2)' }}>
                    <Skeleton width="100%" height="36px" borderRadius="4px" />
                </div>
            ))}
        </div>
    )
}

export default function RobotLogsPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const toast = useToast()
    const [view, setView] = useState<ViewMode>('orders')
    const [audit, setAudit] = useState<TradingRobotAuditResponse | null>(null)
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
            const data = await fetchAuditSection(robotId, view as AuditDataType, range)
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

    const exportJson = useCallback(() => {
        const payload = audit?.[view as keyof TradingRobotAuditResponse]
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `robot-${robotId}-${view}.json`
        a.click()
        URL.revokeObjectURL(url)
    }, [audit, robotId, view])

    const orders = audit?.orders?.items || []
    const trips = audit?.roundTrips?.items || []
    const decisions = audit?.decisions?.items || []
    const auditCount =
        view === 'orders' ? audit?.orders?.total ?? orders.length
        : view === 'roundTrips' ? audit?.roundTrips?.total ?? trips.length
        : view === 'decisions' ? audit?.decisions?.total ?? decisions.length
        : 0

    const shownItems =
        view === 'orders' ? orders.length
            : view === 'roundTrips' ? trips.length
            : decisions.length

    const orderRecords = useMemo(
        () => orders.map(row => row as unknown as Record<string, unknown>),
        [orders],
    )

    const tradeRows = useMemo(
        () => trips.map((row: TradingRobotRoundTrip) => toOrderDisplayRow(row)),
        [trips],
    )

    const tradeTotal = useMemo(() => {
        let sum = 0
        let n = 0
        for (const row of tradeRows) {
            if (row.isOpen || row.pocket == null || !Number.isFinite(row.pocket)) continue
            sum += row.pocket
            n += 1
        }
        if (n === 0) return null
        return fmtNetPnl(sum)
    }, [tradeRows])

    const decisionRecords = useMemo(
        () => decisions.map(row => row as unknown as Record<string, unknown>),
        [decisions],
    )

    const showSkeleton =
        auditLoading
        && ((view === 'orders' && orders.length === 0)
            || (view === 'roundTrips' && trips.length === 0)
            || (view === 'decisions' && decisions.length === 0))

    useQuietChromeActions(() => (
        <>
            <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={exportJson}
                disabled={auditCount === 0}
            >
                Экспорт JSON
            </Button>
            <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void loadAudit()}
                loading={auditLoading}
            >
                Обновить
            </Button>
        </>
    ), [auditCount, auditLoading, exportJson, loadAudit])

    return (
        <div className="dashboard-layout">
            <Card className="portfolio-toolbar robots-toolbar robots-logs-toolbar">
                <div className="robots-logs-toolbar__view">
                    <SegmentedControl
                        className="portfolio-period-control robots-logs-toolbar__sections"
                        aria-label="Раздел истории"
                        options={VIEW_OPTIONS}
                        value={view}
                        onChange={v => setView(v as ViewMode)}
                    />
                    <span className="robots-logs-toolbar__count robots-hint">
                        {auditCount > 0 ? shownCount(shownItems, auditCount) : '0'}
                    </span>
                </div>
                <div className="robots-lab-period robots-logs-toolbar__period" aria-label="Период истории">
                    <span className="robots-logs-toolbar__period-label">Период</span>
                    <SegmentedControl
                        className="portfolio-period-control robots-logs-toolbar__presets"
                        aria-label="Пресет периода"
                        options={[
                            ...PERIOD_PRESETS.map(p => ({
                                value: p.id,
                                label: p.label,
                            })),
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
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="robots-logs-toolbar__reset"
                        onClick={() => {
                            setFromDate(shiftMoscowDate(todayKey, -29))
                            setToDate(todayKey)
                        }}
                    >
                        Сбросить
                    </Button>
                </div>
            </Card>

            {view === 'orders' && (
                <Card className="dashboard-assets-card robots-logs-card portfolio-history-zone robots-logs-card--headless robots-monitor-day-trades">
                    {showSkeleton ? (
                        <AuditTableSkeleton />
                    ) : (
                        <MonitorLiveOrdersCard
                            bare
                            mode="history"
                            title={null}
                            orders={orderRecords}
                            footnote={null}
                        />
                    )}
                </Card>
            )}

            {view === 'roundTrips' && (
                <Card className="dashboard-assets-card robots-logs-card portfolio-history-zone robots-logs-card--headless robots-monitor-day-trades">
                    {showSkeleton ? (
                        <AuditTableSkeleton />
                    ) : (
                        <MonitorOrdersCard
                            bare
                            title={null}
                            rows={tradeRows}
                            includeOpen
                            ariaLabel="История сделок"
                            emptyTitle="Нет сделок за период"
                            emptySub="Сдвиньте даты или дождитесь входа / выхода из позиции."
                            dayTotalLabel={tradeTotal?.text ?? null}
                            dayTotalTone={tradeTotal?.tone ?? 'neutral'}
                        />
                    )}
                </Card>
            )}

            {view === 'decisions' && (
                <Card className="dashboard-assets-card robots-logs-card portfolio-history-zone robots-logs-card--headless robots-monitor-day-trades">
                    {showSkeleton ? (
                        <AuditTableSkeleton />
                    ) : (
                        <MonitorDecisionsCard
                            bare
                            mode="history"
                            title={null}
                            limit={null}
                            decisions={decisionRecords}
                        />
                    )}
                </Card>
            )}
        </div>
    )
}
