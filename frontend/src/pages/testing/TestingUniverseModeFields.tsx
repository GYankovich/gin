import React from 'react'
import { Select } from '@/components/ui/Select'
import {
    CRYPTO_UNIVERSE_MODE_OPTIONS,
    UNIVERSE_MODE_OPTIONS,
    normalizeCryptoUniverseMode,
    normalizeUniverseMode,
    type CryptoUniverseMode,
    type UniverseMode,
} from '@/utils/universeMode'

export type UniverseModeToggleProps = {
    isCrypto?: boolean
    universeMode?: UniverseMode
    onUniverseModeChange?: (mode: UniverseMode) => void
    cryptoUniverseMode?: CryptoUniverseMode
    onCryptoUniverseModeChange?: (mode: CryptoUniverseMode) => void
    onConfigDirty: () => void
    useToggleUI?: boolean
    compact?: boolean
    className?: string
}

export function UniverseModeToggle({
    universeMode = 'dms_pipeline',
    onUniverseModeChange,
    onConfigDirty,
    isCrypto = false,
    cryptoUniverseMode = 'auto',
    onCryptoUniverseModeChange,
    className = '',
    useToggleUI = true,
    compact = false,
}: UniverseModeToggleProps) {
    const dirty = () => onConfigDirty()
    const modeOptions = isCrypto ? CRYPTO_UNIVERSE_MODE_OPTIONS : UNIVERSE_MODE_OPTIONS
    const activeCryptoMode = normalizeCryptoUniverseMode(cryptoUniverseMode)
    const activeMoexMode = normalizeUniverseMode(universeMode)
    const isFixed = isCrypto ? activeCryptoMode === 'fixed' : activeMoexMode === 'fixed'

    const setScreeningMode = () => {
        if (isCrypto) {
            onCryptoUniverseModeChange?.('auto')
        } else {
            onUniverseModeChange?.('dms_pipeline')
        }
        dirty()
    }

    const setFixedMode = () => {
        if (isCrypto) {
            onCryptoUniverseModeChange?.('fixed')
        } else {
            onUniverseModeChange?.('fixed')
        }
        dirty()
    }

    if (useToggleUI) {
        return (
            <div
                className={`testing-universe-mode-toggle${compact ? ' testing-universe-mode-toggle--compact' : ''} ${className}`.trim()}
                role="radiogroup"
                aria-label="Режим отбора инструментов"
            >
                <button
                    type="button"
                    role="radio"
                    aria-checked={isFixed}
                    className={`testing-universe-mode-toggle__option${isFixed ? ' testing-universe-mode-toggle__option--selected' : ''}`}
                    onClick={() => {
                        if (!isFixed) setFixedMode()
                    }}
                >
                    {compact ? 'Список' : 'Фиксированный'}
                </button>
                <button
                    type="button"
                    role="radio"
                    aria-checked={!isFixed}
                    className={`testing-universe-mode-toggle__option${!isFixed ? ' testing-universe-mode-toggle__option--selected' : ''}`}
                    onClick={() => {
                        if (isFixed) setScreeningMode()
                    }}
                >
                    {compact ? 'Скрининг' : 'DailyMarketScanner'}
                </button>
            </div>
        )
    }

    return (
        <div className={`cyber-select-wrap ${className}`.trim()}>
            <Select
                options={modeOptions.map(o => ({ value: o.value, label: o.label }))}
                value={isCrypto ? activeCryptoMode : universeMode}
                onChange={v => {
                    if (isCrypto) {
                        onCryptoUniverseModeChange?.(normalizeCryptoUniverseMode(v))
                    } else {
                        onUniverseModeChange?.(normalizeUniverseMode(v))
                    }
                    dirty()
                }}
            />
        </div>
    )
}

export type FixedTickersFieldProps = {
    isCrypto?: boolean
    fixedTickersText: string
    onFixedTickersTextChange: (text: string) => void
    onConfigDirty: () => void
    compact?: boolean
    className?: string
}

export function FixedTickersField({
    isCrypto = false,
    fixedTickersText,
    onFixedTickersTextChange,
    onConfigDirty,
    compact = false,
    className = '',
}: FixedTickersFieldProps) {
    const tickers = fixedTickersText
        .split(/[,;\s]+/)
        .map(t => t.trim())
        .filter(Boolean)
    const preview = tickers.slice(0, 6)
    const rest = tickers.length - preview.length

    return (
        <div className={`screening-tickers-field${compact ? ' screening-tickers-field--compact' : ''} ${className}`.trim()}>
            <div className="screening-tickers-field__head">
                <label className="screening-tickers-field__label">
                    {isCrypto ? 'Символы ByBit' : 'Тикеры MOEX'}
                </label>
                {tickers.length > 0 && (
                    <span className="badge badge--neutral screening-tickers-field__count">{tickers.length}</span>
                )}
            </div>
            {compact ? (
                <>
                    <input
                        className="form-input cyber-input screening-tickers-field__input"
                        type="text"
                        placeholder={isCrypto ? 'BTCUSDT, ETHUSDT, SOLUSDT' : 'SBER, GAZP, LKOH'}
                        value={fixedTickersText}
                        onChange={e => {
                            onFixedTickersTextChange(e.target.value)
                            onConfigDirty()
                        }}
                    />
                    {preview.length > 0 && (
                        <div className="screening-tickers-field__chips">
                            {preview.map(t => (
                                <span key={t} className="screening-tickers-field__chip">
                                    {t}
                                </span>
                            ))}
                            {rest > 0 && (
                                <span className="screening-tickers-field__chip screening-tickers-field__chip--more">
                                    +{rest}
                                </span>
                            )}
                        </div>
                    )}
                </>
            ) : (
                <textarea
                    className="form-input cyber-input"
                    rows={3}
                    placeholder={isCrypto ? 'BTCUSDT, ETHUSDT' : 'SBER, GAZP, LKOH'}
                    value={fixedTickersText}
                    onChange={e => {
                        onFixedTickersTextChange(e.target.value)
                        onConfigDirty()
                    }}
                />
            )}
        </div>
    )
}

export type TestingUniverseModeFieldsProps = UniverseModeToggleProps &
    FixedTickersFieldProps & {
        className?: string
    }

/** Universe: фиксированный список или DailyMarketScanner (legacy wrapper). */
export function TestingUniverseModeFields({
    fixedTickersText,
    onFixedTickersTextChange,
    className = '',
    ...toggleProps
}: TestingUniverseModeFieldsProps) {
    const isCrypto = toggleProps.isCrypto ?? false
    const universeMode = toggleProps.universeMode ?? 'dms_pipeline'
    const cryptoUniverseMode = toggleProps.cryptoUniverseMode ?? 'auto'
    const isFixed = isCrypto
        ? normalizeCryptoUniverseMode(cryptoUniverseMode) === 'fixed'
        : normalizeUniverseMode(universeMode) === 'fixed'

    return (
        <div className={`testing-universe-mode-fields ${className}`.trim()}>
            <div className="form-group">
                <UniverseModeToggle {...toggleProps} />
            </div>
            {isFixed && (
                <FixedTickersField
                    isCrypto={isCrypto}
                    fixedTickersText={fixedTickersText}
                    onFixedTickersTextChange={onFixedTickersTextChange}
                    onConfigDirty={toggleProps.onConfigDirty}
                />
            )}
        </div>
    )
}
