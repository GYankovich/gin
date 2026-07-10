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
    maxDailyLoss: number
    onMaxDailyLossChange: (v: number) => void
    slippagePct: number
    onSlippagePctChange: (v: number) => void
    executionLatencySec: number
    onExecutionLatencySecChange: (v: number) => void
    maxDrawdownPct: number
    onMaxDrawdownPctChange: (v: number) => void
    maxDailyLossLabel?: string
    /** Мин. нотионал сделки (risk.min_trade_amount_rub). */
    minTradeAmountRub?: number
    onMinTradeAmountRubChange?: (v: number) => void
    showMinTradeAmount?: boolean
    minTradeAmountLabel?: string
    minProfitTargetPct?: number | null
    onMinProfitTargetPctChange?: (v: number) => void
    showMinProfitTarget?: boolean
    onConfigDirty?: () => void
    className?: string
    showCosts?: boolean
    showCommission?: boolean
    showNdfl?: boolean
    capitalLabel?: string
    showCapital?: boolean
    maxPositionRubLabel?: string
    /** Без Card — вложить в двухколоночный блок стратегии/риска. */
    embedded?: boolean
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
    maxDailyLoss,
    onMaxDailyLossChange,
    slippagePct,
    onSlippagePctChange,
    executionLatencySec,
    onExecutionLatencySecChange,
    maxDrawdownPct,
    onMaxDrawdownPctChange,
    maxDailyLossLabel = 'Макс. дневной убыток (%)',
    minTradeAmountRub,
    onMinTradeAmountRubChange,
    showMinTradeAmount = false,
    minTradeAmountLabel = 'Мин. сумма сделки (₽)',
    minProfitTargetPct,
    onMinProfitTargetPctChange,
    showMinProfitTarget = false,
    onConfigDirty,
    className = 'mb-6 cyber-form-card testing-cyber-card',
    showCosts = true,
    showCommission,
    showNdfl,
    capitalLabel = 'Бюджет (₽)',
    showCapital = true,
    maxPositionRubLabel = 'Макс. позиция (₽)',
    embedded = false,
}: TestingRiskParamsCardProps) {
    const dirty = () => onConfigDirty?.()
    const commissionVisible = showCommission ?? showCosts
    const ndflVisible = showNdfl ?? showCosts

    const body = (
        <div className="testing-risk-two-cols">
                {showCapital && (
                <div className="form-group">
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
                )}
                {commissionVisible && (
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
                )}
                {ndflVisible && (
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
                )}
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
                    <label className="form-label">{maxPositionRubLabel}</label>
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
                {showMinTradeAmount && onMinTradeAmountRubChange != null && (
                    <div className="form-group">
                        <label className="form-label">{minTradeAmountLabel}</label>
                        <input
                            className="form-input"
                            type="number"
                            min={0}
                            step={1}
                            value={minTradeAmountRub ?? 0}
                            onChange={e => {
                                onMinTradeAmountRubChange(parseNum(e.target.value, true, 0))
                                dirty()
                            }}
                        />
                        <p className="form-hint">Сделки с нотионалом ниже порога не отправляются (Stage6).</p>
                    </div>
                )}
                <div className="form-group">
                    <label className="form-label">{maxDailyLossLabel}</label>
                    <input
                        className="form-input"
                        type="number"
                        step="0.1"
                        min={0}
                        value={maxDailyLoss}
                        onChange={e => {
                            onMaxDailyLossChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>
                <div className="form-group">
                    <label className="form-label">Проскальзывание (%)</label>
                    <input
                        className="form-input"
                        type="number"
                        step="0.01"
                        min={0}
                        value={slippagePct}
                        onChange={e => {
                            onSlippagePctChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>
                <div className="form-group">
                    <label className="form-label">Задержка исполнения (сек)</label>
                    <input
                        className="form-input"
                        type="number"
                        step="1"
                        min={0}
                        value={executionLatencySec}
                        onChange={e => {
                            onExecutionLatencySecChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>
                <div className="form-group">
                    <label className="form-label">Макс. допустимая просадка (%)</label>
                    <input
                        className="form-input"
                        type="number"
                        step="0.1"
                        min={0}
                        value={maxDrawdownPct}
                        onChange={e => {
                            onMaxDrawdownPctChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>
                {showMinProfitTarget && onMinProfitTargetPctChange != null && (
                    <div className="form-group">
                        <label className="form-label">Мин. цель прибыли (%)</label>
                        <input
                            className="form-input"
                            type="number"
                            min={0}
                            step={0.05}
                            value={minProfitTargetPct ?? 0.35}
                            onChange={e => {
                                onMinProfitTargetPctChange(parseNum(e.target.value, true, 0))
                                dirty()
                            }}
                        />
                        <p className="form-hint">Минимальный профит для закрытия (take-profit min)</p>
                    </div>
                )}
            </div>
    )

    if (embedded) {
        return <div className={className}>{body}</div>
    }

    return (
        <Card className={className}>
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                РИСК-МЕНЕДЖМЕНТ
                <span className="cyber-bracket">]</span>
            </h3>
            {body}
        </Card>
    )
}
