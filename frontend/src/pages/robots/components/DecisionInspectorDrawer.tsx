import React, { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { IntentLifecycleBlock } from '@/pages/robots/components/IntentLifecycleBlock'
import { tradeReasonLabel } from '@/pages/robots/tradeReasonLabels'
import { fmtMoney } from '@/pages/robots/formatters'
import type { BacktestDecisionPacket, BacktestExecutionEvent } from '@/types/robot'

export type DecisionInspectorDrawerProps = {
    open: boolean
    onClose: () => void
    packet: BacktestDecisionPacket | null
    loading?: boolean
    runId?: number | null
    seedExecutionEvents?: BacktestExecutionEvent[] | null
    onPrevTrade?: () => void
    onNextTrade?: () => void
    onLifecycleStepClick?: (event: BacktestExecutionEvent) => void
    onJumpToPriceChart?: () => void
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="robots-inspector__field">
            <dt>{label}</dt>
            <dd>{children}</dd>
        </div>
    )
}

function fmtTs(raw: string | null | undefined): string {
    if (!raw) return '—'
    const d = new Date(raw)
    if (!Number.isFinite(d.getTime())) return String(raw)
    return d.toLocaleString('ru-RU')
}

function fmtMetric(value: unknown): string {
    if (value == null) return '—'
    if (typeof value === 'number') {
        return Number.isInteger(value) ? String(value) : value.toLocaleString('ru-RU', {
            maximumFractionDigits: 4,
        })
    }
    if (typeof value === 'boolean') return value ? 'да' : 'нет'
    return String(value)
}

function isEditableTarget(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false
    return Boolean(target.closest('input, textarea, select, [contenteditable="true"]'))
}

