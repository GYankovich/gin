import { describe, expect, it } from 'vitest'
import {
    buildScreenerFilters,
    customScreenerFieldDefaults,
    defaultWizardDraft,
    draftToV4Config,
    parseScreenerFilters,
} from './wizardDraft'

describe('screener custom filters', () => {
    it('seeds moex and crypto defaults for Свой', () => {
        expect(customScreenerFieldDefaults('stock')).toMatchObject({
            screenerMinVolume: 10_000_000,
            screenerMinPrice: 10,
        })
        expect(customScreenerFieldDefaults('perpetual')).toMatchObject({
            screenerMinVolume: 5_000_000,
            screenerMinPrice: 0,
        })
    })

    it('builds v4 filters and round-trips via parse', () => {
        const draft = {
            ...defaultWizardDraft(),
            screenerPreset: 'custom' as const,
            universeMode: 'screener' as const,
            screenerMinVolume: 7_000_000,
            screenerMinHistVolume: 20_000_000,
            screenerMaxSpreadPct: 0.4,
            screenerMinAtrPct: 1.5,
            screenerMinPrice: 15,
            screenerMaxPrice: 400,
        }
        const filters = buildScreenerFilters(draft)
        expect(filters[0]).toEqual({ type: 'status', allowed: ['trading'] })
        expect(filters).toEqual(expect.arrayContaining([
            expect.objectContaining({ type: 'volume', value: 7_000_000 }),
            expect.objectContaining({ type: 'hist_volume', value: 20_000_000 }),
            expect.objectContaining({ type: 'spread', valuePct: 0.4 }),
            expect.objectContaining({ type: 'atr', value: 1.5 }),
            expect.objectContaining({ type: 'price', op: '>', value: 15 }),
            expect.objectContaining({ type: 'price', op: '<', value: 400 }),
        ]))
        expect(parseScreenerFilters(filters)).toEqual({
            screenerMinVolume: 7_000_000,
            screenerMinHistVolume: 20_000_000,
            screenerMaxSpreadPct: 0.4,
            screenerMinAtrPct: 1.5,
            screenerMinPrice: 15,
            screenerMaxPrice: 400,
        })
    })

    it('emits empty filters when all gates are zero so backend preset applies', () => {
        const draft = {
            ...defaultWizardDraft(),
            screenerPreset: 'custom' as const,
            universeMode: 'screener' as const,
            screenerMinVolume: 0,
            screenerMinHistVolume: 0,
            screenerMaxSpreadPct: 0,
            screenerMinAtrPct: 0,
            screenerMinPrice: 0,
            screenerMaxPrice: 0,
        }
        expect(buildScreenerFilters(draft)).toEqual([])
        const cfg = draftToV4Config(draft)
        const universe = cfg.universe as { screener: { filters: unknown[] } }
        expect(universe.screener.filters).toEqual([])
    })

    it('includes custom filters in draftToV4Config when preset is custom', () => {
        const draft = {
            ...defaultWizardDraft(),
            screenerPreset: 'custom' as const,
            universeMode: 'screener' as const,
            screenerMinVolume: 12_000_000,
            screenerMinPrice: 10,
        }
        const cfg = draftToV4Config(draft)
        const universe = cfg.universe as { screener: { preset: string; filters: Array<{ type: string }> } }
        expect(universe.screener.preset).toBe('custom')
        expect(universe.screener.filters.some(f => f.type === 'volume')).toBe(true)
    })
})
