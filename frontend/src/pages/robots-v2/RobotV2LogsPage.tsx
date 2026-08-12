import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { useToast } from '@/components/ui/Toast'
import { robotV2Service } from '@/services/robotV2Service'

function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    return err?.message || 'Ошибка'
}

export default function RobotV2LogsPage() {
    const { id } = useParams()
    const robotId = Number(id)
    const navigate = useNavigate()
    const toast = useToast()
    const [items, setItems] = useState<Array<Record<string, unknown>>>([])
    const [filter, setFilter] = useState('')
    const [loading, setLoading] = useState(true)

    const load = useCallback(async () => {
        if (!Number.isFinite(robotId)) return
        setLoading(true)
        try {
            const data = await robotV2Service.getLogs(robotId, {
                limit: 200,
                eventType: filter || undefined,
            })
            setItems(data.items || [])
        } catch (e) {
            toast.show(fmtErr(e), 'error')
            setItems([])
        } finally {
            setLoading(false)
        }
    }, [robotId, filter, toast])

    useEffect(() => {
        void load()
        const t = window.setInterval(() => void load(), 4000)
        return () => window.clearInterval(t)
    }, [load])

    const exportJson = () => {
        const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `robot-${robotId}-logs.json`
        a.click()
        URL.revokeObjectURL(url)
    }

    return (
        <div className="robots-v2-page" data-page="robots-v2">
            <header className="robots-v2-page__header">
                <div>
                    <button type="button" className="robots-v2-linkish" onClick={() => navigate('/robots-v2')}>
                        ← Флот v2
                    </button>
                    <h1 className="robots-v2-page__title">Логи робота #{robotId}</h1>
                    <p className="robots-v2-page__subtitle">События session stream (in-memory ring buffer)</p>
                </div>
                <div className="robots-v2-page__actions">
                    <Button type="button" variant="ghost" onClick={() => navigate(`/robots-v2/${robotId}/monitor`)}>
                        Monitor
                    </Button>
                    <Button type="button" variant="secondary" onClick={exportJson} disabled={!items.length}>
                        Export JSON
                    </Button>
                    <Button type="button" onClick={() => void load()} loading={loading}>
                        Refresh
                    </Button>
                </div>
            </header>

            <div className="robots-v2-chip-row">
                {['', 'cycle', 'signal', 'order', 'decision', 'health'].map(t => (
                    <button
                        key={t || 'all'}
                        type="button"
                        className={`robots-v2-chip ${filter === t ? 'robots-v2-chip--on' : ''}`}
                        onClick={() => setFilter(t)}
                    >
                        {t || 'all'}
                    </button>
                ))}
            </div>

            <Card className="robots-v2-logs-card">
                {loading && items.length === 0 ? (
                    <p className="robots-v2-hint">Загрузка…</p>
                ) : items.length === 0 ? (
                    <p className="robots-v2-hint">Пока нет событий. Запустите робота, чтобы наполнять лог.</p>
                ) : (
                    <ul className="robots-v2-event-list robots-v2-event-list--dense">
                        {items.map((ev, i) => {
                            const ts = String(ev.ts || '')
                            const type = String(ev.type || 'event')
                            const rest = { ...ev }
                            delete rest.ts
                            delete rest.type
                            delete rest.robotId
                            return (
                                <li key={`${ts}-${i}`}>
                                    <span className="mono">{ts ? new Date(ts).toLocaleString('ru-RU') : '—'}</span>{' '}
                                    <Badge variant="cyan">{type}</Badge>{' '}
                                    <code className="robots-v2-log-payload">{JSON.stringify(rest)}</code>
                                </li>
                            )
                        })}
                    </ul>
                )}
            </Card>
        </div>
    )
}
