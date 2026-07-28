import React from 'react'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'

export type TestingSetupCollapsibleProps = {
    market: TestingMarket
    extended: React.ReactNode
}

/** Расширенные параметры: MOEX — раскрыт по умолчанию, ByBit — свёрнут. */
export function TestingSetupCollapsible({ market, extended }: TestingSetupCollapsibleProps) {
    const defaultOpen = market === 'moex'

    return (
        <div className="testing-setup-collapsible">
            <CollapsibleSection
                id="testing-setup-extended"
                className="testing-setup-collapsible__section testing-setup-collapsible__section--extended"
                title="Расширенные параметры"
                hint={market === 'moex' ? 'MOEX: пересбор universe' : 'Crypto: модель комиссий'}
                defaultOpen={defaultOpen}
            >
                {extended}
            </CollapsibleSection>
        </div>
    )
}
