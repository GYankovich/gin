import React from 'react'
import { Card } from '@/components/ui/Card'
import {
    TestingRecommendationsCard,
    type TestingRecommendationsCardProps,
} from '@/pages/testing/TestingRecommendationsCard'

export type RecommendationsPanelProps = Omit<
    TestingRecommendationsCardProps,
    'onRefresh' | 'embedded'
> & {
    refresh: () => void
    hasBacktestResult?: boolean
}

/** Рекомендации по конфигу — отдельно от параметров стратегии. */
export function RecommendationsPanel({
    hasBacktestResult = false,
    refresh,
    ...recProps
}: RecommendationsPanelProps) {
    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card testing-recommendations-panel">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                РЕКОМЕНДАЦИИ
                <span className="cyber-bracket">]</span>
            </h3>
            {!hasBacktestResult && (
                <p className="testing-recommendations-panel__hint">
                    Точнее после успешного бэктеста; можно обновить вручную.
                </p>
            )}
            <TestingRecommendationsCard {...recProps} onRefresh={refresh} embedded />
        </Card>
    )
}
