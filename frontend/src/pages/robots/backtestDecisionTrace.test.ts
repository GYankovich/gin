import { describe, expect, it } from 'vitest'
import {
    deriveStatusCounts,
    mergeCycleBundle,
    packetFromSignal,
    resolveObservability,
} from './backtestGlassBox'

describe('backtest decision trace', () => {
    it('keeps the explanation and measured conditions for an ignored signal', () => {
        const row = {
            signal_time: '2026-01-01T10:00:00Z',
            figi: 'SBER',
            signal_type: 'NONE',
            status: 'ignored',
            cycle_id: 'cycle-1',
            decision_code: 'BELOW_MA',
            decision_message: 'Цена 250.00 ≤ MA 252.00',
            decision_metrics: { ma: 252, price: 250 },
        }

        const packet = packetFromSignal(row)
        expect(packet.decision_code).toBe('BELOW_MA')
        expect(packet.decision_message).toContain('Цена')
        expect(packet.decision_metrics).toEqual({ ma: 252, price: 250 })
        expect(deriveStatusCounts([row]).ignored).toBe(1)
    })

    it('also reads trace fields restored from database payload', () => {
        const packet = packetFromSignal({
            figi: 'GAZP',
            status: 'ignored',
            payload: {
                decision_code: 'LOW_VOLUME',
                decision_message: 'Объём ниже порога',
                decision_metrics: { volume: 10, volumeThreshold: 20 },
            },
        })
        expect(packet.decision_code).toBe('LOW_VOLUME')
        expect(packet.decision_metrics?.volumeThreshold).toBe(20)
    })

    it('rewrites legacy execution metadata and keeps truncation honest', () => {
        const obs = resolveObservability({
            signals: [],
            executionModel: { model: 'BAR_CLOSE', look_ahead: true },
            historyStats: { signals: 25_000, signals_truncated: 1 },
        })

        expect(obs.execution_model?.code).toBe('NEXT_BAR_OPEN')
        expect(obs.execution_model?.look_ahead).toBe(false)
        expect(obs.execution_model?.label).toContain('следующего бара')
        expect(obs.signals_logged).toBe(25_000)
        expect(obs.signals_truncated).toBe(true)
    })

    it('preserves cycle links and risk context from the inspector bundle', () => {
        const packet = mergeCycleBundle(
            packetFromSignal({ figi: 'SBER', cycle_id: 'cycle-2', status: 'deferred' }),
            {
                cycle_id: 'cycle-2',
                trades: [{ id: 17, figi: 'SBER', status: 'filled' }],
                config_risk_excerpt: { stopLossPct: 2 },
            },
        )

        expect(packet.linked_trade_ids).toEqual([17])
        expect(packet.config_risk_excerpt).toEqual({ stopLossPct: 2 })
    })
})
