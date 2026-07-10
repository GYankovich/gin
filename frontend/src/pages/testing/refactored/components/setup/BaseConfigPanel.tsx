import React from 'react'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { DateRangePicker } from '@/components/ui/DateRangePicker'
import type { Robot } from '@/types/robot'
import { currencyForMarket, type TestingMarket } from '@/pages/testing/refactored/market'
import { clampDateToToday, parseNum } from '@/pages/testing/testingUtils'

export type BaseConfigPanelProps = {
    market: TestingMarket
    robots: Robot[]
    robotId: number | null
    onRobotIdChange: (id: number | null) => void
    strategyOptions: Array<{ value: string; label: string }>
    strategy: string
    onStrategyChange: (v: string) => void
    invalidPeriod: boolean
    fromDate: string
    toDate: string
    onFromDateChange: (v: string) => void
    onToDateChange: (v: string) => void
    capital: number
    onCapitalChange: (v: number) => void
    onConfigDirty: () => void
    className?: string
}

/** T2.2 — robot, strategy, period, capital. Universe — в UniverseScreeningPanel. */
export function BaseConfigPanel({
    market,
    robots,
    robotId,
    onRobotIdChange,
    strategyOptions,
    strategy,
    onStrategyChange,
    invalidPeriod,
    fromDate,
    toDate,
    onFromDateChange,
    onToDateChange,
    capital,
    onCapitalChange,
    onConfigDirty,
    className = '',
}: BaseConfigPanelProps) {
    const currency = currencyForMarket(market)
    const capitalLabel = currency === 'USDT' ? 'Бюджет (USDT)' : 'Бюджет (₽)'
    const dirty = () => onConfigDirty()

    return (
        <Card className={`mb-6 cyber-form-card testing-cyber-card testing-base-config-panel ${className}`.trim()}>
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                БАЗОВАЯ КОНФИГУРАЦИЯ
                <span className="cyber-bracket">]</span>
            </h3>

            <div className="testing-base-config-panel__grid">
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

                <div className="form-group testing-form-group-flat">
                    <label className="form-label">Стратегия</label>
                    <Select
                        options={strategyOptions}
                        value={strategy}
                        onChange={v => {
                            onStrategyChange(String(v || 'grain_seed'))
                            dirty()
                        }}
                    />
                </div>

                <div className="form-group testing-form-group-flat">
                    <label className="form-label">{capitalLabel}</label>
                    <input
                        className="form-input"
                        type="text"
                        value={String(capital)}
                        onChange={e => {
                            onCapitalChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>

                <div
                    className={`form-group testing-form-group-flat testing-base-config-panel__period${invalidPeriod ? ' testing-base-config-panel__period--invalid' : ''}`}
                >
                    <DateRangePicker
                        fromValue={fromDate}
                        toValue={toDate}
                        onFromChange={v => onFromDateChange(clampDateToToday(v))}
                        onToChange={v => onToDateChange(clampDateToToday(v))}
                        fromLabel="Период бэктеста: с"
                        toLabel="по"
                    />
                </div>
            </div>
        </Card>
    )
}
