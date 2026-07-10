import React from 'react'
import type { RecommendationItem, RobotRecommendationsResponse } from '@/types/recommendations'
import { countApplicableChanges } from '@/pages/testing/recommendationApply'

const SEVERITY_LABEL: Record<string, string> = {
    critical: 'Критично',
    warning: 'Внимание',
    info: 'Совет',
}

const CATEGORY_LABEL: Record<string, string> = {
    strategy: 'Стратегия',
    params: 'Параметры',
    risk: 'Риск',
    backtest: 'Бэктест',
    live: 'Лайв',
    operational: 'Эксплуатация',
}

function severityClass(severity: string): string {
    if (severity === 'critical') return 'testing-rec--critical'
    if (severity === 'warning') return 'testing-rec--warning'
    return 'testing-rec--info'
}

function resolveRuleEngineMeta(data: RobotRecommendationsResponse | null): { version: string | null; enabled: boolean | null } {
    if (!data) return { version: null, enabled: null }
    for (const item of data.recommendations) {
        const evidence = item.evidence as Record<string, unknown>
        const version = typeof evidence?.rules_version === 'string' ? evidence.rules_version : null
        const enabled = typeof evidence?.rule_engine_enabled === 'boolean' ? evidence.rule_engine_enabled : null
        if (version != null || enabled != null) {
            return { version, enabled }
        }
    }
    return { version: null, enabled: null }
}

type RecRowProps = {
    item: RecommendationItem
    onApply?: (item: RecommendationItem) => void
    onDismiss?: (item: RecommendationItem) => void
    canApply?: (item: RecommendationItem) => boolean
}

function RecRow({ item, onApply, onDismiss, canApply }: RecRowProps) {
    const applicable = countApplicableChanges(item)
    const showApply = applicable > 0 && onApply != null

    return (
        <li className={`testing-rec-item ${severityClass(item.severity)}`}>
            <div className="testing-rec-item__head">
                <span className="testing-rec-item__severity">{SEVERITY_LABEL[item.severity] ?? item.severity}</span>
                <span className="testing-rec-item__category">{CATEGORY_LABEL[item.category] ?? item.category}</span>
            </div>
            <strong className="testing-rec-item__title">{item.title}</strong>
            <p className="testing-rec-item__message">{item.message}</p>
            {item.suggested_changes.length > 0 && (
                <ul className="testing-rec-item__changes">
                    {item.suggested_changes.map((ch) => (
                        <li key={`${ch.path}-${String(ch.suggested_value)}`}>
                            <code>{ch.path}</code>:{' '}
                            {ch.current_value != null ? String(ch.current_value) : '—'} →{' '}
                            <strong>{ch.suggested_value != null ? String(ch.suggested_value) : '—'}</strong>
                            {ch.reason ? ` (${ch.reason})` : ''}
                        </li>
                    ))}
                </ul>
            )}
            {(showApply || onDismiss) && (
                <div className="testing-rec-item__actions">
                    {showApply && (
                        <button
                            type="button"
                            className="btn btn--primary btn--sm"
                            disabled={canApply ? !canApply(item) : false}
                            onClick={() => onApply?.(item)}
                        >
                            Применить{applicable > 1 ? ` (${applicable})` : ''}
                        </button>
                    )}
                    {onDismiss && (
                        <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            onClick={() => onDismiss(item)}
                        >
                            Скрыть
                        </button>
                    )}
                </div>
            )}
        </li>
    )
}

function BacktestKpi({ data }: { data: RobotRecommendationsResponse }) {
    const best = data.best_backtest
    if (!best) return null
    return (
        <div className="testing-rec-kpi">
            <span>
                Лучший бэктест #{best.run_id}:{' '}
                {best.total_return_percent != null ? `${best.total_return_percent.toFixed(2)}%` : '—'}
                {best.max_drawdown_percent != null ? ` · DD ${best.max_drawdown_percent.toFixed(1)}%` : ''}
            </span>
            {data.live.metrics && (
                <span>
                    Лайв PnL:{' '}
                    {typeof data.live.metrics.total_pnl === 'number'
                        ? `${data.live.metrics.total_pnl.toFixed(0)} ₽`
                        : '—'}
                    {typeof data.live.metrics.win_rate === 'number'
                        ? ` · WR ${data.live.metrics.win_rate}%`
                        : ''}
                </span>
            )}
        </div>
    )
}

