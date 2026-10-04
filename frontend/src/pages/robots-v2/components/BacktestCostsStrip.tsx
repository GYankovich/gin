import React from 'react'
import { Card } from '@/components/ui/Card'
import { StatTile } from '@/components/ui/StatTile'
import { fmtMoney } from '@/pages/robots-v2/formatters'
import type { BacktestFeeSummary } from '@/types/robot'

type Props = {
    fee: BacktestFeeSummary
}

/** Zone M — compact costs / funding strip under anatomy. */
export function BacktestCostsStrip({ fee }: Props) {
    const commission = Number(fee.commission_total ?? 0)
    const funding = Number(fee.funding_total ?? 0)
    const events = Number(fee.funding_events ?? 0)
    const tax = fee.tax_total
    const showTax = tax != null && Number.isFinite(Number(tax))

    return (
        <Card className="dashboard-totals-card robots-v2-glass-costs">
            <div className="dashboard-totals-card__head">
                <h3 className="dashboard-panel-title">Издержки</h3>
            </div>
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
                        label="Налог"
                        value={fmtMoney(Number(tax))}
                        valueClassName={Number(tax) !== 0 ? 'color-warn' : undefined}
                    />
                ) : null}
            </div>
        </Card>
    )
}
