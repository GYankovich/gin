import React from 'react'
import { Card } from '@/components/ui/Card'
import {
    TestingOptimizationCard,
    type TestingOptimizationCardProps,
} from '@/pages/testing/TestingOptimizationCard'

export type OptimizationPanelProps = TestingOptimizationCardProps & {
    hasBacktestResult?: boolean
}

export function OptimizationPanel({ hasBacktestResult = false, ...props }: OptimizationPanelProps) {
    return (
        <Card className="mb-4 cyber-form-card testing-cyber-card testing-optimization-panel testing-optimization-panel--compact">
            <div className="testing-optimization-panel__head">
                <h3 className="testing-optimization-panel__title">
                    <span className="cyber-bracket">[</span>
                    ОПТИМИЗАЦИЯ
                    <span className="cyber-bracket">]</span>
                </h3>
                {!hasBacktestResult && (
                    <p className="testing-optimization-panel__hint">
                        Ранжирование и сетка · история ниже · «Анализ» открывает прогон на вкладке «Анализ»
                    </p>
                )}
            </div>
            <TestingOptimizationCard {...props} embedded />
        </Card>
    )
}