export function DecisionInspectorDrawer({
    open,
    onClose,
    packet,
    loading,
    runId,
    seedExecutionEvents,
    onPrevTrade,
    onNextTrade,
    onLifecycleStepClick,
    onJumpToPriceChart,
}: DecisionInspectorDrawerProps) {
    const closeBtnRef = useRef<HTMLButtonElement | null>(null)
    const restoreFocusRef = useRef<HTMLElement | null>(null)

    useEffect(() => {
        if (!open) return
        const active = document.activeElement
        restoreFocusRef.current = active instanceof HTMLElement ? active : null
        const t = window.setTimeout(() => closeBtnRef.current?.focus(), 0)

        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                e.preventDefault()
                onClose()
                return
            }
            if (isEditableTarget(e.target)) return
            if (e.key === 'j' || e.key === 'J') {
                onNextTrade?.()
                return
            }
            if (e.key === 'k' || e.key === 'K') {
                onPrevTrade?.()
            }
        }
        document.addEventListener('keydown', onKey)
        const prev = document.body.style.overflow
        document.body.style.overflow = 'hidden'
        return () => {
            window.clearTimeout(t)
            document.removeEventListener('keydown', onKey)
            document.body.style.overflow = prev
            restoreFocusRef.current?.focus?.()
            restoreFocusRef.current = null
        }
    }, [open, onClose, onNextTrade, onPrevTrade])

    if (!open) return null
    if (typeof document === 'undefined') return null

    const cycleMissing = Boolean(packet && !packet.cycle_id)
    const seedEvents =
        seedExecutionEvents
        ?? (packet as BacktestDecisionPacket & { execution_events?: BacktestExecutionEvent[] } | null)
            ?.execution_events
        ?? null

    return createPortal(
        <div className="robots-inspector" role="presentation">
            <button
                type="button"
                className="robots-inspector__backdrop"
                aria-label="Закрыть инспектор"
                onClick={onClose}
            />
            <aside
                className="robots-inspector__panel"
                role="dialog"
                aria-modal="true"
                aria-label="Инспектор решения"
            >
                <header className="robots-inspector__head">
                    <div>
                        <span className="robots-inspector__eyebrow">DECISION</span>
                        <h3 className="robots-inspector__title">Решение движка</h3>
                    </div>
                    <button
                        ref={closeBtnRef}
                        type="button"
                        className="robots-inspector__close"
                        onClick={onClose}
                        aria-label="Закрыть"
                    >
                        ×
                    </button>
                </header>

                <div className="robots-inspector__body">
                    {!packet ? (
                        <p className="robots-inspector__empty">
                            Выберите сделку на графике или строку в таблице — покажем решение движка:
                            вход, выход, отказ или отложение.
                        </p>
                    ) : (
                        <>
                            {loading ? (
                                <p className="robots-hint robots-inspector__loading">
                                    Загрузка цикла…
                                </p>
                            ) : null}
                            <dl className="robots-inspector__dl">
                                <Field label="cycle_id">
                                    {packet.cycle_id ? (
                                        <span className="mono">{packet.cycle_id}</span>
                                    ) : (
                                        <span className="robots-hint">Связь с циклом недоступна</span>
                                    )}
                                </Field>
                                <Field label="Время сигнала">{fmtTs(packet.signal_time)}</Field>
                                <Field label="Время бара / fill">{fmtTs(packet.bar_time)}</Field>
                                <Field label="Тикер">
                                    {packet.ticker || packet.figi || '—'}
                                </Field>
                                <Field label="kind">
                                    <span className="robots-scan-reason">
                                        {tradeReasonLabel(packet.kind)}
                                    </span>
                                    {packet.kind ? (
                                        <span className="mono robots-inspector__code"> {packet.kind}</span>
                                    ) : null}
                                </Field>
                                <Field label="Сторона">{packet.side || '—'}</Field>
                                <Field label="Статус">{packet.status || '—'}</Field>
                                <Field label="Причина стратегии">
                                    <span className="robots-scan-reason">
                                        {tradeReasonLabel(packet.strategy_reason)}
                                    </span>
                                    {packet.strategy_reason ? (
                                        <span className="mono robots-inspector__code">
                                            {' '}
                                            {packet.strategy_reason}
                                        </span>
                                    ) : null}
                                </Field>
                                {packet.decision_message ? (
                                    <Field label={packet.status === 'ignored' ? 'Почему сигнала нет' : 'Проверка условий'}>
                                        <span className="robots-scan-reason">
                                            {packet.decision_message}
                                        </span>
                                        {packet.decision_code ? (
                                            <span className="mono robots-inspector__code">
                                                {' '}{packet.decision_code}
                                            </span>
                                        ) : null}
                                    </Field>
                                ) : null}
                                {packet.decision_metrics && Object.keys(packet.decision_metrics).length > 0 ? (
                                    <Field label="Значения условий">
                                        <div className="robots-decision-metrics">
                                            {Object.entries(packet.decision_metrics).map(([key, value]) => (
                                                <span key={key} className="robots-chip robots-chip--static">
                                                    {key}: <span className="mono">{fmtMetric(value)}</span>
                                                </span>
                                            ))}
                                        </div>
                                    </Field>
                                ) : null}
                                <Field label="Отказ">
                                    {packet.reject_reason ? (
                                        <>
                                            <span className="robots-scan-reason">
                                                {tradeReasonLabel(packet.reject_reason)}
                                            </span>
                                            <span className="mono robots-inspector__code">
                                                {' '}
                                                {packet.reject_reason}
                                            </span>
                                        </>
                                    ) : (
                                        '—'
                                    )}
                                </Field>
                                <Field label="Кол-во">
                                    <span className="mono">
                                        {packet.quantity == null ? '—' : packet.quantity}
                                    </span>
                                </Field>
                                <Field label="Цена">
                                    <span className="mono">
                                        {packet.price == null ? '—' : fmtMoney(packet.price)}
                                    </span>
                                </Field>
                                <Field label="PnL">
                                    {(() => {
                                        const pnl = packet.pnl_net
                                        const tone = pnl == null ? 'neutral' : pnl >= 0 ? 'up' : 'down'
                                        return (
                                            <span className={`mono robots-pnl--${tone}`}>
                                                {pnl == null ? '—' : fmtMoney(pnl)}
                                            </span>
                                        )
                                    })()}
                                </Field>
                                <Field label="Связанные сделки">
                                    {packet.linked_trade_ids && packet.linked_trade_ids.length > 0 ? (
                                        <span className="mono">{packet.linked_trade_ids.join(', ')}</span>
                                    ) : (
                                        '—'
                                    )}
                                </Field>
                                <Field label="Исполнение">
                                    {packet.execution_note || 'Исполнение на открытии следующего бара'}
                                </Field>
                                {cycleMissing ? (
                                    <p className="robots-hint robots-inspector__gap">
                                        Связь с циклом недоступна — прогон без stamp cycle_id (старые данные).
                                    </p>
                                ) : null}
                            </dl>

                            <IntentLifecycleBlock
                                runId={runId ?? null}
                                cycleId={packet.cycle_id}
                                seedEvents={seedEvents}
                                onStepClick={onLifecycleStepClick}
                            />

                            {onJumpToPriceChart ? (
                                <button
                                    type="button"
                                    className="robots-chip robots-inspector__to-chart"
                                    onClick={onJumpToPriceChart}
                                >
                                    К графику цены
                                </button>
                            ) : null}
                        </>
                    )}
                </div>

                {(onPrevTrade || onNextTrade) && packet ? (
                    <footer className="robots-inspector__foot">
                        <button
                            type="button"
                            className="robots-chip"
                            disabled={!onPrevTrade}
                            onClick={onPrevTrade}
                        >
                            ← k
                        </button>
                        <button
                            type="button"
                            className="robots-chip"
                            disabled={!onNextTrade}
                            onClick={onNextTrade}
                        >
                            j →
                        </button>
                    </footer>
                ) : null}
            </aside>
        </div>,
        document.body,
    )
}
