import React, { useMemo } from 'react'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { DataTable, type Column } from '@/components/ui/DataTable'
import {
    formatPortfolioMoney,
    formatPortfolioMoneySigned,
} from '@/utils/portfolioFormat'

export type PortfolioCompositionRow = {
    figi: string
    ticker?: string | null
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
    /** ByBit / crypto: колонка «Символ» вместо «FIGI». */
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

export function PortfolioComposition({
    positions,
    loading = false,
    currency = 'RUB',
    bybitAccount = false,
    open,
    onOpenChange,
    defaultOpen = true,
    className = 'portfolio-collapse',
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
                key: 'figi',
                header: bybitAccount ? 'Символ' : 'FIGI',
                sortable: true,
                width: '140px',
            },
            {
                key: 'ticker',
                header: 'Тикер',
                sortable: true,
                width: '80px',
                render: r => r.ticker || '—',
            },
            {
                key: 'type_name',
                header: 'Тип',
                sortable: true,
                width: '120px',
                render: r => String(r.type_name || r.instrument_type || '—'),
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
        [bybitAccount, currency],
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
                <div className="ops-loader">
                    <div className="soft-loading-bar" />
                    <div className="ops-loader__text">Загрузка состава портфеля...</div>
                </div>
            ) : (
                <DataTable
                    columns={columns}
                    data={positions}
                    keyField="figi"
                    emptyText={emptyText}
                    mobilePrimary={r => `${r.ticker || '—'} (${r.figi || '—'})`}
                    mobileSecondary={r =>
                        `${Number(r.quantity ?? 0).toLocaleString('ru-RU')} шт. | ${money(r.total_value)}`
                    }
                    mobileDetails={r => (
                        <>
                            <div>Тип: {r.type_name || r.instrument_type || '—'}</div>
                            <div>Средняя цена: {money(r.avg_price)}</div>
                            <div>
                                Текущая цена: {money(r.current_price)}{' '}
                                <span
                                    className={
                                        Number(r.expected_yield ?? 0) >= 0 ? 'color-up' : 'color-down'
                                    }
                                >
                                    ({Number(r.expected_yield ?? 0) >= 0 ? '+' : ''}
                                    {money(r.expected_yield ?? 0)})
                                </span>
                            </div>
                            <div>
                                P&amp;L:{' '}
                                <span
                                    className={
                                        Number(r.expected_yield ?? 0) >= 0 ? 'color-up' : 'color-down'
                                    }
                                >
                                    {money(r.expected_yield ?? 0)}
                                </span>
                            </div>
                        </>
                    )}
                />
            )}
        </CollapsibleSection>
    )
}
