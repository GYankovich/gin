/** Shared formatters for Robots V2 pages. */

/** Resolve a CSS custom property for canvas APIs that need concrete hex/rgb. */
export function readCssColor(varName: string, fallback: string): string {
    if (typeof window === 'undefined' || typeof document === 'undefined') return fallback
    const raw = getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
    return raw || fallback
}

export function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    return err?.message || 'Ошибка'
}

export function fmtMoney(v: number, digits = 2): string {
    return v.toLocaleString('ru-RU', { maximumFractionDigits: digits })
}

export function fmtNum(v: unknown, digits = 2): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return '—'
    return n.toLocaleString('ru-RU', { maximumFractionDigits: digits })
}

export function fmtPct(v: number | null | undefined): string {
    if (v == null || !Number.isFinite(v)) return '—'
    return `${v.toLocaleString('ru-RU', { maximumFractionDigits: 2, signDisplay: 'exceptZero' })}%`
}

export function fmtPrice(v: unknown, digits = 2): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return '—'
    return n.toLocaleString('ru-RU', { maximumFractionDigits: digits })
}

export function fmtTime(ts: string | null | undefined): string {
    if (!ts) return '—'
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return String(ts)
    return d.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    })
}

export function fmtDate(iso: string | null | undefined): string {
    if (!iso) return '—'
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return iso
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    })
}

export function fmtDateTimeShort(iso: string): string {
    const t = new Date(iso).getTime()
    if (Number.isNaN(t)) return iso
    return new Date(t).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    })
}

/** Relative age for fleet sync captions (RU). */
export function fmtSyncAge(iso: string | null | undefined): string {
    if (!iso) return '—'
    const t = new Date(iso).getTime()
    if (Number.isNaN(t)) return String(iso)
    const sec = Math.max(0, Math.round((Date.now() - t) / 1000))
    if (sec < 60) return `${sec} с назад`
    const min = Math.round(sec / 60)
    if (min < 60) return `${min} мин назад`
    const hrs = Math.round(min / 60)
    if (hrs < 48) return `${hrs} ч назад`
    return fmtDateTimeShort(iso)
}

/** User-facing session / run status labels (RU). */
export function sessionStateLabel(state: string | null | undefined): string {
    const s = String(state || '').toUpperCase()
    const map: Record<string, string> = {
        RUNNING: 'В работе',
        STOPPING: 'Остановка',
        STOPPED: 'Остановлен',
        IDLE: 'Ожидание',
        ERROR: 'Ошибка',
        FAILED: 'Ошибка',
        SYNCING: 'Синхронизация',
        STARTING: 'Запуск',
        COMPLETED: 'Завершён',
        SUCCESS: 'Успех',
        CANCELLED: 'Отменён',
        CANCELED: 'Отменён',
        QUEUED: 'В очереди',
    }
    return map[s] || (state ? String(state) : '—')
}
