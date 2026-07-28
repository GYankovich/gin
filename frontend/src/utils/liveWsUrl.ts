/**
 * Live monitor WebSocket URL.
 *
 * DEV: same-origin through Vite (`ws://<page-host>/ws/live`) → proxy to
 * `http://127.0.0.1:8001`. Direct `ws://127.0.0.1:8001` from a page on
 * `http://localhost:5173` is a different browser origin and often fails to open.
 *
 * Override: `VITE_WS_BASE=ws://127.0.0.1:8001` (only if the page is also on 127.0.0.1).
 */
export function buildLiveWsUrl(robotId: number, token: string): string {
    const qs = `robot_id=${robotId}&token=${encodeURIComponent(token)}`
    const explicit = String(import.meta.env.VITE_WS_BASE || '').trim().replace(/\/$/, '')
    if (explicit) {
        if (explicit.startsWith('ws://') || explicit.startsWith('wss://')) {
            return `${explicit}/ws/live?${qs}`
        }
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        return `${proto}://${explicit}/ws/live?${qs}`
    }
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    // Same host:port as the page (Vite proxies /ws → WS gateway in DEV).
    return `${proto}://${window.location.host}/ws/live?${qs}`
}
