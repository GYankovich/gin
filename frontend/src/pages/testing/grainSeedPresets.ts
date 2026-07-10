/**
 * @deprecated Импортируйте из `@/pages/testing/strategyPresets`.
 *
 * Файл сохранён как реэкспорт, чтобы не ломать существующие импорты
 * после расширения архитектуры под 3 стратегии (BRD-ARCH-03 §6).
 */
export {
    GRAIN_SEED_STRATEGY_PARAMS_PRESET,
    getGrainSeedRiskPreset,
    stripTradingHoursMsk,
    toRiskMskTime,
} from '@/pages/testing/strategyPresets'

export type { GrainSeedRiskPreset } from '@/pages/testing/strategyPresets'
