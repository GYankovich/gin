import React from 'react'
import { Card } from '@/components/ui/Card'
import { TestingUniverseModeFields, type TestingUniverseModeFieldsProps } from '@/pages/testing/TestingUniverseModeFields'

export type TestingUniverseModeCardProps = TestingUniverseModeFieldsProps

/** @deprecated Prefer `BaseConfigPanel` (T2.2); thin wrapper for backward compatibility. */
export function TestingUniverseModeCard(props: TestingUniverseModeCardProps) {
    const isCrypto = props.isCrypto ?? false
    return (
        <Card className="mb-6 pipeline-card testing-universe-mode-card">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                {isCrypto ? 'UNIVERSE (CRYPTO)' : 'ОТБОР БУМАГ (UNIVERSE)'}
                <span className="cyber-bracket">]</span>
            </h3>
            <TestingUniverseModeFields {...props} />
        </Card>
    )
}
