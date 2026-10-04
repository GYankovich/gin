import React, { useEffect, useState } from 'react'
import {
    executionStatusLabel,
    executionStatusTone,
} from '@/pages/robots-v2/backtestGlassBox'
import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'
import { fmtMoney } from '@/pages/robots-v2/formatters'
import { robotV2Service } from '@/services/robotV2Service'
import type { BacktestExecutionEvent } from '@/types/robot'

type Props = {
    runId: number | null
    cycleId: string | null | undefined
    /** Prefetched from cycle bundle when available. */
    seedEvents?: BacktestExecutionEvent[] | null
    onStepClick?: (event: BacktestExecutionEvent) => void
}

function fmtTs(raw: string | null | undefined): string {
    if (!raw) return '—'
    const d = new Date(raw)
    if (!Number.isFinite(d.getTime())) return String(raw)
    return d.toLocaleString('ru-RU')
}

/** Zone O — intent↔fill lifecycle inside decision inspector. */
export function IntentLifecycleBlock({
    runId,
    cycleId,
    seedEvents,
    onStepClick,
}: Props) {
    const [loading, setLoading] = useState(false)
    const [events, setEvents] = useState<BacktestExecutionEvent[] | null>(
        seedEvents && seedEvents.length ? seedEvents : null,
    )
    const [failed, setFailed] = useState(false)

    useEffect(() => {
        if (seedEvents && seedEvents.length) {
            setEvents(seedEvents)
            setFailed(false)
            setLoading(false)
            return
        }
        if (!cycleId || runId == null) {
            setEvents([])
            setLoading(false)
            return
        }
        let cancelled = false
        setLoading(true)
        setFailed(false)
        void (async () => {
            try {
                const res = await robotV2Service.getBacktestExecutionEvents(runId, {
                    cycleId,
                    limit: 200,
                })
                if (cancelled) return
                if (!res) {
                    setFailed(true)
                    setEvents([])
                    return
                }
                const items = [...(res.items || [])].sort((a, b) => {
                    const ta = new Date(String(a.ts || 0)).getTime()
                    const tb = new Date(String(b.ts || 0)).getTime()
                    return ta - tb
                })
                setEvents(items)
            } finally {
                if (!cancelled) setLoading(false)
            }
        })()
        return () => {
            cancelled = true
        }
    }, [runId, cycleId, seedEvents])

    return (
        <section className="robots-v2-inspector__lifecycle" aria-label="Намерение → исполнение">
            <h4 className="robots-v2-inspector__lifecycle-title">Намерение → исполнение</h4>
            {loading ? (
                <p className="robots-v2-hint">Загрузка цепочки…</p>
            ) : !events || events.length === 0 || failed ? (
                <p className="robots-v2-hint">
                    Цепочка намерение→исполнение недоступна для этого прогона
                </p>
            ) : (
                <ol className="robots-v2-inspector__lifecycle-list">
                    {events.map((ev, i) => {
                        const tone = executionStatusTone(ev.status)
                        const reason = ev.reject_reason || ev.reason
                        return (
                            <li key={String(ev.event_id || `${ev.ts}-${i}`)}>
                                <button
                                    type="button"
                                    className={`robots-v2-inspector__lifecycle-step robots-v2-inspector__lifecycle-step--${tone}`}
                                    onClick={() => onStepClick?.(ev)}
                                >
                                    <span className="robots-v2-inspector__lifecycle-status">
                                        {executionStatusLabel(ev.status)}
                                    </span>
                                    <span className="mono robots-v2-inspector__lifecycle-ts">
                                        {fmtTs(ev.ts)}
                                    </span>
                                    <span className="robots-v2-inspector__lifecycle-meta">
                                        {[ev.side, ev.kind ? tradeReasonLabel(ev.kind) : null]
                                            .filter(Boolean)
                                            .join(' · ') || '—'}
                                        {ev.quantity != null ? ` · qty ${ev.quantity}` : ''}
                                        {ev.price != null ? ` · ${fmtMoney(Number(ev.price))}` : ''}
                                    </span>
                                    {reason ? (
                                        <span className="robots-v2-scan-reason">
                                            {tradeReasonLabel(reason)}
                                        </span>
                                    ) : null}
                                </button>
                            </li>
                        )
                    })}
                </ol>
            )}
        </section>
    )
}
