export type RiskRewardLevel = 'ok' | 'warn' | 'err' | 'neutral'

export type RiskFieldFeedback = {
    level: RiskRewardLevel
    message: string
}

export type RiskParamsValidation = {
    maxPosition: number
    riskRewardRatio: number | null
    riskReward: RiskFieldFeedback
    positionShare: RiskFieldFeedback | null
    minTrade: RiskFieldFeedback | null
    dailyLoss: RiskFieldFeedback | null
    /** true если есть блокирующая ошибка */
    hasError: boolean
}

export function calcMaxPositionFromBudget(capital: number, pct: number): number {
    const raw = (Number(capital) * Number(pct)) / 100
    if (!Number.isFinite(raw) || raw < 0) return 0
    return Number(raw.toFixed(2))
}

export function calcRiskRewardRatio(stopLossPct: number, takeProfitPct: number): number | null {
    const stop = Number(stopLossPct)
    const take = Number(takeProfitPct)
    if (!(stop > 0) || !(take >= 0) || !Number.isFinite(stop) || !Number.isFinite(take)) return null
    return Number((take / stop).toFixed(2))
}

export function validateRiskParams(params: {
    budget: number
    positionShare: number
    stopLoss: number
    takeProfit: number
    minTradeSize?: number | null
    maxDailyLoss?: number | null
    checkMinTrade?: boolean
}): RiskParamsValidation {
    const maxPosition = calcMaxPositionFromBudget(params.budget, params.positionShare)
    const ratio = calcRiskRewardRatio(params.stopLoss, params.takeProfit)

    let riskReward: RiskFieldFeedback
    if (ratio == null) {
        riskReward = { level: 'neutral', message: 'Укажите стоп-лосс и тейк-профит' }
    } else if (ratio < 1) {
        riskReward = { level: 'err', message: 'R/R < 1: риск больше прибыли' }
    } else if (ratio < 1.5) {
        riskReward = { level: 'warn', message: 'Рекомендуется R/R ≥ 1.5' }
    } else {
        riskReward = { level: 'ok', message: 'R/R в норме' }
    }

    let positionShare: RiskFieldFeedback | null = null
    if (params.positionShare > 100) {
        positionShare = { level: 'err', message: 'Доля позиции не может быть больше 100%' }
    } else if (params.positionShare <= 0) {
        positionShare = { level: 'warn', message: 'Доля позиции должна быть больше 0' }
    }

    let minTrade: RiskFieldFeedback | null = null
    if (params.checkMinTrade && params.minTradeSize != null) {
        if (maxPosition < Number(params.minTradeSize || 0)) {
            minTrade = {
                level: 'err',
                message: 'Макс. позиция меньше мин. суммы сделки',
            }
        }
    }

    let dailyLoss: RiskFieldFeedback | null = null
    if (params.maxDailyLoss != null && Number(params.budget) > 0) {
        if (Number(params.maxDailyLoss) > Number(params.budget)) {
            dailyLoss = {
                level: 'err',
                message: 'Дневной убыток не может превышать бюджет',
            }
        }
    }

    const hasError =
        riskReward.level === 'err' ||
        positionShare?.level === 'err' ||
        minTrade?.level === 'err' ||
        dailyLoss?.level === 'err'

    return {
        maxPosition,
        riskRewardRatio: ratio,
        riskReward,
        positionShare,
        minTrade,
        dailyLoss,
        hasError,
    }
}

export function riskInputClass(level: RiskRewardLevel | null | undefined): string {
    const base = 'form-input cyber-input'
    if (level === 'err') return `${base} risk-field--error`
    if (level === 'warn') return `${base} risk-field--warning`
    if (level === 'ok') return `${base} risk-field--valid`
    return base
}
