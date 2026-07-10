import type { TestingFormState, TestingMarket } from '@/pages/testing/refactored/types/forms'

/** §8.2 — base market checks. */
export function isMoexMarket(market: TestingMarket): boolean {
    return market === 'moex'
}

export function isCryptoMarket(market: TestingMarket): boolean {
    return market === 'crypto'
}

/** §7.2 Group 2 — MOEX-specific UI blocks. */
export function showMoexFields(market: TestingMarket): boolean {
    return isMoexMarket(market)
}

/** §7.2 Group 3 — Crypto-specific UI blocks. */
export function showCryptoFields(market: TestingMarket): boolean {
    return isCryptoMarket(market)
}

/** §7.2 — broker commission in risk panel (MOEX only). */
export function showBrokerCommission(market: TestingMarket): boolean {
    return isMoexMarket(market)
}

/** §8.2 — crypto universe extended filters (auto mode). */
export function showCryptoExtendedFilters(
    form: Pick<TestingFormState, 'market' | 'cryptoUniverseMode'>,
): boolean {
    return isCryptoMarket(form.market) && form.cryptoUniverseMode === 'auto'
}

/** §7.2 Group 1 — poll + create robot (shown for both markets). */
export function showAdvancedRobotActions(_market: TestingMarket): boolean {
    return true
}

/** MOEX-only extras inside AdvancedPanel (cache, live universe card). */
export function showMoexAdvancedExtras(market: TestingMarket): boolean {
    return isMoexMarket(market)
}
