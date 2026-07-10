import React from 'react'
import { MoexExtendedPanel, type MoexExtendedPanelProps } from '@/pages/testing/refactored/components/setup/MoexExtendedPanel'
import { CryptoExtendedPanel, type CryptoExtendedPanelProps } from '@/pages/testing/refactored/components/setup/CryptoExtendedPanel'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'
import { showCryptoFields, showMoexFields } from '@/pages/testing/refactored/visibility'

export type ExtendedPanelProps = {
    market: TestingMarket
    moex: MoexExtendedPanelProps
    crypto: CryptoExtendedPanelProps
}

/** §7.2 Group 2 / Group 3 — mutually exclusive extended blocks. */
export function ExtendedPanel({ market, moex, crypto }: ExtendedPanelProps) {
    if (showCryptoFields(market)) {
        return <CryptoExtendedPanel {...crypto} />
    }
    if (showMoexFields(market)) {
        return <MoexExtendedPanel {...moex} />
    }
    return null
}
