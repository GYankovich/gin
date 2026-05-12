///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiDatatable [1]
///@ Исходный модуль `frontend/src/components/ui/DataTable.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { useEffect, useMemo, useState } from 'react'

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
    mobilePrimary?: (row: T) => React.ReactNode
    mobileSecondary?: (row: T) => React.ReactNode
    mobileDetails?: (row: T) => React.ReactNode
    mobileBreakpoint?: number
    rowClassName?: (row: T) => string
}

export function DataTable<T extends Record<string, any>>({
    columns,
    data,
    keyField,
    onRowClick,
    emptyText = 'Нет данных',
    maxHeight,
    mobilePrimary,
    mobileSecondary,
    mobileDetails,
    mobileBreakpoint = 768,
    rowClassName,
}: DataTableProps<T>) {
    const [sortKey, setSortKey] = useState<string | null>(null)
    const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
    const [isMobile, setIsMobile] = useState(false)
    const [expandedKey, setExpandedKey] = useState<string | number | null>(null)

    useEffect(() => {
        const updateViewport = () => {
            setIsMobile(window.innerWidth < mobileBreakpoint)
        }
        updateViewport()
        window.addEventListener('resize', updateViewport)
        return () => window.removeEventListener('resize', updateViewport)
    }, [mobileBreakpoint])

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

    if (isMobile && mobilePrimary) {
        if (sorted.length === 0) {
            return (
                <div className="data-table-wrap">
                    <div className="data-table__empty">{emptyText}</div>
                </div>
            )
        }
        return (
            <div className="mobile-data-table-list" style={maxHeight ? { maxHeight, overflowY: 'auto' } : undefined}>
                {sorted.map(row => {
                    const key = row[keyField]
                    const expanded = expandedKey === key
                    return (
                        <div key={key} className={`mobile-data-row ${expanded ? 'mobile-data-row--expanded' : ''} ${rowClassName ? rowClassName(row) : ''}`}>
                            <button
                                type="button"
                                className="mobile-data-row__main"
                                onClick={() => {
                                    if (mobileDetails) setExpandedKey(prev => (prev === key ? null : key))
                                    onRowClick?.(row)
                                }}
                            >
                                <div className="mobile-data-row__primary">{mobilePrimary(row)}</div>
                                {mobileSecondary && <div className="mobile-data-row__secondary">{mobileSecondary(row)}</div>}
                            </button>
                            {mobileDetails && expanded && (
                                <div className="mobile-data-row__details">
                                    {mobileDetails(row)}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        )
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
                            className={`${onRowClick ? 'data-table__row--clickable' : ''} ${rowClassName ? rowClassName(row) : ''}`.trim()}
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
