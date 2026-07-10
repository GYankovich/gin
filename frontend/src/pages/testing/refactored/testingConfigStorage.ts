const STORAGE_KEY = 'gin-testing-config-preset'

export function saveTestingConfigSnapshot(snapshot: unknown): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot))
    } catch {
        // ignore quota / private mode
    }
}

export function loadTestingConfigSnapshot<T>(): T | null {
    try {
        const raw = localStorage.getItem(STORAGE_KEY)
        if (!raw) return null
        return JSON.parse(raw) as T
    } catch {
        return null
    }
}
