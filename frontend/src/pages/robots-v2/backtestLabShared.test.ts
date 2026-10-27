import { describe, expect, it } from 'vitest'
import { backtestRunPath, parseBacktestRunId } from './backtestLabShared'

describe('backtest lab routes', () => {
    it('builds a dedicated run path', () => {
        expect(backtestRunPath(231)).toBe('/backtest/231')
    })

    it('parses positive integer run ids', () => {
        expect(parseBacktestRunId('231')).toBe(231)
        expect(parseBacktestRunId('0')).toBeNull()
        expect(parseBacktestRunId('foo')).toBeNull()
        expect(parseBacktestRunId(undefined)).toBeNull()
    })
})
