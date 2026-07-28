import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { FixedTickersField, UniverseModeToggle } from '@/pages/testing/TestingUniverseModeFields'
import {
    TestingPipelineCard,
    type TestingPipelineCardProps,
} from '@/pages/testing/TestingPipelineCard'
import {
    TestingCryptoPipelineCard,
    type TestingCryptoPipelineCardProps,
} from '@/pages/testing/TestingCryptoPipelineCard'
import type { CryptoUniverseMode, UniverseMode } from '@/utils/universeMode'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'
import {
    getCryptoPipelineMissingFilterLabels,
    getMoexPipelineMissingFilterLabels,
} from '@/pages/testing/universeScreeningMissing'
import type { PipelineFilter } from '@/pages/testing/testingPipeline'

export type UniverseScreeningPanelProps = {
    market: TestingMarket
    filters: PipelineFilter[]
    universeMode: UniverseMode
    onUniverseModeChange: (mode: UniverseMode) => void
    cryptoUniverseMode: CryptoUniverseMode
    onCryptoUniverseModeChange: (mode: CryptoUniverseMode) => void
    fixedTickersText: string
    onFixedTickersTextChange: (text: string) => void
    universeRefreshMinutes?: number
    onUniverseRefreshMinutesChange?: (v: number) => void
    onConfigDirty: () => void
    pipeline?: TestingPipelineCardProps | null
    cryptoPipeline?: TestingCryptoPipelineCardProps | null
}

/** Компактный блок отбора инструментов: режим, пресеты, плитки фильтров. */
export function UniverseScreeningPanel({
    market,
    universeMode,
    onUniverseModeChange,
    cryptoUniverseMode,
    onCryptoUniverseModeChange,
    fixedTickersText,
    onFixedTickersTextChange,
    universeRefreshMinutes = 0,
    onUniverseRefreshMinutesChange,
    onConfigDirty,
    pipeline,
    cryptoPipeline,
    filters,
}: UniverseScreeningPanelProps) {
    const isCrypto = market === 'crypto'
    const isFixed = isCrypto ? cryptoUniverseMode === 'fixed' : universeMode === 'fixed'
    const isScreening = !isFixed

    const missingChips = isCrypto
        ? isScreening && cryptoPipeline
            ? getCryptoPipelineMissingFilterLabels(cryptoPipeline.filters)
            : []
        : isScreening
          ? getMoexPipelineMissingFilterLabels(filters)
          : []

    const activeFilterCount = useMemo(() => {
        if (isCrypto && cryptoPipeline) return cryptoPipeline.filters.length
        if (!isCrypto) return filters.length
        return 0
    }, [isCrypto, cryptoPipeline, filters])

    const modeDescription = isFixed
        ? isCrypto
            ? 'Фиксированный список символов ByBit'
            : 'Фиксированный список тикеров MOEX'
        : isCrypto
          ? 'DailyMarketScanner — фильтры на каждый торговый день'
          : 'DMS pipeline — отбор бумаг по условиям на каждый день'

    return (
        <Card className="mb-4 cyber-form-card testing-cyber-card testing-universe-screening-panel">
            <div className="screening-panel__head">
                <div className="screening-panel__title-row">
                    <h3 className="screening-panel__title">
                        <span className="cyber-bracket">[</span>
                        {isCrypto ? 'ОТБОР МОНЕТ' : 'ОТБОР БУМАГ'}
                        <span className="cyber-bracket">]</span>
                    </h3>
                    <UniverseModeToggle
                        isCrypto={isCrypto}
                        universeMode={universeMode}
                        onUniverseModeChange={onUniverseModeChange}
                        cryptoUniverseMode={cryptoUniverseMode}
                        onCryptoUniverseModeChange={onCryptoUniverseModeChange}
                        onConfigDirty={onConfigDirty}
                        useToggleUI
                        compact
                    />
                </div>
                <div className="screening-panel__meta">
                    <span className="screening-panel__desc">{modeDescription}</span>
                    {isScreening && activeFilterCount > 0 && (
                        <span className="badge badge--neutral screening-panel__count">{activeFilterCount} фильтр.</span>
                    )}
                    {missingChips.length > 0 && (
                        <div className="screening-panel__missing" role="status">
                            <span className="screening-panel__missing-label">Не задано</span>
                            {missingChips.map(label => (
                                <span key={label} className="badge badge--warn screening-panel__missing-chip">
                                    {label}
                                </span>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            <div className="screening-panel__body">
                {isFixed && (
                    <FixedTickersField
                        isCrypto={isCrypto}
                        fixedTickersText={fixedTickersText}
                        onFixedTickersTextChange={onFixedTickersTextChange}
                        onConfigDirty={onConfigDirty}
                        compact
                    />
                )}

                {isScreening && (
                    <>
                        {isCrypto && cryptoPipeline && (
                            <TestingCryptoPipelineCard {...cryptoPipeline} embedded compact />
                        )}
                        {!isCrypto && pipeline && (
                            <TestingPipelineCard
                                {...pipeline}
                                embedded
                                compact
                                universeRefreshMinutes={universeRefreshMinutes}
                                onUniverseRefreshMinutesChange={onUniverseRefreshMinutesChange}
                            />
                        )}
                    </>
                )}
            </div>
        </Card>
    )
}
