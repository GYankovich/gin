import React, { useMemo } from 'react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { SCAN_CODE_VARIANT } from '@/pages/robots-v2/monitorUtils'
import type { RobotV2TickerScan } from '@/types/robotV2'

type ScanTableRow = RobotV2TickerScan & { id: string }

type MonitorUniverseCardProps = {
    displayTickerScan: RobotV2TickerScan[]
    displayUniverse: string[]
    tickerScanAt: string | null
    canRefreshUniverse: boolean
    universeBusy: boolean
    onRefreshUniverse: () => void
}

export function MonitorUniverseCard({
    displayTickerScan,
    displayUniverse,
    tickerScanAt,
    canRefreshUniverse,
    universeBusy,
    onRefreshUniverse,
}: MonitorUniverseCardProps) {
    const scanTableRows = useMemo(
        () => displayTickerScan.map(row => ({ ...row, id: row.ticker })),
        [displayTickerScan],
    )

    const scanColumns = useMemo<Column<ScanTableRow>[]>(() => [
        {
            key: 'ticker',
            header: 'Название',
            sortable: true,
            render: row => {
                const code = String(row.code || '—')
                return (
                    <div className="robots-v2-scan-ticker">
                        <strong>{row.ticker}</strong>
                        <Badge variant={SCAN_CODE_VARIANT[code] || 'neutral'}>{code}</Badge>
                    </div>
                )
            },
        },
        {
            key: 'message',
            header: 'Почему нет сигнала',
            render: row => (
                <span className="robots-v2-scan-reason">{String(row.message || '—')}</span>
            ),
        },
    ], [])

    return (
        <Card className="dashboard-assets-card robots-v2-monitor-scan">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Пул активов</h3>
                <div className="robots-v2-universe-head-actions">
                    {displayTickerScan.length > 0 ? (
                        <span className="robots-v2-hint">{displayTickerScan.length}</span>
                    ) : displayUniverse.length > 0 ? (
                        <span className="robots-v2-hint">{displayUniverse.length}</span>
                    ) : null}
                    {canRefreshUniverse ? (
                        <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            loading={universeBusy}
                            disabled={universeBusy}
                            onClick={onRefreshUniverse}
                        >
                            Обновить пул
                        </Button>
                    ) : null}
                </div>
            </div>
            <p className="robots-v2-hint robots-v2-universe-caption">
                Кандидаты и результат последней оценки стратегии
                {tickerScanAt ? (
                    <span className="mono">
                        {' '}
                        · {new Date(tickerScanAt).toLocaleTimeString('ru-RU')}
                    </span>
                ) : null}
            </p>
            {displayTickerScan.length === 0 && displayUniverse.length === 0 ? (
                <p className="dashboard-empty">—</p>
            ) : displayTickerScan.length === 0 ? (
                <div className="robots-v2-chip-row">
                    {displayUniverse.map(t => (
                        <span key={t} className="robots-v2-chip robots-v2-chip--on">{t}</span>
                    ))}
                    <p className="robots-v2-hint">Диагностика появится после первого цикла</p>
                </div>
            ) : (
                <DataTable
                    columns={scanColumns}
                    data={scanTableRows}
                    keyField="id"
                    emptyText="—"
                    maxHeight={320}
                    mobilePrimary={r => (
                        <div className="robots-v2-scan-ticker">
                            <strong>{r.ticker}</strong>
                            <Badge variant={SCAN_CODE_VARIANT[String(r.code || '')] || 'neutral'}>
                                {String(r.code || '—')}
                            </Badge>
                        </div>
                    )}
                    mobileDetails={r => String(r.message || '—')}
                />
            )}
        </Card>
    )
}
