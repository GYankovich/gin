import React from 'react'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { TestingMoexCacheCard } from '@/pages/testing/TestingMoexCacheCard'
import { TestingUniverseCard } from '@/pages/testing/TestingUniverseCard'
import {
    TestingRobotParamsCard,
    type TestingRobotParamsCardProps,
} from '@/pages/testing/TestingRobotParamsCard'
import type { MoexCandleJobState } from '@/pages/testing/hooks/useMoexCandleJobState'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'
import { showMoexAdvancedExtras } from '@/pages/testing/refactored/visibility'

export type AdvancedPanelUniverseProps = React.ComponentProps<typeof TestingUniverseCard>['universe']

export type AdvancedPanelProps = {
    market: TestingMarket
    moex: MoexCandleJobState
    robotId: number | null
    universe: AdvancedPanelUniverseProps
    robotActions: Pick<
        TestingRobotParamsCardProps,
        | 'brokerType'
        | 'onConfigDirty'
        | 'createName'
        | 'onCreateNameChange'
        | 'createTokenId'
        | 'onCreateTokenIdChange'
        | 'createTokenOptions'
        | 'onCreateRobot'
        | 'creatingRobot'
    >
}

/** MOEX extras + создание робота. */
export function AdvancedPanel({
    market,
    moex,
    robotId,
    universe,
    robotActions,
}: AdvancedPanelProps) {
    const isCrypto = market === 'crypto'
    return (
        <CollapsibleSection
            id="testing-setup-advanced"
            className="testing-setup-collapsible__section testing-setup-collapsible__section--advanced testing-advanced-panel"
            title={(
                <span className="dashboard-collapse__label">
                    <IconAdvanced />
                    Дополнительно
                </span>
            )}
            badge={<span className="badge badge--neutral testing-advanced-panel__badge">Опционально</span>}
            hint="Создание робота, кеш MOEX"
            defaultOpen={false}
        >
            <div className="testing-advanced-panel__body">
                <TestingRobotParamsCard
                    {...robotActions}
                    isCrypto={isCrypto}
                    hideBroker
                    hidePoll
                    compactTitle
                />

                {showMoexAdvancedExtras(market) && (
                    <>
                        <TestingMoexCacheCard moex={moex} />
                        <TestingUniverseCard robotId={robotId} universe={universe} />
                    </>
                )}
            </div>
        </CollapsibleSection>
    )
}

function IconAdvanced() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <circle cx="12" cy="12" r="8.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M12 8.2v4.2l2.6 2.6" />
        </svg>
    )
}
