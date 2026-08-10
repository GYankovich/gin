import React, { useMemo } from 'react'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Skeleton } from '@/components/ui/Skeleton'
import {
    formatPortfolioMoney,
    formatPortfolioMoneySigned,
} from '@/utils/portfolioFormat'

export type PortfolioCompositionRow = {
    figi?: string | null
    ticker?: string | null
    ticker_name?: string | null
    short_name?: string | null
    instrument_type?: string | null
    type_name?: string | null
    quantity?: number | null
    avg_price?: number | null
    current_price?: number | null
    expected_yield?: number | null
    total_value?: number | null
}

type Props = {
    positions: PortfolioCompositionRow[]
    loading?: boolean
    currency?: string
    /** Kept for callers; FIGI column removed — asset label uses ticker_name/ticker. */
    bybitAccount?: boolean
    open?: boolean
    onOpenChange?: (open: boolean) => void
    defaultOpen?: boolean
    className?: string
    emptyText?: string
    /** Доп. контент над таблицей (кнопка обновления и т.п.). */
    toolbar?: React.ReactNode
    hint?: string
}

function fullAssetLabel(row: PortfolioCompositionRow): string {
    const name = String(row.ticker_name || '').trim()
    if (name) return name
    const shortName = String(row.short_name || '').trim()
    if (shortName) return shortName
    const ticker = String(row.ticker || '').trim()
    if (ticker) return ticker
    return '—'
}

function shortAssetLabel(row: PortfolioCompositionRow): string {
    const shortName = String(row.short_name || '').trim()
    if (shortName) return shortName
    const ticker = String(row.ticker || '').trim()
    if (ticker) return ticker
    return '—'
}

export function PortfolioComposition({
    positions,
    loading = false,
    currency = 'RUB',
    open,
    onOpenChange,
    defaultOpen = true,
    className = 'portfolio-collapse portfolio-composition-collapse',
    emptyText = 'Нет позиций',
    toolbar,
    hint,
}: Props) {
    const money = (val: unknown, maxFractionDigits = 2) =>
        formatPortfolioMoney(val, currency, maxFractionDigits)
    const moneySigned = (val: unknown) => formatPortfolioMoneySigned(val, currency)

    const columns: Column<PortfolioCompositionRow>[] = useMemo(
        () => [
            {
                key: 'ticker',
                header: 'Актив',
                sortable: true,
                width: '180px',
                render: r => fullAssetLabel(r),
            },
            {
                key: 'type_name',
                header: 'Тип',
                sortable: true,
                width: '140px',
                render: r => {
                    const label = String(r.type_name || '').trim()
                    if (label) return label
                    return String(r.instrument_type || '—')
                },
            },
            {
                key: 'quantity',
                header: 'Кол-во',
                sortable: true,
                align: 'right',
                render: r => Number(r.quantity ?? 0).toLocaleString('ru-RU'),
            },
            {
                key: 'avg_price',
                header: 'Средняя',
                sortable: true,
                align: 'right',
                render: r => money(r.avg_price),
            },
            {
                key: 'current_price',
                header: 'Текущая',
                align: 'right',
                render: r => money(r.current_price),
            },
            {
                key: 'expected_yield',
                header: 'P&L',
                sortable: true,
                align: 'right',
                render: r => {
                    const v = Number(r.expected_yield ?? 0)
                    return (
                        <span className={v >= 0 ? 'color-up' : 'color-down'}>
                            {moneySigned(v)}
                        </span>
                    )
                },
            },
            {
                key: 'total_value',
                header: 'Стоимость',
                sortable: true,
                align: 'right',
                render: r => money(r.total_value),
            },
        ],
        [currency],
    )

    const tableData = useMemo(
        () =>
            positions.map((row, index) => ({
                ...row,
                // Stable DataTable row id (FIGI column removed from UI).
                figi: String(row.figi || row.ticker || row.ticker_name || `row-${index}`),
            })),
        [positions],
    )

    return (
        <CollapsibleSection
            className={className}
            title="Состав портфеля "
            hint={hint}
            badge={
                <span className="portfolio-collapse__count">
                    {positions.length}
                </span>
            }
            open={open}
            onOpenChange={onOpenChange}
            defaultOpen={defaultOpen}
        >
            {toolbar}
            {loading ? (
                <div aria-busy="true" aria-label="Загрузка состава портфеля">
                    <Skeleton width="100%" height="120px" borderRadius="8px" />
                </div>
            ) : (
                <DataTable
                    columns={columns}
                    data={tableData}
                    keyField="figi"
                    emptyText={emptyText}
                    mobilePrimary={r => (
                        <div className="portfolio-mobile-split">
                            <span className="portfolio-mobile-split__asset">{shortAssetLabel(r)}</span>
                            <span className="portfolio-mobile-split__value mono">{money(r.total_value)}</span>
                        </div>
                    )}
                    mobileDetails={r => (
                        <>
                            <div className="portfolio-mobile-split__asset-full">{fullAssetLabel(r)}</div>
                            <div className="portfolio-mobile-split__muted mono portfolio-mobile-details-price">
                                <span>Цена: {money(r.current_price)}</span>
                                <span className="portfolio-mobile-metrics__avg" title="Средняя цена">
                                    <svg
                                        className="portfolio-mobile-metrics__avg-icon"
                                        viewBox="0 0 16 16"
                                        width="12"
                                        height="12"
                                        aria-hidden
                                    >
                                        <path
                                            d="M2 8h12M3.5 5h9M3.5 11h9"
                                            fill="none"
                                            stroke="currentColor"
                                            strokeWidth="1.5"
                                            strokeLinecap="round"
                                        />
                                    </svg>
                                    {money(r.avg_price)}
                                </span>
                            </div>
                            <div className="portfolio-mobile-split__muted mono">
                                Количество: {Number(r.quantity ?? 0).toLocaleString('ru-RU')}
                            </div>
                            <div>Тип: {r.type_name || r.instrument_type || '—'}</div>
                            <div>
                                P&amp;L:{' '}
                                <span
                                    className={
                                        Number(r.expected_yield ?? 0) >= 0 ? 'color-up' : 'color-down'
                                    }
                                >
                                    {moneySigned(r.expected_yield ?? 0)}
                                </span>
                            </div>
                        </>
                    )}
                />
            )}
        </CollapsibleSection>
    )
}
