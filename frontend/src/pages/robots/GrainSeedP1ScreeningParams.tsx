import React from 'react'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { getP1Field } from '@/modules/robots/config/p1ScreeningFields'

export type GrainSeedP1ScreeningParamsProps = {
    params: Record<string, unknown>
    onParamChange: (key: string, value: number) => void
    onAtrFilterSync?: (period: number, minPercent: number) => void
}

/** ATR + ADX — та же 3-col сетка, что у universe-вкладок. */
export function GrainSeedP1ScreeningParams({
    params,
    onParamChange,
    onAtrFilterSync,
}: GrainSeedP1ScreeningParamsProps) {
    const atrPeriodField = getP1Field('atr_period', 'moex')
    const atrMinField = getP1Field('atr_min_pct', 'moex')
    const adxPeriodField = getP1Field('adx_period', 'moex')
    const adxThresholdField = getP1Field('adx_threshold', 'moex')

    const atrPeriod = Number(params.atr_period ?? atrPeriodField?.defaultValue ?? 14)
    const atrMinPct = Number(params.atr_min_pct ?? atrMinField?.defaultValue ?? 1.5)
    const adxPeriod = Number(params.adx_period ?? adxPeriodField?.defaultValue ?? 14)
    const adxThreshold = Number(params.adx_threshold ?? adxThresholdField?.defaultValue ?? 22)

    const patchAtr = (period: number, minPct: number) => {
        onParamChange('atr_period', period)
        onParamChange('atr_min_pct', minPct)
        onAtrFilterSync?.(period, minPct)
    }

    return (
        <div className="form-row grain-seed-p1-params">
            <div className="form-group">
                <label className="form-label">
                    {atrPeriodField?.label ?? 'Период ATR'}
                    {atrPeriodField?.tooltip && <FormLabelTooltip text={atrPeriodField.tooltip} />}
                </label>
                <input
                    className="form-input cyber-input"
                    type="number"
                    min={atrPeriodField?.min ?? 2}
                    step={1}
                    value={atrPeriod}
                    onChange={e => {
                        const period = Math.max(2, Number(e.target.value || 14))
                        patchAtr(period, atrMinPct)
                    }}
                />
            </div>
            <div className="form-group">
                <label className="form-label">
                    {atrMinField?.label ?? 'Мин. ATR (%)'}
                    {atrMinField?.tooltip && <FormLabelTooltip text={atrMinField.tooltip} />}
                </label>
                <input
                    className="form-input cyber-input"
                    type="number"
                    min={atrMinField?.min ?? 0}
                    step={atrMinField?.step ?? 0.1}
                    value={atrMinPct}
                    onChange={e => {
                        const minPct = Math.max(0, Number(e.target.value || 0))
                        patchAtr(atrPeriod, minPct)
                    }}
                />
            </div>
            <div className="form-group">
                <label className="form-label">
                    {adxPeriodField?.label ?? 'Период ADX'}
                    {adxPeriodField?.tooltip && <FormLabelTooltip text={adxPeriodField.tooltip} />}
                </label>
                <input
                    className="form-input cyber-input"
                    type="number"
                    min={adxPeriodField?.min ?? 2}
                    step={1}
                    value={adxPeriod}
                    onChange={e => onParamChange('adx_period', Math.max(2, Number(e.target.value || 14)))}
                />
            </div>
            <div className="form-group">
                <label className="form-label">
                    {adxThresholdField?.label ?? 'Порог ADX'}
                    {adxThresholdField?.tooltip && <FormLabelTooltip text={adxThresholdField.tooltip} />}
                </label>
                <input
                    className="form-input cyber-input"
                    type="number"
                    min={adxThresholdField?.min ?? 0}
                    step={adxThresholdField?.step ?? 0.5}
                    value={adxThreshold}
                    onChange={e => onParamChange('adx_threshold', Math.max(0, Number(e.target.value || 0)))}
                />
            </div>
        </div>
    )
}
