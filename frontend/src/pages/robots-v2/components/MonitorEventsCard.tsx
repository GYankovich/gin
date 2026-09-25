import React from 'react'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { stageLabel } from '@/pages/robots-v2/monitorUtils'

type MonitorEvent = { ts: string; type: string; payload: unknown }

type MonitorEventsCardProps = {
    events: MonitorEvent[]
    streamConnected: boolean
    isRunning: boolean
    hasToken: boolean
}

export function MonitorEventsCard({
    events,
    streamConnected,
    isRunning,
    hasToken,
}: MonitorEventsCardProps) {
    return (
        <Card className="dashboard-assets-card robots-v2-monitor-events">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Живой поток</h3>
                <Badge variant={streamConnected ? 'up' : 'neutral'}>
                    {streamConnected ? 'WS подключен' : 'WS офлайн'}
                </Badge>
            </div>
            {events.length === 0 ? (
                <p className="dashboard-empty">
                    {isRunning
                        ? (streamConnected
                            ? 'Стрим подключён, ждём события сессии…'
                            : !hasToken
                                ? 'Нужна авторизация для live-стрима. События подтягиваются по REST каждые 5с.'
                                : 'WS офлайн — события подтягиваются по REST каждые 5с. Проверьте proxy ws для /api.')
                        : 'Сессия не запущена — нажмите «Запуск»'}
                </p>
            ) : (
                <ul className="robots-v2-event-list">
                    {events.map((ev, i) => (
                        <li key={`${ev.ts}-${i}`}>
                            <span className="mono">{new Date(ev.ts).toLocaleTimeString('ru-RU')}</span>{' '}
                            <Badge variant="cyan">{ev.type}</Badge>
                            {ev.type === 'stage' && ev.payload && typeof ev.payload === 'object' ? (
                                <span className="robots-v2-hint">
                                    {' '}
                                    {stageLabel(String((ev.payload as { stage?: string }).stage || ''))}
                                </span>
                            ) : null}
                        </li>
                    ))}
                </ul>
            )}
        </Card>
    )
}
