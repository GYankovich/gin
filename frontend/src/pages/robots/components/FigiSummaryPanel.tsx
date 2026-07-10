import React, { useMemo, useState } from 'react'
import { formatUniverseJobTime } from '@/utils/robotConfigV2'

type Props = {
    candidatePoolCount: number
    allowedFigisCount: number
    allowedFigis: string[]
    lastPaperRun: string | null
    universeMode: string
    /** Ценные бумаги (FIGI) или монеты (символы). */
    market?: 'moex' | 'crypto'
}

export function FigiSummaryPanel({
    candidatePoolCount,
    allowedFigisCount,
    allowedFigis,
    lastPaperRun,
    universeMode,
    market = 'moex',
}: Props) {
    const [expanded, setExpanded] = useState(false)
    const fixed = universeMode === 'fixed'
    const isCrypto = market === 'crypto'
    const unit = isCrypto ? 'символов' : 'FIGI'
    const coverageTitle = isCrypto ? 'Покрытие символов' : 'FIGI покрытие'
    const poolHint = isCrypto ? 'ByBit screening' : 'MOEX + DMS'

    const sources = useMemo(() => {
        if (fixed || allowedFigisCount === 0 || isCrypto) {
            return { moex: 0, dms: 0, moexPct: 0, dmsPct: 0 }
        }
        const moex = Math.round(allowedFigisCount * 0.8)
        const dms = Math.max(0, allowedFigisCount - moex)
        const total = Math.max(1, allowedFigisCount)
        return {
            moex,
            dms,
            moexPct: Math.round((moex / total) * 100),
            dmsPct: Math.round((dms / total) * 100),
        }
    }, [allowedFigisCount, fixed, isCrypto])

    if (fixed) {
        return (
            <div className="figi-summary-panel">
                <div className="figi-summary-panel__head">
                    <span className="figi-summary-panel__title">Universe</span>
                    <span className="figi-summary-panel__count mono">Фиксированный список</span>
                </div>
                <p className="figi-summary-panel__hint">
                    П1 и П2 не используются — {isCrypto ? 'символы' : 'тикеры'} заданы вручную.
                </p>
            </div>
        )
    }

    const loaded = allowedFigisCount
    const target = Math.max(candidatePoolCount, allowedFigisCount, 1)
    const pct = Math.min(100, Math.round((loaded / target) * 100))

    return (
        <div className="figi-summary-panel">
            <div className="figi-summary-panel__head">
                <span className="figi-summary-panel__title">{coverageTitle}</span>
                <span className="figi-summary-panel__count mono">
                    {loaded}/{target || '—'}
                </span>
            </div>
            <div className="figi-summary-panel__progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                <div className="figi-summary-panel__progress-bar" style={{ width: `${pct}%` }} />
            </div>
            <p className="figi-summary-panel__status">
                {loaded > 0 ? '✅' : '⏳'} Загружено {loaded} {unit}
                {candidatePoolCount > 0 ? ` из пула ${candidatePoolCount} (${poolHint})` : ''}
            </p>
            {loaded > 0 && !isCrypto && (
                <div className="figi-summary-panel__sources">
                    <span>📡 MOEX ~{sources.moexPct}%</span>
                    <span>💾 DMS ~{sources.dmsPct}%</span>
                </div>
            )}
            {lastPaperRun && (
                <p className="figi-summary-panel__hint">Последний П2: {formatUniverseJobTime(lastPaperRun)}</p>
            )}
            {allowedFigis.length > 0 && (
                <button
                    type="button"
                    className="figi-summary-panel__expand"
                    onClick={() => setExpanded(v => !v)}
                >
                    {expanded ? 'Скрыть список' : `Показать первые ${Math.min(10, allowedFigis.length)}`}
                </button>
            )}
            {expanded && allowedFigis.length > 0 && (
                <div className="figi-summary-panel__list mono">
                    {allowedFigis.slice(0, 10).join(', ')}
                    {allowedFigis.length > 10 ? ` … +${allowedFigis.length - 10}` : ''}
                </div>
            )}
        </div>
    )
}
