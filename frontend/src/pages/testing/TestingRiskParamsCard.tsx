import React from 'react'
import { Card } from '@/components/ui/Card'
import { parseNum } from '@/pages/testing/testingUtils'

export type TestingRiskParamsCardProps = {
    capital: number
    onCapitalChange: (v: number) => void
    brokerCommissionPct: number
    onBrokerCommissionPctChange: (v: number) => void
    ndflPct: number
    onNdflPctChange: (v: number) => void
    stopLossPct: number
    onStopLossPctChange: (v: number) => void
    takeProfitPct: number
    onTakeProfitPctChange: (v: number) => void
    maxPositionPct: number
    onMaxPositionPctChange: (v: number) => void
    maxPositionRub: number
    onMaxPositionRubChange: (v: number) => void
    onConfigDirty: () => void
}

export function TestingRiskParamsCard({
    capital,
    onCapitalChange,
    brokerCommissionPct,
    onBrokerCommissionPctChange,
    ndflPct,
    onNdflPctChange,
    stopLossPct,
    onStopLossPctChange,
    takeProfitPct,
    onTakeProfitPctChange,
    maxPositionPct,
    onMaxPositionPctChange,
    maxPositionRub,
    onMaxPositionRubChange,
    onConfigDirty,
}: TestingRiskParamsCardProps) {
    const dirty = () => onConfigDirty()

    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                РИСК-МЕНЕДЖМЕНТ
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="form-row">
                <div className="form-group">
                    <label className="form-label">Бюджет (₽)</label>
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
                <div className="form-group">
                    <label className="form-label">Комиссия брокера (%)</label>
                    <input
                        className="form-input"
                        type="number"
                        step="0.01"
                        value={brokerCommissionPct}
                        onChange={e => {
                            onBrokerCommissionPctChange(parseNum(e.target.value, true, 0, 100))
                            dirty()
                        }}
                    />
                </div>
                <div className="form-group">
                    <label className="form-label">НДФЛ (%)</label>
                    <input
                        className="form-input"
                        type="number"
                        step="0.01"
                        value={ndflPct}
                        onChange={e => {
                            onNdflPctChange(parseNum(e.target.value, true, 0, 100))
                            dirty()
                        }}
                    />
                </div>
            </div>
            <div className="form-row">
                <div className="form-group">
                    <label className="form-label">Стоп-лосс (%)</label>
                    <input
                        className="form-input"
                        type="number"
                        step="0.1"
                        value={stopLossPct}
                        onChange={e => {
                            onStopLossPctChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>
                <div className="form-group">
                    <label className="form-label">Тейк-профит (%)</label>
                    <input
                        className="form-input"
                        type="number"
                        step="0.1"
                        value={takeProfitPct}
                        onChange={e => {
                            onTakeProfitPctChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>
                <div className="form-group">
                    <label className="form-label">Макс. доля позиции (%)</label>
                    <input
                        className="form-input"
                        type="number"
                        step="0.1"
                        value={maxPositionPct}
                        onChange={e => {
                            onMaxPositionPctChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>
                <div className="form-group">
                    <label className="form-label">Макс. позиция (₽)</label>
                    <input
                        className="form-input"
                        type="number"
                        step="1000"
                        value={maxPositionRub}
                        onChange={e => {
                            onMaxPositionRubChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>
            </div>
        </Card>
    )
}
