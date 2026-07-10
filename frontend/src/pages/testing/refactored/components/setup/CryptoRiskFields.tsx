import React from 'react'
import { Select } from '@/components/ui/Select'
import {
    FUNDING_MODE_OPTIONS,
    type FundingSimulationMode,
} from '@/pages/testing/executionRiskDefaults'

export type CryptoRiskFieldsProps = {
    bybitTestnet: boolean
    onBybitTestnetChange: (v: boolean) => void
    instrumentCategory: 'spot' | 'linear' | 'inverse'
    onInstrumentCategoryChange: (v: 'spot' | 'linear' | 'inverse') => void
    leverage: number
    makerFeePct: number
    onMakerFeePctChange: (v: number) => void
    takerFeePct: number
    onTakerFeePctChange: (v: number) => void
    fundingMode: FundingSimulationMode
    onFundingModeChange: (v: FundingSimulationMode) => void
    backtestExecution: 'limit_maker' | 'market_taker'
    onBacktestExecutionChange: (v: 'limit_maker' | 'market_taker') => void
    maintenanceMarginPct: number
    onConfigDirty: () => void
}

const CATEGORY_OPTIONS = [
    { value: 'linear', label: 'Linear (USDT perp)' },
    { value: 'inverse', label: 'Inverse' },
    { value: 'spot', label: 'Spot' },
]

/** Поля риска ByBit (блок 4, правая колонка). */
export function CryptoRiskFields({
    bybitTestnet,
    onBybitTestnetChange,
    instrumentCategory,
    onInstrumentCategoryChange,
    leverage,
    makerFeePct,
    onMakerFeePctChange,
    takerFeePct,
    onTakerFeePctChange,
    fundingMode,
    onFundingModeChange,
    backtestExecution,
    onBacktestExecutionChange,
    maintenanceMarginPct,
    onConfigDirty,
}: CryptoRiskFieldsProps) {
    const dirty = () => onConfigDirty()

    return (
        <>
            <div className="form-group">
                <label className="form-label">Maker fee (%)</label>
                <input
                    className="form-input"
                    type="number"
                    step="0.001"
                    value={makerFeePct}
                    onChange={e => {
                        onMakerFeePctChange(Number(e.target.value) || 0)
                        dirty()
                    }}
                />
            </div>
            <div className="form-group">
                <label className="form-label">Taker fee (%)</label>
                <input
                    className="form-input"
                    type="number"
                    step="0.001"
                    value={takerFeePct}
                    onChange={e => {
                        onTakerFeePctChange(Number(e.target.value) || 0)
                        dirty()
                    }}
                />
            </div>
            <div className="form-group">
                <label className="form-label">Плечо</label>
                <input className="form-input" type="number" value={leverage} readOnly disabled aria-readonly />
            </div>
            <div className="form-group">
                <label className="form-label">Maintenance margin (%)</label>
                <input
                    className="form-input"
                    type="number"
                    value={maintenanceMarginPct}
                    readOnly
                    disabled
                    aria-readonly
                />
            </div>
            <div className="form-group">
                <label className="form-label">Среда ByBit</label>
                <input className="form-input" value="Mainnet" readOnly disabled aria-readonly />
            </div>
            <div className="form-group">
                <label className="form-label">Категория инструмента</label>
                <Select
                    options={CATEGORY_OPTIONS}
                    value={instrumentCategory}
                    onChange={v => {
                        onInstrumentCategoryChange(v as 'spot' | 'linear' | 'inverse')
                        dirty()
                    }}
                />
            </div>
            <div className="form-group">
                <label className="form-label">Исполнение в бэктесте</label>
                <Select
                    value={backtestExecution}
                    onChange={v => {
                        onBacktestExecutionChange(v === 'limit_maker' ? 'limit_maker' : 'market_taker')
                        dirty()
                    }}
                    options={[
                        { value: 'market_taker', label: 'Market (taker fee)' },
                        { value: 'limit_maker', label: 'Limit (maker fee)' },
                    ]}
                />
            </div>
            <div className="form-group">
                <label className="form-label">Режим фандинга</label>
                <Select
                    searchable={false}
                    value={fundingMode}
                    onChange={v => {
                        const mode = String(v || 'historical') as FundingSimulationMode
                        onFundingModeChange(
                            mode === 'off' || mode === 'forecast' || mode === 'average'
                                ? mode
                                : 'historical',
                        )
                        dirty()
                    }}
                    options={FUNDING_MODE_OPTIONS}
                />
            </div>
        </>
    )
}
