/** Текст причины для строк daily_universe (ACCEPT / REJECT). */
export function formatDmsUniverseReason(row: {
    filter_result?: string
    reject_reason?: string | null
    applied_filters?: unknown
}): string {
    const status = String(row.filter_result || '').toUpperCase()
    if (status === 'ACCEPT' || status === 'ACCEPTED') {
        const af = row.applied_filters
        const n = Array.isArray(af)
            ? af.length
            : af && typeof af === 'object'
              ? Object.keys(af as object).length
              : 0
        return n > 0 ? `Одобрена · фильтров: ${n}` : 'Одобрена'
    }

    const raw = String(row.reject_reason || '').trim()
    const legacy: Record<string, string> = {
        'Not in allowed_figis': 'Не в списке разрешённых инструментов (universe)',
        'Outside trading hours': 'Вне торговых часов',
    }
    if (legacy[raw]) return legacy[raw]
    return raw || 'Отклонена'
}
