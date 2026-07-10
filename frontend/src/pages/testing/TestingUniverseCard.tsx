import React, { useMemo } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { Skeleton } from '@/components/ui/Skeleton'
import type { useTestingUniverse } from '@/pages/testing/hooks/useTestingUniverse'
import { formatDmsUniverseReason } from '@/utils/dmsUniverseDisplay'
import { formatUniverseJobTime } from '@/utils/robotConfigV2'

export type TestingUniverseCardProps = {
    robotId: number | null
    universe: ReturnType<typeof useTestingUniverse>
}

export function TestingUniverseCard({ robotId, universe }: TestingUniverseCardProps) {
    const {
        dailyUniverse,
        allowedFigis,
        candidatePoolTickers,
        candidatePoolAsOf,
        lastHistoricalRun,
        lastPaperRun,
        loading,
        syncing,
        histJobLoading,
        paperJobLoading,
        load,
        syncUniverse,
        runHistoricalScreening,
        runPaperSelection,
        subscribeDms,
        universeAccepted,
        universeRejected,
    } = universe

    const columns: Column<(typeof dailyUniverse)[number]>[] = useMemo(
        () => [
            { key: 'ticker', header: 'Тикер' },
            { key: 'source', header: 'Источник' },
            { key: 'filter_result', header: 'Статус' },
            {
                key: 'reason',
                header: 'Причина',
                render: r => formatDmsUniverseReason(r),
            },
            {
                key: 'created_at',
                header: 'Время',
                render: r => (r.created_at ? new Date(r.created_at).toLocaleTimeString('ru-RU') : '—'),
            },
        ],
        [],
    )

    return (
        <Card className="mb-6 pipeline-card testing-universe-card">
            <div className="pipeline-header">
                <h3 className="card__section-title pipeline-title">
                    <span className="cyber-bracket">[</span>
                    UNIVERSE (LIVE)
                    <span className="cyber-bracket">]</span>
                </h3>
            </div>

            {!robotId ? (
                <p className="testing-universe-card__hint">Выберите торгового робота — отбор бумаг как на Live.</p>
            ) : (
                <>
                    <div className="live-dms-info testing-universe-card__info">
                        <strong>Как это связано с бэктестом</strong>
                        <ol>
                            <li>
                                Режим universe — в карточке «Отбор бумаг» или в настройках робота: фиксированный список,
                                DMS pipeline или вся TQBR.
                            </li>
                            <li>
                                При <span className="mono">dms_pipeline</span> фильтры слева совпадают с{' '}
                                <span className="mono">config.pipeline</span>.
                            </li>
                            <li>
                                <span className="mono">Пересобрать universe</span> — snapshot MOEX →{' '}
                                <span className="mono">daily_universe</span> → FIGI в{' '}
                                <span className="mono">allowed_figis</span>.
                            </li>
                            <li>
                                Бэктест считает universe <em>по каждому дню истории</em>; здесь — актуальный список для
                                live на сегодня.
                            </li>
                        </ol>
                    </div>

                    <div className="live-accordion__toolbar live-accordion__toolbar--end testing-universe-card__toolbar">
                        <Button
                            variant="ghost"
                            size="sm"
                            loading={histJobLoading}
                            disabled={histJobLoading}
                            onClick={() => void runHistoricalScreening()}
                        >
                            П1 (MOEX)
                        </Button>
                        <Button
                            variant="ghost"
                            size="sm"
                            loading={paperJobLoading}
                            disabled={paperJobLoading}
                            onClick={() => void runPaperSelection()}
                        >
                            П2 (снапшот)
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => void subscribeDms()}>
                            Подписать DMS
                        </Button>
                        <Button
                            variant="ghost"
                            size="sm"
                            loading={syncing}
                            disabled={syncing}
                            onClick={() => void syncUniverse()}
                        >
                            Пересобрать universe
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => void load()} disabled={loading}>
                            Обновить
                        </Button>
                    </div>

                    <p className="live-dms-section-hint testing-universe-card__meta mono">
                        candidate_pool: <strong>{candidatePoolTickers.length}</strong>
                        {candidatePoolAsOf && <> · {formatUniverseJobTime(candidatePoolAsOf)}</>}
                        {candidatePoolTickers.length > 0 && (
                            <> · {candidatePoolTickers.slice(0, 8).join(', ')}</>
                        )}
                        <br />
                        П1: {formatUniverseJobTime(lastHistoricalRun)} · П2: {formatUniverseJobTime(lastPaperRun)}
                    </p>

                    <p className="live-dms-section-hint testing-universe-card__meta">
                        В конфиге робота: <strong>{allowedFigis.length}</strong> FIGI · принято сегодня:{' '}
                        {universeAccepted.length} · отклонено: {universeRejected.length}
                        {dailyUniverse[0]?.snapshot_id != null && (
                            <> · snapshot #{dailyUniverse[0].snapshot_id}</>
                        )}
                    </p>

                    {allowedFigis.length > 0 && (
                        <p className="testing-universe-card__figis mono">
                            {allowedFigis.slice(0, 12).join(', ')}
                            {allowedFigis.length > 12 ? ` … +${allowedFigis.length - 12}` : ''}
                        </p>
                    )}

                    {loading ? (
                        <Skeleton height="120px" />
                    ) : (
                        <DataTable
                            columns={columns}
                            data={dailyUniverse}
                            keyField="id"
                            emptyText="Нет данных за сегодня — «Подписать DMS» или «Пересобрать universe»"
                            maxHeight={200}
                        />
                    )}
                </>
            )}
        </Card>
    )
}
