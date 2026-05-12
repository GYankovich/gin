import React from 'react'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import type { Robot } from '@/types/robot'
import { normalizeSignalInterval } from '@/pages/testing/testingPipeline'
import { clampDateToToday } from '@/pages/testing/testingUtils'

const TRADING_POLL_MINUTE_OPTIONS = [1, 2, 5, 10, 15, 30, 60]

const SIGNAL_CANDLE_INTERVAL_OPTIONS = [
    { value: 'CANDLE_INTERVAL_1_MIN', label: '1м' },
    { value: 'CANDLE_INTERVAL_5_MIN', label: '5м' },
    { value: 'CANDLE_INTERVAL_10_MIN', label: '10м' },
    { value: 'CANDLE_INTERVAL_HOUR', label: '1ч' },
    { value: 'CANDLE_INTERVAL_DAY', label: '1д' },
    { value: 'CANDLE_INTERVAL_WEEK', label: '1н' },
    { value: 'CANDLE_INTERVAL_MONTH', label: '1М' },
    { value: 'CANDLE_INTERVAL_QUARTER', label: '1К' },
]

export type TestingRobotParamsCardProps = {
    robots: Robot[]
    robotId: number | null
    onRobotIdChange: (id: number | null) => void
    strategyOptions: Array<{ value: string; label: string }>
    strategy: string
    onStrategyChange: (v: string) => void
    brokerType: string
    onBrokerTypeChange: (v: string) => void
    pollValue: number
    onPollValueChange: (v: number) => void
    pollUnit: 'minutes' | 'hours'
    onPollUnitChange: (u: 'minutes' | 'hours') => void
    invalidPeriod: boolean
    fromDate: string
    toDate: string
    onFromDateChange: (v: string) => void
    onToDateChange: (v: string) => void
    interval: string
    onIntervalChange: (v: string) => void
    onConfigDirty: () => void
}

export function TestingRobotParamsCard({
    robots,
    robotId,
    onRobotIdChange,
    strategyOptions,
    strategy,
    onStrategyChange,
    brokerType,
    onBrokerTypeChange,
    pollValue,
    onPollValueChange,
    pollUnit,
    onPollUnitChange,
    invalidPeriod,
    fromDate,
    toDate,
    onFromDateChange,
    onToDateChange,
    interval,
    onIntervalChange,
    onConfigDirty,
}: TestingRobotParamsCardProps) {
    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                ПАРАМЕТРЫ РОБОТА
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="testing-robot-grid">
                <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Выбор робота</label>
                    <Select
                        options={robots.filter(r => r.type === 2).map(r => ({ value: String(r.id), label: r.name }))}
                        value={robotId != null ? String(robotId) : ''}
                        onChange={v => onRobotIdChange(v ? Number(v) : null)}
                    />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Стратегия</label>
                    <Select
                        options={strategyOptions}
                        value={strategy}
                        onChange={(v) => {
                            onStrategyChange(String(v || 'grain_seed'))
                            onConfigDirty()
                        }}
                    />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Брокер</label>
                    <Select
                        options={[
                            { value: 'tinvest', label: 'T-Invest' },
                            { value: 'sandbox', label: 'Sandbox' },
                        ]}
                        value={brokerType}
                        onChange={(v) => {
                            onBrokerTypeChange(String(v || 'tinvest'))
                            onConfigDirty()
                        }}
                    />
                </div>
                <div className="form-group">
                    <label className="form-label">Частота опроса</label>
                    <div className="testing-poll-inline">
                        <div className="testing-poll-inline__value">
                            {pollUnit === 'minutes' ? (
                                <Select
                                    options={TRADING_POLL_MINUTE_OPTIONS.map(v => ({ value: String(v), label: String(v) }))}
                                    value={String(pollValue)}
                                    onChange={v => {
                                        onPollValueChange(Number(v || 5))
                                        onConfigDirty()
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
                                        onConfigDirty()
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
                                    onConfigDirty()
                                }}
                            />
                        </div>
                    </div>
                </div>
                <div
                    className="testing-robot-grid__period"
                    style={invalidPeriod ? { border: '1px solid var(--color-down)', borderRadius: 'var(--radius-md)', padding: 6 } : undefined}
                >
                    <DateRangePicker
                        fromValue={fromDate}
                        toValue={toDate}
                        onFromChange={(v) => onFromDateChange(clampDateToToday(v))}
                        onToChange={(v) => onToDateChange(clampDateToToday(v))}
                        fromLabel="Интервал тестирования: с"
                        toLabel="по"
                    />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Интервал свечей (сигналы)</label>
                    <Select
                        options={SIGNAL_CANDLE_INTERVAL_OPTIONS}
                        value={interval}
                        onChange={(v) => {
                            onIntervalChange(normalizeSignalInterval(v))
                            onConfigDirty()
                        }}
                    />
                    {normalizeSignalInterval(interval).includes('5_MIN') && (
                        <p className="form-hint" style={{ marginTop: 6 }}>
                            В общем кеше MOEX нет шага 5m — для дозагрузки используйте 10m (или 1m); симуляция 5m идёт из legacy кеша.
                        </p>
                    )}
                </div>
            </div>
        </Card>
    )
}
