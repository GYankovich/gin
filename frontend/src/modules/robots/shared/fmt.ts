/** Shared error formatting for robot UI. */

export function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    if (d && typeof d === 'object') return JSON.stringify(d)
    return err?.message ?? String(e)
}
