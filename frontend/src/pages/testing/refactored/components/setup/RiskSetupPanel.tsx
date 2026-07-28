import React from 'react'
import { Card } from '@/components/ui/Card'
import { RiskManagementPanel } from '@/pages/testing/refactored/components/setup/RiskManagementPanel'
import { CryptoRiskFields } from '@/pages/testing/refactored/components/setup/CryptoRiskFields'
import { currencyForMarket, type TestingMarket } from '@/pages/testing/refactored/market'
import { showBrokerCommission } from '@/pages/testing/refactored/visibility'
import type { TestingRiskParamsCardProps } from '@/pages/testing/TestingRiskParamsCard'

export type RiskSetupPanelProps = {
    market: TestingMarket
    risk: Omit<
        TestingRiskParamsCardProps,
        'className' | 'showCommission' | 'showNdfl' | 'capitalLabel' | 'maxPositionRubLabel' | 'showCapital' | 'embedded'
    > & {
        showMinProfitTarget?: boolean
        minProfitTargetPct?: number | null
        onMinProfitTargetPctChange?: (v: number) => void
    }
    crypto?: Omit<React.ComponentProps<typeof CryptoRiskFields>, 'onConfigDirty'>
    onConfigDirty: () => void
    className?: string
}

/** Риск-менеджмент (+ crypto-поля для ByBit). */
export function RiskSetupPanel({ market, risk, crypto, onConfigDirty, className = '' }: RiskSetupPanelProps) {
    const isCrypto = market === 'crypto'
    const currency = currencyForMarket(market)
    const capitalLabel = currency === 'USDT' ? 'Бюджет (USDT)' : 'Бюджет (₽)'
    const positionLabel = currency === 'USDT' ? 'Макс. позиция (USDT)' : 'Макс. позиция (₽)'
    const dirty = () => onConfigDirty()

    return (
        <Card className={`mb-6 cyber-form-card testing-cyber-card testing-risk-setup-panel ${className}`.trim()}>
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                РИСК-МЕНЕДЖМЕНТ
                <span className="cyber-bracket">]</span>
            </h3>
            <RiskManagementPanel
                {...risk}
                embedded
                isCrypto={isCrypto}
                showCapital
                showCommission={showBrokerCommission(market)}
                showNdfl={!isCrypto}
                capitalLabel={capitalLabel}
                maxPositionRubLabel={positionLabel}
                onConfigDirty={dirty}
                className="testing-risk-setup-panel__core"
            />
            {isCrypto && crypto && (
                <div className="testing-risk-setup-panel__crypto testing-risk-two-cols">
                    <CryptoRiskFields {...crypto} onConfigDirty={dirty} />
                </div>
            )}
        </Card>
    )
}
