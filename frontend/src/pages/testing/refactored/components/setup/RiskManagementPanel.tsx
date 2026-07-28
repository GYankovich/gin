import React from 'react'
import {
    TestingRiskParamsCard,
    type TestingRiskParamsCardProps,
} from '@/pages/testing/TestingRiskParamsCard'

export type RiskManagementPanelProps = TestingRiskParamsCardProps & {
    isCrypto?: boolean
    embedded?: boolean
}

/** T2.7 — SL/TP/position/max daily loss % (+ commission for all markets). */
export function RiskManagementPanel({
    isCrypto = false,
    embedded = false,
    maxDailyLossLabel = 'Макс. дневной убыток, %',
    showCapital = false,
    showCommission = true,
    showNdfl = false,
    maxPositionRubLabel,
    className = embedded
        ? 'testing-risk-management-panel testing-risk-management-panel--embedded'
        : 'mb-6 cyber-form-card testing-cyber-card testing-risk-management-panel',
    ...props
}: RiskManagementPanelProps) {
    const positionLabel = maxPositionRubLabel ?? (isCrypto ? 'Макс. позиция (USDT)' : 'Макс. позиция (₽)')

    return (
        <TestingRiskParamsCard
            {...props}
            embedded={embedded}
            className={className}
            maxDailyLossLabel={maxDailyLossLabel}
            showCapital={showCapital}
            showCommission={showCommission}
            showNdfl={showNdfl}
            maxPositionRubLabel={positionLabel}
        />
    )
}
