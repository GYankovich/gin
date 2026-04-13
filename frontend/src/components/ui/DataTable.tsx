import React, { useMemo, useState, memo } from 'react'

export interface Column<T> {
    key: string
    header: string
    render?: (row: T) => React.ReactNode
    sortable?: boolean
    align?: 'left' | 'center' | 'right'
    width?: string
}

interface DataTableProps<T> {
    columns: Column<T>[]
    data: T[]
    keyField: string
    onRowClick?: (row: T) => void
    emptyText?: string
    maxHeight?: number | string
}

export function DataTable<T extends Record<string, any>>({
    columns,
    data,
    keyField,
    onRowClick,
    emptyText = 'Нет данных',
    maxHeight,
}: DataTableProps<T>) {
    const [sortKey, setSortKey] = useState<string | null>(null)
    const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

    const sorted = useMemo(() => {
        if (!sortKey) return data
        return [...data].sort((a, b) => {
            const va = a[sortKey], vb = b[sortKey]
            if (va == null || vb == null) return 0
            const cmp = va < vb ? -1 : va > vb ? 1 : 0
            return sortDir === 'asc' ? cmp : -cmp
        })
    }, [data, sortKey, sortDir])

    const toggleSort = (key: string) => {
        if (sortKey === key) {
            setSortDir(d => d === 'asc' ? 'desc' : 'asc')
        } else {
            setSortKey(key)
            setSortDir('asc')
        }
    }

    return (
        <div
            className="data-table-wrap"
            style={maxHeight ? { maxHeight, overflowY: 'auto' } : undefined}
        >
            <table className="data-table">
                <thead>
                    <tr>
                        {columns.map(col => (
                            <th
                                key={col.key}
                                style={{ textAlign: col.align || 'left', width: col.width }}
                                className={col.sortable ? 'data-table__th--sortable' : ''}
                                onClick={() => col.sortable && toggleSort(col.key)}
                            >
                                {col.header}
                                {col.sortable && sortKey === col.key && (
                                    <span className="data-table__sort-arrow">{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>
                                )}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {sorted.length === 0 ? (
                        <tr><td colSpan={columns.length} className="data-table__empty">{emptyText}</td></tr>
                    ) : sorted.map(row => (
                        <tr
                            key={row[keyField]}
                            className={onRowClick ? 'data-table__row--clickable' : ''}
                            onClick={() => onRowClick?.(row)}
                        >
                            {columns.map(col => (
                                <td key={col.key} style={{ textAlign: col.align || 'left' }}>
                                    {col.render ? col.render(row) : row[col.key]}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}
