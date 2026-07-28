import { MOEX_INTERVAL_FIELD, getStrategyIntervalFieldForMarket } from '@/pages/testing/strategyIntervals'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'

/**
 * Пресеты `strategy_params` и описание полей для всех поддерживаемых стратегий
 * (`grain_seed`, `momentum_breakout`, `reversion_to_ma`).
 *
 * Дефолты ДОЛЖНЫ совпадать с Pydantic-моделями в
 * `backend/app/modules/robots/schemas.py` и реестром стратегий в
 * `backend/app/modules/robots/trading/strategies/__init__.py`
 * (BRD-ARCH-03 §6, TESTING-UX §7.4).
 */
export const STRATEGY_NAMES = ['grain_seed', 'momentum_breakout', 'reversion_to_ma'] as const

export type StrategyName = (typeof STRATEGY_NAMES)[number]

export function isKnownStrategy(value: string): value is StrategyName {
    return (STRATEGY_NAMES as readonly string[]).includes(value)
}

/** Секции формы параметров стратегии (порядок отображения). */
export const STRATEGY_PARAM_GROUP_ORDER = ['candles', 'filters', 'signals', 'targets', 'eod'] as const

export type StrategyParamGroup = (typeof STRATEGY_PARAM_GROUP_ORDER)[number] | string

export const STRATEGY_PARAM_GROUP_LABELS: Record<string, string> = {
    candles: 'Свечи',
    filters: 'Фильтры входа',
    signals: 'Индикаторы сигнала',
    targets: 'Цель прибыли',
    eod: 'Закрытие сессии (MOEX)',
}

/** Тип поля динамической формы — что показать пользователю. */
export type StrategyParamField =
    | {
          key: string
          label: string
          kind: 'number'
          min?: number
          max?: number
          step?: number
          description?: string
          group?: StrategyParamGroup
      }
    | {
          key: string
          label: string
          kind: 'integer'
          min?: number
          max?: number
          description?: string
          group?: StrategyParamGroup
      }
    | { key: string; label: string; kind: 'boolean'; description?: string; group?: StrategyParamGroup }
    | {
          key: string
          label: string
          kind: 'enum'
          options: Array<{ value: string; label: string }>
          description?: string
          group?: StrategyParamGroup
      }
    | { key: string; label: string; kind: 'string'; description?: string; group?: StrategyParamGroup }

/** Универсальная форма метаданных стратегии для UI. */
export type StrategyMeta = {
    name: StrategyName
    title: string
    description: string
    defaults: Record<string, unknown>
    fields: StrategyParamField[]
}

/** @deprecated Use getStrategyIntervalFieldForMarket(market) from strategyIntervals.ts */
export const STRATEGY_INTERVAL_FIELD = MOEX_INTERVAL_FIELD

// ---------------------------------------------------------------------------
// GRAIN_SEED
// ---------------------------------------------------------------------------

export const GRAIN_SEED_STRATEGY_PARAMS_PRESET = {
    gap_filter_pct: 2.5,
    spread_limit_pct: 0.15,
    spread_proxy_multiplier: 8.0,
    atr_period: 14,
    atr_min_pct: 1.5,
    adx_period: 14,
    adx_threshold: 22.0,
    ma_fast_period: 5,
    ma_slow_period: 20,
    bb_period: 20,
    bb_stddev: 2.0,
    commission_pct: 0.05,
    min_profit_target_pct: 0.35,
    day_loss_streak_limit: 3,
    free_funds_reserve_pct: 50.0,
    risk_per_trade_pct: 2.0,
    max_position_size_pct: 20.0,
    force_close_time_msk: '18:45',
    force_market_flatten: true,
    sell_only_if_has_asset: true,
    interval: 'CANDLE_INTERVAL_5_MIN',
    candle_days: 14,
    signal_profile: 'legacy',
} as const

/**
 * Именованные пресеты торговой логики grain_seed (фильтры входа + триггеры).
 * `balanced` — дефолт осторожный; `active_trading` — больше сигналов (в т.ч. SELL/short)
 * по live-логам crypto 5m (ATR%~0.2–0.6, gap часто >2.5%).
 */
export type GrainSeedTradingPresetId = 'balanced' | 'active_trading'

