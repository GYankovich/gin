/** Format screening timestamps for Live collapsible toggle: dd.mm HH:mm */
export function formatScreeningStamp(value?: string | Date | null): string {
    if (value == null || value === '') return '—'
    const d = value instanceof Date ? value : new Date(value)
    if (Number.isNaN(d.getTime())) return '—'
    const dd = String(d.getDate()).padStart(2, '0')
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    return `${dd}.${mm} ${hh}:${mi}`
}

export type ScreeningStatusLike = {
    status?: string | null
    started_at?: string | null
    finished_at?: string | null
    last_completed_at?: string | null
    universe_updated_at?: string | null
}

/** Text for CollapsibleSection badge: «Считается с …» / «Актуализирован в …». */
export function formatCryptoScreeningToggleLabel(status: ScreeningStatusLike | null | undefined): string | null {
    if (!status) return null
    const st = String(status.status || '').toLowerCase()
    if (st === 'queued' || st === 'running' || st === 'already_running') {
        const since = status.started_at || status.finished_at
        return `Считается с ${formatScreeningStamp(since)}`
    }
    const doneAt = status.last_completed_at || status.universe_updated_at || status.finished_at
    if (doneAt) {
        return `Актуализирован в ${formatScreeningStamp(doneAt)}`
    }
    if (st === 'failed') {
        return 'Ошибка screening'
    }
    return null
}

export function isCryptoScreeningInProgress(status: ScreeningStatusLike | null | undefined): boolean {
    const st = String(status?.status || '').toLowerCase()
    return st === 'queued' || st === 'running' || st === 'already_running'
}
