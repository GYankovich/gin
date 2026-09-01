/** Wizard draft model for robots v2 4-step master. */

export type WizardGoal = 'conservative' | 'moderate' | 'aggressive'
export type WizardArchetype = 'scalper' | 'momentum' | 'reversion' | 'grid'
export type WizardUniverseMode = 'fixed' | 'index' | 'screener'
export type WizardInstrumentType = 'stock' | 'futures' | 'perpetual' | 'coin_futures'

export type RobotV2WizardDraft = {
    name: string
    tokenId: number | null
    goal: WizardGoal
    instrumentType: WizardInstrumentType
    mode: 'paper' | 'live'
    advancedMode: boolean
    weekdays: boolean[]
    timeFrom: string
    timeTo: string
    pollInterval: '1m' | '5m' | '15m' | '1h'
    archetype: WizardArchetype | null
    timeframe: string
    strategyParams: Record<string, number | string | boolean>
    universeMode: WizardUniverseMode
    fixedList: string
    indexCode: string
    screenerPreset: 'high_liquidity' | 'volatile' | 'low_price' | 'custom'
    maxAssets: number
    exitOnDrop: boolean
    capital: number
    maxPositionSharePct: number
    stopLossPct: number
    takeProfitPct: number
    maxDailyLoss: number
    maxDrawdownPct: number
    maxConcurrentPositions: number
    brokerCommissionPct: number
    taxPct: number
    slippagePct: number
    stopMode: 'soft' | 'hard'
    eodFlattenEnabled: boolean | null
    eodMinutesBeforeClose: number
    portfolioEnabled: boolean
}

export const DRAFT_STORAGE_KEY = 'gin-robots-v2-wizard-draft'
export const PORTFOLIO_DRAFT_STORAGE_KEY = 'gin-robots-v2-wizard-draft-portfolio'
const DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1000

export function defaultWizardDraft(): RobotV2WizardDraft {
    return {
        name: '',
        tokenId: null,
        goal: 'moderate',
        instrumentType: 'stock',
        mode: 'paper',
        advancedMode: false,
        weekdays: [true, true, true, true, true, false, false],
        timeFrom: '10:00',
        timeTo: '18:30',
        pollInterval: '5m',
        archetype: 'momentum',
        timeframe: '1h',
        strategyParams: {
            maPeriod: 50,
            volumeMultiplier: 2,
            breakoutLookback: 20,
        },
        universeMode: 'fixed',
        fixedList: 'SBER, GAZP',
        indexCode: 'IMOEX',
        screenerPreset: 'high_liquidity',
        maxAssets: 20,
        exitOnDrop: false,
        capital: 100_000,
        maxPositionSharePct: 10,
        stopLossPct: 2,
        takeProfitPct: 4,
        maxDailyLoss: 5000,
        maxDrawdownPct: 50,
        maxConcurrentPositions: 3,
        brokerCommissionPct: 0.05,
        taxPct: 13,
        slippagePct: 0.5,
        stopMode: 'soft',
        eodFlattenEnabled: null,
        eodMinutesBeforeClose: 15,
        portfolioEnabled: true,
    }
}

export function archetypeDefaults(archetype: WizardArchetype): {
    timeframe: string
    params: Record<string, number | string | boolean>
    advancedMode?: boolean
} {
    switch (archetype) {
        case 'scalper':
            return {
                timeframe: '1m',
                advancedMode: true,
                params: {
                    deltaThresholdPct: 8,
                    requiresWebSocket: true,
                    minVolumeWindow: 30,
                    cooldownSec: 180,
                    stopLossCooldownSec: 600,
                    trendLookbackTicks: 10,
                    trendBlockLongBps: 30,
                    minHoldSec: 90,
                    minExitMoveBps: 80,
                    invalidateBelowEntryBps: 180,
                    minFlowTicks: 5,
                },
            }
        case 'momentum':
            return {
                timeframe: '1h',
                params: { maPeriod: 50, volumeMultiplier: 2, breakoutLookback: 20 },
            }
        case 'reversion':
            return {
                timeframe: '15m',
                params: { indicator: 'rsi', overboughtThreshold: 80, oversoldThreshold: 20, rsiPeriod: 14 },
            }
        case 'grid':
            return {
                timeframe: '5m',
                params: { gridStepAtrPct: 1.5, gridDepth: 5, baseAllocationPct: 30, scaleMultiplier: 1.2 },
            }
    }
}

export function parseFixedList(raw: string): string[] {
    return raw
        .split(/[,;\s]+/)
        .map(t => t.trim().toUpperCase())
        .filter(Boolean)
}