export const GRAIN_SEED_TRADING_PRESET_META: Record<
    GrainSeedTradingPresetId,
    { label: string; shortLabel: string; hint: string }
> = {
    balanced: {
        label: 'Сбалансированный',
        shortLabel: 'Баланс',
        hint: 'Осторожные фильтры гэпа/ATR, SELL только при наличии позиции',
    },
    active_trading: {
        label: 'Активные торги',
        shortLabel: 'Активн.',
        hint: 'Мягче ATR/gap для crypto 5m, чаще BB/MA, разрешены SELL без позиции (short)',
    },
}

export const GRAIN_SEED_TRADING_PRESET_ORDER: GrainSeedTradingPresetId[] = [
    'balanced',
    'active_trading',
]

/** Патч strategy_params поверх текущего конфига (не затирает interval/candle_days). */
export const GRAIN_SEED_TRADING_PRESETS: Record<
    GrainSeedTradingPresetId,
    Partial<Record<string, unknown>>
> = {
    balanced: {
        gap_filter_pct: 2.5,
        spread_limit_pct: 0.15,
        spread_proxy_multiplier: 8.0,
        atr_period: 14,
        atr_min_pct: 1.5,
        adx_period: 14,
        adx_threshold: 22.0,
        ma_fast_period: 5,
        ma_slow_period: 20,
        bb_period: 20,
        bb_stddev: 2.0,
        min_profit_target_pct: 0.35,
        sell_only_if_has_asset: true,
        signal_profile: 'legacy',
    },
    active_trading: {
        gap_filter_pct: 7.0,
        spread_limit_pct: 0.15,
        spread_proxy_multiplier: 8.0,
        atr_period: 14,
        atr_min_pct: 0.3,
        adx_period: 14,
        adx_threshold: 18.0,
        ma_fast_period: 5,
        ma_slow_period: 15,
        bb_period: 20,
        bb_stddev: 1.7,
        min_profit_target_pct: 0.35,
        sell_only_if_has_asset: false,
        signal_profile: 'legacy',
    },
}

export function applyGrainSeedTradingPreset(
    current: Record<string, unknown>,
    presetId: GrainSeedTradingPresetId,
): Record<string, unknown> {
    const patch = GRAIN_SEED_TRADING_PRESETS[presetId]
    return { ...current, ...patch }
}

export function detectGrainSeedTradingPreset(
    params: Record<string, unknown>,
): GrainSeedTradingPresetId | null {
    for (const id of GRAIN_SEED_TRADING_PRESET_ORDER) {
        const patch = GRAIN_SEED_TRADING_PRESETS[id]
        const match = Object.entries(patch).every(([key, expected]) => {
            const actual = params[key]
            if (typeof expected === 'number' && typeof actual === 'number') {
                return Math.abs(actual - expected) < 1e-9
            }
            return actual === expected
        })
        if (match) return id
    }
    return null
}

/** Поля grain_seed, которые на MOEX не показываем в П3 (уже в П1 / П2 / риск). */
export const GRAIN_SEED_EXCLUDED_P3_FIELD_KEYS = [
    'gap_filter_pct',
    'spread_limit_pct',
    'spread_proxy_multiplier',
    'atr_period',
    'atr_min_pct',
    'adx_period',
    'adx_threshold',
    'min_profit_target_pct',
] as const

/** MOEX-only: принудительное закрытие сессии — не для ByBit. */
export const GRAIN_SEED_MOEX_ONLY_FIELD_KEYS = ['force_close_time_msk', 'force_market_flatten'] as const

/**
 * Crypto П3: скрываем только MOEX EOD.
 * `atr_min_pct` оставляем — это gate 5m-бара на входе в сигнал (не путать с
 * `crypto_universe.min_atr_percent` на скрининге пула).
 */
export const GRAIN_SEED_CRYPTO_P3_EXCLUDE_FIELD_KEYS = [...GRAIN_SEED_MOEX_ONLY_FIELD_KEYS] as const

