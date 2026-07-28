import React from 'react'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { StrategyParamsPanel } from '@/pages/testing/refactored/components/setup/StrategyParamsPanel'
import { RiskManagementPanel } from '@/pages/testing/refactored/components/setup/RiskManagementPanel'
import { PollFrequencyField } from '@/pages/testing/refactored/components/setup/PollFrequencyField'
import { CryptoRiskFields } from '@/pages/testing/refactored/components/setup/CryptoRiskFields'
import { currencyForMarket, type TestingMarket } from '@/pages/testing/refactored/market'
import { showBrokerCommission } from '@/pages/testing/refactored/visibility'
import type { TestingRiskParamsCardProps } from '@/pages/testing/TestingRiskParamsCard'

export type StrategyRiskColumnsPanelProps = {
    market: TestingMarket
    strategyOptions: Array<{ value: string; label: string }>
    strategy: string
    onStrategyChange: (v: string) => void
    strategyParams: Record<string, unknown>
    onStrategyParamChange: (key: string, value: unknown) => void
    pollValue: number
    onPollValueChange: (v: number) => void
    pollUnit: 'minutes' | 'hours'
    onPollUnitChange: (u: 'minutes' | 'hours') => void
    risk: Omit<
        TestingRiskParamsCardProps,
        'className' | 'isCrypto' | 'showCommission' | 'showNdfl' | 'capitalLabel' | 'maxPositionRubLabel'
    > & {
        showMinProfitTarget?: boolean
        minProfitTargetPct?: number | null
        onMinProfitTargetPctChange?: (v: number) => void
    }
    crypto?: Omit<React.ComponentProps<typeof CryptoRiskFields>, 'onConfigDirty'>
    onConfigDirty: () => void
    className?: string
}

/** Блок 4 — стратегия (слева) и риск-менеджмент (справа). */
export function StrategyRiskColumnsPanel({
    market,
    strategyOptions,
    strategy,
    onStrategyChange,
    strategyParams,
    onStrategyParamChange,
    pollValue,
    onPollValueChange,
    pollUnit,
    onPollUnitChange,
    risk,
    crypto,
    onConfigDirty,
    className = '',
}: StrategyRiskColumnsPanelProps) {
    const isCrypto = market === 'crypto'
    const currency = currencyForMarket(market)
    const capitalLabel = currency === 'USDT' ? 'Бюджет (USDT)' : 'Бюджет (₽)'
    const positionLabel = currency === 'USDT' ? 'Макс. позиция (USDT)' : 'Макс. позиция (₽)'
    const dirty = () => onConfigDirty()

    return (
        <Card className={`mb-6 cyber-form-card testing-cyber-card testing-strategy-risk-columns ${className}`.trim()}>
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                СТРАТЕГИЯ И РИСК
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="testing-strategy-risk-columns__grid">
                <div className="testing-strategy-risk-columns__strategy">
                    <h4 className="card__subsection-title">Параметры стратегии</h4>
                    <div className="form-group">
                        <label className="form-label">Стратегия</label>
                        <Select
                            options={strategyOptions}
                            value={strategy}
                            onChange={v => {
                                onStrategyChange(String(v || 'grain_seed'))
                                dirty()
                            }}
                        />
                    </div>
                    <StrategyParamsPanel
                        market={market}
                        strategy={strategy}
                        params={strategyParams}
                        onParamChange={onStrategyParamChange}
                        onConfigDirty={dirty}
                        embedded
                        sectionTitle=""
                        excludeFieldKeys={['interval']}
                        className="testing-strategy-risk-columns__params"
                    />
                    <div className="testing-strategy-risk-columns__poll">
                        <h4 className="card__subsection-title">Имитация запуска робота</h4>
                        <PollFrequencyField
                            pollValue={pollValue}
                            onPollValueChange={onPollValueChange}
                            pollUnit={pollUnit}
                            onPollUnitChange={onPollUnitChange}
                            onConfigDirty={dirty}
                        />
                    </div>
                </div>
                <div className="testing-strategy-risk-columns__risk">
                    <h4 className="card__subsection-title">Риск-менеджмент</h4>
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
                        className="testing-strategy-risk-columns__risk-card"
                    />
                    {isCrypto && crypto && (
                        <div className="testing-strategy-risk-columns__crypto-risk testing-risk-two-cols">
                            <CryptoRiskFields {...crypto} onConfigDirty={dirty} />
                        </div>
                    )}
                </div>
            </div>
        </Card>
    )
}
