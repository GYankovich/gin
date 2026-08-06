import React from 'react'

type StatTileProps = {
    label: string
    value: React.ReactNode
    /** Extra classes on the value (e.g. color-up / color-down). */
    valueClassName?: string
    className?: string
}

/** Dense KPI cell used on dashboard summary and portfolio statistics. */
export function StatTile({ label, value, valueClassName = '', className = '' }: StatTileProps) {
    return (
        <div className={`portfolio-stat-tile ${className}`.trim()}>
            <div className="portfolio-stat-tile__label">{label}</div>
            <div className={`portfolio-stat-tile__value ${valueClassName}`.trim()}>{value}</div>
        </div>
    )
}
