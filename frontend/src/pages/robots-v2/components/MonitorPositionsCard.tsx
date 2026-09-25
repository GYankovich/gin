import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { TickerWarningMark } from '@/pages/robots-v2/components/TickerWarningMark'

export type MonitorPositionRow = {
    id: string
    tickerLabel: string
    tickerWarning: string
    side: string
    quantity: string
    entry: string
    breakEven: string
    current: string
    sl: string
    tp: string
}

type MonitorPositionsCardProps = {
    rows: MonitorPositionRow[]
    positionsCount: number
    positionsUpdatedAt: string | null | undefined
    brokerSoftStopHint: boolean
    isRunning: boolean
}

export function MonitorPositionsCard({
    rows,
    positionsCount,
    positionsUpdatedAt,
    brokerSoftStopHint,
    isRunning,
}: MonitorPositionsCardProps) {
    const columns = useMemo<Column<MonitorPositionRow>[]>(() => [
        {
            key: 'tickerLabel',
            header: 'Тикер',
            sortable: true,
            render: r => (
                <span className="robots-v2-ticker-cell">
                    {r.tickerWarning ? <TickerWarningMark text={r.tickerWarning} /> : null}
                    {r.tickerLabel}
                </span>
            ),
        },
        { key: 'side', header: 'Сторона' },
        { key: 'quantity', header: 'Кол-во', render: r => <span className="mono">{r.quantity}</span> },
        { key: 'entry', header: 'Вход', render: r => <span className="mono">{r.entry}</span> },
        {
            key: 'breakEven',
            header: 'Точка безубыточности',
            render: r => <span className="mono">{r.breakEven}</span>,
        },
        { key: 'current', header: 'Текущая', render: r => <span className="mono">{r.current}</span> },
        { key: 'sl', header: 'SL', render: r => <span className="mono">{r.sl}</span> },
        { key: 'tp', header: 'TP', render: r => <span className="mono">{r.tp}</span> },
    ], [])

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-positions">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Открытые позиции</h3>
                {positionsCount > 0 ? (
                    <span className="robots-v2-hint">{positionsCount}</span>
                ) : null}
            </div>
            {positionsUpdatedAt ? (
                <p className="robots-v2-hint robots-v2-universe-caption">
                    Данные обновлены
                    <span className="mono">
                        {' '}
                        · {new Date(positionsUpdatedAt).toLocaleString('ru-RU', {
                            day: '2-digit',
                            month: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit',
                        })}
                    </span>
                </p>
            ) : null}
            {brokerSoftStopHint ? (
                <p className="robots-v2-hint robots-v2-universe-caption">
                    Сессия остановлена · позиции с брокера (soft stop их не закрывает).
                    После Start робот подхватит и продолжит торговать.
                </p>
            ) : null}
            <DataTable
                columns={columns}
                data={rows}
                keyField="id"
                emptyText={
                    isRunning
                        ? 'Нет открытых позиций — робот ещё не вошёл в сделку'
                        : 'Нет открытых позиций на брокере (в universe / по audit fills)'
                }
                maxHeight={320}
                mobilePrimary={r => (
                    <div className="portfolio-mobile-split">
                        <strong>{r.tickerLabel}</strong>
                        <span className="mono">{r.quantity}</span>
                    </div>
                )}
                mobileDetails={r => (
                    <span className="mono">
                        {r.side} · вход {r.entry} · тек. {r.current}
                    </span>
                )}
            />
        </Card>
    )
}
