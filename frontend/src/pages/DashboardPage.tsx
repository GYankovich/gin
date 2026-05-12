import React, { useCallback, useEffect, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { Button } from '@/components/ui/Button'
import { dashboardService } from '@/services/dashboardService'
import type { DashboardAccountItem, DashboardDataResponse } from '@/types/api'

///@EPIC Frontend.ITEM Dashboard.TOPIC Accounts Summary View [1]
///@ Дашборд загружает сводку по счетам/капиталу и показывает карточки состояния
///@ с базовыми действиями обновления данных.
export default function DashboardPage() {
    const [data, setData] = useState<DashboardDataResponse | null>(null)
    const [loading, setLoading] = useState(true)

    const load = useCallback(async () => {
        setLoading(true)
        try {
            const res = await dashboardService.fetchData()
            setData(res)
        } catch { /* interceptor */ }
        setLoading(false)
    }, [])

    useEffect(() => {
        load()
    }, [load])

    if (loading) {
        return (
            <div className="page" data-page="dashboard">
                <h1 className="page__title">Дашборд</h1>
                <Skeleton height="120px" />
                <Skeleton height="200px" />
            </div>
        )
    }

    if (!data) {
        return (
            <div className="page" data-page="dashboard">
                <h1 className="page__title">Дашборд</h1>
                <Card>
                    <p>Не удалось загрузить данные.</p>
                    <Button onClick={() => load()}>Повторить</Button>
                </Card>
            </div>
        )
    }

    return (
        <div className="page" data-page="dashboard">
            <div className="dashboard-page-head">
                <h1 className="page__title">Дашборд</h1>
            </div>

            {data.accounts.length === 0 ? (
                <Card>
                    <p className="dashboard-empty">Нет открытых счетов (статус OPEN). Добавьте счёт в T‑Invest или проверьте синхронизацию.</p>
                </Card>
            ) : (
                <div className="dashboard-account-stack">
                    {data.accounts.map((row) => (
                        <AccountSection key={row.account_id} row={row} />
                    ))}
                </div>
            )}
        </div>
    )
}

function AccountSection({ row }: { row: DashboardAccountItem }) {
    const title = row.account_name || row.external_account_id
    const syncText = row.last_account_sync
        ? new Date(row.last_account_sync).toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        })
        : '—'
    const s = row.summary
    const d = s.day_over_day_delta
    const dp = s.day_over_day_delta_percent

    return (
        <Card className="dashboard-account-card">
            <div className="dashboard-account-card__head">
                <h2 className="dashboard-account-card__title">{title}</h2>
                <div className="dashboard-account-card__meta-sync">
                    <div className="dashboard-account-card__meta mono">
                        {row.external_account_id} · {row.account_type} · {row.account_status}
                        <span className="dashboard-account-card__meta-sync-append">
                            {' · '}
                            {syncText}
                        </span>
                    </div>
                    <div className="dashboard-account-card__sync">
                        <span className="dashboard-account-card__sync-label">Обновлено</span>
                        <span className="dashboard-account-card__sync-value">{syncText}</span>
                    </div>
                </div>
            </div>

            <div className="mt-4">
                <div className="portfolio-stats-grid dashboard-summary-grid">
                    <div className="portfolio-stat-tile">
                        <div className="portfolio-stat-tile__label">Собственные средства</div>
                        <div className="portfolio-stat-tile__value">{formatMoney(s.own_funds, s.currency)}</div>
                    </div>
                    <div className="portfolio-stat-tile">
                        <div className="portfolio-stat-tile__label">Текущая стоимость</div>
                        <div className="portfolio-stat-tile__value">{formatMoney(s.total_value, s.currency)}</div>
                    </div>
                    <div className="portfolio-stat-tile">
                        <div className="portfolio-stat-tile__label">К портфелю vs вводы</div>
                        <div className={`portfolio-stat-tile__value ${roiClass(s.total_minus_own_funds)}`}>
                            {formatMoneySigned(s.total_minus_own_funds, s.currency)}
                        </div>
                    </div>
                    <div className="portfolio-stat-tile">
                        <div className="portfolio-stat-tile__label">Изменение к пред. дню</div>
                        <div className={`portfolio-stat-tile__value ${d == null ? '' : roiClass(d)}`}>
                            {d == null
                                ? '—'
                                : `${d >= 0 ? '+' : ''}${d.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${s.currency}`}
                            {dp != null && d != null && (
                                <span className="dashboard-dod-pct">
                                    {' '}({dp >= 0 ? '+' : ''}
                                    {dp.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%)
                                </span>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    )
}

function formatMoney(val: any, currency = 'RUB'): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val ?? 0)
    const sym = currency === 'RUB' ? '₽' : currency
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ' + sym
}

function formatMoneySigned(val: any, currency = 'RUB'): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    const sym = currency === 'RUB' ? '₽' : currency
    return `${n >= 0 ? '+' : ''}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${sym}`
}

function roiClass(val: number | null | undefined, drawdown = false): string {
    if (val == null || Number.isNaN(Number(val))) return ''
    const n = Number(val)
    if (drawdown) return n > 0 ? 'color-down' : 'color-up'
    return n >= 0 ? 'color-up' : 'color-down'
}
