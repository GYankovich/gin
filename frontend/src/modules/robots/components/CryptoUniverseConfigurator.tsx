import React from 'react'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { CryptoScreeningFormFields } from '@/modules/robots/components/CryptoScreeningFormFields'
import {
    cryptoScreeningFiltersFromPreset,
    type CryptoScreeningFilter,
} from '@/pages/testing/cryptoScreeningPipeline'
import { getP1Field } from '@/modules/robots/config/p1ScreeningFields'
import { CRYPTO_UNIVERSE_MODE_OPTIONS, type CryptoUniverseMode } from '@/utils/universeMode'
import type { UniverseFilterPresetId } from '@/modules/robots/config/universeFilterPresets'
import type { ValidationIssue } from '@/modules/robots/config/validate/collectIssues'

export type CryptoUniverseConfiguratorStage = 'p1' | 'p2'

export type CryptoUniverseConfiguratorProps = {
    stage: CryptoUniverseConfiguratorStage
    cryptoUniverseMode: CryptoUniverseMode
    onCryptoUniverseModeChange: (mode: CryptoUniverseMode) => void
    fixedTickersText: string
    onFixedTickersTextChange: (v: string) => void
    cryptoFilters: CryptoScreeningFilter[]
    onCryptoFiltersChange: (filters: CryptoScreeningFilter[]) => void
    robotId?: number
    cryptoScreeningLoading?: boolean
    onRunCryptoScreening?: () => void
    screeningPreview?: { symbols: string[]; accepted: number; scanned: number; message?: string | null } | null
    allowedSymbols?: string[]
    universeFieldIssues?: ValidationIssue[]
    onConfigDirty?: () => void
}

function fieldIssues(issues: ValidationIssue[] | undefined, field: string): ValidationIssue[] {
    return (issues || []).filter(i => i.field === field)
}

export function CryptoUniverseConfigurator({
    stage,
    cryptoUniverseMode,
    onCryptoUniverseModeChange,
    fixedTickersText,
    onFixedTickersTextChange,
    cryptoFilters,
    onCryptoFiltersChange,
    robotId,
    cryptoScreeningLoading = false,
    onRunCryptoScreening,
    screeningPreview,
    allowedSymbols = [],
    universeFieldIssues,
    onConfigDirty,
}: CryptoUniverseConfiguratorProps) {
    const dirty = () => onConfigDirty?.()
    const universeField = getP1Field('universe_mode', 'crypto')

    const universeSelect = (
        <div className="form-group">
            <label className="form-label">
                {universeField?.label ?? 'Режим universe'}
                <FormLabelTooltip
                    text={
                        universeField?.tooltip ??
                        'Авто — отбор по фильтрам. Фиксированный — заданный список символов.'
                    }
                />
            </label>
            <div className="cyber-select-wrap">
                <Select
                    options={CRYPTO_UNIVERSE_MODE_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
                    value={cryptoUniverseMode}
                    onChange={v => {
                        onCryptoUniverseModeChange((v as CryptoUniverseMode) || 'auto')
                        dirty()
                    }}
                />
            </div>
        </div>
    )

    const fixedSymbolsField = (
        <div className="form-group">
            <label className="form-label">Символы ByBit</label>
            <textarea
                className="form-input cyber-input"
                rows={3}
                placeholder="BTCUSDT, ETHUSDT"
                value={fixedTickersText}
                onChange={e => {
                    onFixedTickersTextChange(e.target.value)
                    dirty()
                }}
            />
            <p className="field-hint-below">Через запятую или с новой строки.</p>
            {fieldIssues(universeFieldIssues, 'universe').map(issue => (
                <p key={issue.id} className="field-inline-error">{issue.message}</p>
            ))}
        </div>
    )

    if (stage === 'p1') {
        return (
            <>
                <p className="form-hint">
                    Подбор торгуемых пар ByBit по ликвидности, спреду и funding. Результат — пул символов для стратегии.
                </p>
                {universeSelect}
                {cryptoUniverseMode === 'fixed' ? (
                    fixedSymbolsField
                ) : (
                    <CryptoScreeningFormFields
                        filters={cryptoFilters}
                        onFiltersChange={onCryptoFiltersChange}
                        onConfigDirty={onConfigDirty}
                    />
                )}
            </>
        )
    }

    if (cryptoUniverseMode === 'fixed') {
        return (
            <>
                <p className="form-hint">
                    Фиксированный список символов — crypto-screening не используется.
                </p>
                {universeSelect}
                {fixedSymbolsField}
            </>
        )
    }

    return (
        <>
            <p className="form-hint">
                Пересчёт пула символов по фильтрам этапа «Поиск монет». Результат сохраняется в{' '}
                <code>allowed_symbols</code>.
            </p>
            {universeSelect}
            {robotId != null && onRunCryptoScreening && (
                <div className="form-group">
                    <label className="form-label">Crypto screening</label>
                    <Button
                        type="button"
                        variant="secondary"
                        disabled={cryptoScreeningLoading}
                        onClick={onRunCryptoScreening}
                    >
                        {cryptoScreeningLoading ? 'Screening…' : 'Запустить crypto-screening'}
                    </Button>
                    {screeningPreview && (
                        <p className="form-hint" style={{ marginTop: 8 }}>
                            Принято: {screeningPreview.accepted} / {screeningPreview.scanned}
                            {screeningPreview.symbols.length > 0 && (
                                <>
                                    {' '}
                                    · {screeningPreview.symbols.slice(0, 8).join(', ')}
                                    {screeningPreview.symbols.length > 8 ? '…' : ''}
                                </>
                            )}
                            {screeningPreview.message ? ` · ${screeningPreview.message}` : ''}
                        </p>
                    )}
                </div>
            )}
            {allowedSymbols.length > 0 && (
                <div className="form-group">
                    <label className="form-label">Текущий пул</label>
                    <p className="form-readonly-value">
                        {allowedSymbols.slice(0, 12).join(', ')}
                        {allowedSymbols.length > 12 ? ` (+${allowedSymbols.length - 12})` : ''}
                    </p>
                </div>
            )}
        </>
    )
}

export function applyCryptoUniversePreset(
    presetId: UniverseFilterPresetId,
    onCryptoFiltersChange: (filters: CryptoScreeningFilter[]) => void,
    onConfigDirty?: () => void,
) {
    onCryptoFiltersChange(cryptoScreeningFiltersFromPreset(presetId))
    onConfigDirty?.()
}
