import React from 'react'
import { Select } from '@/components/ui/Select'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import {
    getP1FieldsForMarket,
    type P1Market,
    type P1ScreeningFieldDef,
} from '@/modules/robots/config/p1ScreeningFields'

export type P1ScheduleValues = {
    lookbackDays?: number
    candleInterval?: string
    refreshDailyAtMsk?: string
}

export type P1ScheduleHandlers = {
    onLookbackDaysChange?: (v: number) => void
    onCandleIntervalChange?: (v: string) => void
    onRefreshDailyAtMskChange?: (v: string) => void
    onDirty?: () => void
}

type Props = {
    market: P1Market
    values: P1ScheduleValues
    handlers: P1ScheduleHandlers
    /** Scalar schedule-поля historical_screening (MOEX). */
    includeKeys?: readonly string[]
}

function readValue(field: P1ScreeningFieldDef, values: P1ScheduleValues): string | number {
    switch (field.key) {
        case 'lookback_days':
            return values.lookbackDays ?? Number(field.defaultValue ?? 14)
        case 'candle_interval':
            return values.candleInterval ?? String(field.defaultValue ?? '')
        case 'refresh_daily_at_msk':
            return values.refreshDailyAtMsk ?? String(field.defaultValue ?? '07:00')
        default:
            return ''
    }
}

/** Scalar-поля MOEX historical_screening — плоский form-row. */
export function P1ScreeningFieldSections({
    market,
    values,
    handlers,
    includeKeys = ['lookback_days', 'candle_interval', 'refresh_daily_at_msk'],
}: Props) {
    const fields = getP1FieldsForMarket(market, 'p1').filter(
        f => includeKeys.includes(f.key) && !f.strategyParamKey && !f.cryptoFilterType,
    )
    if (fields.length === 0) return null

    const dirty = () => handlers.onDirty?.()

    return (
        <div className="form-row p1-screening-schedule">
            {fields.map(field => (
                <P1ScalarField
                    key={field.key}
                    field={field}
                    value={readValue(field, values)}
                    onChange={next => {
                        if (field.key === 'lookback_days') {
                            handlers.onLookbackDaysChange?.(Math.max(1, Number(next || 14)))
                        } else if (field.key === 'candle_interval') {
                            handlers.onCandleIntervalChange?.(String(next))
                        } else if (field.key === 'refresh_daily_at_msk') {
                            handlers.onRefreshDailyAtMskChange?.(String(next))
                        }
                        dirty()
                    }}
                />
            ))}
        </div>
    )
}

function P1ScalarField({
    field,
    value,
    onChange,
}: {
    field: P1ScreeningFieldDef
    value: string | number
    onChange: (next: string | number) => void
}) {
    return (
        <div className="form-group">
            <label className="form-label">
                {field.label}
                {field.tooltip && <FormLabelTooltip text={field.tooltip} />}
            </label>
            {field.kind === 'enum' && field.options ? (
                <div className="cyber-select-wrap">
                    <Select
                        options={field.options}
                        value={String(value)}
                        onChange={v => onChange(String(v))}
                    />
                </div>
            ) : field.kind === 'time' ? (
                <input
                    className="form-input cyber-input"
                    type="time"
                    value={String(value)}
                    onChange={e => onChange(e.target.value)}
                />
            ) : (
                <input
                    className="form-input cyber-input"
                    type="number"
                    min={field.min}
                    max={field.max}
                    step={field.kind === 'integer' ? 1 : field.step ?? 0.1}
                    value={Number(value)}
                    onChange={e => onChange(Number(e.target.value))}
                />
            )}
        </div>
    )
}
