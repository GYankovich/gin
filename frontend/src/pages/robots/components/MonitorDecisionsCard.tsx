import React, { useMemo, useState } from 'react'
import { Card } from '@/components/ui/Card'
import {
    fmtContextValue,
    MonitorContextPanel,
} from '@/pages/robots/components/MonitorContextPanel'
import { MonitorTableViewport } from '@/pages/robots/components/MonitorTableViewport'
import {
    decisionCodeLabel,
    decisionMessageRu,
    fmtOrderClockSeconds,
} from '@/pages/robots/monitorUtils'

type MonitorDecisionsCardProps = {
    decisions: Array<Record<string, unknown>>
    bare?: boolean
    /** Compact feed limit. Defaults to 12. Ignored in history mode when null. */
    limit?: number | null
    /** feed = monitor list; history = table + context inspector */
    mode?: 'feed' | 'history'
    title?: string | null
    emptyTitle?: string
    emptySub?: string
    ariaLabel?: string
    className?: string
}

type HistoryDecisionRow = {
    id: string
    time: string
    ticker: string
    stage: string
    outcome: string
    code: string
    codeRaw: string
    message: string
    context: Record<string, unknown>
    contextKeys: number
    cycleId: string
}

function stageLabel(stage: string): string {
    switch (String(stage || '').toLowerCase()) {
        case 'risk':
            return 'Риск'
        case 'strategy':
            return 'Стратегия'
        case 'execution':
            return 'Исполнение'
        case 'universe':
            return 'Пул'
        case 'cycle':
            return 'Цикл'
        default:
            return stage || '—'
    }
}

function outcomeLabel(outcome: string): string {
    switch (String(outcome || '').toLowerCase()) {
        case 'allow':
        case 'allowed':
            return 'Разрешено'
        case 'block':
        case 'blocked':
            return 'Блок'
        case 'skip':
        case 'skipped':
            return 'Пропуск'
        case 'enter':
            return 'Вход'
        case 'exit':
            return 'Выход'
        case 'hold':
            return 'Держим'
        case 'info':
            return 'Инфо'
        default:
            return outcome || '—'
    }
}

function toHistoryRow(raw: Record<string, unknown>, index: number): HistoryDecisionRow {
    const tickerRaw = raw.ticker != null ? String(raw.ticker).toUpperCase() : ''
    const code = String(raw.code ?? raw.decision_code ?? '').trim()
    const msg = decisionMessageRu(raw.message ?? raw.decision_message, tickerRaw || undefined)
    const message = tickerRaw && msg.startsWith(`${tickerRaw} · `)
        ? msg.slice(tickerRaw.length + 3)
        : msg
    const created = raw.createdAt ?? raw.created_at
    const ctxRaw = raw.context
    const context = (ctxRaw && typeof ctxRaw === 'object' && !Array.isArray(ctxRaw))
        ? ctxRaw as Record<string, unknown>
        : {}
    return {
        id: String(raw.id ?? `${code}-${index}`),
        time: fmtOrderClockSeconds(created != null ? String(created) : null),
        ticker: tickerRaw || '—',
        stage: stageLabel(String(raw.stage || '')),
        outcome: outcomeLabel(String(raw.outcome || '')),
        code: decisionCodeLabel(code),
        codeRaw: code,
        message: message || '—',
        context,
        contextKeys: Object.keys(context).length,
        cycleId: String(raw.cycleId ?? raw.cycle_id ?? ''),
    }
}

/**
 * Decisions — compact feed on Лайв, history blotter + context on История.
 */
