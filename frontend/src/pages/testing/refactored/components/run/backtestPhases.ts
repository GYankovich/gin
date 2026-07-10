/** Mirrors `backend/app/modules/robots/backtest_progress.py` phase weights and order. */

export const BACKTEST_PHASE_ORDER = [
    'fetching_market_data',
    'prefetching_market_snapshots',
    'scoring',
    'prefetching_candles',
    'loading_candles',
    'simulating',
    'persisting',
] as const

export type BacktestPhaseId = (typeof BACKTEST_PHASE_ORDER)[number]

export const BACKTEST_PHASE_WEIGHTS: Record<BacktestPhaseId, number> = {
    fetching_market_data: 4,
    prefetching_market_snapshots: 12,
    scoring: 36,
    prefetching_candles: 10,
    loading_candles: 8,
    simulating: 28,
    persisting: 2,
}

export const BACKTEST_PHASE_LABELS_RU: Record<BacktestPhaseId, string> = {
    fetching_market_data: 'Подготовка',
    prefetching_market_snapshots: 'Снимки MOEX',
    scoring: 'Отбор бумаг',
    prefetching_candles: 'Кэш свечей MOEX',
    loading_candles: 'Загрузка свечей',
    simulating: 'Симуляция',
    persisting: 'Сохранение',
}

export type PhaseStepState = 'pending' | 'active' | 'done'

export type PhaseStepView = {
    id: BacktestPhaseId
    label: string
    weight: number
    state: PhaseStepState
    detail?: string | null
}

export function normalizeRunPhase(runPhase: string | null | undefined): string {
    const p = String(runPhase || '').trim().toLowerCase()
    if (p === 'prefetching_crypto_market') return 'prefetching_market_snapshots'
    return p
}

/** Human label for a run phase (supports crypto prefetch alias). */
export function runPhaseLabelRu(runPhase: string | null | undefined): string {
    const raw = String(runPhase || '').trim().toLowerCase()
    if (raw === 'prefetching_crypto_market') return 'Кэш ByBit (D1 + funding)'
    const norm = normalizeRunPhase(runPhase) as BacktestPhaseId
    return BACKTEST_PHASE_LABELS_RU[norm] ?? (raw || '—')
}

export function phaseIndex(runPhase: string | null | undefined): number {
    const p = normalizeRunPhase(runPhase)
    if (!p || p === 'fetching_market_data') return 0
    if (p === 'cancelled' || p === 'cancelled_simulation') {
        return BACKTEST_PHASE_ORDER.indexOf('simulating')
    }
    const idx = BACKTEST_PHASE_ORDER.indexOf(p as BacktestPhaseId)
    return idx >= 0 ? idx : 0
}

export function derivePhaseSteps(args: {
    runPhase?: string | null
    running: boolean
    hasResult: boolean
    phaseUnitsDone?: number | null
    phaseUnitsTotal?: number | null
}): PhaseStepView[] {
    const { runPhase, running, hasResult, phaseUnitsDone, phaseUnitsTotal } = args

    const phaseDetail =
        phaseUnitsTotal != null && phaseUnitsTotal > 0 && phaseUnitsDone != null
            ? `${phaseUnitsDone}/${phaseUnitsTotal}`
            : null

    if (hasResult && !running) {
        return BACKTEST_PHASE_ORDER.map(id => ({
            id,
            label: BACKTEST_PHASE_LABELS_RU[id],
            weight: BACKTEST_PHASE_WEIGHTS[id],
            state: 'done' as const,
        }))
    }

    const activeIdx = running || normalizeRunPhase(runPhase) ? phaseIndex(runPhase) : -1

    return BACKTEST_PHASE_ORDER.map((id, idx) => {
        let state: PhaseStepState = 'pending'
        if (activeIdx < 0) {
            state = 'pending'
        } else if (idx < activeIdx) {
            state = 'done'
        } else if (idx === activeIdx) {
            state = running ? 'active' : hasResult ? 'done' : 'pending'
        }

        return {
            id,
            label:
                state === 'active' && normalizeRunPhase(runPhase) === 'prefetching_crypto_market'
                    ? runPhaseLabelRu(runPhase)
                    : BACKTEST_PHASE_LABELS_RU[id],
            weight: BACKTEST_PHASE_WEIGHTS[id],
            state,
            detail: state === 'active' ? phaseDetail : null,
        }
    })
}

export function phaseStepIcon(state: PhaseStepState): string {
    if (state === 'done') return '✅'
    if (state === 'active') return '⏳'
    return '○'
}
