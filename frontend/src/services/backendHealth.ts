import { useBackendStatusStore } from '@/stores/backendStatusStore'

export async function probeBackendHealth(): Promise<boolean> {
    try {
        const response = await fetch('/health', { cache: 'no-store' })
        return response.ok
    } catch {
        return false
    }
}

/** Probe /health and clear the global down flag on success. */
export async function checkBackendReachable(): Promise<boolean> {
    const ok = await probeBackendHealth()
    if (ok) useBackendStatusStore.getState().markReachable()
    return ok
}
