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
                title={(
                    <span className="dashboard-collapse__label">
                        <IconExtended />
                        Расширенные параметры
                    </span>
                )}
                hint={market === 'moex' ? 'MOEX: пересбор universe' : 'Crypto: модель комиссий'}
                defaultOpen={defaultOpen}
            >
                {extended}
            </CollapsibleSection>
        </div>
    )
}

function IconExtended() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M5 4v16M12 4v16M19 4v16" />
            <circle cx="5" cy="9" r="2.1" fill="var(--bg-card)" stroke="currentColor" strokeWidth="1.7" />
            <circle cx="12" cy="15" r="2.1" fill="var(--bg-card)" stroke="currentColor" strokeWidth="1.7" />
            <circle cx="19" cy="11" r="2.1" fill="var(--bg-card)" stroke="currentColor" strokeWidth="1.7" />
        </svg>
    )
}
