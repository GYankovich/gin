import React, { useMemo } from 'react'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { Toggle } from '@/components/ui/Toggle'
import {
    GRAIN_SEED_TRADING_PRESET_META,
    GRAIN_SEED_TRADING_PRESET_ORDER,
    applyGrainSeedTradingPreset,
    detectGrainSeedTradingPreset,
    getStrategyFieldsForUi,
    getStrategyMeta,
    groupStrategyFields,
    type GrainSeedTradingPresetId,
    type StrategyParamField,
} from '@/pages/testing/strategyPresets'
import { normalizeStrategyInterval } from '@/pages/testing/strategyIntervals'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'

export type TestingStrategyParamsCardProps = {
    strategy: string
    params: Record<string, unknown>
    onParamChange: (key: string, value: unknown) => void
    /** Массовый патч (пресеты торговой логики). Если нет — применяется через onParamChange. */
    onParamsPatch?: (patch: Record<string, unknown>) => void
    onConfigDirty?: () => void
    /** MOEX vs Crypto — label, options и нормализация interval. */
    market?: TestingMarket
    className?: string
    sectionTitle?: string
    sectionHint?: string
    /** Без обёртки Card — вложить в секцию настроек робота. */
    embedded?: boolean
    /** Скрыть поля (для grain_seed — перенесены в П1/П2/риск). */
    excludeFieldKeys?: readonly string[]
    /** Группировать поля по секциям (свечи / фильтры / индикаторы). */
    grouped?: boolean
    /** Показать кнопки пресетов grain_seed (по умолчанию — для crypto). */
    showTradingPresets?: boolean
}

/**
 * Динамическая форма параметров выбранной стратегии (BRD-ARCH-03 §6).
 * Метаданные полей — из `strategyPresets.ts`. Поля рендерятся
 * в зависимости от `kind` (number/integer/boolean/enum/string).
 */
export function TestingStrategyParamsCard({
    strategy,
    params,
    onParamChange,
    onParamsPatch,
    onConfigDirty,
    market = 'moex',
    className = 'mb-6 cyber-form-card testing-cyber-card',
    sectionTitle,
    sectionHint,
    embedded = false,
    excludeFieldKeys,
    grouped = false,
    showTradingPresets,
}: TestingStrategyParamsCardProps) {
    const meta = getStrategyMeta(strategy)
    const fields = getStrategyFieldsForUi(strategy, { excludeKeys: excludeFieldKeys, market })
    const tradingPresetsVisible =
        showTradingPresets ?? (strategy === 'grain_seed' && market === 'crypto')
    const activeTradingPreset = useMemo(
        () => (strategy === 'grain_seed' ? detectGrainSeedTradingPreset(params) : null),
        [strategy, params],
    )
    const update = (key: string, value: unknown) => {
        if (key === 'interval' && typeof value === 'string') {
            onParamChange(key, normalizeStrategyInterval(value, market))
        } else {
            onParamChange(key, value)
        }
        onConfigDirty?.()
    }
    const applyTradingPreset = (presetId: GrainSeedTradingPresetId) => {
        const next = applyGrainSeedTradingPreset(params, presetId)
        if (onParamsPatch) {
            onParamsPatch(next)
        } else {
            for (const [key, value] of Object.entries(next)) {
                if (params[key] !== value) onParamChange(key, value)
            }
        }
        onConfigDirty?.()
    }
    const title = sectionTitle ?? 'ПАРАМЕТРЫ СТРАТЕГИИ'
    const hint = sectionHint ?? `${meta.title}: ${meta.description}`
    const fieldGrid = grouped ? (
        <div className="strategy-params-groups">
            {groupStrategyFields(fields).map(section => (
                <section key={section.id} className="strategy-params-group">
                    {section.label ? <h5 className="strategy-params-group__title">{section.label}</h5> : null}
                    <div className="testing-robot-grid">
                        {section.fields.map(field => (
                            <StrategyParamField
                                key={field.key}
                                field={field}
                                value={params[field.key]}
                                onChange={value => update(field.key, value)}
                            />
                        ))}
                    </div>
                </section>
            ))}
        </div>
    ) : (
        <div className="testing-robot-grid">
            {fields.map(field => (
                <StrategyParamField
                    key={field.key}
                    field={field}
                    value={params[field.key]}
                    onChange={value => update(field.key, value)}
                />
            ))}
        </div>
    )
    const body = (
        <>
            {!embedded && (
                <h3 className="card__section-title pipeline-title">
                    <span className="cyber-bracket">[</span>
                    {title}
                    <span className="cyber-bracket">]</span>
                </h3>
            )}
            {embedded && sectionTitle && <h4 className="card__subsection-title">{sectionTitle}</h4>}
            {hint && (
                <p className="form-hint" style={{ marginTop: embedded ? 0 : undefined }}>
                    {hint}
                </p>
            )}
            {tradingPresetsVisible && (
                <div className="pipeline-presets-row" style={{ marginBottom: 12 }}>
                    <span className="pipeline-presets-row__label">Пресет логики</span>
                    <div className="preset-buttons">
                        {GRAIN_SEED_TRADING_PRESET_ORDER.map(id => {
                            const pMeta = GRAIN_SEED_TRADING_PRESET_META[id]
                            return (
                                <Button
                                    key={id}
                                    size="sm"
                                    variant={activeTradingPreset === id ? 'primary' : 'ghost'}
                                    title={pMeta.hint}
                                    onClick={() => applyTradingPreset(id)}
                                >
                                    {pMeta.label}
                                </Button>
                            )
                        })}
                    </div>
                    {activeTradingPreset && (
                        <p className="form-hint" style={{ margin: 0 }}>
                            {GRAIN_SEED_TRADING_PRESET_META[activeTradingPreset].hint}
                        </p>
                    )}
                </div>
            )}
            {fieldGrid}
        </>
    )
    if (embedded) {
        return <div className={className}>{body}</div>
    }
    return <Card className={className}>{body}</Card>
}

