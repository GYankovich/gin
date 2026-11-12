import React from 'react'
import { Toggle } from '@/components/ui/Toggle'
import {
    WEEKDAY_FULL_WEEK_OPTION,
    WEEKDAYS,
    clampWeekdaysMask,
    isFullWeekMask,
    isWeekdaySelected,
    toggleFullWeek,
    toggleWeekday,
} from '@/utils/weekdaysMask'

export type WeekdaysMaskFieldProps = {
    value: number
    onChange: (mask: number) => void
    className?: string
    /** Показать поле «маска» для продвинутых пользователей */
    showAdvancedMask?: boolean
}

export function WeekdaysMaskField({
    value,
    onChange,
    className = '',
    showAdvancedMask = false,
}: WeekdaysMaskFieldProps) {
    const mask = clampWeekdaysMask(value)
    const fullWeek = isFullWeekMask(mask)

    return (
        <div className={`weekdays-mask-field ${className}`.trim()}>
            <div className="form-label weekdays-mask-field__label">Дни недели</div>
            <Toggle
                className="weekdays-mask-field__full-week"
                checked={fullWeek}
                title={WEEKDAY_FULL_WEEK_OPTION.label}
                label="все"
                onChange={(on) => onChange(toggleFullWeek(mask, on))}
            />
            <div
                className="weekdays-mask-field__days"
                role="group"
                aria-label="Дни недели"
            >
                {WEEKDAYS.map(d => {
                    const checked = isWeekdaySelected(mask, d.bit)
                    return (
                        <label
                            key={d.bit}
                            className={`weekdays-mask-field__day ${checked ? 'weekdays-mask-field__day--on' : ''}`}
                            title={`${d.label} · бит ${d.bit}`}
                        >
                            <input
                                type="checkbox"
                                checked={checked}
                                onChange={e => onChange(toggleWeekday(mask, d.bit, e.target.checked))}
                            />
                            <span>{d.short}</span>
                        </label>
                    )
                })}
            </div>

            {showAdvancedMask && (
                <div className="form-group weekdays-mask-field__advanced">
                    <label className="form-label">Маска (0–127)</label>
                    <input
                        className="form-input cyber-input"
                        type="number"
                        min={0}
                        max={127}
                        value={mask}
                        onChange={e => onChange(clampWeekdaysMask(Number(e.target.value)))}
                    />
                </div>
            )}
        </div>
    )
}
