import React from 'react'
import { brokerTypeLabel } from '@/modules/robots/config/brokerImmutability'
import type { BybitAccountType } from '@/modules/robots/config/builders/buildPortfolioConfig'
import { isCryptoBroker } from '@/modules/robots/config/builders/buildCryptoConfig'
import { Select } from '@/components/ui/Select'

const ACCOUNT_TYPE_OPTIONS: Array<{ value: BybitAccountType; label: string }> = [
    { value: 'UNIFIED', label: 'Unified (рекомендуется)' },
    { value: 'CONTRACT', label: 'Contract (деривативы)' },
    { value: 'SPOT', label: 'Spot' },
]

export type PortfolioConfiguratorProps = {
    brokerType: string
    bybitTestnet: boolean
    onBybitTestnetChange: (v: boolean) => void
    bybitAccountType: BybitAccountType
    onBybitAccountTypeChange: (v: BybitAccountType) => void
    onConfigDirty?: () => void
    embedded?: boolean
}

export function PortfolioConfigurator({
    brokerType,
    bybitTestnet,
    onBybitTestnetChange,
    bybitAccountType,
    onBybitAccountTypeChange,
    onConfigDirty,
    embedded = false,
}: PortfolioConfiguratorProps) {
    const dirty = () => onConfigDirty?.()
    const isBybit = isCryptoBroker(brokerType)

    return (
        <div className={embedded ? undefined : 'step-editor-panel__subsection'}>
            {!embedded && (
                <h3 className="card__section-title pipeline-title">
                    <span className="cyber-bracket">[</span>
                    PORTFOLIO UPDATER
                    <span className="cyber-bracket">]</span>
                </h3>
            )}
            <p className="form-hint">
                Синхронизация портфеля брокера по расписанию. Торговая логика (П1/П2/П3) и backtest не используются.
            </p>
            <div className="testing-robot-grid">
                <div className="form-group">
                    <label className="form-label">Брокер</label>
                    <div className="form-readonly-value">{brokerTypeLabel(brokerType)}</div>
                </div>
            </div>
            {!isBybit && (
                <p className="form-hint">
                    T-Invest: периодическая загрузка счетов и позиций в аналитику портфеля (MOEX).
                </p>
            )}
            {isBybit && (
                <div className="testing-robot-grid">
                    <div className="form-group">
                        <label className="form-label">Среда</label>
                        <Select
                            options={[
                                { value: 'true', label: 'Testnet' },
                                { value: 'false', label: 'Mainnet' },
                            ]}
                            value={bybitTestnet ? 'true' : 'false'}
                            onChange={v => {
                                onBybitTestnetChange(v === 'true')
                                dirty()
                            }}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Тип аккаунта ByBit</label>
                        <Select
                            options={ACCOUNT_TYPE_OPTIONS}
                            value={bybitAccountType}
                            onChange={v => {
                                onBybitAccountTypeChange((v as BybitAccountType) || 'UNIFIED')
                                dirty()
                            }}
                        />
                    </div>
                </div>
            )}
        </div>
    )
}
