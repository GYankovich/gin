import React from 'react'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { Toggle } from '@/components/ui/Toggle'
import {
    getStrategyFieldsForUi,
    getStrategyMeta,
    groupStrategyFields,
    type StrategyParamField,
} from '@/pages/testing/strategyPresets'
import { normalizeStrategyInterval } from '@/pages/testing/strategyIntervals'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'

export type TestingStrategyParamsCardProps = {
    strategy: string
    params: Record<string, unknown>
    onParamChange: (key: string, value: unknown) => void
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
    onConfigDirty,
    market = 'moex',
    className = 'mb-6 cyber-form-card testing-cyber-card',
    sectionTitle,
    sectionHint,
    embedded = false,
    excludeFieldKeys,
    grouped = false,
}: TestingStrategyParamsCardProps) {
    const meta = getStrategyMeta(strategy)
    const fields = getStrategyFieldsForUi(strategy, { excludeKeys: excludeFieldKeys, market })
    const update = (key: string, value: unknown) => {
        if (key === 'interval' && typeof value === 'string') {
            onParamChange(key, normalizeStrategyInterval(value, market))
        } else {
            onParamChange(key, value)
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
