import React, { useMemo } from 'react'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { fmtMoney } from '@/pages/robots-v2/formatters'
import {
    normalizeHoldings,
    pickSnapshotByMode,
    snapshotTimeIso,
    snapshotsAreLegacyCountOnly,
    type HoldingsSampleMode,
} from '@/pages/robots-v2/backtestGlassBox'
import type { BacktestHoldingPosition, BacktestPortfolioSnapshot } from '@/types/robot'

type HoldingRow = BacktestHoldingPosition & { id: string }

type Props = {
    snapshots: BacktestPortfolioSnapshot[]
    sampleMode: HoldingsSampleMode
    onSampleModeChange: (mode: HoldingsSampleMode) => void
    markerTimeSec: number | null
    open?: boolean
    onOpenChange?: (open: boolean) => void
}

function fmtTs(raw: string | null): string {
    if (!raw) return '—'
    const d = new Date(raw)
    if (!Number.isFinite(d.getTime())) return raw
    return d.toLocaleString('ru-RU')
}

/** Zone L — holdings at sampled portfolio snapshot. */
export function BacktestHoldingsSection({
    snapshots,
    sampleMode,
    onSampleModeChange,
    markerTimeSec,
    open,
    onOpenChange,
}: Props) {
    const legacy = snapshotsAreLegacyCountOnly(snapshots)
    const snap = useMemo(
        () => pickSnapshotByMode(snapshots, sampleMode, markerTimeSec),
        [snapshots, sampleMode, markerTimeSec],
    )
    const { holdings, count } = normalizeHoldings(snap)
    const sampleIso = snap ? snapshotTimeIso(snap) : null

    const rows = useMemo<HoldingRow[]>(
        () => holdings.map((h, i) => ({
            ...h,
            id: String(h.ticker || h.figi || i),
        })),
        [holdings],
    )

    const columns = useMemo<Column<HoldingRow>[]>(() => [
        {
            key: 'ticker',
            header: 'Тикер',
            sortable: true,
            render: r => String(r.ticker || r.figi || '—'),
        },
        {
            key: 'side',
            header: 'Сторона',
            render: r => String(r.side || '—').toUpperCase(),
        },
        {
            key: 'qty',
            header: 'Кол-во',
            render: r => {
                const q = r.qty ?? r.quantity
                return <span className="mono">{q == null ? '—' : q}</span>
            },
        },
        {
            key: 'avg_entry',
            header: 'Вход',
            render: r => (
                <span className="mono">
                    {r.avg_entry == null ? '—' : fmtMoney(Number(r.avg_entry))}
                </span>
            ),
        },
        {
            key: 'mark',
            header: 'Mark',
            render: r => (
                <span className="mono">
                    {r.mark == null ? '—' : fmtMoney(Number(r.mark))}
                </span>
            ),
        },
        {
            key: 'notional',
            header: 'Нотионал',
            render: r => {
                const q = Number(r.qty ?? r.quantity ?? NaN)
                const m = Number(r.mark ?? NaN)
                if (!Number.isFinite(q) || !Number.isFinite(m)) return '—'
                return <span className="mono">{fmtMoney(q * m)}</span>
            },
        },
        {
            key: 'delta',
            header: 'Δ mark',
            render: r => {
                const entry = Number(r.avg_entry ?? NaN)
                const mark = Number(r.mark ?? NaN)
                if (!Number.isFinite(entry) || !Number.isFinite(mark) || entry === 0) return '—'
                const pct = ((mark - entry) / entry) * 100
                const tone = pct >= 0 ? 'up' : 'down'
                return (
                    <span className={`mono robots-v2-pnl--${tone}`}>
                        {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                    </span>
                )
            },
        },
    ], [])

    const sampleOptions: Array<{ value: HoldingsSampleMode; label: string }> = [
        { value: 'marker', label: 'У маркера' },
        { value: 'start', label: 'Начало' },
        { value: 'mid', label: 'Середина' },
        { value: 'end', label: 'Конец' },
    ]

    let body: React.ReactNode
    if (!snapshots.length) {
        body = <p className="robots-v2-hint">Нет снимков портфеля за прогон</p>
    } else if (legacy) {
        body = (
            <p className="robots-v2-hint">
                Детализация позиций недоступна для этого прогона
                {count > 0 ? ` · count ${count}` : ''}
            </p>
        )
    } else if (rows.length === 0) {
        body = <p className="robots-v2-hint">На этот момент позиций не было</p>
    } else {
        body = (
            <DataTable
                columns={columns}
                data={rows as Array<HoldingRow & Record<string, unknown>>}
                keyField="id"
                emptyText="На этот момент позиций не было"
                maxHeight={280}
                mobilePrimary={r => (
                    <div className="portfolio-mobile-split">
                        <strong>{String(r.ticker || r.figi || '—')}</strong>
                        <span className="mono">{r.qty ?? r.quantity ?? '—'}</span>
                    </div>
                )}
                mobileDetails={r =>
                    `${String(r.side || '—').toUpperCase()} · mark ${
                        r.mark == null ? '—' : fmtMoney(Number(r.mark))
                    }`
                }
            />
        )
    }

    return (
        <CollapsibleSection
            title={(
                <span className="dashboard-collapse__label">
                    <IconHoldings />
                    Позиции на {fmtTs(sampleIso)}
                </span>
            )}
            badge={
                <span className="robots-v2-hint">
                    {legacy ? 'нет деталей' : rows.length}
                    {sampleMode === 'marker' && markerTimeSec != null ? ' · у маркера' : ''}
                </span>
            }
            headerEnd={(
                <SegmentedControl
                    className="robots-v2-glass-holdings__sample"
                    aria-label="Момент снимка позиций"
                    options={sampleOptions}
                    value={sampleMode}
                    onChange={onSampleModeChange}
                />
            )}
            className="dashboard-assets-card robots-v2-glass-holdings"
            open={open}
            onOpenChange={onOpenChange}
            defaultOpen={false}
        >
            {body}
        </CollapsibleSection>
    )
}

function IconHoldings() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinejoin="round"
                d="M4 18V8l4 3 4-5 4 4 4-2v10H4z"
            />
        </svg>
    )
}
