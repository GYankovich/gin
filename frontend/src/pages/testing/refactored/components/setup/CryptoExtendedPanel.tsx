import React from 'react'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'

export type CryptoExtendedPanelProps = {
    backtestFeeModel: 'maker_taker' | 'taker_only' | 'maker_only'
    onBacktestFeeModelChange: (v: 'maker_taker' | 'taker_only' | 'maker_only') => void
    onConfigDirty: () => void
    className?: string
}

/** Crypto-only: модель комиссий (остальные поля — в блоке риска). */
export function CryptoExtendedPanel({
    backtestFeeModel,
    onBacktestFeeModelChange,
    onConfigDirty,
    className = '',
}: CryptoExtendedPanelProps) {
    const dirty = () => onConfigDirty()

    return (
        <Card className={`mb-6 cyber-form-card testing-cyber-card testing-crypto-extended-panel ${className}`.trim()}>
            <div className="form-group testing-form-group-flat">
                <label className="form-label">Модель комиссий в бэктесте</label>
                <Select
                    value={backtestFeeModel}
                    onChange={v => {
                        onBacktestFeeModelChange(
                            v === 'taker_only' ? 'taker_only' : v === 'maker_only' ? 'maker_only' : 'maker_taker',
                        )
                        dirty()
                    }}
                    options={[
                        { value: 'maker_taker', label: 'Maker + Taker' },
                        { value: 'taker_only', label: 'Только taker' },
                        { value: 'maker_only', label: 'Только maker' },
                    ]}
                />
            </div>
        </Card>
    )
}
