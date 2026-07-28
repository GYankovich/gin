import React, { useEffect, useMemo, useState } from 'react'
import { Select } from '@/components/ui/Select'
import { bybitService } from '@/services/bybitService'
import { parseFixedTickersInput } from '@/utils/universeMode'
import { fmtErr } from '@/pages/testing/testingUtils'
import {
    FUNDING_MODE_OPTIONS,
    type FundingSimulationMode,
} from '@/pages/testing/executionRiskDefaults'

export type CryptoCostsCardProps = {
    instrumentCategory: 'spot' | 'linear' | 'inverse'
    fixedTickersText: string
    bybitTestnet?: boolean
    makerFeePct: number
    onMakerFeePctChange: (v: number) => void
    takerFeePct: number
    onTakerFeePctChange: (v: number) => void
    fundingMode: FundingSimulationMode
    onFundingModeChange: (v: FundingSimulationMode) => void
    backtestExecution: 'limit_maker' | 'market_taker'
    onBacktestExecutionChange: (v: 'limit_maker' | 'market_taker') => void
    backtestFeeModel: 'maker_taker' | 'taker_only' | 'maker_only'
    onBacktestFeeModelChange: (v: 'maker_taker' | 'taker_only' | 'maker_only') => void
    onConfigDirty?: () => void
    embedded?: boolean
    className?: string
}

/** Комиссии, funding и модель исполнения для crypto-робота (шаг «Риск»). */
export function CryptoCostsCard({
    instrumentCategory,
    fixedTickersText,
    bybitTestnet = false,
    makerFeePct,
    onMakerFeePctChange,
    takerFeePct,
    onTakerFeePctChange,
    fundingMode,
    onFundingModeChange,
    backtestExecution,
    onBacktestExecutionChange,
    backtestFeeModel,
    onBacktestFeeModelChange,
    onConfigDirty,
    embedded = true,
    className = 'cyber-form-card',
}: CryptoCostsCardProps) {
    const dirty = () => onConfigDirty?.()
    const previewSymbol = useMemo(
        () => parseFixedTickersInput(fixedTickersText)[0] ?? 'BTCUSDT',
        [fixedTickersText],
    )
    const [fundingPreview, setFundingPreview] = useState<string | null>(null)
    const [fundingError, setFundingError] = useState<string | null>(null)

    useEffect(() => {
        if (instrumentCategory === 'spot' || fundingMode === 'off') {
            setFundingPreview('Funding не применяется (spot или выключен)')
            setFundingError(null)
            return
        }
        let cancelled = false
        setFundingPreview('Загрузка…')
        setFundingError(null)
        void bybitService
            .getFundingRate({
                symbol: previewSymbol,
                instrument_category: instrumentCategory,
                testnet: bybitTestnet,
            })
            .then(row => {
                if (cancelled) return
                const pct = (row.funding_rate * 100).toFixed(4)
                const next = row.next_funding_time
                    ? new Date(row.next_funding_time).toLocaleString('ru-RU', { timeZone: 'UTC' }) + ' UTC'
                    : '—'
                setFundingPreview(`Текущий rate: ${pct}% · следующий funding: ${next}`)
            })
            .catch(err => {
                if (cancelled) return
                setFundingPreview(null)
                setFundingError(fmtErr(err))
            })
        return () => {
            cancelled = true
        }
    }, [previewSymbol, instrumentCategory, fundingMode, bybitTestnet])

    const body = (
        <>
            <p className="form-hint">Комиссии ByBit и funding для бэктеста. НДФЛ не применяется.</p>
            <div className="testing-risk-two-cols">
                <div className="form-group">
                    <label className="form-label">Maker fee (%)</label>
                    <input
                        className="form-input cyber-input"
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
                        className="form-input cyber-input"
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
                    <label className="form-label">Funding в симуляции</label>
                    <Select
                        value={fundingMode}
                        onChange={v => {
                            onFundingModeChange(v as FundingSimulationMode)
                            dirty()
                        }}
                        options={FUNDING_MODE_OPTIONS}
                    />
                    {fundingPreview && <p className="form-hint">{fundingPreview}</p>}
                    {fundingError && <p className="form-hint testing-rec-error">{fundingError}</p>}
                </div>
                <div className="form-group">
                    <label className="form-label">Исполнение в бэктесте</label>
                    <Select
                        value={backtestExecution}
                        onChange={v => {
                            onBacktestExecutionChange(v as 'limit_maker' | 'market_taker')
                            dirty()
                        }}
                        options={[
                            { value: 'market_taker', label: 'Market (taker fee)' },
                            { value: 'limit_maker', label: 'Limit (maker fee)' },
                        ]}
                    />
                </div>
                <div className="form-group">
                    <label className="form-label">Модель комиссии (override)</label>
                    <Select
                        value={backtestFeeModel}
                        onChange={v => {
                            onBacktestFeeModelChange(
                                v as 'maker_taker' | 'taker_only' | 'maker_only',
                            )
                            dirty()
                        }}
                        options={[
                            { value: 'maker_taker', label: 'Maker/Taker по типу ордера' },
                            { value: 'taker_only', label: 'Только taker' },
                            { value: 'maker_only', label: 'Только maker' },
                        ]}
                    />
                </div>
            </div>
        </>
    )

    if (embedded) {
        return <div className={className}>{body}</div>
    }
    return body
}