export interface TestingRecommendationsCardProps {
    robotId: number | null
    data: RobotRecommendationsResponse | null
    loading: boolean
    error: string | null
    onRefresh: () => void
    recommendations?: RecommendationItem[]
    onApply?: (item: RecommendationItem) => void
    onDismiss?: (item: RecommendationItem) => void
    onClearDismissed?: () => void
    dismissedCount?: number
    canApply?: (item: RecommendationItem) => boolean
    /** Без внешней обёртки card — заголовок в RecommendationsPanel. */
    embedded?: boolean
}

export function TestingRecommendationsCard({
    robotId,
    data,
    loading,
    error,
    onRefresh,
    recommendations,
    onApply,
    onDismiss,
    onClearDismissed,
    dismissedCount = 0,
    canApply,
    embedded = false,
}: TestingRecommendationsCardProps) {
    const ruleEngineMeta = resolveRuleEngineMeta(data)
    const visibleItems = recommendations ?? data?.recommendations ?? []

    if (!robotId) {
        const empty = <p className="testing-rec-empty">Выберите торгового робота</p>
        if (embedded) return empty
        return (
            <section className="card testing-rec-card">
                <h2 className="card__title">Рекомендации</h2>
                {empty}
            </section>
        )
    }

    const inner = (
        <>
            <div className="testing-rec-card__head">
                {!embedded && <h2 className="card__title">Рекомендации</h2>}
                <div className="testing-rec-card__head-actions">
                    {dismissedCount > 0 && onClearDismissed && (
                        <button type="button" className="btn btn--ghost btn--sm" onClick={onClearDismissed}>
                            Показать скрытые ({dismissedCount})
                        </button>
                    )}
                    <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        disabled={loading}
                        onClick={() => void onRefresh()}
                    >
                        {loading ? 'Загрузка…' : 'Обновить'}
                    </button>
                </div>
            </div>

            {error && <p className="testing-rec-error">{error}</p>}

            {data && !loading && (
                <>
                    <p className="testing-rec-meta">
                        {data.strategy_title ?? data.strategy} · проанализировано бэктестов:{' '}
                        {data.backtest_runs_analyzed}
                        {data.live.risk_events_7d > 0
                            ? ` · risk events (7д): ${data.live.risk_events_7d}`
                            : ''}
                    </p>
                    {(ruleEngineMeta.version != null || ruleEngineMeta.enabled != null) && (
                        <p className="testing-rec-meta">
                            rule-engine: {ruleEngineMeta.enabled === false ? 'off' : 'on'}
                            {ruleEngineMeta.version ? ` · rules ${ruleEngineMeta.version}` : ''}
                        </p>
                    )}
                    <BacktestKpi data={data} />
                </>
            )}

            {loading && !data && <p className="testing-rec-empty">Анализ бэктестов и лайва…</p>}

            {data && visibleItems.length === 0 && !loading && (
                <p className="testing-rec-empty">
                    {dismissedCount > 0
                        ? 'Все рекомендации скрыты — нажмите «Показать скрытые».'
                        : 'Явных рекомендаций нет — конфиг выглядит согласованным.'}
                </p>
            )}

            {visibleItems.length > 0 && (
                <ul className="testing-rec-list">
                    {visibleItems.map((item) => (
                        <RecRow
                            key={item.id}
                            item={item}
                            onApply={onApply}
                            onDismiss={onDismiss}
                            canApply={canApply}
                        />
                    ))}
                </ul>
            )}
        </>
    )

    if (embedded) {
        return <div className="testing-rec-card testing-rec-card--embedded">{inner}</div>
    }

    return <section className="card testing-rec-card">{inner}</section>
}
