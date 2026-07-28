import React from 'react'
import { Card } from '@/components/ui/Card'

export type MoexExtendedPanelProps = {
    universeRefreshMinutes: number
    onUniverseRefreshMinutesChange: (v: number) => void
    onConfigDirty: () => void
    className?: string
}

/** MOEX-only: авто-пересбор universe (сессия и НДФЛ — в блоках 2 и 4). */
export function MoexExtendedPanel({
    universeRefreshMinutes,
    onUniverseRefreshMinutesChange,
    onConfigDirty,
    className = '',
}: MoexExtendedPanelProps) {
    const dirty = () => onConfigDirty()

    return (
        <Card className={`mb-6 cyber-form-card testing-cyber-card testing-moex-extended-panel ${className}`.trim()}>
            <div className="testing-moex-extended-panel__grid">
                <div className="form-group testing-form-group-flat">
                    <label className="form-label">Авто-пересбор universe (мин, 0 = выкл)</label>
                    <input
                        className="form-input"
                        type="number"
                        min={0}
                        max={1440}
                        step={5}
                        value={universeRefreshMinutes}
                        onChange={e => {
                            const n = Math.max(0, Math.min(1440, Number(e.target.value || 0)))
                            onUniverseRefreshMinutesChange(Number.isFinite(n) ? n : 0)
                            dirty()
                        }}
                    />
                </div>
            </div>
        </Card>
    )
}
