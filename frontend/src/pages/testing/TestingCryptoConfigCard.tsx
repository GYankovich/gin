import React from 'react'
import {
    CryptoExtendedPanel,
    type CryptoExtendedPanelProps,
} from '@/pages/testing/refactored/components/setup/CryptoExtendedPanel'

export type TestingCryptoConfigCardProps = CryptoExtendedPanelProps

/** @deprecated Prefer `CryptoExtendedPanel` (T2.4). */
export function TestingCryptoConfigCard(props: TestingCryptoConfigCardProps) {
    return <CryptoExtendedPanel {...props} />
}