const GRAIN_SEED_META: StrategyMeta = {
    name: 'grain_seed',
    title: 'По зёрнышку, по семечке',
    description: 'Осторожная стратегия с фильтрами гэпа/волатильности и режимами тренд/флэт',
    defaults: { ...GRAIN_SEED_STRATEGY_PARAMS_PRESET },
    fields: [
        { ...STRATEGY_INTERVAL_FIELD, group: 'candles' },
        {
            key: 'candle_days',
            label: 'Период истории свечей (дней)',
            kind: 'integer',
            min: 1,
            max: 3650,
            group: 'candles',
            description: 'Сколько дней истории подгружать для индикаторов.',
        },
        {
            key: 'gap_filter_pct',
            label: 'Фильтр гэпа, %',
            kind: 'number',
            min: 0,
            step: 0.1,
            group: 'filters',
            description: 'Пропуск сигнала при слишком большом гэпе к предыдущему закрытию.',
        },
        {
            key: 'spread_limit_pct',
            label: 'Лимит спреда, %',
            kind: 'number',
            min: 0,
            step: 0.05,
            group: 'filters',
            description:
                'На входе в сделку: базовый порог спреда. На crypto сравнивается с proxy (HL) × множитель. Отбор в пул — max_spread_bps на «Поиске монет».',
        },
        {
            key: 'spread_proxy_multiplier',
            label: 'Множитель proxy-спреда',
            kind: 'number',
            min: 1,
            step: 0.5,
            group: 'filters',
            description: 'На входе в сделку: потолок = лимит спреда × множитель. Типично 6–10 для ByBit (HL≈1–2%).',
        },
        {
            key: 'atr_period',
            label: 'Период ATR',
            kind: 'integer',
            min: 2,
            group: 'filters',
            description: 'На входе в сделку: окно ATR для gate волатильности бара сигнала.',
        },
        {
            key: 'atr_min_pct',
            label: 'Мин. ATR/Close, %',
            kind: 'number',
            min: 0,
            step: 0.1,
            group: 'filters',
            description:
                'На входе в сделку: мин. волатильность бара. Отбор монет в пул — min_atr_percent на «Поиске монет».',
        },
        {
            key: 'adx_period',
            label: 'Период ADX',
            kind: 'integer',
            min: 2,
            group: 'filters',
            description: 'Окно ADX — силы тренда.',
        },
        {
            key: 'adx_threshold',
            label: 'Порог ADX (trend)',
            kind: 'number',
            min: 0,
            step: 0.5,
            group: 'filters',
            description: 'Ниже ~20 — флэт; 20–40 — умеренный тренд; выше 40 — сильный.',
        },
        { key: 'ma_fast_period', label: 'MA fast', kind: 'integer', min: 1, group: 'signals' },
        { key: 'ma_slow_period', label: 'MA slow', kind: 'integer', min: 2, group: 'signals' },
        { key: 'bb_period', label: 'Период Bollinger', kind: 'integer', min: 5, group: 'signals' },
        {
            key: 'bb_stddev',
            label: 'Отклонение Bollinger',
            kind: 'number',
            min: 0,
            step: 0.1,
            group: 'signals',
        },
        {
            key: 'signal_profile',
            label: 'Профиль сигналов',
            kind: 'enum',
            group: 'signals',
            description: 'legacy — фильтры гэп/ATR/ADX + тренд/флэт; tz_signals_v1 — BUY + SL/TP в движке.',
            options: [
                { value: 'legacy', label: 'legacy — тренд/флэт, гэп/ATR/ADX' },
                { value: 'tz_signals_v1', label: 'tz_signals_v1 (BUY + SL/TP в движке)' },
            ],
        },
        {
            key: 'sell_only_if_has_asset',
            label: 'SELL только при наличии позиции',
            kind: 'boolean',
            group: 'signals',
            description:
                'Если выкл. и risk.allow_short=true — SELL без позиции открывает short. Нужно для активных торгов.',
        },
        {
            key: 'min_profit_target_pct',
            label: 'Мин. цель прибыли, %',
            kind: 'number',
            min: 0,
            step: 0.05,
            group: 'targets',
            description: 'Минимальный ожидаемый ход до входа (после комиссий/спреда).',
        },
        {
            key: 'force_close_time_msk',
            label: 'Принудительное закрытие (МСК)',
            kind: 'string',
            group: 'eod',
        },
        {
            key: 'force_market_flatten',
            label: 'После времени закрытия: рыночный выход',
            kind: 'boolean',
            group: 'eod',
        },
    ],
}

// ---------------------------------------------------------------------------
// MOMENTUM_BREAKOUT
// ---------------------------------------------------------------------------

