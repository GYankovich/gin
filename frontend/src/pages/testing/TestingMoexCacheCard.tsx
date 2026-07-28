import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { TestingSectionState } from '@/pages/testing/TestingSectionState'
import type { MoexCandleJobState } from '@/pages/testing/hooks/useMoexCandleJobState'

type Props = {
    moex: MoexCandleJobState
}

/** Показываем не больше этого числа строк в выпадающем списке. */
const TQBR_VISIBLE_OPTIONS = 15

function filterTqbrSecids(all: string[], queryUpper: string, cap: number): string[] {
    if (!queryUpper) return all.slice(0, cap)
    const starts: string[] = []
    const includes: string[] = []
    for (const s of all) {
        if (s.startsWith(queryUpper)) {
            starts.push(s)
            if (starts.length >= cap) return starts
        }
    }
    for (const s of all) {
        if (!s.startsWith(queryUpper) && s.includes(queryUpper)) {
            includes.push(s)
            if (starts.length + includes.length >= cap) break
        }
    }
    return [...starts, ...includes].slice(0, cap)
}

function lastTickerToken(raw: string): string {
    const parts = raw.split(',')
    return (parts[parts.length - 1] ?? '').trim()
}

function valueAfterBulkPick(raw: string, picked: string[]): string {
    if (picked.length === 0) return raw
    const merged = picked.join(', ')
    const lastComma = raw.lastIndexOf(',')
    if (lastComma === -1) return merged
    const head = raw.slice(0, lastComma + 1)
    const spacer = raw[lastComma + 1] === ' ' ? ' ' : ' '
    return `${head}${spacer}${merged}`
}

