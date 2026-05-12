import React from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Skeleton } from '@/components/ui/Skeleton'
import { MOEX_CACHE_INTERVALS, type MoexCacheInterval } from '@/services/marketService'
import { parseTickers } from '@/pages/testing/testingUtils'
import type { MoexCandleJobState } from '@/pages/testing/hooks/useMoexCandleJobState'

type Props = {
    moex: MoexCandleJobState
}

export function TestingMoexCacheCard({ moex }: Props) {
    const {
        moexTickers,
        setMoexTickers,
        moexBoard,
        setMoexBoard,
        moexInterval,
        setMoexInterval,
        moexJobId,
        moexJobStatus,
        moexJobError,
        moexJobSubmitting,
        moexPreviewLoading,
        moexPreview,
        suggestedMoexForSignal,
        moexIntervalMismatch,
        alignMoexIntervalToSignal,
        startMoexCandleLoad,
        previewMoexCache,
        clearMoexCandleJob,
    } = moex

    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card testing-moex-cache-card">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                ОБЩИЙ КЕШ СВЕЧЕЙ MOEX
                <span className="cyber-bracket">]</span>
            </h3>
            <p className="form-hint" style={{ marginBottom: 'var(--space-3)' }}>
                Фоновая дозагрузка в общую таблицу (ARCH-01): те же даты «Интервал тестирования», что и для бэктеста ниже.
                Идентификатор — только тикер, без FIGI.
            </p>
            {!parseTickers(moexTickers).length && (
                <div
                    className="form-hint"
                    style={{
                        marginBottom: 'var(--space-3)',
                        padding: 'var(--space-3)',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--color-accent, #6cf)',
                        background: 'color-mix(in srgb, var(--color-accent, #6cf) 12%, transparent)',
                    }}
                    role="status"
                >
                    <strong>Режим: автоподбор бумаг.</strong> Поле тикеров пустое — список инструментов строится по конвейеру DMS и
                    снимку рынка для <strong>выбранного робота</strong> (как в «Проверить кеш» / превью pipeline). Нужен робот в блоке
                    «Параметры робота»; учитываются фильтры и режим ALL/ANY на этой странице.
                </div>
            )}
            <div className="form-row" style={{ flexWrap: 'wrap', gap: 'var(--space-3)' }}>
                <div className="form-group" style={{ flex: '1 1 220px', marginBottom: 0 }}>
                    <label className="form-label">Тикеры (необязательно)</label>
                    <input
                        className="form-input"
                        value={moexTickers}
                        onChange={(e) => setMoexTickers(e.target.value)}
                        placeholder="Пусто = автоподбор по DMS; иначе SBER, GAZP…"
                    />
                </div>
                <div className="form-group" style={{ width: 120, marginBottom: 0 }}>
                    <label className="form-label">Доска</label>
                    <input className="form-input" value={moexBoard} onChange={(e) => setMoexBoard(e.target.value.toUpperCase())} />
                </div>
                <div className="form-group" style={{ width: 100, marginBottom: 0 }}>
                    <label className="form-label">Интервал</label>
                    <Select
                        options={MOEX_CACHE_INTERVALS.map((v) => ({ value: v, label: v }))}
                        value={moexInterval}
                        onChange={(v) => setMoexInterval((v as MoexCacheInterval) || '10m')}
                    />
                </div>
            </div>
            {moexIntervalMismatch && (
                <div className="form-hint color-down" style={{ marginBottom: 'var(--space-3)' }}>
                    Интервал кеша MOEX ({moexInterval}) не совпадает с рекомендуемым под выбранный интервал сигналов ({suggestedMoexForSignal}).
                    Бэктест сначала читает общий кеш (ARCH-01) с тем же шагом, что и job.{' '}
                    <Button size="sm" variant="ghost" type="button" onClick={alignMoexIntervalToSignal}>
                        Подставить {suggestedMoexForSignal}
                    </Button>
                </div>
            )}
            <div className="testing-moex-cache-actions">
                <Button loading={moexJobSubmitting} onClick={startMoexCandleLoad}>
                    Запустить загрузку (job)
                </Button>
                <Button variant="secondary" loading={moexPreviewLoading} onClick={previewMoexCache}>
                    Проверить кеш (GET candles)
                </Button>
                {(moexJobId || moexJobStatus || moexJobError) && (
                    <Button variant="ghost" onClick={clearMoexCandleJob}>
                        Сбросить статус job
                    </Button>
                )}
            </div>
            {moexPreview && (
                <div className="form-hint testing-moex-preview" style={{ marginTop: 'var(--space-3)' }}>
                    Снимок кеша: баров в ответе — {moexPreview.bars}, записей о пробелах (gaps) — {moexPreview.gaps}.
                </div>
            )}
            {moexJobError && (
                <div className="form-hint color-down" style={{ marginTop: 'var(--space-2)' }}>
                    {moexJobError}
                </div>
            )}
            {moexJobId && (
                <div className="testing-moex-job-panel" style={{ marginTop: 'var(--space-4)' }}>
                    <div className="form-hint" style={{ marginBottom: 8 }}>
                        Job ID: <code style={{ wordBreak: 'break-all' }}>{moexJobId}</code>
                    </div>
                    {!moexJobStatus && !moexJobError && <Skeleton height="12px" count={3} />}
                    {moexJobStatus && (
                        <>
                            <div className="testing-moex-job-meta">
                                <span
                                    className={`badge ${moexJobStatus.status === 'completed' ? 'badge--up' : moexJobStatus.status === 'failed' ? 'badge--down' : 'badge--cyan'}`}
                                >
                                    {moexJobStatus.status}
                                </span>
                                <span className="form-hint">
                                    {moexJobStatus.tickers_done}/{moexJobStatus.tickers_total} тикеров · баров записано:{' '}
                                    {moexJobStatus.bars_written}
                                    {moexJobStatus.eta_seconds != null &&
                                    (moexJobStatus.status === 'queued' || moexJobStatus.status === 'running')
                                        ? ` · ETA ~${Math.max(0, Math.ceil(moexJobStatus.eta_seconds))} с`
                                        : ''}
                                </span>
                            </div>
                            <div className="testing-moex-job-progress" aria-hidden>
                                <div
                                    className="testing-moex-job-progress__bar"
                                    style={{
                                        width: `${Math.min(100, Math.max(0, moexJobStatus.progress_percent))}%`,
                                    }}
                                />
                            </div>
                            {moexJobStatus.message && (
                                <div className="form-hint" style={{ marginTop: 8 }}>{moexJobStatus.message}</div>
                            )}
                            {moexJobStatus.error && (
                                <div className="form-hint color-down" style={{ marginTop: 8 }}>{moexJobStatus.error}</div>
                            )}
                        </>
                    )}
                </div>
            )}
        </Card>
    )
}
