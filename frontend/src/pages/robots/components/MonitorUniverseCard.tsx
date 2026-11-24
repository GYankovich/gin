import React, { useMemo, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { MonitorTableViewport } from '@/pages/robots/components/MonitorTableViewport'
import type { PoolDecisionRow } from '@/pages/robots/monitorUtils'

type SortKey = 'ticker' | 'decision' | 'reason' | 'updatedMs'
type SortDir = 'asc' | 'desc'

type MonitorUniverseCardProps = {
    rows: PoolDecisionRow[]
    canRefreshUniverse: boolean
    universeBusy: boolean
    onRefreshUniverse: () => void
}

function comparePoolRows(a: PoolDecisionRow, b: PoolDecisionRow, key: SortKey, dir: SortDir): number {
    let cmp = 0
    if (key === 'updatedMs') {
        const va = a.updatedMs
        const vb = b.updatedMs
        if (va == null && vb == null) cmp = 0
        else if (va == null) cmp = 1
        else if (vb == null) cmp = -1
        else cmp = va - vb
    } else {
        cmp = String(a[key] || '').localeCompare(String(b[key] || ''), 'ru', { sensitivity: 'base' })
    }
    if (cmp === 0 && key !== 'ticker') {
        cmp = a.ticker.localeCompare(b.ticker, 'ru', { sensitivity: 'base' })
    }
    return dir === 'asc' ? cmp : -cmp
}

/**
 * Pool blotter: ticker · decision · reason · updated.
 */
export function MonitorUniverseCard({
    rows,
    canRefreshUniverse,
    universeBusy,
    onRefreshUniverse,
}: MonitorUniverseCardProps) {
    const [sortKey, setSortKey] = useState<SortKey>('ticker')
    const [sortDir, setSortDir] = useState<SortDir>('asc')

    const sorted = useMemo(
        () => [...rows].sort((a, b) => comparePoolRows(a, b, sortKey, sortDir)),
        [rows, sortKey, sortDir],
    )

    const toggleSort = (key: SortKey) => {
        if (sortKey === key) {
            setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
            return
        }
        setSortKey(key)
        setSortDir(key === 'updatedMs' ? 'desc' : 'asc')
    }

    const sortMark = (key: SortKey) => (
        sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''
    )

    return (
        <Card className="dashboard-assets-card robots-monitor-day-trades robots-monitor-pool-decisions">
            <div className="dashboard-assets-card__head robots-monitor-orders__head">
                <h3 className="dashboard-panel-title">
                    Пул
                    {rows.length > 0 ? (
                        <span className="robots-hint"> · {rows.length}</span>
                    ) : null}
                </h3>
                {canRefreshUniverse ? (
                    <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        loading={universeBusy}
                        disabled={universeBusy}
                        onClick={onRefreshUniverse}
                    >
                        Обновить пул
                    </Button>
                ) : null}
            </div>
            {sorted.length === 0 ? (
                <div className="robots-monitor-empty">
                    <p className="robots-monitor-empty__sub">
                        {canRefreshUniverse
                            ? 'Сейчас пусто — нет кандидатов. Обновите скринер или проверьте режим universe.'
                            : 'Сейчас пусто — нет кандидатов. Проверьте режим universe в настройках робота.'}
                    </p>
                </div>
            ) : (
                <MonitorTableViewport
                    ariaLabel="Пул и решения"
                    syncKey={`${sortKey}:${sortDir}:${sorted.map(r => r.id).join('|')}`}
                    renderHead={() => (
                        <tr>
                            <th aria-sort={sortKey === 'ticker' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                                <button
                                    type="button"
                                    className="robots-monitor-day-trades__sort"
                                    onClick={() => toggleSort('ticker')}
                                >
                                    Тикер{sortMark('ticker')}
                                </button>
                            </th>
                            <th aria-sort={sortKey === 'decision' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                                <button
                                    type="button"
                                    className="robots-monitor-day-trades__sort"
                                    onClick={() => toggleSort('decision')}
                                >
                                    Решение{sortMark('decision')}
                                </button>
                            </th>
                            <th aria-sort={sortKey === 'reason' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                                <button
                                    type="button"
                                    className="robots-monitor-day-trades__sort"
                                    onClick={() => toggleSort('reason')}
                                >
                                    Причина{sortMark('reason')}
                                </button>
                            </th>
                            <th
                                className="robots-monitor-day-trades__num"
                                aria-sort={sortKey === 'updatedMs' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                            >
                                <button
                                    type="button"
                                    className="robots-monitor-day-trades__sort"
                                    onClick={() => toggleSort('updatedMs')}
                                >
                                    Обновлено{sortMark('updatedMs')}
                                </button>
                            </th>
                        </tr>
                    )}
                    bodyRows={sorted.map(row => (
                        <tr key={row.id}>
                            <td>
                                <b className="robots-monitor-day-trades__tk">{row.ticker}</b>
                            </td>
                            <td title={row.decision}>{row.decision}</td>
                            <td
                                className="robots-monitor-day-trades__muted"
                                title={row.reason}
                            >
                                {row.reason}
                            </td>
                            <td className="robots-monitor-day-trades__num mono robots-monitor-day-trades__muted">
                                {row.updatedLabel}
                            </td>
                        </tr>
                    ))}
                />
            )}
        </Card>
    )
}