export const MOMENTUM_BREAKOUT_STRATEGY_PARAMS_PRESET = {
    lookback_days: 5,
    entry_minutes_from_open: 30,
    hold_candles: 4,
    volume_confirmation: true,
    volume_multiplier: 1.5,
    exit_on_reverse: true,
    sell_only_if_has_asset: true,
    allow_entry_all_day: false,
    interval: 'CANDLE_INTERVAL_10_MIN',
    candle_days: 14,
} as const

const MOMENTUM_BREAKOUT_META: StrategyMeta = {
    name: 'momentum_breakout',
    title: 'Пробой максимума',
    description: 'Вход при пробое максимума N дней в первые M минут торгов',
    defaults: { ...MOMENTUM_BREAKOUT_STRATEGY_PARAMS_PRESET },
    fields: [
        STRATEGY_INTERVAL_FIELD,
        { key: 'candle_days', label: 'Период истории свечей (дней)', kind: 'integer', min: 1, max: 3650 },
        { key: 'lookback_days', label: 'Дней истории для уровня', kind: 'integer', min: 1, max: 30 },
        { key: 'entry_minutes_from_open', label: 'Окно входа от открытия, мин', kind: 'integer', min: 1, max: 360 },
        { key: 'hold_candles', label: 'Удерживать (свечей)', kind: 'integer', min: 1, max: 240 },
        {
            key: 'volume_confirmation',
            label: 'Подтверждение объёмом',
            kind: 'boolean',
            description: 'Требовать, чтобы пробойный бар имел повышенный объём',
        },
        { key: 'volume_multiplier', label: 'Множитель объёма', kind: 'number', min: 0.1, step: 0.1 },
        { key: 'exit_on_reverse', label: 'Выход при пробое вниз', kind: 'boolean' },
        { key: 'sell_only_if_has_asset', label: 'SELL только при наличии бумаги', kind: 'boolean' },
        { key: 'allow_entry_all_day', label: 'Разрешить вход весь день', kind: 'boolean' },
    ],
}

// ---------------------------------------------------------------------------
// REVERSION_TO_MA
// ---------------------------------------------------------------------------

export const REVERSION_TO_MA_STRATEGY_PARAMS_PRESET = {
    ma_period: 20,
    deviation_pct: 2.0,
    rsi_period: 14,
    rsi_overbought: 80.0,
    rsi_oversold: 20.0,
    max_hold_candles: 12,
    use_volume_filter: true,
    interval: 'CANDLE_INTERVAL_5_MIN',
    candle_days: 14,
} as const

const REVERSION_TO_MA_META: StrategyMeta = {
    name: 'reversion_to_ma',
    title: 'Возврат к MA',
    description: 'Mean-reversion: отскок от MA при перекупленности/перепроданности RSI',
    defaults: { ...REVERSION_TO_MA_STRATEGY_PARAMS_PRESET },
    fields: [
        STRATEGY_INTERVAL_FIELD,
        { key: 'candle_days', label: 'Период истории свечей (дней)', kind: 'integer', min: 1, max: 3650 },
        { key: 'ma_period', label: 'Период MA', kind: 'integer', min: 5, max: 500 },
        { key: 'deviation_pct', label: 'Отклонение от MA, %', kind: 'number', min: 0, step: 0.1 },
        { key: 'rsi_period', label: 'Период RSI', kind: 'integer', min: 2, max: 100 },
        { key: 'rsi_overbought', label: 'RSI перекупленность', kind: 'number', min: 50, max: 100, step: 1 },
        { key: 'rsi_oversold', label: 'RSI перепроданность', kind: 'number', min: 0, max: 50, step: 1 },
        { key: 'max_hold_candles', label: 'Макс. удержание (свечей)', kind: 'integer', min: 1, max: 500 },
        { key: 'use_volume_filter', label: 'Фильтр объёма', kind: 'boolean' },
    ],
}

// ---------------------------------------------------------------------------
// Реестр
// ---------------------------------------------------------------------------

const REGISTRY: Record<StrategyName, StrategyMeta> = {
    grain_seed: GRAIN_SEED_META,
    momentum_breakout: MOMENTUM_BREAKOUT_META,
    reversion_to_ma: REVERSION_TO_MA_META,
}

