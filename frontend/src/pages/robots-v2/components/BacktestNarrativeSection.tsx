import React, { useEffect, useState } from 'react'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { robotV2Service } from '@/services/robotV2Service'
import type { BacktestNarrativeStep } from '@/types/robot'

type Props = {
    runId: number | null
    /** Steps embedded on details when present. */
    seedSteps?: BacktestNarrativeStep[] | null
    highlightedTs?: string | null
    onStepClick?: (step: BacktestNarrativeStep) => void
    /** Open on first paint so a finished run can be read without hunting. */
    defaultOpen?: boolean
}

function fmtTs(raw: string | null | undefined): string {
    if (!raw) return ''
    const d = new Date(raw)
    if (!Number.isFinite(d.getTime())) return String(raw)
    return d.toLocaleString('ru-RU')
}

/** Zone P — RU narrative stream (collapsed by default). */
export function BacktestNarrativeSection({
    runId,
    seedSteps,
    highlightedTs,
    onStepClick,
    defaultOpen = false,
}: Props) {
    const [open, setOpen] = useState(defaultOpen)
    const [loading, setLoading] = useState(false)
    const [steps, setSteps] = useState<BacktestNarrativeStep[] | null>(
        seedSteps && seedSteps.length ? seedSteps : null,
    )
    const [failed, setFailed] = useState(false)

    useEffect(() => {
        setSteps(seedSteps && seedSteps.length ? seedSteps : null)
        setFailed(false)
    }, [runId, seedSteps])

    useEffect(() => {
        // `steps != null` means we already resolved (seed or fetch), including empty [].
        if (!open || runId == null || steps != null || failed) return
        if (seedSteps && seedSteps.length) return
        let cancelled = false
        setLoading(true)
        void (async () => {
            try {
                const res = await robotV2Service.getBacktestNarrative(runId)
                if (cancelled) return
                if (!res) {
                    setFailed(true)
                    setSteps([])
                    return
                }
                setSteps(res.items || [])
            } finally {
                if (!cancelled) setLoading(false)
            }
        })()
        return () => {
            cancelled = true
        }
    }, [open, runId, steps, failed, seedSteps])

    const highlightSec = highlightedTs
        ? Math.floor(new Date(highlightedTs).getTime() / 1000)
        : null

    const nearestIdx = (() => {
        if (highlightSec == null || !steps?.length) return -1
        let best = -1
        let bestDist = Infinity
        steps.forEach((s, i) => {
            if (!s.ts) return
            const sec = Math.floor(new Date(s.ts).getTime() / 1000)
            if (!Number.isFinite(sec)) return
            const d = Math.abs(sec - highlightSec)
            if (d < bestDist) {
                bestDist = d
                best = i
            }
        })
        return best
    })()

    const empty = !loading && (!steps || steps.length === 0)

    return (
        <CollapsibleSection
            id="backtest-journal"
            title={(
                <span className="dashboard-collapse__label">
                    <IconNarrative />
                    Журнал решений
                </span>
            )}
            hint="Шаги прогона по порядку: данные, сигналы, отказы"
            badge={
                <span className="robots-v2-hint">
                    {failed || (steps != null && steps.length === 0)
                        ? 'нет'
                        : (steps?.length ?? '')}
                </span>
            }
            className="dashboard-assets-card robots-v2-glass-narrative"
            open={open}
            onOpenChange={(next) => {
                setOpen(next)
                if (next && failed) {
                    setFailed(false)
                    setSteps(seedSteps && seedSteps.length ? seedSteps : null)
                }
            }}
        >
            {loading ? (
                <p className="robots-v2-hint">Загрузка журнала…</p>
            ) : empty || failed ? (
                <p className="robots-v2-hint">
                    Текстового журнала для этого прогона нет. Сделки и сигналы ниже всё равно можно открыть по строке.
                </p>
            ) : (
                <>
                <p className="robots-v2-hint">
                    Полный след прогона: какие данные взяли, какой сигнал вышел и почему сделка могла не случиться.
                </p>
                <ol className="robots-v2-glass-narrative__list">
                    {(steps || []).map((s, i) => (
                        <li
                            key={`${s.section}-${s.step}-${i}`}
                            className={
                                i === nearestIdx
                                    ? 'robots-v2-glass-narrative__item robots-v2-glass-narrative__item--on'
                                    : 'robots-v2-glass-narrative__item'
                            }
                        >
                            <button
                                type="button"
                                className="robots-v2-glass-narrative__btn"
                                onClick={() => onStepClick?.(s)}
                            >
                                <span className="robots-v2-glass-narrative__meta">
                                    <span className="robots-v2-glass-narrative__section">
                                        {s.section}
                                    </span>
                                    {s.ts ? (
                                        <span className="mono robots-v2-hint">{fmtTs(s.ts)}</span>
                                    ) : null}
                                </span>
                                <span className="robots-v2-glass-narrative__text">{s.text}</span>
                            </button>
                        </li>
                    ))}
                </ol>
                </>
            )}
        </CollapsibleSection>
    )
}

function IconNarrative() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                d="M5 6h14M5 12h10M5 18h12"
            />
        </svg>
    )
}
