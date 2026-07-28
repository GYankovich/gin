import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { parseNum } from '@/pages/testing/testingUtils'
import {
    calcMaxPositionFromBudget,
    riskInputClass,
    validateRiskParams,
    type RiskRewardLevel,
} from '@/pages/testing/riskParamsValidation'

export { calcMaxPositionFromBudget } from '@/pages/testing/riskParamsValidation'

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

function RiskIndicator({ level, children }: { level: RiskRewardLevel; children: React.ReactNode }) {
    if (level === 'neutral') return null
    return <p className={`risk-indicator risk-indicator--${level}`}>{children}</p>
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
    maxPositionRub: _maxPositionRub,
    onMaxPositionRubChange,
    maxDailyLoss,
    onMaxDailyLossChange,
    slippagePct,
    onSlippagePctChange,
    executionLatencySec,
    onExecutionLatencySecChange,
    maxDrawdownPct,
    onMaxDrawdownPctChange,
    maxDailyLossLabel = 'Макс. дневной убыток',
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
    const checkMinTrade = showMinTradeAmount && onMinTradeAmountRubChange != null

    const validation = useMemo(
        () =>
            validateRiskParams({
                budget: capital,
                positionShare: maxPositionPct,
                stopLoss: stopLossPct,
                takeProfit: takeProfitPct,
                minTradeSize: minTradeAmountRub,
                maxDailyLoss,
                checkMinTrade,
            }),
        [capital, maxPositionPct, stopLossPct, takeProfitPct, minTradeAmountRub, maxDailyLoss, checkMinTrade],
    )

    const derivedMaxPosition = validation.maxPosition
    const rrLevel = validation.riskReward.level
    const rrBadgeClass =
        rrLevel === 'err' ? 'badge badge--down' : rrLevel === 'warn' ? 'badge badge--warn' : 'badge badge--up'

    const syncMaxPosition = (nextCapital: number, nextPct: number) => {
        onMaxPositionRubChange(calcMaxPositionFromBudget(nextCapital, nextPct))
    }

    const body = (
        <div className="risk-params-layout">
            {showCapital && (
                <div className="form-group risk-params-layout__full">
                    <label className="form-label">{capitalLabel}</label>
                    <input
                        className="form-input cyber-input"
                        type="number"
                        min={0}
                        step="1"
                        value={capital}
                        onChange={e => {
                            const next = parseNum(e.target.value, true, 0)
                            onCapitalChange(next)
                            syncMaxPosition(next, maxPositionPct)
                            dirty()
                        }}
                    />
                    <p className="form-hint">Общий капитал для торговли</p>
                </div>
            )}

            <div className="risk-params-layout__row testing-risk-two-cols">
                <div className="form-group">
                    <label className="form-label">Макс. доля позиции (%)</label>
                    <input
                        className={riskInputClass(validation.positionShare?.level)}
                        type="number"
                        step="0.1"
                        min={0}
                        max={100}
                        value={maxPositionPct}
                        onChange={e => {
                            const next = parseNum(e.target.value, true, 0, 100)
                            onMaxPositionPctChange(next)
                            syncMaxPosition(capital, next)
                            dirty()
                        }}
                    />
                    <p className="form-hint">% от бюджета на 1 позицию</p>
                    {validation.positionShare && (
                        <RiskIndicator level={validation.positionShare.level}>
                            {validation.positionShare.message}
                        </RiskIndicator>
                    )}
                </div>
                <div className="form-group">
                    <label className="form-label">{maxPositionRubLabel}</label>
                    <input
                        className={riskInputClass(
                            validation.minTrade?.level === 'err' ? 'err' : null,
                        )}
                        type="number"
                        value={derivedMaxPosition}
                        readOnly
                        tabIndex={-1}
                        aria-readonly="true"
                    />
                    <p className="form-hint form-hint--cyan">Рассчитывается автоматически</p>
                </div>
            </div>

            <div className="risk-params-layout__row testing-risk-two-cols">
                <div className="form-group">
                    <label className="form-label">Стоп-лосс (%)</label>
                    <input
                        className={riskInputClass(rrLevel === 'neutral' ? null : rrLevel)}
                        type="number"
                        step="0.1"
                        min={0}
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
                        className={riskInputClass(rrLevel === 'neutral' ? null : rrLevel)}
                        type="number"
                        step="0.1"
                        min={0}
                        value={takeProfitPct}
                        onChange={e => {
                            onTakeProfitPctChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                </div>
                {validation.riskRewardRatio != null && (
                    <div className="form-group risk-params-layout__span">
                        <div className="risk-ratio-indicator">
                            <span className={rrBadgeClass}>
                                R/R = {validation.riskRewardRatio.toFixed(2)}
                            </span>
                            {rrLevel === 'warn' && (
                                <span className="badge badge--warn">Рекомендуется ≥ 1.5</span>
                            )}
                            {rrLevel === 'err' && (
                                <span className="badge badge--down">Риск больше прибыли</span>
                            )}
                            {rrLevel === 'ok' && (
                                <span className="badge badge--up">Соотношение в норме</span>
                            )}
                        </div>
                    </div>
                )}
            </div>

            <div className="risk-params-layout__row testing-risk-two-cols">
                {checkMinTrade && (
                    <div className="form-group">
                        <label className="form-label">{minTradeAmountLabel}</label>
                        <input
                            className={riskInputClass(validation.minTrade?.level)}
                            type="number"
                            min={0}
                            step={1}
                            value={minTradeAmountRub ?? 0}
                            onChange={e => {
                                onMinTradeAmountRubChange!(parseNum(e.target.value, true, 0))
                                dirty()
                            }}
                        />
                        <p className="form-hint">Ниже порога — сделка не исполняется</p>
                        {validation.minTrade && (
                            <RiskIndicator level={validation.minTrade.level}>
                                {validation.minTrade.message}
                            </RiskIndicator>
                        )}
                    </div>
                )}
                <div className="form-group">
                    <label className="form-label">{maxDailyLossLabel}</label>
                    <input
                        className={riskInputClass(validation.dailyLoss?.level)}
                        type="number"
                        step="0.1"
                        min={0}
                        value={maxDailyLoss}
                        onChange={e => {
                            onMaxDailyLossChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                    <p className="form-hint color-warn">При достижении — торговля останавливается</p>
                    {validation.dailyLoss && (
                        <RiskIndicator level={validation.dailyLoss.level}>
                            {validation.dailyLoss.message}
                        </RiskIndicator>
                    )}
                </div>
                {commissionVisible && (
                    <div className="form-group">
                        <label className="form-label">Комиссия брокера (%)</label>
                        <input
                            className="form-input cyber-input"
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
                            className="form-input cyber-input"
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
            </div>

            <div className="risk-params-layout__row testing-risk-two-cols">
                <div className="form-group">
                    <label className="form-label">Проскальзывание (%)</label>
                    <input
                        className="form-input cyber-input"
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
                        className="form-input cyber-input"
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
                        className="form-input cyber-input"
                        type="number"
                        step="0.1"
                        min={0}
                        value={maxDrawdownPct}
                        onChange={e => {
                            onMaxDrawdownPctChange(parseNum(e.target.value, true, 0))
                            dirty()
                        }}
                    />
                    <p className="form-hint color-down">При превышении — бот останавливается</p>
                </div>
                {showMinProfitTarget && onMinProfitTargetPctChange != null && (
                    <div className="form-group">
                        <label className="form-label">Мин. цель прибыли (%)</label>
                        <input
                            className="form-input cyber-input"
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
