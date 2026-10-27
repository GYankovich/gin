import React from 'react'
import { Card } from '@/components/ui/Card'
import { StatTile } from '@/components/ui/StatTile'
import { fmtMoney, fmtPct } from '@/pages/robots-v2/formatters'
import type { BacktestCostStressCase, BacktestFeeSummary } from '@/types/robot'

type Props = {
    fee: BacktestFeeSummary
}

function stressValue(row: BacktestCostStressCase | null | undefined): string {
    if (!row) return '—'
    const eq = Number(row.final_equity)
    const ret = Number(row.total_return_percent)
    const eqBit = Number.isFinite(eq) ? fmtMoney(eq) : '—'
    const retBit = Number.isFinite(ret) ? fmtPct(ret) : ''
    return retBit ? `${eqBit} (${retBit})` : eqBit
}

/** Zone M — compact costs / funding strip under anatomy. */
export function BacktestCostsStrip({ fee }: Props) {
    const commission = Number(fee.commission_total ?? 0)
    const funding = Number(fee.funding_total ?? 0)
    const events = Number(fee.funding_events ?? 0)
    const tax = fee.tax_total
    const showTax = tax != null && Number.isFinite(Number(tax))
    const stress = fee.cost_stress
    const assumptions = String(fee.assumptions || '').trim()

    return (
        <Card className="dashboard-totals-card robots-v2-glass-costs">
            <div className="dashboard-totals-card__head">
                <h3 className="dashboard-panel-title">Издержки</h3>
            </div>
            {assumptions ? (
                <p className="robots-v2-hint robots-v2-glass-costs__assumptions">{assumptions}</p>
            ) : null}
            <div className="portfolio-stats-grid dashboard-summary-grid robots-v2-glass-costs__grid">
                <StatTile
                    label="Комиссия"
                    value={fmtMoney(commission)}
                    valueClassName={commission !== 0 ? 'color-warn' : undefined}
                />
                <StatTile
                    label="Funding"
                    value={fmtMoney(funding)}
                    valueClassName={funding !== 0 ? 'color-warn' : undefined}
                />
                <StatTile label="События funding" value={Number.isFinite(events) ? events : '—'} />
                {showTax ? (
                    <StatTile
                        label="НДФЛ"
                        value={fmtMoney(Number(tax))}
                        valueClassName={Number(tax) !== 0 ? 'color-warn' : undefined}
                    />
                ) : null}
                {fee.avg_win != null && Number.isFinite(Number(fee.avg_win)) ? (
                    <StatTile label="Средний выигрыш" value={fmtMoney(Number(fee.avg_win))} />
                ) : null}
                {fee.avg_loss != null && Number.isFinite(Number(fee.avg_loss)) ? (
                    <StatTile
                        label="Средний проигрыш"
                        value={fmtMoney(Number(fee.avg_loss))}
                        valueClassName="color-down"
                    />
                ) : null}
                {fee.turnover != null && Number.isFinite(Number(fee.turnover)) ? (
                    <StatTile label="Оборот" value={Number(fee.turnover).toFixed(2)} />
                ) : null}
                {fee.avg_exposure_pct != null && Number.isFinite(Number(fee.avg_exposure_pct)) ? (
                    <StatTile label="Ср. экспозиция" value={`${Number(fee.avg_exposure_pct).toFixed(1)}%`} />
                ) : null}
            </div>
            {stress ? (
                <>
                    <div className="dashboard-totals-card__head robots-v2-glass-costs__stress-head">
                        <h3 className="dashboard-panel-title">Стресс издержек</h3>
                    </div>
                    <p className="robots-v2-hint">
                        Аналитическая надбавка к факту прогона, не повторная симуляция
                    </p>
                    <div className="portfolio-stats-grid dashboard-summary-grid robots-v2-glass-costs__grid">
                        <StatTile
                            label="Комиссия +50%"
                            value={stressValue(stress.commission_plus_50pct)}
                        />
                        <StatTile
                            label="Slippage ×2"
                            value={stressValue(stress.slippage_x2)}
                        />
                        <StatTile
                            label="Оба"
                            value={stressValue(stress.combined)}
                        />
                    </div>
                </>
            ) : null}
        </Card>
    )
}
