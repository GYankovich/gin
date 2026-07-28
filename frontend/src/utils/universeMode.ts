export type UniverseMode = 'fixed' | 'dms_pipeline' | 'tqbr_scan'

export type CryptoUniverseMode = 'fixed' | 'auto'

export const CRYPTO_UNIVERSE_MODE_OPTIONS: { value: CryptoUniverseMode; label: string; hint: string }[] = [
    {
        value: 'auto',
        label: 'Auto-screening',
        hint: 'Отбор пар ByBit по объёму и спреду (нужен API token)',
    },
    {
        value: 'fixed',
        label: 'Фиксированные символы',
        hint: 'Только указанные пары (allowed_symbols)',
    },
]

export const UNIVERSE_MODE_OPTIONS: { value: UniverseMode; label: string; hint: string }[] = [
    {
        value: 'fixed',
        label: 'Фиксированный список',
        hint: 'Только указанные тикеры TQBR — без DMS pipeline',
    },
    {
        value: 'dms_pipeline',
        label: 'DMS pipeline',
        hint: 'Отбор по фильтрам на snapshot MOEX (как в бэктесте)',
    },
    {
        value: 'tqbr_scan',
        label: 'Вся TQBR',
        hint: 'Все торгуемые бумаги board TQBR без pipeline-фильтров',
    },
]

/** Опции для настроек торгового робота (v2: MOEX П1 + DMS П2). */
export const TRADING_UNIVERSE_MODE_OPTIONS: { value: UniverseMode; label: string; hint: string }[] = [
    {
        value: 'dms_pipeline',
        label: 'MOEX + DMS',
        hint: 'П1 — скрининг по свечам MOEX, П2 — фильтры снапшота и allowed_figis',
    },
    {
        value: 'fixed',
        label: 'Фиксированный список',
        hint: 'Только заданные тикеры, без П1/П2 pipeline',
    },
]

export function normalizeUniverseMode(raw: unknown): UniverseMode {
    const v = String(raw || '').trim().toLowerCase()
    if (v === 'fixed' || v === 'dms_pipeline' || v === 'tqbr_scan') return v
    return 'dms_pipeline'
}

export function normalizeCryptoUniverseMode(raw: unknown): CryptoUniverseMode {
    const v = String(raw || '').trim().toLowerCase()
    if (v === 'fixed' || v === 'auto') return v
    return 'auto'
}

export function parseFixedTickersInput(text: string): string[] {
    return [...new Set(
        text
            .split(/[\s,;]+/)
            .map(s => s.trim().toUpperCase())
            .filter(Boolean),
    )].sort()
}

export function formatFixedTickers(tickers: string[]): string {
    return (tickers || []).join(', ')
}

export function universeModeLabel(mode: UniverseMode | string | undefined): string {
    return UNIVERSE_MODE_OPTIONS.find(o => o.value === normalizeUniverseMode(mode))?.label ?? 'DMS pipeline'
}
