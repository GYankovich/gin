import React from 'react'
import {
    isCryptoInstrument,
    type RobotV2WizardDraft,
} from '@/pages/robots-v2/wizardDraft'

type Props = {
    draft: RobotV2WizardDraft
    patch: (partial: Partial<RobotV2WizardDraft>) => void
}

export function ScreenerCustomFilters({ draft, patch }: Props) {
    const crypto = isCryptoInstrument(draft.instrumentType)
    return (
        <div className="robots-v2-screener-custom">
            <p className="robots-v2-hint robots-v2-screener-custom__hint">
                Ручная настройка фильтров скринера. Ноль — не применять условие.
            </p>
            <div className="robots-v2-grid robots-v2-grid--2">
                <label className="robots-v2-field">
                    <span>{crypto ? 'Мин. объём 24ч, $' : 'Мин. объём'}</span>
                    <input
                        className="robots-v2-input"
                        type="number"
                        min={0}
                        step={crypto ? 100_000 : 1_000_000}
                        value={draft.screenerMinVolume}
                        onChange={e => patch({ screenerMinVolume: Number(e.target.value) })}
                    />
                </label>
                {!crypto && (
                    <label className="robots-v2-field">
                        <span>Мин. ср. объём (20д)</span>
                        <input
                            className="robots-v2-input"
                            type="number"
                            min={0}
                            step={1_000_000}
                            value={draft.screenerMinHistVolume}
                            onChange={e => patch({ screenerMinHistVolume: Number(e.target.value) })}
                        />
                    </label>
                )}
                <label className="robots-v2-field">
                    <span>Макс. спред %</span>
                    <input
                        className="robots-v2-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={draft.screenerMaxSpreadPct}
                        onChange={e => patch({ screenerMaxSpreadPct: Number(e.target.value) })}
                    />
                </label>
                <label className="robots-v2-field">
                    <span>Мин. ATR %</span>
                    <input
                        className="robots-v2-input"
                        type="number"
                        min={0}
                        step={0.1}
                        value={draft.screenerMinAtrPct}
                        onChange={e => patch({ screenerMinAtrPct: Number(e.target.value) })}
                    />
                </label>
                <label className="robots-v2-field">
                    <span>Мин. цена</span>
                    <input
                        className="robots-v2-input"
                        type="number"
                        min={0}
                        step={crypto ? 0.01 : 1}
                        value={draft.screenerMinPrice}
                        onChange={e => patch({ screenerMinPrice: Number(e.target.value) })}
                    />
                </label>
                <label className="robots-v2-field">
                    <span>Макс. цена</span>
                    <input
                        className="robots-v2-input"
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
