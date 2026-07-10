import React from 'react'
import { StrategyParamsPanel, type StrategyParamsPanelProps } from '@/pages/testing/refactored/components/setup/StrategyParamsPanel'
import { RiskManagementPanel, type RiskManagementPanelProps } from '@/pages/testing/refactored/components/setup/RiskManagementPanel'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'
import { showBrokerCommission } from '@/pages/testing/refactored/visibility'

export type StrategyRiskPanelProps = {
    market: TestingMarket
    strategy: StrategyParamsPanelProps['strategy']
    strategyParams: StrategyParamsPanelProps['params']
    onStrategyParamChange: StrategyParamsPanelProps['onParamChange']
    risk: Omit<RiskManagementPanelProps, 'isCrypto' | 'className' | 'showCommission' | 'showNdfl'>
    onConfigDirty: () => void
}

/** §7.2 Group 1 — strategy + risk; commission only when showBrokerCommission(market). */
export function StrategyRiskPanel({
    market,
    strategy,
    strategyParams,
    onStrategyParamChange,
    risk,
    onConfigDirty,
}: StrategyRiskPanelProps) {
    const dirty = () => onConfigDirty()
    const isCrypto = market === 'crypto'

    return (
        <>
            <StrategyParamsPanel
                market={market}
                strategy={strategy}
                params={strategyParams}
                onParamChange={onStrategyParamChange}
                onConfigDirty={dirty}
            />
            <RiskManagementPanel
                {...risk}
                isCrypto={isCrypto}
                showCapital={false}
                showCommission={showBrokerCommission(market)}
                showNdfl={false}
                onConfigDirty={dirty}
            />
        </>
    )
}
