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
import type { ConfigValidationIssue as ValidationIssue } from '@/modules/robots/config/validate/collectIssues'

export type CryptoUniverseConfiguratorProps = {
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

/** Единая вкладка: поиск + отбор монет (та же сетка, что у MOEX). */
export function CryptoUniverseConfigurator({
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

    return (
        <div className="robots-universe-tab">
            <p className="form-hint">
                Подбор торгуемых пар ByBit: режим universe, фильтры screening и пересчёт пула{' '}
                <code>allowed_symbols</code>.
            </p>

            <div className="form-row robots-universe-tab__controls">
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
                            options={CRYPTO_UNIVERSE_MODE_OPTIONS.map(o => ({
                                value: o.value,
                                label: o.label,
                            }))}
                            value={cryptoUniverseMode}
                            onChange={v => {
                                onCryptoUniverseModeChange((v as CryptoUniverseMode) || 'auto')
                                dirty()
                            }}
                        />
                    </div>
                </div>
            </div>

            {cryptoUniverseMode === 'fixed' ? (
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
                    <p className="field-hint-below">
                        Через запятую или с новой строки. Screening не используется.
                    </p>
                    {fieldIssues(universeFieldIssues, 'universe').map(issue => (
                        <p key={issue.id} className="field-inline-error">{issue.message}</p>
                    ))}
                </div>
            ) : (
                <>
                    <div className="step-editor-panel__subsection">
                        <h4 className="card__subsection-title">Фильтры screening</h4>
                        <p className="form-hint">Пороги отбора в пул. Пресет можно править и дополнять полями.</p>
                        <CryptoScreeningFormFields
                            filters={cryptoFilters}
                            onFiltersChange={onCryptoFiltersChange}
                            onConfigDirty={onConfigDirty}
                        />
                    </div>

                    <div className="step-editor-panel__subsection">
                        <h4 className="card__subsection-title">Отбор / screening</h4>
                        <p className="form-hint">
                            Пересчёт пула по активным фильтрам. Результат сохраняется в{' '}
                            <code>allowed_symbols</code>.
                        </p>
                        <div className="form-row robots-universe-tab__controls">
                            <div className="form-group">
                                <label className="form-label">Запуск</label>
                                {robotId != null && onRunCryptoScreening ? (
                                    <Button
                                        type="button"
                                        variant="secondary"
                                        disabled={cryptoScreeningLoading}
                                        onClick={onRunCryptoScreening}
                                    >
                                        {cryptoScreeningLoading ? 'Screening…' : 'Запустить crypto-screening'}
                                    </Button>
                                ) : (
                                    <p className="form-hint" style={{ margin: 0 }}>
                                        Сохраните робота, чтобы запустить screening.
                                    </p>
                                )}
                                {screeningPreview && (
                                    <p className="form-hint" style={{ marginTop: 8 }}>
                                        {screeningPreview.scanned > 0 || screeningPreview.accepted > 0 ? (
                                            <>
                                                Принято: {screeningPreview.accepted} / {screeningPreview.scanned}
                                                {screeningPreview.symbols.length > 0 && (
                                                    <>
                                                        {' '}
                                                        · {screeningPreview.symbols.slice(0, 8).join(', ')}
                                                        {screeningPreview.symbols.length > 8 ? '…' : ''}
                                                    </>
                                                )}
                                                {screeningPreview.message ? ` · ${screeningPreview.message}` : ''}
                                            </>
                                        ) : (
                                            screeningPreview.message || 'Ожидание результата…'
                                        )}
                                    </p>
                                )}
                            </div>
                            {allowedSymbols.length > 0 && (
                                <div className="form-group">
                                    <label className="form-label">Текущий пул</label>
                                    <p className="form-readonly-value">
                                        {allowedSymbols.slice(0, 12).join(', ')}
                                        {allowedSymbols.length > 12
                                            ? ` (+${allowedSymbols.length - 12})`
                                            : ''}
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                </>
            )}
        </div>
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
