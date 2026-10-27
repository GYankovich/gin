import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { PageHero } from '@/components/ui/PageHero'
import { useToast } from '@/components/ui/Toast'
import { BacktestRunWorkspace } from '@/pages/robots-v2/components/BacktestRunWorkspace'
import { SaveAsRobotModal } from '@/pages/robots-v2/components/SaveAsRobotModal'
import {
    archetypeOfConfig,
    backtestStatusVariant,
    parseBacktestRunId,
    tokenIdOf,
} from '@/pages/robots-v2/backtestLabShared'
import { fmtErr, sessionStateLabel } from '@/pages/robots-v2/formatters'
import { robotV2Service } from '@/services/robotV2Service'
import type { RobotV2 } from '@/types/robotV2'
import type { RobotBacktestRunDetails } from '@/types/robot'

export default function BacktestRunPage() {
    const { runId: runIdParam } = useParams()
    const runId = parseBacktestRunId(runIdParam)
    const navigate = useNavigate()
    const toast = useToast()

    const [robots, setRobots] = useState<RobotV2[]>([])
    const [status, setStatus] = useState<RobotBacktestRunDetails | null>(null)
    const [opening, setOpening] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [cancelling, setCancelling] = useState(false)
    const [saveAsOpen, setSaveAsOpen] = useState(false)
    const pollFailStreakRef = useRef(0)

    const runStatus = String(status?.status || '').toUpperCase()
    const isActive = runStatus === 'RUNNING' || runStatus === 'QUEUED'

    const loadRobots = useCallback(async () => {
        try {
            const data = await robotV2Service.list()
            setRobots(data.items || [])
        } catch {
            setRobots([])
        }
    }, [])

    const loadDetails = useCallback(async (id: number) => {
        setOpening(true)
        try {
            const details = await robotV2Service.getBacktestRunDetails(id)
            setStatus(details)
            const st = String(details.status || '').toUpperCase()
            setError(st === 'FAILED' ? (details.error_message || 'Ошибка прогона') : null)
            return details
        } catch (e) {
            const msg = fmtErr(e)
            setError(msg)
            setStatus(null)
            toast.show(msg, 'error')
            return null
        } finally {
            setOpening(false)
        }
    }, [toast])

    const poll = useCallback(async (idToPoll: number) => {
        const st = await robotV2Service.getBacktestRunStatus(idToPoll)
        setStatus(prev => {
            const merged = { ...(prev || {}), ...st } as RobotBacktestRunDetails
            if (!merged.result_payload && prev?.result_payload) {
                merged.result_payload = prev.result_payload
            }
            return merged
        })
        const phase = String(st.status || '').toUpperCase()
        if (phase === 'SUCCESS' || phase === 'FAILED' || phase === 'CANCELLED') {
            const details = await robotV2Service.getBacktestRunDetails(idToPoll)
            setStatus(details)
            pollFailStreakRef.current = 0
            if (phase === 'FAILED') {
                setError(details.error_message || 'Прогон завершился с ошибкой')
                toast.show(details.error_message || 'Прогон завершился с ошибкой', 'error')
            } else if (phase === 'CANCELLED') {
                setError(null)
                toast.show('Прогон отменён', 'info')
            } else {
                setError(null)
            }
        }
        return st
    }, [toast])

    useEffect(() => {
        void loadRobots()
    }, [loadRobots])

    useEffect(() => {
        if (runId == null) return
        setStatus(null)
        setError(null)
        void loadDetails(runId)
    }, [runId, loadDetails])

    useEffect(() => {
        if (runId == null || !isActive) return
        let stopped = false
        const loop = async () => {
            while (!stopped) {
                try {
                    const st = await poll(runId)
                    pollFailStreakRef.current = 0
                    const phase = String(st.status || '').toUpperCase()
                    if (phase === 'SUCCESS' || phase === 'FAILED' || phase === 'CANCELLED') return
                } catch (e) {
                    pollFailStreakRef.current += 1
                    if (pollFailStreakRef.current === 5) {
                        toast.show(
                            `Не удаётся получить статус прогона: ${fmtErr(e)}. Повторяем опрос…`,
                            'error',
                        )
                    }
                }
                await new Promise(r => window.setTimeout(r, 1500))
            }
        }
        void loop()
        return () => {
            stopped = true
        }
    }, [runId, isActive, poll, toast])

    const onCancel = async () => {
        if (runId == null) return
        setCancelling(true)
        try {
            await robotV2Service.cancelBacktestRun(runId)
            toast.show('Отмена запрошена…', 'info')
            for (let i = 0; i < 45; i++) {
                const st = await poll(runId)
                const phase = String(st.status || '').toUpperCase()
                if (phase === 'CANCELLED' || phase === 'FAILED' || phase === 'SUCCESS') return
                await new Promise(r => window.setTimeout(r, 1000))
            }
            toast.show('Отмена отправлена — статус обновится при следующем опросе', 'info')
        } catch (e) {
            toast.show(fmtErr(e), 'error')
        } finally {
            setCancelling(false)
        }
    }

    const boundRobotId = Number(status?.robot_id ?? 0)
    const boundRobot = useMemo(
        () => (Number.isFinite(boundRobotId) && boundRobotId > 0
            ? robots.find(r => r.id === boundRobotId) ?? null
            : null),
        [robots, boundRobotId],
    )
    const runAlreadyBound = Number.isFinite(boundRobotId) && boundRobotId > 0
    const configSnapshot = (
        status as (RobotBacktestRunDetails & { config_snapshot?: Record<string, unknown> | null }) | null
    )?.config_snapshot
        ?? (status?.result_payload as { config?: Record<string, unknown> } | undefined)?.config
        ?? null
    const saveAsDefaultName = useMemo(() => {
        if (runId == null) return 'Новый робот'
        const hint = archetypeOfConfig(configSnapshot) || 'стратегия'
        return `Бэктест · ${hint} #${runId}`.slice(0, 50)
    }, [runId, configSnapshot])

    if (runId == null) {
        return <Navigate to="/backtest" replace />
    }

    const fromIso = String(status?.requested_from || '').slice(0, 10)
    const toIso = String(status?.requested_to || '').slice(0, 10)
    const periodLabel = fromIso && toIso ? `${fromIso} → ${toIso}` : null

    return (
        <div className="page" data-page="robots" data-screen="backtest-run">
            <PageHero
                className="dashboard-hero--node"
                eyebrow="ПРОГОН"
                title={`#${runId}`}
                subtitle={
                    <p className="dashboard-hero__sub">
                        Журнал сделок и издержки этого прогона.
                        {periodLabel ? ` ${periodLabel}.` : ''}
                        {' '}Биржу это не трогает.
                    </p>
                }
                actions={
                    <>
                        <Link to="/backtest" className="btn btn--ghost btn--sm robots-v2-run-back">
                            <span className="btn__content">К лаборатории</span>
                        </Link>
                        {runStatus ? (
                            <Badge variant={backtestStatusVariant(runStatus)}>
                                {sessionStateLabel(runStatus) || runStatus}
                            </Badge>
                        ) : null}
                        {isActive ? (
                            <Button
                                type="button"
                                variant="danger"
                                size="sm"
                                loading={cancelling}
                                onClick={() => void onCancel()}
                            >
                                Отменить
                            </Button>
                        ) : null}
                    </>
                }
            />

            <div className="dashboard-layout">
                {error && !status && !opening ? (
                    <Card className="dashboard-totals-card dashboard-error-card">
                        <p className="dashboard-empty">{error}</p>
                        <div className="dashboard-error-card__actions">
                            <Button type="button" onClick={() => void loadDetails(runId)}>Повторить</Button>
                            <Button type="button" variant="ghost" onClick={() => navigate('/backtest')}>
                                К лаборатории
                            </Button>
                        </div>
                    </Card>
                ) : (
                    <BacktestRunWorkspace
                        runId={runId}
                        status={status}
                        opening={opening}
                        error={error}
                        onSaveAsRobot={() => setSaveAsOpen(true)}
                    />
                )}

                <SaveAsRobotModal
                    open={saveAsOpen}
                    onClose={() => setSaveAsOpen(false)}
                    runId={runId}
                    defaultName={saveAsDefaultName}
                    suggestedTokenId={tokenIdOf(boundRobot)}
                    runAlreadyBound={runAlreadyBound}
                    onSaved={robotId => {
                        setSaveAsOpen(false)
                        toast.show('Робот создан из прогона', 'success')
                        navigate(`/robots/edit/${robotId}`)
                    }}
                />
            </div>
        </div>
    )
}