/** Возвращает метаданные стратегии. Для неизвестных — fallback на grain_seed. */
export function getStrategyMeta(name: string): StrategyMeta {
    return REGISTRY[name as StrategyName] ?? REGISTRY.grain_seed
}

/** Поля стратегии для UI с опциональным исключением (П3 / перенос в П1·П2·риск). */
export function getStrategyFieldsForUi(
    name: string,
    opts?: { excludeKeys?: readonly string[]; market?: TestingMarket },
): StrategyParamField[] {
    const meta = getStrategyMeta(name)
    const exclude = new Set<string>()
    if (opts?.excludeKeys !== undefined) {
        for (const key of opts.excludeKeys) exclude.add(key)
    } else if (name === 'grain_seed' && opts?.market !== 'crypto') {
        // MOEX П3: фильтры уже на П1/риске. Crypto — показываем все фильтры здесь.
        for (const key of GRAIN_SEED_EXCLUDED_P3_FIELD_KEYS) exclude.add(key)
    }
    if (name === 'grain_seed' && opts?.market === 'crypto') {
        for (const key of GRAIN_SEED_MOEX_ONLY_FIELD_KEYS) exclude.add(key)
    }
    return meta.fields
        .filter(f => !exclude.has(f.key))
        .map(f => {
            if (f.key !== 'interval' || !opts?.market) return f
            const intervalField = getStrategyIntervalFieldForMarket(opts.market)
            return { ...intervalField, group: f.group ?? 'candles' }
        })
}

/** Группирует поля по `group` с сохранением порядка STRATEGY_PARAM_GROUP_ORDER. */
export function groupStrategyFields(
    fields: StrategyParamField[],
): Array<{ id: string; label: string; fields: StrategyParamField[] }> {
    const byGroup = new Map<string, StrategyParamField[]>()
    for (const field of fields) {
        const id = field.group || '_ungrouped'
        const list = byGroup.get(id)
        if (list) list.push(field)
        else byGroup.set(id, [field])
    }
    const orderedIds = [
        ...STRATEGY_PARAM_GROUP_ORDER.filter(id => byGroup.has(id)),
        ...[...byGroup.keys()].filter(id => !(STRATEGY_PARAM_GROUP_ORDER as readonly string[]).includes(id)),
    ]
    return orderedIds.map(id => ({
        id,
        label: id === '_ungrouped' ? '' : STRATEGY_PARAM_GROUP_LABELS[id] ?? id,
        fields: byGroup.get(id) ?? [],
    }))
}

/** Дефолтные `strategy_params` для стратегии (включая `interval`). */
export function getStrategyParamsPreset(name: string): Record<string, unknown> {
    return { ...getStrategyMeta(name).defaults }
}

/** Список метаданных всех известных стратегий (для UI-списков). */
export function listStrategyMeta(): StrategyMeta[] {
    return STRATEGY_NAMES.map(n => REGISTRY[n])
}

// ---------------------------------------------------------------------------
// Риск-пресет и хелперы MSK — единые для всех стратегий (BRD-ARCH-03 §7).
// Оставлены под старыми именами для обратной совместимости с импортами.
// ---------------------------------------------------------------------------

export type GrainSeedRiskPreset = {
    stop_loss_percent: number
    take_profit_percent: number
    max_position_percent: number
    max_position_rub: number
    max_daily_loss: number
    trading_hours_start: string
    trading_hours_end: string
    allowed_weekdays: number
}

export function getGrainSeedRiskPreset(): GrainSeedRiskPreset {
    return {
        stop_loss_percent: 2.0,
        take_profit_percent: 3.0,
        max_position_percent: 10.0,
        max_position_rub: 50_000.0,
        max_daily_loss: 5.0,
        trading_hours_start: '10:00 MSK',
        trading_hours_end: '18:45 MSK',
        allowed_weekdays: 31,
    }
}

export function stripTradingHoursMsk(s: string): string {
    return String(s || '')
        .replace(/\s*MSK\s*$/i, '')
        .trim()
}

export function toRiskMskTime(display: string, fallbackMsk: string): string {
    const d = String(display || '').trim()
    if (!d) return fallbackMsk
    if (/msk/i.test(d)) return d
    return `${d} MSK`
}
