import React from 'react'
import {
    isCryptoInstrument,
    type TradingRobotWizardDraft,
} from '@/pages/robots/wizardDraft'

type Props = {
    draft: TradingRobotWizardDraft
    patch: (partial: Partial<TradingRobotWizardDraft>) => void
    columns?: 2 | 3
}

export function ScreenerCustomFilters({ draft, patch, columns = 2 }: Props) {
    const crypto = isCryptoInstrument(draft.instrumentType)
    return (
        <div className="robots-screener-custom">
            <p className="robots-hint robots-screener-custom__hint">
                Ноль — условие не применяется.
            </p>
            <div className={`robots-grid robots-grid--${columns}`}>
                <label className="robots-field">
                    <span>{crypto ? 'Мин. объём 24ч, $' : 'Мин. объём'}</span>
                    <input
                        className="robots-input"
                        type="number"
                        min={0}
                        step={crypto ? 100_000 : 1_000_000}
                        value={draft.screenerMinVolume}
                        onChange={e => patch({ screenerMinVolume: Number(e.target.value) })}
                    />
                </label>
                {!crypto && (
                    <label className="robots-field">
                        <span>Мин. ср. объём (20д)</span>
                        <input
                            className="robots-input"
                            type="number"
                            min={0}
                            step={1_000_000}
                            value={draft.screenerMinHistVolume}
                            onChange={e => patch({ screenerMinHistVolume: Number(e.target.value) })}
                        />
                    </label>
                )}
                <label className="robots-field">
                    <span>Макс. спред %</span>
                    <input
                        className="robots-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={draft.screenerMaxSpreadPct}
                        onChange={e => patch({ screenerMaxSpreadPct: Number(e.target.value) })}
                    />
                </label>
                <label className="robots-field">
                    <span>Мин. ATR %</span>
                    <input
                        className="robots-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={draft.screenerMinAtrPct}
                        onChange={e => patch({ screenerMinAtrPct: Number(e.target.value) })}
                    />
                </label>
                <label className="robots-field">
                    <span>Мин. цена</span>
                    <input
                        className="robots-input"
                        type="number"
                        min={0}
                        step={crypto ? 0.01 : 1}
                        value={draft.screenerMinPrice}
                        onChange={e => patch({ screenerMinPrice: Number(e.target.value) })}
                    />
                </label>
                <label className="robots-field">
                    <span>Макс. цена</span>
                    <input
                        className="robots-input"
                        type="number"
                        min={0}
                        step={crypto ? 0.01 : 1}
                        value={draft.screenerMaxPrice}
                        onChange={e => patch({ screenerMaxPrice: Number(e.target.value) })}
                    />
                </label>
            </div>
        </div>
    )
}
