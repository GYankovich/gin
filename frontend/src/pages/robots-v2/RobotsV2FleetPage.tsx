import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2 } from '@/types/robotV2'

function isSessionRunning(state: string | null | undefined): boolean {
    return String(state || '').toUpperCase() === 'RUNNING'
}

function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    return err?.message || 'Ошибка'
}

function archetypeOf(robot: RobotV2): string {
    const strategy = (robot.config?.strategy || {}) as Record<string, unknown>
    return String(strategy.archetype || '—')
}

function modeOf(robot: RobotV2): string {
    const core = (robot.config?.core || {}) as Record<string, unknown>
    return String(core.mode || 'paper')
}

export default function RobotsV2FleetPage() {
    const navigate = useNavigate()
    const toast = useToast()
    const [robots, setRobots] = useState<RobotV2[]>([])
    const [sessionById, setSessionById] = useState<Record<number, string | null>>({})
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [busyId, setBusyId] = useState<number | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            const data = await robotV2Service.list({ robot_type: [2] })
            setRobots(data.items)
            const sessions = await Promise.all(
                data.items.map(async r => {
                    try {
                        const s = await robotV2Service.getStatus(r.id)
                        const state = (s.sessionState ?? s.session_state ?? null) as string | null
                        return [r.id, state] as const
                    } catch {
                        return [r.id, null] as const
                    }
                }),
            )
            setSessionById(Object.fromEntries(sessions))
        } catch (e) {
            setError(fmtErr(e))
            setRobots([])
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void load()
    }, [load])

    const onStart = async (robot: RobotV2) => {
        setBusyId(robot.id)
        try {
            const risk = (robot.config?.risk || {}) as Record<string, unknown>
            const capital = Number(risk.capital || 100_000)
            await robotV2Service.start(robot.id, { virtualCapital: capital })
            toast.show(`Робот #${robot.id} запущен`, 'success')
            await load()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    const onStop = async (robot: RobotV2) => {
        setBusyId(robot.id)
        try {
            await robotV2Service.stop(robot.id, 'soft')
            toast.show(`Робот #${robot.id} остановлен`, 'info')
            await load()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    const onClone = async (robot: RobotV2) => {
        setBusyId(robot.id)
        try {
            const cloned = await robotV2Service.clone(robot.id)
            toast.show(`Создана копия #${cloned.id}`, 'success')
            await load()
            navigate(`/robots-v2/edit/${cloned.id}`)
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    const onDelete = async (robot: RobotV2) => {
        if (!window.confirm(`Удалить робота «${robot.name}»?`)) return
        setBusyId(robot.id)
        try {
            await robotV2Service.delete(robot.id)
            toast.show('Удалён', 'success')
            await load()
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setBusyId(null)
        }
    }

    return (
        <div className="robots-v2-page" data-page="robots-v2">
            <header className="robots-v2-page__header">
                <div>
                    <h1 className="robots-v2-page__title">Роботы v2</h1>
                    <p className="robots-v2-page__subtitle">Greenfield флот: paper engine, 4 архетипа, unified cycle</p>
                </div>
                <div className="robots-v2-page__actions">
                    <Button type="button" variant="ghost" onClick={() => navigate('/robots')}>
                        Legacy /robots
                    </Button>
                    <Button type="button" onClick={() => navigate('/robots-v2/new')}>
                        Новый робот
                    </Button>
                </div>
            </header>

            {loading && (
                <div className="robots-v2-fleet-grid">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <Card key={i} className="robots-v2-fleet-card">
                            <Skeleton height="120px" />
                        </Card>
                    ))}
                </div>
            )}

            {!loading && error && (
                <Card className="robots-v2-banner robots-v2-banner--error">
                    <p>{error}</p>
                    <Button type="button" variant="secondary" onClick={() => void load()}>Повторить</Button>
                </Card>
            )}

            {!loading && !error && robots.length === 0 && (
                <Card className="robots-v2-empty">
                    <h2>Пока нет роботов v2</h2>
                    <p>Создайте первого через 4-шаговый мастер.</p>
                    <Button type="button" onClick={() => navigate('/robots-v2/new')}>Создать</Button>
                </Card>
            )}

            {!loading && robots.length > 0 && (
                <div className="robots-v2-fleet-grid">
                    {robots.map(robot => {
                        const running = isSessionRunning(sessionById[robot.id])
                        return (
                        <Card key={robot.id} className="robots-v2-fleet-card">
                            <div className="robots-v2-fleet-card__head">
                                <div>
                                    <h3>{robot.name}</h3>
                                    <div className="robots-v2-fleet-card__meta">
                                        #{robot.id} · {archetypeOf(robot)} · {modeOf(robot)}
                                    </div>
                                </div>
                                <Badge variant={running ? 'up' : 'neutral'}>
                                    {running ? 'RUNNING' : 'STOPPED'}
                                </Badge>
                            </div>
                            <div className="robots-v2-fleet-card__actions">
                                <Button type="button" size="sm" variant="secondary" onClick={() => navigate(`/robots-v2/${robot.id}/monitor`)}>
                                    Monitor
                                </Button>
                                <Button type="button" size="sm" variant="ghost" onClick={() => navigate(`/robots-v2/edit/${robot.id}`)}>
                                    Edit
                                </Button>
                                <Button type="button" size="sm" variant="ghost" onClick={() => navigate(`/robots-v2/${robot.id}/logs`)}>
                                    Logs
                                </Button>
                                <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    loading={busyId === robot.id}
                                    onClick={() => void onClone(robot)}
                                >
                                    Clone
                                </Button>
                                {running ? (
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="danger"
                                        loading={busyId === robot.id}
                                        onClick={() => void onStop(robot)}
                                    >
                                        Stop
                                    </Button>
                                ) : (
                                    <Button
                                        type="button"
                                        size="sm"
                                        loading={busyId === robot.id}
                                        onClick={() => void onStart(robot)}
                                    >
                                        Start
                                    </Button>
                                )}
                                <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    loading={busyId === robot.id}
                                    onClick={() => void onDelete(robot)}
                                >
                                    Delete
                                </Button>
                            </div>
                        </Card>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
