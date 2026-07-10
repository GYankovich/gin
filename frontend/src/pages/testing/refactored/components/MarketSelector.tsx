import React from 'react'
import { Card } from '@/components/ui/Card'
import {
    TESTING_MARKET_OPTIONS,
    type TestingMarket,
} from '@/pages/testing/refactored/market'

export type MarketSelectorProps = {
    value: TestingMarket
    onChange: (market: TestingMarket) => void
    disabled?: boolean
    className?: string
}

/** T2.1 — explicit MOEX / Crypto market choice (first control on Setup). */
export function MarketSelector({ value, onChange, disabled = false, className = '' }: MarketSelectorProps) {
    return (
        <Card className={`testing-market-selector cyber-form-card testing-cyber-card ${className}`.trim()}>
            <div className="testing-market-selector__head">
                <h3 className="card__section-title pipeline-title testing-market-selector__title">
                    <span className="cyber-bracket">[</span>
                    РЫНОК
                    <span className="cyber-bracket">]</span>
                </h3>
                <span className="testing-market-selector__currency" aria-live="polite">
                    Валюта: {TESTING_MARKET_OPTIONS.find(o => o.value === value)?.currency ?? '₽'}
                </span>
            </div>
            <div
                className="testing-market-selector__options"
                role="radiogroup"
                aria-label="Выбор рынка для бэктеста"
            >
                {TESTING_MARKET_OPTIONS.map(opt => {
                    const selected = value === opt.value
                    return (
                        <button
                            key={opt.value}
                            type="button"
                            role="radio"
                            aria-checked={selected}
                            disabled={disabled}
                            className={`testing-market-selector__option${selected ? ' testing-market-selector__option--selected' : ''}`}
                            onClick={() => {
                                if (!disabled && !selected) onChange(opt.value)
                            }}
                        >
                            <span className="testing-market-selector__option-label">{opt.label}</span>
                            <span className="testing-market-selector__option-desc">{opt.description}</span>
                        </button>
                    )
                })}
            </div>
        </Card>
    )
}
