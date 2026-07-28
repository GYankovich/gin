/**
 * @deprecated Импортируйте из `@/pages/testing/strategyPresets`.
 *
 * Файл сохранён как реэкспорт, чтобы не ломать существующие импорты
 * после расширения архитектуры под 3 стратегии (BRD-ARCH-03 §6).
 */
export {
    GRAIN_SEED_STRATEGY_PARAMS_PRESET,
    GRAIN_SEED_TRADING_PRESETS,
    GRAIN_SEED_TRADING_PRESET_META,
    applyGrainSeedTradingPreset,
    getGrainSeedRiskPreset,
    stripTradingHoursMsk,
    toRiskMskTime,
} from '@/pages/testing/strategyPresets'

export type {
    GrainSeedRiskPreset,
    GrainSeedTradingPresetId,
} from '@/pages/testing/strategyPresets'