export function draftToV4Config(draft: RobotV2WizardDraft): Record<string, unknown> {
    const fixed = parseFixedList(draft.fixedList)
    let universe: Record<string, unknown>
    if (draft.universeMode === 'fixed') {
        universe = {
            mode: 'fixed',
            fixedList: fixed,
            excluded: [],
            maxAssets: draft.maxAssets,
            exitOnDrop: draft.exitOnDrop,
        }
    } else if (draft.universeMode === 'index') {
        universe = {
            mode: 'index',
            index: draft.indexCode,
            excluded: [],
            maxAssets: draft.maxAssets,
            exitOnDrop: draft.exitOnDrop,
        }
    } else {
        universe = {
            mode: 'screener',
            screener: {
                preset: draft.screenerPreset,
                filters: [],
                filterMode: 'all',
                refreshPolicy: 'daily',
            },
            excluded: [],
            maxAssets: draft.maxAssets,
            exitOnDrop: draft.exitOnDrop,
        }
    }

    return {
        configVersion: 4,
        core: {
            goal: draft.goal,
            instrumentType: draft.instrumentType,
            mode: draft.mode,
            advancedMode: draft.advancedMode || draft.archetype === 'scalper',
            schedule: {
                weekdays: draft.weekdays,
                timeFrom: draft.timeFrom,
                timeTo: draft.timeTo,
                pollInterval: draft.pollInterval,
            },
        },
        strategy: {
            archetype: draft.archetype || 'momentum',
            timeframe: draft.timeframe,
            params: draft.strategyParams,
        },
        universe,
        risk: {
            // Live sizing uses broker equity at runtime; keep a positive placeholder for schema.
            capital: draft.mode === 'live' ? Math.max(Number(draft.capital) || 1, 1) : draft.capital,
            maxPositionSharePct: draft.maxPositionSharePct,
            stopLossPct: draft.stopLossPct,
            takeProfitPct: draft.takeProfitPct,
            maxDailyLoss: draft.maxDailyLoss,
            maxDrawdownPct: draft.maxDrawdownPct,
            maxConcurrentPositions: draft.maxConcurrentPositions,
            brokerCommissionPct: draft.brokerCommissionPct,
            taxPct: draft.taxPct,
            slippagePct: draft.slippagePct,
            stopMode: draft.stopMode,
            eodFlatten: {
                enabled: draft.eodFlattenEnabled,
                minutesBeforeClose: draft.eodMinutesBeforeClose,
            },
        },
    }
}

export function configToDraft(config: Record<string, unknown>, name: string, tokenId: number | null): RobotV2WizardDraft {
    const base = defaultWizardDraft()
    const core = (config.core || {}) as Record<string, unknown>
    const schedule = (core.schedule || {}) as Record<string, unknown>
    const strategy = (config.strategy || {}) as Record<string, unknown>
    const universe = (config.universe || {}) as Record<string, unknown>
    const risk = (config.risk || {}) as Record<string, unknown>
    const screener = (universe.screener || {}) as Record<string, unknown>
    const fixedList = Array.isArray(universe.fixedList)
        ? (universe.fixedList as string[]).join(', ')
        : base.fixedList

    return {
        ...base,
        name,
        tokenId,
        goal: (core.goal as RobotV2WizardDraft['goal']) || base.goal,
        instrumentType: (core.instrumentType as RobotV2WizardDraft['instrumentType']) || base.instrumentType,
        mode: (core.mode as 'paper' | 'live') || 'paper',
        advancedMode: Boolean(core.advancedMode),
        weekdays: Array.isArray(schedule.weekdays) ? (schedule.weekdays as boolean[]) : base.weekdays,
        timeFrom: String(schedule.timeFrom || base.timeFrom),
        timeTo: String(schedule.timeTo || base.timeTo),
        pollInterval: (schedule.pollInterval as RobotV2WizardDraft['pollInterval']) || base.pollInterval,
        archetype: (strategy.archetype as WizardArchetype) || 'momentum',
        timeframe: String(strategy.timeframe || base.timeframe),
        strategyParams: (() => {
            const stored = (strategy.params as Record<string, number | string | boolean>) || {}
            const arch = (strategy.archetype as WizardArchetype) || 'momentum'
            if (arch === 'scalper') {
                return { ...archetypeDefaults('scalper').params, ...stored }
            }
            return Object.keys(stored).length ? stored : base.strategyParams
        })(),
        universeMode: (universe.mode as WizardUniverseMode) || 'fixed',
        fixedList,
        indexCode: String(universe.index || base.indexCode),
        screenerPreset: (screener.preset as RobotV2WizardDraft['screenerPreset']) || base.screenerPreset,
        maxAssets: Number(universe.maxAssets ?? base.maxAssets),
        exitOnDrop: Boolean(universe.exitOnDrop),
        capital: Number(risk.capital ?? base.capital),
        maxPositionSharePct: Number(risk.maxPositionSharePct ?? base.maxPositionSharePct),
        stopLossPct: Number(risk.stopLossPct ?? base.stopLossPct),
        takeProfitPct: Number(risk.takeProfitPct ?? base.takeProfitPct),
        maxDailyLoss: Number(risk.maxDailyLoss ?? base.maxDailyLoss),
        maxDrawdownPct: Number(risk.maxDrawdownPct ?? base.maxDrawdownPct),
        maxConcurrentPositions: Number(risk.maxConcurrentPositions ?? base.maxConcurrentPositions),
        brokerCommissionPct: Number(risk.brokerCommissionPct ?? base.brokerCommissionPct),
        taxPct: Number(risk.taxPct ?? base.taxPct),
        slippagePct: Number(risk.slippagePct ?? base.slippagePct),
        stopMode: (risk.stopMode as 'soft' | 'hard') || 'soft',
        eodFlattenEnabled:
            (risk.eodFlatten as { enabled?: boolean | null } | undefined)?.enabled ?? null,
        eodMinutesBeforeClose: Number(
            (risk.eodFlatten as { minutesBeforeClose?: number } | undefined)?.minutesBeforeClose ?? 15,
        ),
        portfolioEnabled: true,
    }
}

