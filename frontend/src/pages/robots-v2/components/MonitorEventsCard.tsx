import React from 'react'
import { Card } from '@/components/ui/Card'
import { stageLabel } from '@/pages/robots-v2/monitorUtils'

const EVENT_KIND: Record<string, string> = {
    stage: 'этап',
    cycle: 'цикл',
    positions: 'позиции',
    decision: 'решение',
    order: 'заявка',
    orders: 'заявка',
    equity_snapshot: 'капитал',
}

function eventKind(type: string): string {
    const key = type.trim().toLowerCase()
    return EVENT_KIND[key] || key || 'событие'
}

function eventClock(ts: string): string {
    const date = new Date(ts)
    if (Number.isNaN(date.getTime())) return ''
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

type MonitorEvent = { ts: string; type: string; payload: unknown }

type MonitorEventsCardProps = {
    events: MonitorEvent[]
    streamConnected: boolean
    isRunning: boolean
    hasToken: boolean
    bare?: boolean
    /** How many rows to show. Omit to show the full list. */
    limit?: number
    /** Stream status line above the list. */
    showStatus?: boolean
}

export function MonitorEventsCard({
    events,
    streamConnected,
    isRunning,
    hasToken,
    bare = false,
    limit,
    showStatus = true,
}: MonitorEventsCardProps) {
    const shown = limit != null ? events.slice(0, limit) : events
    const body = (
        <>
            {bare && showStatus ? (
                <p className="robots-v2-hint robots-v2-universe-caption">
                    {streamConnected ? 'Стрим подключён' : 'Стрим офлайн'}
                </p>
            ) : null}
            {shown.length === 0 ? (
                <p className="dashboard-empty">
                    {isRunning
                        ? (streamConnected
                            ? 'Стрим подключён, ждём события сессии…'
                            : !hasToken
                                ? 'Нужна авторизация для live-стрима. События подтягиваются по REST каждые 5с.'
                                : 'Стрим офлайн — события по REST')
                        : 'Сессия не запущена — нажмите «Запуск»'}
                </p>
            ) : (
                <ul className="robots-v2-event-list robots-v2-event-list--compact">
                    {shown.map((ev, i) => (
                        <li key={`${ev.ts}-${i}`}>
                            <span className="mono robots-v2-monitor-events__ts">{eventClock(ev.ts)}</span>
                            <span className="robots-monitor-event__kind">{eventKind(ev.type)}</span>
                            {ev.type.toLowerCase() === 'stage' && ev.payload && typeof ev.payload === 'object' ? (
                                <span className="robots-v2-hint">
                                    {stageLabel(String((ev.payload as { stage?: string }).stage || ''))}
                                </span>
                            ) : null}
                        </li>
                    ))}
                </ul>
            )}
        </>
    )

    if (bare) {
        return <div className="robots-v2-monitor-events">{body}</div>
    }

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-events">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Живой поток</h3>
                <span className="robots-v2-hint">{streamConnected ? 'стрим' : 'стрим офлайн'}</span>
            </div>
            {body}
        </Card>
    )
}
