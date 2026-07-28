import React from 'react'
import {
    TestingStrategyParamsCard,
    type TestingStrategyParamsCardProps,
} from '@/pages/testing/TestingStrategyParamsCard'

export type StrategyParamsPanelProps = Omit<TestingStrategyParamsCardProps, 'sectionTitle'> & {
    sectionTitle?: string
}

/** T2.6 — strategy params from `strategyPresets`. */
export function StrategyParamsPanel({
    sectionTitle = 'ПАРАМЕТРЫ СТРАТЕГИИ',
    className,
    embedded = false,
    ...props
}: StrategyParamsPanelProps) {
    return (
        <TestingStrategyParamsCard
            {...props}
            embedded={embedded}
            sectionTitle={sectionTitle}
            className={
                className ??
                (embedded ? 'testing-strategy-params-panel' : 'mb-6 cyber-form-card testing-cyber-card testing-strategy-params-panel')
            }
        />
    )
}
