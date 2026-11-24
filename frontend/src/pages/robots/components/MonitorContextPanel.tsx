import React from 'react'
import { Button } from '@/components/ui/Button'

export type MonitorContextMetaItem = {
    label: string
    value: React.ReactNode
}

export type MonitorContextBlock = {
    label: string
    body: React.ReactNode
}

type MonitorContextPanelProps = {
    title: string
    onClose: () => void
    meta: MonitorContextMetaItem[]
    blocks: MonitorContextBlock[]
}

/** Side / stack inspector shared by История заявки and решения. */
export function MonitorContextPanel({
    title,
    onClose,
    meta,
    blocks,
}: MonitorContextPanelProps) {
    return (
        <div className="robots-logs-context-panel">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">{title}</h3>
                <Button type="button" variant="ghost" size="sm" onClick={onClose}>
                    Закрыть
                </Button>
            </div>
            <dl className="robots-logs-context__meta">
                {meta.map(item => (
                    <div key={item.label}>
                        <dt>{item.label}</dt>
                        <dd>{item.value}</dd>
                    </div>
                ))}
            </dl>
            <div className="robots-decision-metrics" aria-label="Детали">
                {blocks.map(block => (
                    <div key={block.label} className="robots-decision-metrics__item">
                        <span className="robots-decision-metrics__key">{block.label}</span>
                        {block.body}
                    </div>
                ))}
            </div>
        </div>
    )
}

export function fmtContextValue(value: unknown): string {
    if (value == null) return '—'
    if (typeof value === 'number') {
        return Number.isInteger(value)
            ? String(value)
            : value.toLocaleString('ru-RU', { maximumFractionDigits: 6 })
    }
    if (typeof value === 'boolean') return value ? 'да' : 'нет'
    if (typeof value === 'object') {
        try {
            return JSON.stringify(value, null, 2)
        } catch {
            return String(value)
        }
    }
    return String(value)
}
