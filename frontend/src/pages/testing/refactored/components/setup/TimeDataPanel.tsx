import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import { WeekdaysMaskField } from '@/components/ui/WeekdaysMaskField'
import { BYBIT_CANDLE_INTERVAL_OPTIONS } from '@/pages/testing/bybitCandleIntervals'
import { MOEX_TESTING_CANDLE_INTERVAL_OPTIONS } from '@/pages/testing/tinvestCandleIntervals'
import { normalizeStrategyInterval } from '@/pages/testing/strategyIntervals'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'
import { clampDateToToday } from '@/pages/testing/testingUtils'
import type { Robot } from '@/types/robot'

export type TimeDataPanelProps = {
    market: TestingMarket
    testName: string
    onTestNameChange: (v: string) => void
    robots: Robot[]
    robotId: number | null
    onRobotIdChange: (id: number | null) => void
    invalidPeriod: boolean
    fromDate: string
    toDate: string
    onFromDateChange: (v: string) => void
    onToDateChange: (v: string) => void
    interval: string
    onIntervalChange: (v: string) => void
    tradingHoursStart: string
    onTradingHoursStartChange: (v: string) => void
    tradingHoursEnd: string
    onTradingHoursEndChange: (v: string) => void
    allowedWeekdays: number
    onAllowedWeekdaysChange: (v: number) => void
    onConfigDirty: () => void
    className?: string
}

/** Идентичность + период, таймфрейм, сессия (MOEX). */
export function TimeDataPanel({
    market,
    testName,
    onTestNameChange,
    robots,
    robotId,
    onRobotIdChange,
    invalidPeriod,
    fromDate,
    toDate,
    onFromDateChange,
    onToDateChange,
    interval,
    onIntervalChange,
    tradingHoursStart,
    onTradingHoursStartChange,
    tradingHoursEnd,
    onTradingHoursEndChange,
    allowedWeekdays,
    onAllowedWeekdaysChange,
    onConfigDirty,
    className = '',
}: TimeDataPanelProps) {
    const isMoex = market === 'moex'
    const dirty = () => onConfigDirty()

    const timeframeOptions = useMemo(
        () =>
            (isMoex ? MOEX_TESTING_CANDLE_INTERVAL_OPTIONS : BYBIT_CANDLE_INTERVAL_OPTIONS).map(o => ({
                value: o.value,
                label: o.label,
            })),
        [isMoex],
    )

    const normalizedInterval = normalizeStrategyInterval(interval, market)

    return (
        <Card className={`mb-6 cyber-form-card testing-cyber-card testing-time-data-panel ${className}`.trim()}>
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                ВРЕМЯ И ДАННЫЕ
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="testing-time-data-panel__grid">
                <div className="form-group testing-form-group-flat">
                    <label className="form-label">Название теста</label>
                    <input
                        className="form-input"
                        type="text"
                        value={testName}
                        onChange={e => {
                            onTestNameChange(e.target.value)
                            dirty()
                        }}
                        placeholder="Бэктест MOEX 22.06.2026"
                    />
                </div>
                <div className="form-group testing-form-group-flat">
                    <label className="form-label">Робот</label>
                    <Select
                        options={[
                            { value: '', label: '— без робота —' },
                            ...robots.filter(r => r.type === 2).map(r => ({ value: String(r.id), label: r.name })),
                        ]}
                        value={robotId != null ? String(robotId) : ''}
                        onChange={v => onRobotIdChange(v ? Number(v) : null)}
                    />
                </div>
                <div
                    className={`form-group testing-form-group-flat testing-time-data-panel__period${invalidPeriod ? ' testing-time-data-panel__period--invalid' : ''}`}
                >
                    <DateRangePicker
                        fromValue={fromDate}
                        toValue={toDate}
                        onFromChange={v => {
                            onFromDateChange(clampDateToToday(v))
                            dirty()
                        }}
                        onToChange={v => {
                            onToDateChange(clampDateToToday(v))
                            dirty()
                        }}
                        fromLabel="Период бэктеста: с"
                        toLabel="по"
                    />
                </div>
                <div className="form-group testing-form-group-flat">
                    <label className="form-label">Таймфрейм</label>
                    <Select
                        options={timeframeOptions}
                        value={normalizedInterval}
                        onChange={v => {
                            onIntervalChange(String(v || timeframeOptions[0]?.value || ''))
                            dirty()
                        }}
                    />
                </div>
                {isMoex && (
                    <>
                        <div className="form-group testing-form-group-flat">
                            <label className="form-label">Сессия: начало (ЧЧ:ММ)</label>
                            <input
                                className="form-input"
                                type="text"
                                placeholder="10:00"
                                value={tradingHoursStart}
                                onChange={e => {
                                    onTradingHoursStartChange(e.target.value)
                                    dirty()
                                }}
                            />
                        </div>
                        <div className="form-group testing-form-group-flat">
                            <label className="form-label">Сессия: конец (ЧЧ:ММ)</label>
                            <input
                                className="form-input"
                                type="text"
                                placeholder="18:45"
                                value={tradingHoursEnd}
                                onChange={e => {
                                    onTradingHoursEndChange(e.target.value)
                                    dirty()
                                }}
                            />
                        </div>
                        <WeekdaysMaskField
                            className="testing-form-group-flat testing-weekdays-mask testing-time-data-panel__weekdays"
                            value={allowedWeekdays}
                            onChange={mask => {
                                onAllowedWeekdaysChange(mask)
                                dirty()
                            }}
                        />
                    </>
                )}
            </div>
        </Card>
    )
}
