/** Detect backend 404 when robots v2 contour is disabled. */
export function isRobotsV2DisabledError(e: unknown): boolean {
    const err = e as { response?: { status?: number; data?: { detail?: unknown } } }
    if (err.response?.status !== 404) return false
    const d = err.response.data?.detail
    if (typeof d === 'string') {
        const lower = d.toLowerCase()
        return d.includes('ROBOTS_V2_ENABLED') || lower.includes('robots v2 contour is disabled')
    }
    return false
}

export const ROBOTS_V2_DISABLED_MESSAGE =
    'Robots v2 отключён (ROBOTS_V2_ENABLED=false). Включите модуль в конфигурации backend и перезапустите сервис.'