export function TestingMoexCacheCard({ moex }: Props) {
    const {
        moexTickers,
        setMoexTickers,
        moexJobId,
        moexJobStatus,
        moexJobError,
        moexCoverage,
        tqbrSuggestSecids,
        startMoexCandleLoad,
        clearMoexCandleJob,
    } = moex
    const listboxId = useId().replace(/:/g, '')
    const wrapRef = useRef<HTMLDivElement>(null)
    const [open, setOpen] = useState(false)
    const [bulkSelected, setBulkSelected] = useState<Set<string>>(() => new Set())

    const token = useMemo(() => lastTickerToken(moexTickers).toUpperCase(), [moexTickers])
    const filtered = useMemo(
        () => filterTqbrSecids(tqbrSuggestSecids, token, TQBR_VISIBLE_OPTIONS),
        [tqbrSuggestSecids, token],
    )

    const close = useCallback(() => setOpen(false), [])

    useEffect(() => {
        if (!open) setBulkSelected(new Set())
    }, [open])

    useEffect(() => {
        if (!open) return
        setBulkSelected(new Set())
    }, [open, token, tqbrSuggestSecids])

    useEffect(() => {
        const onDocMouseDown = (e: MouseEvent) => {
            if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) close()
        }
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') close()
        }
        document.addEventListener('mousedown', onDocMouseDown)
        document.addEventListener('keydown', onKey)
        return () => {
            document.removeEventListener('mousedown', onDocMouseDown)
            document.removeEventListener('keydown', onKey)
        }
    }, [close])

    const toggleBulk = useCallback((secid: string) => {
        setBulkSelected(prev => {
            const next = new Set(prev)
            if (next.has(secid)) next.delete(secid)
            else next.add(secid)
            return next
        })
    }, [])

    const selectAllVisible = useCallback(() => {
        setBulkSelected(new Set(filtered))
    }, [filtered])

    const applyBulk = useCallback(() => {
        if (bulkSelected.size === 0) return
        const ordered = filtered.filter(s => bulkSelected.has(s))
        const rest = [...bulkSelected].filter(s => !ordered.includes(s))
        const picks = [...new Set([...ordered, ...rest].map(s => s.toUpperCase()))]
        setMoexTickers(valueAfterBulkPick(moexTickers, picks))
        close()
    }, [bulkSelected, close, filtered, moexTickers, setMoexTickers])

    const hasJobProgress = Boolean(moexJobId || moexJobStatus)
    const isJobRunning = moexJobStatus?.status === 'queued' || moexJobStatus?.status === 'running'
    const updatedAtText = moexJobStatus?.updated_at ? new Date(moexJobStatus.updated_at).toLocaleString('ru-RU') : null

    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card testing-moex-cache-card">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                ОБЩИЙ КЕШ СВЕЧЕЙ MOEX
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="form-row testing-moex-form-row">
                <div className="form-group testing-moex-form-row__tickers">
                    <label className="form-label" htmlFor={`testing-moex-tqbr-${listboxId}`}>
                        Тикеры
                    </label>
                    <div
                        ref={wrapRef}
                        className={`gin-select gin-select--md testing-moex-tqbr-combobox ${open ? 'gin-select--open' : ''}`}
                    >
                        <input
                            id={`testing-moex-tqbr-${listboxId}`}
                            className="gin-select__trigger"
                            value={moexTickers}
                            onChange={e => setMoexTickers(e.target.value)}
                            onFocus={() => {
                                if (tqbrSuggestSecids.length > 0) setOpen(true)
                            }}
                            onKeyDown={e => {
                                if (e.key === 'Escape') close()
                            }}
                            placeholder="SBER, GAZP… Подсказки TQBR (до 15 строк, чекбоксы + Добавить)"
                            autoComplete="off"
                            role="combobox"
                            aria-autocomplete="list"
                            aria-expanded={open}
                            aria-controls={open ? `testing-moex-tqbr-list-${listboxId}` : undefined}
                        />
                        {open && tqbrSuggestSecids.length > 0 && (
                            <div
                                id={`testing-moex-tqbr-list-${listboxId}`}
                                className="gin-select__dropdown"
                                role="group"
                                aria-label="Подсказки TQBR"
                            >
                                <div className="gin-select__options">
                                    {filtered.length === 0 && (
                                        <div className="gin-select__empty">
                                            {token ? 'Нет совпадений в TQBR' : 'Справочник пуст'}
                                        </div>
                                    )}
                                    {filtered.map(secid => (
                                        <label
                                            key={secid}
                                            className="gin-select__option testing-moex-tqbr-option"
                                            onMouseDown={e => e.preventDefault()}
                                        >
                                            <input
                                                type="checkbox"
                                                checked={bulkSelected.has(secid)}
                                                onChange={() => toggleBulk(secid)}
                                                aria-label={`Выбрать ${secid}`}
                                            />
                                            <span className="testing-moex-tqbr-option__text">{secid}</span>
                                        </label>
                                    ))}
                                </div>
                                {filtered.length > 0 && (
                                    <div className="testing-moex-tqbr-dropdown-footer">
                                        <button
                                            type="button"
                                            className="btn btn--ghost btn--sm"
                                            onMouseDown={e => e.preventDefault()}
                                            onClick={selectAllVisible}
                                        >
                                            Выбрать все ({filtered.length})
                                        </button>
                                        <button
                                            type="button"
                                            className="btn btn--primary btn--sm"
                                            disabled={bulkSelected.size === 0}
                                            onMouseDown={e => e.preventDefault()}
                                            onClick={applyBulk}
                                        >
                                            Добавить выбранные ({bulkSelected.size})
                                        </button>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
            {moexCoverage && moexCoverage.items.length > 0 && (
                <div className="testing-moex-coverage testing-form-hint-top-lg" role="region" aria-label="Сводка покрытия shared_market_candles">
                    <div className="form-hint testing-form-hint-bottom-sm">
                        Сводка покрытия (БД): доска {moexCoverage.board}, интервал {moexCoverage.interval}
                    </div>
                    <div className="testing-moex-coverage-table-wrap">
                        <table className="testing-moex-coverage-table">
                            <thead>
                                <tr>
                                    <th>Тикер</th>
                                    <th>Баров</th>
                                    <th>От</th>
                                    <th>До</th>
                                </tr>
                            </thead>
                            <tbody>
                                {moexCoverage.items.map(row => (
                                    <tr key={row.ticker}>
                                        <td>{row.ticker}</td>
                                        <td>{row.bucket_count}</td>
                                        <td>{row.min_bucket_start ? new Date(row.min_bucket_start).toLocaleString('ru-RU') : '—'}</td>
                                        <td>{row.max_bucket_start ? new Date(row.max_bucket_start).toLocaleString('ru-RU') : '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
            {moexJobError && hasJobProgress && (
                <TestingSectionState
                    title="MOEX CACHE JOB"
                    message={`Job продолжается с ошибкой: ${moexJobError}`}
                    variant="partial"
                    actionLabel="Повторить загрузку"
                    onAction={startMoexCandleLoad}
                    compact
                />
            )}
            {moexJobError && !hasJobProgress && (
                <TestingSectionState
                    title="MOEX CACHE JOB"
                    message={moexJobError}
                    variant="error"
                    actionLabel="Повторить загрузку"
                    onAction={startMoexCandleLoad}
                    compact
                />
            )}
            {moexJobId && (
                <div className="testing-moex-job-panel testing-form-hint-top-lg">
                    <div className="form-hint testing-form-hint-bottom-sm testing-moex-job-id-row">
                        <span>
                            Job ID: <code className="testing-break-word">{moexJobId}</code>
                        </span>
                        <button
                            type="button"
                            className="btn btn--ghost btn--sm pipeline-action-btn pipeline-action-btn--reset"
                            onClick={clearMoexCandleJob}
                        >
                            Сбросить статус job
                        </button>
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
                                {updatedAtText && (
                                    <span className="form-hint testing-moex-job-meta__updated">Обновлено: {updatedAtText}</span>
                                )}
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
                                <div className="form-hint testing-form-hint-top-sm">{moexJobStatus.message}</div>
                            )}
                            {isJobRunning && (
                                <div className="form-hint testing-form-hint-top-sm testing-moex-job-progress-hint">
                                    Загрузка выполняется дольше 1.5 сек — прогресс обновляется автоматически.
                                </div>
                            )}
                            {moexJobStatus.error && (
                                <div className="form-hint color-down testing-form-hint-top-sm">{moexJobStatus.error}</div>
                            )}
                        </>
                    )}
                </div>
            )}
        </Card>
    )
}
