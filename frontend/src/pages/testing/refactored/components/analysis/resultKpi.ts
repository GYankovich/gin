import type { RobotHistoryBacktestResult, RobotHistoryBacktestTrade } from '@/types/robot'

export type ResultKpiTile = {
    id: string
    label: string
    value: string
    tone?: 'up' | 'down' | 'neutral'
    hint?: string
}

function fmtPct(v: number | null | undefined, digits = 2): string {
    if (v == null || !Number.isFinite(v)) return '—'
    return `${v.toFixed(digits)}%`
}

function fmtNum(v: number | null | undefined, digits = 2): string {
    if (v == null || !Number.isFinite(v)) return '—'
    return v.toFixed(digits)
}

function tradeMetrics(trades: RobotHistoryBacktestTrade[]): {
    winRate: number | null
    profitFactor: number | null
} {
    const withPnl = trades.filter(t => t.pnl_net != null && Number.isFinite(Number(t.pnl_net)))
    if (withPnl.length === 0) return { winRate: null, profitFactor: null }

    const winning = withPnl.filter(t => Number(t.pnl_net) > 0)
    const winRate = (winning.length * 100) / withPnl.length

    const grossProfit = withPnl
        .filter(t => Number(t.pnl_net) > 0)
        .reduce((sum, t) => sum + Number(t.pnl_net), 0)
    const grossLoss = Math.abs(
        withPnl.filter(t => Number(t.pnl_net) < 0).reduce((sum, t) => sum + Number(t.pnl_net), 0),
    )
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? null : null

    return { winRate, profitFactor }
}

function sharpeFromEquityCurve(
    equityCurve: RobotHistoryBacktestResult['equity_curve'],
    annualizationDays: number,
): number | null {
    if (!equityCurve || equityCurve.length < 3) return null
    const returns: number[] = []
    for (let i = 1; i < equityCurve.length; i++) {
        const prev = Number(equityCurve[i - 1]?.equity)
        const cur = Number(equityCurve[i]?.equity)
        if (prev > 0 && Number.isFinite(cur)) {
            returns.push((cur - prev) / prev)
        }
    }
    if (returns.length < 2) return null
    const mean = returns.reduce((a, b) => a + b, 0) / returns.length
    const variance = returns.reduce((a, b) => a + (b - mean) ** 2, 0) / (returns.length - 1)
    const std = Math.sqrt(variance)
    if (std <= 0) return null
    return (mean / std) * Math.sqrt(annualizationDays)
}

/** Primary KPI tiles for T4.1 ResultsDashboard. */
export function buildResultKpis(
    result: RobotHistoryBacktestResult,
    currencyLabel: string,
    opts?: { isCrypto?: boolean },
): ResultKpiTile[] {
    const ret = Number(result.total_return_percent || 0)
    const { winRate, profitFactor } = tradeMetrics(result.trades)
    const annDays = opts?.isCrypto ? 365 : 252
    const sharpe = sharpeFromEquityCurve(result.equity_curve, annDays)
    const hs = result.history_stats
    const tradingDays = hs?.trading_days_with_equity
    const calendarDays = hs?.calendar_days
    const annualized = hs?.annualized_return_percent
    const fee = result.fee_summary
    const margin = result.margin_summary

    const tiles: ResultKpiTile[] = [
        {
            id: 'return',
            label: 'Доходность за период',
            value: fmtPct(ret),
            tone: ret >= 0 ? 'up' : 'down',
        },
        {
            id: 'annualized',
            label: `Годовая (${annDays} дн.)`,
            value: fmtPct(annualized ?? null),
            tone: (annualized ?? 0) >= 0 ? 'up' : 'down',
            hint:
                tradingDays != null && calendarDays != null
                    ? `Торговых дней: ${tradingDays} из ${calendarDays}`
                    : undefined,
        },
        {
            id: 'sharpe',
            label: 'Sharpe',
            value: fmtNum(sharpe, 2),
            hint: sharpe == null ? 'мало точек equity' : `√${annDays}`,
        },
        {
            id: 'drawdown',
            label: 'Max drawdown',
            value: fmtPct(result.max_drawdown_percent),
            tone: 'down',
        },
        {
            id: 'win_rate',
            label: 'Win rate',
            value: fmtPct(winRate),
        },
        {
            id: 'profit_factor',
            label: 'Profit factor',
            value: fmtNum(profitFactor, 2),
        },
        {
            id: 'final_equity',
            label: `Итоговый капитал, ${currencyLabel}`,
            value: Number(result.final_equity || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }),
        },
    ]

    if (fee && (fee.maker_commission != null || fee.taker_commission != null)) {
        tiles.push({
            id: 'fees',
            label: 'Комиссии maker/taker',
            value: `${fmtNum(fee.maker_commission, 2)} / ${fmtNum(fee.taker_commission, 2)}`,
            hint: fee.total_funding != null ? `Funding: ${fmtNum(fee.total_funding, 2)}` : undefined,
        })
    }

    if (margin?.enabled) {
        tiles.push({
            id: 'margin',
            label: `Маржа ${margin.leverage}x`,
            value: margin.liquidations ? `${margin.liquidations} liq.` : '0 liq.',
            tone: (margin.liquidations ?? 0) > 0 ? 'down' : 'neutral',
            hint: margin.maintenance_margin_rate != null
                ? `MMR ${(Number(margin.maintenance_margin_rate) * 100).toFixed(2)}%`
                : undefined,
        })
    }

    return tiles
}
