/** Resolve broker from robot REST config, falling back to token type. */

import { brokerFromTokenType, type TokenTypeRef } from '@/modules/robots/config/tokenBroker'
import {
    DEFAULT_EXECUTION_LATENCY_SEC,
    DEFAULT_MAX_DRAWDOWN_PCT,
    defaultSlippagePct,
} from '@/pages/testing/executionRiskDefaults'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'

export function resolveBrokerFromRobotConfig(
    cfg: Record<string, unknown>,
    token?: TokenTypeRef | null,
): 'tinvest' | 'bybit' {
    const raw = String(cfg.broker_type || '').trim().toLowerCase()
    if (raw === 'bybit' || raw === 'tinvest') return raw
    return brokerFromTokenType(token)
}

/** execution_model + risk.max_drawdown from GET /robots/id/{id} config. */
export function hydrateExecutionRiskFromConfig(
    cfg: Record<string, unknown>,
    market: TestingMarket,
): {
    slippagePct: number
    executionLatencySec: number
    maxDrawdownPct: number
} {
    const exec = (cfg.execution_model || {}) as Record<string, unknown>
    const risk = (cfg.risk || {}) as Record<string, unknown>
    const slippage =
        exec.slippage_pct != null && Number.isFinite(Number(exec.slippage_pct))
            ? Number(exec.slippage_pct)
            : defaultSlippagePct(market)
    const latency =
        exec.latency_sec != null && Number.isFinite(Number(exec.latency_sec))
            ? Math.max(0, Number(exec.latency_sec))
            : DEFAULT_EXECUTION_LATENCY_SEC
    const drawdown =
        risk.max_drawdown_percent != null && Number.isFinite(Number(risk.max_drawdown_percent))
            ? Number(risk.max_drawdown_percent)
            : DEFAULT_MAX_DRAWDOWN_PCT
    return {
        slippagePct: slippage,
        executionLatencySec: latency,
        maxDrawdownPct: drawdown,
    }
}
