import type { TradePipelineItem } from './tradePipeline'

interface TradePipelineFeedProps {
    items: TradePipelineItem[]
    maxHeight?: string
}

function stageClass(active: boolean, kind?: string): string {
    if (!active) return 'live-pipeline__stage live-pipeline__stage--idle'
    if (kind === 'failed' || kind === 'error' || kind === 'rejected') {
        return 'live-pipeline__stage live-pipeline__stage--bad'
    }
    if (kind === 'skipped' || kind === 'cancelled') {
        return 'live-pipeline__stage live-pipeline__stage--muted'
    }
    if (kind === 'filled' || kind === 'open' || kind === 'partial') {
        return 'live-pipeline__stage live-pipeline__stage--ok'
    }
    return 'live-pipeline__stage live-pipeline__stage--active'
}

export function TradePipelineFeed({ items, maxHeight = '220px' }: TradePipelineFeedProps) {
    return (
        <div className="live-pipeline" style={{ maxHeight }}>
            {items.length === 0 && (
                <div className="event-feed__empty">Нет событий в ленте</div>
            )}
            {items.map(item => {
                const sideClass = item.side === 'buy'
                    ? 'live-pipeline__row--buy'
                    : item.side === 'sell'
                        ? 'live-pipeline__row--sell'
                        : ''
                return (
                    <div key={item.id} className={`live-pipeline__row ${sideClass}`}>
                        <div className="live-pipeline__head">
                            <span className="live-pipeline__time mono">{item.time}</span>
                            <span className={`live-pipeline__side live-pipeline__side--${item.side}`}>
                                {(item.side || 'info').toUpperCase()}
                            </span>
                            <span className="live-pipeline__ticker mono">{item.ticker || item.figi || '—'}</span>
                        </div>
                        <div className="live-pipeline__flow" aria-label="Сигнал → Заявка → Результат">
                            <div className={stageClass(!!item.signal)}>
                                <span className="live-pipeline__stage-value mono">
                                    {item.signal?.label || '—'}
                                </span>
                            </div>
                            <span className="live-pipeline__arrow" aria-hidden>→</span>
                            <div className={stageClass(!!item.order, item.order?.status)}>
                                <span className="live-pipeline__stage-value mono">
                                    {item.order?.label || '—'}
                                </span>
                            </div>
                            <span className="live-pipeline__arrow" aria-hidden>→</span>
                            <div className={stageClass(!!item.result, item.result?.kind)}>
                                <span className="live-pipeline__stage-value mono" title={item.result?.reason || undefined}>
                                    {item.result?.label || '—'}
                                    {item.result?.reason
                                        ? ` · ${item.result.reason.length > 48
                                            ? `${item.result.reason.slice(0, 48)}…`
                                            : item.result.reason}`
                                        : ''}
                                </span>
                            </div>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}
