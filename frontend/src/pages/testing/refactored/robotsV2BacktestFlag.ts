/** Feature flag: route /testing backtest through robots v2 API. */
export function isRobotsV2BacktestEnabled(): boolean {
    const raw = String(import.meta.env.VITE_ROBOTS_V2_BACKTEST ?? '').trim().toLowerCase()
    return raw === 'true' || raw === '1' || raw === 'yes'
}

/** v2 archetypes supported on /testing when flag is on. */
export const V2_BACKTEST_STRATEGIES = ['momentum_breakout', 'reversion_to_ma'] as const

export function isV2BacktestStrategy(strategy: string): boolean {
    return (V2_BACKTEST_STRATEGIES as readonly string[]).includes(String(strategy || '').trim())
}
