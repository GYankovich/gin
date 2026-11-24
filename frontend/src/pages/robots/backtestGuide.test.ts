import { describe, expect, it } from 'vitest'
import {
    buildBacktestVerdict,
    presetDraftPatch,
    reasonDigest,
} from './backtestGuide'

describe('backtest presets', () => {
    it('fills a runnable trend draft', () => {
        const patch = presetDraftPatch('trend')
        expect(patch.archetype).toBe('momentum')
        expect(patch.universeMode).toBe('fixed')
        expect(patch.fixedList).toContain('SBER')
        expect(patch.capital).toBe(100_000)
        expect(patch.mode).toBe('paper')
        expect(Number(patch.stopLossPct)).toBeLessThan(Number(patch.takeProfitPct))
    })
})

describe('backtest verdict', () => {
    it('says when nothing traded', () => {
        const v = buildBacktestVerdict({
            totalReturnPercent: 0,
            maxDrawdownPercent: 0,
            winRatePercent: null,
            tradeCount: 0,
            initialCapital: 100_000,
            finalEquity: 100_000,
            reasonCodes: [],
        })
        expect(v.headline).toMatch(/ни одной сделки/)
        expect(v.caution).toMatch(/Входов не было/)
        expect(v.digest).toEqual([])
    })

    it('groups fill reasons in Russian', () => {
        const lines = reasonDigest([
            'stop_loss',
            'momentum_breakout',
            'momentum_breakout',
            'take_profit',
        ])
        expect(lines[0]).toBe('Пробой + объём — 2')
        expect(lines).toHaveLength(3)
    })

    it('warns on a deep drawdown', () => {
        const v = buildBacktestVerdict({
            totalReturnPercent: 4.2,
            maxDrawdownPercent: 31,
            winRatePercent: 55,
            tradeCount: 8,
            initialCapital: 100_000,
            finalEquity: 104_200,
            reasonCodes: ['momentum_breakout'],
        })
        expect(v.headline).toMatch(/\+4\.2%/)
        expect(v.caution).toMatch(/25%/)
        expect(v.body).toMatch(/104[\s\u00a0]?200/)
    })
})
