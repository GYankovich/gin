import { create } from 'zustand'

interface BackendStatusState {
    /** Backend process or proxy is unreachable (network, 502, 503, 504). */
    down: boolean
    /** Bumped only on down → up so the current page remounts and refetches. */
    epoch: number
    /** Timestamp of the last successful API or health response. */
    lastOkAt: number
    markDown: (requestStartedAt: number) => void
    markReachable: () => void
}

export const useBackendStatusStore = create<BackendStatusState>((set, get) => ({
    down: false,
    epoch: 0,
    lastOkAt: 0,
    markDown: (requestStartedAt) => {
        // A later success means the process is up; this failure is a single route.
        if (get().lastOkAt > requestStartedAt) return
        if (get().down) return
        set({ down: true })
    },
    markReachable: () => {
        const wasDown = get().down
        set({
            lastOkAt: Date.now(),
            down: false,
            epoch: wasDown ? get().epoch + 1 : get().epoch,
        })
    },
}))
