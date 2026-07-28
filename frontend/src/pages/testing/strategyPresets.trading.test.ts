import { describe, expect, it } from 'vitest'
import {
    GRAIN_SEED_STRATEGY_PARAMS_PRESET,
    applyGrainSeedTradingPreset,
    detectGrainSeedTradingPreset,
} from '@/pages/testing/strategyPresets'

describe('grain_seed trading presets', () => {
    it('active_trading softens ATR/gap and allows SELL without position', () => {
        const next = applyGrainSeedTradingPreset(
            { ...GRAIN_SEED_STRATEGY_PARAMS_PRESET },
            'active_trading',
        )
        expect(next.atr_min_pct).toBe(0.3)
        expect(next.gap_filter_pct).toBe(7)
        expect(next.bb_stddev).toBe(1.7)
        expect(next.adx_threshold).toBe(18)
        expect(next.ma_slow_period).toBe(15)
        expect(next.sell_only_if_has_asset).toBe(false)
        expect(next.interval).toBe(GRAIN_SEED_STRATEGY_PARAMS_PRESET.interval)
    })

    it('detects active_trading after apply', () => {
        const next = applyGrainSeedTradingPreset(
            { ...GRAIN_SEED_STRATEGY_PARAMS_PRESET },
            'active_trading',
        )
        expect(detectGrainSeedTradingPreset(next)).toBe('active_trading')
    })

    it('detects balanced defaults', () => {
        expect(
            detectGrainSeedTradingPreset({ ...GRAIN_SEED_STRATEGY_PARAMS_PRESET }),
        ).toBe('balanced')
    })
})
