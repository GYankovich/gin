import React from 'react'
import { Select } from '@/components/ui/Select'

const TRADING_POLL_MINUTE_OPTIONS = [1, 2, 5, 10, 15, 30, 60]

export type PollFrequencyFieldProps = {
    pollValue: number
    onPollValueChange: (v: number) => void
    pollUnit: 'minutes' | 'hours'
    onPollUnitChange: (u: 'minutes' | 'hours') => void
    onConfigDirty: () => void
}

/** Частота опроса для имитации live-цикла в бэктесте. */
export function PollFrequencyField({
    pollValue,
    onPollValueChange,
    pollUnit,
    onPollUnitChange,
    onConfigDirty,
}: PollFrequencyFieldProps) {
    const dirty = () => onConfigDirty()

    return (
        <div className="form-group testing-poll-frequency-field">
            <label className="form-label">Частота опроса</label>
            <div className="testing-poll-inline">
                <div className="testing-poll-inline__value">
                    {pollUnit === 'minutes' ? (
                        <Select
                            options={TRADING_POLL_MINUTE_OPTIONS.map(v => ({ value: String(v), label: String(v) }))}
                            value={String(pollValue)}
                            onChange={v => {
                                onPollValueChange(Number(v || 5))
                                dirty()
                            }}
                        />
                    ) : (
                        <input
                            className="form-input"
                            type="number"
                            min={1 / 60}
                            max={12}
                            step={0.1}
                            value={pollValue}
                            onChange={e => {
                                onPollValueChange(Math.max(1 / 60, Math.min(12, Number(e.target.value || 1))))
                                dirty()
                            }}
                        />
                    )}
                </div>
                <div className="testing-poll-inline__unit">
                    <Select
                        options={[
                            { value: 'minutes', label: 'минуты' },
                            { value: 'hours', label: 'часы' },
                        ]}
                        value={pollUnit}
                        onChange={v => {
                            onPollUnitChange(v === 'hours' ? 'hours' : 'minutes')
                            dirty()
                        }}
                    />
                </div>
            </div>
        </div>
    )
}