export function MonitorDecisionsCard({
    decisions,
    bare = false,
    limit = 12,
    mode = 'feed',
    title = 'Решения',
    emptyTitle,
    emptySub,
    ariaLabel = 'История решений',
    className = '',
}: MonitorDecisionsCardProps) {
    const [selectedId, setSelectedId] = useState<string | null>(null)

    const historyRows = useMemo(() => {
        if (mode !== 'history') return []
        const mapped = (decisions || []).map((d, i) => toHistoryRow(d, i))
        if (limit == null) return mapped
        return mapped.slice(0, limit)
    }, [decisions, mode, limit])

    const selected = useMemo(
        () => historyRows.find(r => r.id === selectedId) ?? null,
        [historyRows, selectedId],
    )

    if (mode === 'history') {
        const resolvedEmpty = emptyTitle ?? 'Нет решений за период'
        const resolvedSub = emptySub
            ?? 'Робот ещё не писал audit-решения в этом окне. Сдвиньте даты или дождитесь цикла.'

        const body = historyRows.length === 0 ? (
            <div className="robots-monitor-empty">
                <p className="robots-monitor-empty__sub"><b>{resolvedEmpty}</b></p>
                {resolvedSub ? <p className="robots-monitor-empty__sub">{resolvedSub}</p> : null}
            </div>
        ) : (
            <div className={`robots-logs-split${selected ? ' robots-logs-split--open' : ''}`}>
                <div className="robots-logs-split__table">
                    <MonitorTableViewport
                        ariaLabel={ariaLabel}
                        syncKey={historyRows.map(r => r.id).join('|')}
                        renderHead={() => (
                            <tr>
                                <th>Время</th>
                                <th>Тикер</th>
                                <th>Код</th>
                                <th>Причина</th>
                            </tr>
                        )}
                        bodyRows={historyRows.map(row => (
                            <tr
                                key={row.id}
                                className={selectedId === row.id ? 'robots-table__row--active' : undefined}
                                onClick={() => setSelectedId(selectedId === row.id ? null : row.id)}
                                style={{ cursor: 'pointer' }}
                            >
                                <td className="mono">{row.time}</td>
                                <td>
                                    <b className="robots-monitor-day-trades__tk">{row.ticker}</b>
                                </td>
                                <td title={row.codeRaw}>{row.code}</td>
                                <td className="robots-monitor-day-trades__muted" title={row.message}>
                                    {row.message}
                                </td>
                            </tr>
                        ))}
                    />
                </div>
                {selected ? (
                    <MonitorContextPanel
                        title={`${selected.ticker} · ${selected.code}`}
                        onClose={() => setSelectedId(null)}
                        meta={[
                            { label: 'Время', value: <span className="mono">{selected.time}</span> },
                            { label: 'Этап / исход', value: `${selected.stage} · ${selected.outcome}` },
                            { label: 'Сообщение', value: selected.message },
                            ...(selected.cycleId
                                ? [{ label: 'Цикл', value: <span className="mono">{selected.cycleId}</span> }]
                                : []),
                        ]}
                        blocks={
                            selected.contextKeys > 0
                                ? Object.entries(selected.context).map(([key, value]) => ({
                                    label: key,
                                    body: <pre className="robots-log-payload">{fmtContextValue(value)}</pre>,
                                }))
                                : [{
                                    label: 'Контекст',
                                    body: <p className="robots-hint">У этого решения нет доп. контекста.</p>,
                                }]
                        }
                    />
                ) : null}
            </div>
        )

        if (bare) {
            return <div className={`robots-monitor-day-trades robots-monitor-decisions ${className}`.trim()}>{body}</div>
        }

        return (
            <Card className={`dashboard-assets-card robots-monitor-day-trades robots-monitor-decisions ${className}`.trim()}>
                {title != null ? (
                    <div className="dashboard-assets-card__head">
                        <h3 className="dashboard-panel-title">
                            {title}
                            {historyRows.length > 0 ? (
                                <span className="robots-hint"> · {historyRows.length}</span>
                            ) : null}
                        </h3>
                    </div>
                ) : null}
                {body}
            </Card>
        )
    }

    const shown = limit == null ? decisions : decisions.slice(0, limit)
    const feedBody = shown.length === 0 ? (
        <p className="dashboard-empty">{emptyTitle ?? 'Пока нет решений риска'}</p>
    ) : (
        <ul className="robots-event-list robots-event-list--compact">
            {shown.map((d, i) => (
                <li key={i}>
                    <strong>{decisionCodeLabel(d.code)}</strong>
                    <span className="robots-monitor-decisions__msg">
                        {' '}{decisionMessageRu(d.message, d.ticker)}
                    </span>
                </li>
            ))}
        </ul>
    )

    if (bare) {
        return <div className={`robots-monitor-decisions ${className}`.trim()}>{feedBody}</div>
    }

    return (
        <Card className={`dashboard-assets-card robots-monitor-decisions ${className}`.trim()}>
            {title != null ? (
                <div className="dashboard-assets-card__head">
                    <h3 className="dashboard-panel-title">{title}</h3>
                    {decisions.length > 0 && limit != null ? (
                        <span className="robots-hint">{Math.min(decisions.length, limit)}</span>
                    ) : null}
                </div>
            ) : null}
            {feedBody}
        </Card>
    )
}