function StrategyParamField({
    field,
    value,
    onChange,
}: {
    field: StrategyParamField
    value: unknown
    onChange: (next: unknown) => void
}) {
    if (field.kind === 'boolean') {
        const checked = Boolean(value)
        return (
            <div className="form-group testing-form-group-flat">
                <label className="form-label">{field.label}</label>
                <Toggle
                    checked={checked}
                    onChange={onChange}
                    label={checked ? 'Включено' : 'Выключено'}
                />
                {field.description && <p className="form-hint">{field.description}</p>}
            </div>
        )
    }

    if (field.kind === 'enum') {
        const v = String(value ?? field.options[0]?.value ?? '')
        return (
            <div className="form-group testing-form-group-flat">
                <label className="form-label">{field.label}</label>
                <Select
                    options={field.options}
                    value={v}
                    onChange={next => onChange(String(next))}
                />
                {field.description && <p className="form-hint">{field.description}</p>}
            </div>
        )
    }

    if (field.kind === 'string') {
        return (
            <div className="form-group testing-form-group-flat">
                <label className="form-label">{field.label}</label>
                <input
                    className="form-input"
                    type="text"
                    value={String(value ?? '')}
                    onChange={e => onChange(e.target.value)}
                />
                {field.description && <p className="form-hint">{field.description}</p>}
            </div>
        )
    }

    const isInt = field.kind === 'integer'
    const num = typeof value === 'number' ? value : Number(value ?? 0)
    return (
        <div className="form-group testing-form-group-flat">
            <label className="form-label">{field.label}</label>
            <input
                className="form-input"
                type="number"
                min={field.min}
                max={field.max}
                step={isInt ? 1 : (field as { step?: number }).step ?? 0.1}
                value={Number.isFinite(num) ? num : 0}
                onChange={e => {
                    const raw = e.target.value
                    if (raw === '') {
                        onChange(undefined)
                        return
                    }
                    const parsed = isInt ? Math.trunc(Number(raw)) : Number(raw)
                    onChange(Number.isFinite(parsed) ? parsed : 0)
                }}
            />
            {field.description && <p className="form-hint">{field.description}</p>}
        </div>
    )
}
