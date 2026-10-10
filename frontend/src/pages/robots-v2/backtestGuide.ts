import { tradeReasonLabel } from '@/pages/robots-v2/tradeReasonLabels'
import {
    archetypeDefaults,
    type RobotV2WizardDraft,
    type WizardArchetype,
} from '@/pages/robots-v2/wizardDraft'

/** Ready-made rule sets a new user can run without tuning indicators. */
export type BacktestPresetId = 'trend' | 'bounce' | 'grid'

export type BacktestPreset = {
    id: BacktestPresetId
    title: string
    blurb: string
    /** How the generator decides, in one sentence. */
    rule: string
    archetype: Exclude<WizardArchetype, 'scalper'>
    tickers: string
    /** Inclusive day count, same convention as the period presets. */
    days: number
    capital: number
}

export const BACKTEST_PRESETS: BacktestPreset[] = [
    {
        id: 'trend',
        title: 'Тренд',
        blurb: 'SBER, GAZP, LKOH · час · 90 дней',
        rule: 'Покупает, когда цена выше средней и пробивает недавний максимум на повышенном объёме. Выходит, когда цена падает ниже средней.',
        archetype: 'momentum',
        tickers: 'SBER, GAZP, LKOH',
        days: 90,
        capital: 100_000,
    },
    {
        id: 'bounce',
        title: 'Отскок',
        blurb: 'SBER, GAZP · 15 минут · 90 дней',
        rule: 'Покупает, когда RSI слишком низкий, и закрывает, когда индикатор возвращается к обычным значениям.',
        archetype: 'reversion',
        tickers: 'SBER, GAZP',
        days: 90,
        capital: 100_000,
    },
    {
        id: 'grid',
        title: 'Сетка',
        blurb: 'SBER · 5 минут · 30 дней',
        rule: 'Раскладывает уровни вокруг цены и фиксирует небольшой шаг. На мелком таймфрейме прогон длиннее.',
        archetype: 'grid',
        tickers: 'SBER',
        days: 30,
        capital: 100_000,
    },
]

export function matchingPreset(
    draft: Pick<RobotV2WizardDraft, 'archetype' | 'fixedList'>,
): BacktestPresetId | null {
    const list = draft.fixedList.replace(/\s+/g, '')
    for (const preset of BACKTEST_PRESETS) {
        if (draft.archetype === preset.archetype && list === preset.tickers.replace(/\s+/g, '')) {
            return preset.id
        }
    }
    return null
}

export function collectReasonCodes(rows: ReadonlyArray<unknown>): string[] {
    const out: string[] = []
    for (const row of rows) {
        if (!row || typeof row !== 'object') continue
        const rec = row as Record<string, unknown>
        const code = rec.reason ?? rec.exit_reason ?? rec.strategy_reason
        if (code != null && String(code).trim()) out.push(String(code))
    }
    return out
}

export function presetById(id: BacktestPresetId): BacktestPreset {
    const found = BACKTEST_PRESETS.find(p => p.id === id)
    if (!found) throw new Error(`unknown preset ${id}`)
    return found
}

/** Fields the Lab form needs so «Запустить» is valid without extra clicks. */
export function presetDraftPatch(id: BacktestPresetId): Partial<RobotV2WizardDraft> {
    const preset = presetById(id)
    const defaults = archetypeDefaults(preset.archetype)
    return {
        goal: 'moderate',
        instrumentType: 'stock',
        mode: 'paper',
        advancedMode: false,
        archetype: preset.archetype,
        timeframe: defaults.timeframe,
        strategyParams: defaults.params,
        universeMode: 'fixed',
        fixedList: preset.tickers,
        capital: preset.capital,
        stopLossPct: 2,
        takeProfitPct: 4,
    }
}

export type BacktestVerdictInput = {
    totalReturnPercent: number | null
    maxDrawdownPercent: number | null
    winRatePercent: number | null
    tradeCount: number
    initialCapital: number
    finalEquity: number | null
    /** Raw strategy/risk reason codes from fills. */
    reasonCodes: Array<string | null | undefined>
}

export type BacktestVerdict = {
    headline: string
    body: string
    caution: string | null
    digest: string[]
}

function fmtRub(n: number): string {
    return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(Math.round(n))} ₽`
}

function fmtPct1(n: number): string {
    const sign = n > 0 ? '+' : ''
    return `${sign}${n.toFixed(1)}%`
}

/** Top reasons a person can read without opening the signal table. */
export function reasonDigest(
    codes: Array<string | null | undefined>,
    limit = 3,
): string[] {
    const counts = new Map<string, number>()
    for (const code of codes) {
        const label = tradeReasonLabel(code)
        if (!code || label === '—') continue
        counts.set(label, (counts.get(label) ?? 0) + 1)
    }
    return [...counts.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ru'))
        .slice(0, limit)
        .map(([label, n]) => `${label} — ${n}`)
}

export function buildBacktestVerdict(input: BacktestVerdictInput): BacktestVerdict {
    const ret = input.totalReturnPercent
    const dd = input.maxDrawdownPercent
    const trades = input.tradeCount
    const start = input.initialCapital
    const end = input.finalEquity

    let headline: string
    if (trades <= 0) {
        headline = 'За период стратегия не открыла ни одной сделки'
    } else if (ret == null || !Number.isFinite(ret)) {
        headline = 'Прогон завершён'
    } else if (ret >= 0) {
        headline = `За период правила заработали ${fmtPct1(ret)}`
    } else {
        headline = `За период правила потеряли ${fmtPct1(ret)}`
    }

    const bits: string[] = []
    if (Number.isFinite(start) && start > 0 && end != null && Number.isFinite(end)) {
        bits.push(`Старт ${fmtRub(start)}, итог ${fmtRub(end)}.`)
    }
    if (dd != null && Number.isFinite(dd)) {
        bits.push(`Самая глубокая просадка ${Math.abs(dd).toFixed(1)}%.`)
    }
    if (trades > 0) {
        const wr = input.winRatePercent
        bits.push(
            wr != null && Number.isFinite(wr)
                ? `Сделок ${trades}, прибыльных ${wr.toFixed(0)}%.`
                : `Сделок ${trades}.`,
        )
    }
    bits.push('Считается по историческим свечам, с комиссией и проскальзыванием из настроек.')

    let caution: string | null = null
    if (trades <= 0) {
        caution = 'Входов не было. Проверьте тикеры, период и пороги — или выберите другой готовый набор правил.'
    } else if (dd != null && Number.isFinite(dd) && Math.abs(dd) >= 25) {
        caution = 'Просадка больше 25%. Для первого робота это много: уменьшите долю позиции или стоп и прогоните ещё раз.'
    } else if (ret != null && Number.isFinite(ret) && ret < 0) {
        caution = 'Период убыточный. Это проверка правил на истории, не повод сразу включать торговлю.'
    } else {
        caution = 'Это история. Следующий период может быть другим. Робот из прогона создаётся остановленным.'
    }

    return {
        headline,
        body: bits.join(' '),
        caution,
        digest: reasonDigest(input.reasonCodes),
    }
}
