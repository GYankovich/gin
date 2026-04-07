import React, { useEffect, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { KpiTile } from '@/components/ui/KpiTile'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Skeleton } from '@/components/ui/Skeleton'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { RobotSettingsModal } from './RobotSettingsModal'
import { robotService } from '@/services/robotService'
import { analyticsService } from '@/services/analyticsService'
import type { Robot, RobotMetricsResponse } from '@/types/robot'

export default function RobotsPage() {
    const [robots, setRobots] = useState<Robot[]>([])
    const [loading, setLoading] = useState(true)
    const [softLoading, setSoftLoading] = useState(false)
    const [settingsOpen, setSettingsOpen] = useState(false)
    const [editingRobot, setEditingRobot] = useState<Robot | null>(null)
    const [statsOpen, setStatsOpen] = useState(false)
    const [statsRobot, setStatsRobot] = useState<Robot | null>(null)
    const [metrics, setMetrics] = useState<RobotMetricsResponse | null>(null)
    const [metricsLoading, setMetricsLoading] = useState(false)

    useEffect(() => { loadRobots() }, [])

    const loadRobots = async (soft = true) => {
        if (robots.length === 0 || !soft) setLoading(true)
        else setSoftLoading(true)
        try {
            const res = await robotService.list()
            setRobots(res.items)
        } catch { /* */ }
        setLoading(false)
        setSoftLoading(false)
    }

    const toggleStatus = async (robot: Robot) => {
        const newStatus = robot.status === 1 ? 2 : 1
        try {
            await robotService.changeStatus(robot.id, newStatus)
            loadRobots(true)
        } catch { /* */ }
    }

    const handleDelete = async (robot: Robot) => {
        if (!window.confirm(`Удалить робота «${robot.name}»?`)) return
        try {
            await robotService.deleteRobot(robot.id)
            loadRobots(true)
        } catch { /* */ }
    }

    const openStats = async (robot: Robot) => {
        setStatsRobot(robot)
        setStatsOpen(true)
        setMetricsLoading(true)
        try {
            const m = await analyticsService.getRobotMetrics(robot.id)
            setMetrics(m)
        } catch { setMetrics(null) }
        setMetricsLoading(false)
    }

    const tradeColumns: Column<any>[] = [
        { key: 'figi', header: 'FIGI', sortable: true },
        { key: 'side', header: 'Тип', render: r => <Badge variant={r.side === 'buy' ? 'up' : 'down'}>{r.side.toUpperCase()}</Badge> },
        { key: 'quantity', header: 'Кол-во', align: 'right' },
        { key: 'entry_price', header: 'Вход', align: 'right', render: r => Number(r.entry_price).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) },
        { key: 'exit_price', header: 'Выход', align: 'right', render: r => r.exit_price != null ? Number(r.exit_price).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) : '—' },
        {
            key: 'profit', header: 'Прибыль', sortable: true, align: 'right',
            render: r => {
                if (r.profit == null) return '—'
                return <span className={r.profit >= 0 ? 'color-up' : 'color-down'}>{r.profit >= 0 ? '+' : ''}{Number(r.profit).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽</span>
            },
        },
        { key: 'status', header: 'Статус', render: r => <Badge variant="neutral">{r.status}</Badge> },
    ]

    if (loading) {
        return <div className="page"><h1 className="page__title">Роботы</h1><Skeleton height="140px" count={3} /></div>
    }

    return (
        <div className="page">
            <div className="dashboard-header">
                <h1 className="page__title">Роботы</h1>
                <Button variant="primary" glow onClick={() => { setEditingRobot(null); setSettingsOpen(true) }}>+ Создать робота</Button>
            </div>
            {softLoading && <div className="soft-loading-bar" />}

            {robots.length === 0 ? (
                <div className="empty-state">
                    <RobotIllustration size={160} />
                    <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-secondary)' }}>Роботов пока нет. Создайте первого!</p>
                </div>
            ) : (
                <div className="robots-grid">
                    {robots.map(robot => (
                        <Card key={robot.id} className="robot-card">
                            <div className="robot-card__header">
                                <span className="robot-card__name">🤖 {robot.name}</span>
                                <Badge variant={robot.status === 1 ? 'up' : 'neutral'}>
                                    <span className={`status-dot status-dot--${robot.status === 1 ? 'active' : 'inactive'}`} /> {robot.statusName}
                                </Badge>
                            </div>
                            <div className="robot-card__meta">
                                <span>Тип: {robot.typeName}</span>
                                {robot.config?.strategy && <span>Стратегия: {robot.config.strategy}</span>}
                            </div>
                            <div className="robot-card__stats mono">
                                {robot.last_started && <span>Запуск: {new Date(robot.last_started).toLocaleString('ru-RU')}</span>}
                            </div>
                            <div className="robot-card__actions">
                                <Button variant="ghost" size="sm" onClick={() => { setEditingRobot(robot); setSettingsOpen(true) }}>Редактировать</Button>
                                <Button variant={robot.status === 1 ? 'danger' : 'primary'} size="sm" onClick={() => toggleStatus(robot)}>
                                    {robot.status === 1 ? 'Остановить' : 'Запустить'}
                                </Button>
                                <Button variant="secondary" size="sm" onClick={() => openStats(robot)}>📊 Статистика</Button>
                                <Button variant="danger" size="sm" onClick={() => handleDelete(robot)}>Удалить</Button>
                            </div>
                        </Card>
                    ))}
                </div>
            )}

            <RobotSettingsModal
                open={settingsOpen}
                onClose={() => setSettingsOpen(false)}
                robot={editingRobot}
                onSaved={loadRobots}
            />

            <Modal open={statsOpen} onClose={() => setStatsOpen(false)} title={`Статистика: ${statsRobot?.name ?? ''}`} width="740px">
                {metricsLoading ? <Skeleton height="200px" /> : metrics ? (
                    <>
                        <div className="grid-kpi" style={{ marginBottom: 'var(--space-5)' }}>
                            <KpiTile label="Win Rate" value={metrics.metrics.win_rate} format={v => v.toFixed(1)} suffix="%" icon={<span>🎯</span>} />
                            <KpiTile label="Profit Factor" value={metrics.metrics.profit_factor} format={v => v.toFixed(2)} icon={<span>💹</span>} />
                            <KpiTile label="Сделок" value={metrics.metrics.total_trades} icon={<span>📊</span>} />
                            <KpiTile label="Общий P&L" value={metrics.metrics.total_pnl} format={v => v.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} suffix=" ₽" change={metrics.metrics.total_pnl >= 0 ? 1 : -1} icon={<span>💰</span>} />
                            <KpiTile label="Max Drawdown" value={metrics.metrics.max_drawdown} format={v => v.toFixed(1)} suffix="%" icon={<span>📉</span>} />
                        </div>
                        <h4 style={{ marginBottom: 'var(--space-3)' }}>Последние сделки</h4>
                        <DataTable columns={tradeColumns} data={metrics.recent_trades} keyField="id" emptyText="Нет сделок" />
                    </>
                ) : (
                    <div className="event-feed__empty">Нет данных по метрикам</div>
                )}
            </Modal>
        </div>
    )
}
