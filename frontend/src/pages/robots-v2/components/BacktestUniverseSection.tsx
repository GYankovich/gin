import React, { useEffect, useMemo, useState } from 'react'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { groupUniverseByDay, type UniverseDayRow } from '@/pages/robots-v2/backtestGlassBox'
import { robotV2Service } from '@/services/robotV2Service'
import type { BacktestUniverseMembershipItem } from '@/types/robot'

type Props = {
    runId: number | null
    fromDate?: string | null
    toDate?: string | null
}

/** Zone K — universe membership over time (lazy-fetch on expand). */
export function BacktestUniverseSection({ runId, fromDate, toDate }: Props) {
    const [open, setOpen] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(false)
    const [items, setItems] = useState<BacktestUniverseMembershipItem[] | null>(null)
    const [selectedDay, setSelectedDay] = useState<string | null>(null)

    useEffect(() => {
        setItems(null)
        setError(false)
        setSelectedDay(null)
    }, [runId])

    useEffect(() => {
        if (!open || runId == null || items != null) return
        let cancelled = false
        setLoading(true)
        setError(false)
        void (async () => {
            try {
                const res = await robotV2Service.getBacktestUniverse(runId, {
                    from: fromDate ? String(fromDate).slice(0, 10) : undefined,
                    to: toDate ? String(toDate).slice(0, 10) : undefined,
                })
                if (cancelled) return
                if (!res) {
                    setError(true)
                    setItems([])
                    return
                }
                setItems(res.items || [])
                const days = (res.days || []).map(d => String(d).slice(0, 10))
                if (days.length) setSelectedDay(days[days.length - 1])
            } finally {
                if (!cancelled) setLoading(false)
            }
        })()
        return () => {
            cancelled = true
        }
    }, [open, runId, fromDate, toDate, items])

    const dayRows = useMemo(() => groupUniverseByDay(items || []), [items])

    useEffect(() => {
        if (!selectedDay && dayRows.length) {
            setSelectedDay(dayRows[dayRows.length - 1].trade_date)
        }
    }, [dayRows, selectedDay])

    const selected = dayRows.find(d => d.trade_date === selectedDay) || null

    const dayColumns = useMemo<Column<UniverseDayRow>[]>(() => [
        {
            key: 'trade_date',
            header: 'Дата',
            sortable: true,
            render: r => <span className="mono">{r.trade_date}</span>,
        },
        {
            key: 'size',
            header: 'Тикеров',
            render: r => <span className="mono">{r.size}</span>,
        },
        {
            key: 'adds',
            header: '+',
            render: r => (
                <span className="mono robots-v2-glass-universe__add">
                    {r.adds > 0 ? `+${r.adds}` : '—'}
                </span>
            ),
        },
        {
            key: 'drops',
            header: '−',
            render: r => (
                <span className="mono robots-v2-glass-universe__drop">
                    {r.drops > 0 ? `−${r.drops}` : '—'}
                </span>
            ),
        },
    ], [])

    const badge = (() => {
        if (error || (items && items.length === 0)) {
            return <span className="robots-v2-hint">нет данных</span>
        }
        if (items) {
            return <span className="robots-v2-hint">{dayRows.length} дн.</span>
        }
        return undefined
    })()

    return (
        <CollapsibleSection
            title={(
                <span className="dashboard-collapse__label">
                    <IconUniverse />
                    Вселенная
                </span>
            )}
            badge={badge}
            className="dashboard-assets-card robots-v2-glass-universe"
            open={open}
            onOpenChange={setOpen}
            defaultOpen={false}
        >
            {loading ? (
                <p className="robots-v2-hint">Загрузка вселенной…</p>
            ) : error || !items || items.length === 0 ? (
                <p className="robots-v2-hint">Нет данных о составе вселенной за прогон</p>
            ) : (
                <>
                    <div className="robots-v2-glass-universe__days" role="list" aria-label="Дни вселенной">
                        {dayRows.map(d => (
                            <button
                                key={d.trade_date}
                                type="button"
                                role="listitem"
                                className={`robots-v2-chip ${
                                    selectedDay === d.trade_date ? 'robots-v2-chip--on' : ''
                                }`}
                                onClick={() => setSelectedDay(d.trade_date)}
                            >
                                {d.trade_date.slice(5)}
                                <span className="mono robots-v2-glass-universe__chip-n">{d.size}</span>
                            </button>
                        ))}
                    </div>
                    <DataTable
                        columns={dayColumns}
                        data={dayRows}
                        keyField="id"
                        emptyText="Нет данных о составе вселенной за прогон"
                        maxHeight={240}
                        onRowClick={r => setSelectedDay(r.trade_date)}
                        rowClassName={r =>
                            selectedDay === r.trade_date ? 'robots-v2-glass-row--selected' : ''
                        }
                    />
                    {selected ? (
                        <div className="robots-v2-glass-universe__tickers">
                            <p className="robots-v2-hint robots-v2-universe-caption">
                                {selected.trade_date} · {selected.size} тикеров
                                {selected.adds || selected.drops
                                    ? ` · +${selected.adds} / −${selected.drops}`
                                    : ''}
                            </p>
                            <div className="robots-v2-chip-row">
                                {selected.tickers.map(t => (
                                    <span
                                        key={t}
                                        className={`robots-v2-chip robots-v2-chip--static ${
                                            selected.added.includes(t)
                                                ? 'robots-v2-glass-universe__ticker--add'
                                                : ''
                                        }`}
                                    >
                                        {selected.added.includes(t) ? `+${t}` : t}
                                    </span>
                                ))}
                                {selected.dropped.map(t => (
                                    <span
                                        key={`drop-${t}`}
                                        className="robots-v2-chip robots-v2-chip--static robots-v2-glass-universe__ticker--drop"
                                    >
                                        −{t}
                                    </span>
                                ))}
                            </div>
                        </div>
                    ) : null}
                </>
            )}
        </CollapsibleSection>
    )
}

function IconUniverse() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" strokeWidth="1.7" />
            <path
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                d="M4 12h16M12 4c2.5 2.8 2.5 12.2 0 16M12 4c-2.5 2.8-2.5 12.2 0 16"
            />
        </svg>
    )
}