function padWeekdays(raw: unknown): boolean[] {
    const src = Array.isArray(raw) ? raw.map(Boolean) : []
    const out = [...src.slice(0, 7)]
    while (out.length < 7) out.push(false)
    if (!out.some(Boolean)) {
        return [true, true, true, true, true, false, false]
    }
    return out
}

export function draftToPortfolioV4Config(draft: RobotV2WizardDraft): Record<string, unknown> {
    return {
        configVersion: 4,
        schedule: {
            weekdays: padWeekdays(draft.weekdays),
            timeFrom: draft.timeFrom,
            timeTo: draft.timeTo,
            pollInterval: draft.pollInterval,
        },
    }
}

export function configToPortfolioDraft(
    config: Record<string, unknown>,
    name: string,
    tokenId: number | null,
    status?: number | null,
): RobotV2WizardDraft {
    const base = defaultWizardDraft()
    const core = (config.core || {}) as Record<string, unknown>
    const schedule = (
        (config.schedule as Record<string, unknown> | undefined)
        || (core.schedule as Record<string, unknown> | undefined)
        || {}
    )
    return {
        ...base,
        name,
        tokenId,
        weekdays: padWeekdays(schedule.weekdays),
        timeFrom: String(schedule.timeFrom || base.timeFrom),
        timeTo: String(schedule.timeTo || base.timeTo),
        pollInterval: (schedule.pollInterval as RobotV2WizardDraft['pollInterval']) || base.pollInterval,
        portfolioEnabled: status !== 2,
    }
}

export function saveDraftLocal(draft: RobotV2WizardDraft, key?: string): void {
    const storageKey = key ?? DRAFT_STORAGE_KEY
    try {
        localStorage.setItem(
            storageKey,
            JSON.stringify({ savedAt: Date.now(), draft }),
        )
    } catch {
        /* ignore quota */
    }
}

export function loadDraftLocal(key?: string): RobotV2WizardDraft | null {
    const storageKey = key ?? DRAFT_STORAGE_KEY
    try {
        const raw = localStorage.getItem(storageKey)
        if (!raw) return null
        const parsed = JSON.parse(raw) as { savedAt?: number; draft?: RobotV2WizardDraft }
        if (!parsed?.draft || !parsed.savedAt) return null
        if (Date.now() - parsed.savedAt > DRAFT_TTL_MS) {
            localStorage.removeItem(storageKey)
            return null
        }
        return { ...defaultWizardDraft(), ...parsed.draft }
    } catch {
        return null
    }
}

export function clearDraftLocal(key?: string): void {
    try {
        localStorage.removeItem(key ?? DRAFT_STORAGE_KEY)
    } catch {
        /* ignore */
    }
}

export const ARCHETYPE_CARDS: Array<{
    id: WizardArchetype
    title: string
    description: string
}> = [
    { id: 'momentum', title: 'Momentum', description: 'Пробой и тренд: цена vs MA + объём' },
    { id: 'reversion', title: 'Reversion', description: 'Отскок от перекупленности / перепроданности' },
    { id: 'grid', title: 'Grid', description: 'Сетка уровней с шагом ATR' },
    { id: 'scalper', title: 'Scalper', description: 'Быстрые входы по дисбалансу (нужен WS)' },
]

export const WEEKDAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
