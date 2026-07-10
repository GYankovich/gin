///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiKpitile [1]
///@ Исходный модуль `frontend/src/components/ui/KpiTile.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { memo } from 'react'
import { useCountUp } from '@/hooks/useCountUp'

interface KpiTileProps {
    label: string
    value: number
    format?: (v: number) => string
    change?: number
    suffix?: string
    icon?: React.ReactNode
}

export const KpiTile = memo(function KpiTile({ label, value, format, change, suffix, icon }: KpiTileProps) {
    const displayed = useCountUp(value)
    const formatted = format ? format(displayed) : displayed.toLocaleString('ru-RU')

    return (
        <div className="kpi-tile">
            {icon && <div className="kpi-tile__icon">{icon}</div>}
            <div className="kpi-tile__content">
                <span className="kpi-tile__label">{label}</span>
                <span className="kpi-tile__value mono">
                    {formatted}{suffix}
                </span>
                {change !== undefined && (
                    <span className={`kpi-tile__change ${change >= 0 ? 'color-up' : 'color-down'}`}>
                        {change >= 0 ? '▲' : '▼'} {change >= 0 ? '+' : ''}{change.toFixed(1)}%
                    </span>
                )}
            </div>
        </div>
    )
})
