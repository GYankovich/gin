import React, { useEffect } from 'react'
import { Select } from '@/components/ui/Select'
import { bybitService } from '@/services/bybitService'
import { parseFixedTickersInput } from '@/utils/universeMode'

const CATEGORY_OPTIONS = [
    { value: 'linear', label: 'Linear (USDT perp)' },
    { value: 'inverse', label: 'Inverse' },
    { value: 'spot', label: 'Spot' },
]

export type CryptoBrokerConfiguratorProps = {
    instrumentCategory: 'spot' | 'linear' | 'inverse'
    onInstrumentCategoryChange: (v: 'spot' | 'linear' | 'inverse') => void
    leverage: number
    onLeverageChange: (v: number) => void
    fixedTickersText: string
    bybitTestnet?: boolean
    onBybitTestnetChange?: (v: boolean) => void
    onConfigDirty?: () => void
    /** Заблокировать плечо на 1× (live без маржи). */
    leverageLocked?: boolean
}

/** Брокер-специфичные настройки ByBit (категория, плечо) — шаг «Торговая логика». */
export function CryptoBrokerConfigurator({
    instrumentCategory,
    onInstrumentCategoryChange,
    leverage,
    onLeverageChange,
    fixedTickersText,
    bybitTestnet = false,
    onBybitTestnetChange,
    onConfigDirty,
    leverageLocked = false,
}: CryptoBrokerConfiguratorProps) {
    const dirty = () => onConfigDirty?.()
    const [instrumentSymbols, setInstrumentSymbols] = React.useState<string[]>([])

    useEffect(() => {
        if (leverageLocked && leverage !== 0) {
            onLeverageChange(0)
        }
    }, [leverageLocked, leverage, onLeverageChange])

    useEffect(() => {
        let cancelled = false
        void bybitService
            .getInstruments({
                category: instrumentCategory,
                quote_coin: 'USDT',
                testnet: bybitTestnet,
            })
            .then(res => {
                if (cancelled) return
                setInstrumentSymbols(res.items.map(i => i.symbol).slice(0, 500))
            })
            .catch(() => {
                if (!cancelled) setInstrumentSymbols([])
            })
        return () => {
            cancelled = true
        }
    }, [instrumentCategory, bybitTestnet])

    void parseFixedTickersInput(fixedTickersText)

    return (
        <>
            <p className="form-hint">
                Категория инструмента и плечо. Комиссии и funding — на шаге «Риск-менеджмент».
            </p>
            <div className="testing-robot-grid">
                {onBybitTestnetChange && (
                    <div className="form-group">
                        <label className="form-label">Среда ByBit</label>
                        <Select
                            options={[
                                { value: 'false', label: 'Mainnet' },
                                { value: 'true', label: 'Testnet' },
                            ]}
                            value={bybitTestnet ? 'true' : 'false'}
                            onChange={v => {
                                onBybitTestnetChange(v === 'true')
                                dirty()
                            }}
                        />
                    </div>
                )}
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
                    <label className="form-label">Плечо</label>
                    <input
                        className="form-input cyber-input"
                        type="number"
                        min={0}
                        max={125}
                        value={leverageLocked ? 0 : leverage}
                        readOnly={leverageLocked}
                        disabled={leverageLocked}
                        aria-readonly={leverageLocked}
                        onChange={e => {
                            if (leverageLocked) return
                            onLeverageChange(Math.max(0, Number(e.target.value) || 0))
                            dirty()
                        }}
                    />
                    {leverageLocked && (
                        <p className="form-hint">0 — без маржинальной торговли</p>
                    )}
                    {!leverageLocked && (
                        <p className="form-hint">0 = без маржи; ≥1 = плечо на ByBit</p>
                    )}
                </div>
            </div>
            {instrumentSymbols.length > 0 && (
                <datalist id="bybit-symbol-suggestions">
                    {instrumentSymbols.map(sym => (
                        <option key={sym} value={sym} />
                    ))}
                </datalist>
            )}
        </>
    )
}

/** @deprecated Используйте CryptoBrokerConfigurator + CryptoCostsCard + CryptoUniverseConfigurator */
export type CryptoConfiguratorProps = CryptoBrokerConfiguratorProps

/** @deprecated Используйте CryptoBrokerConfigurator */
export function CryptoConfigurator(props: CryptoBrokerConfiguratorProps) {
    return <CryptoBrokerConfigurator {...props} />
}
