/**
 * T6.1 — refactored `/testing` UI is **on by default**.
 * Legacy monolithic page: `VITE_TESTING_LEGACY=true`
 * (or legacy opt-out: `VITE_TESTING_REFACTOR=false`).
 */
export function isTestingLegacyEnabled(): boolean {
    const legacy = String(import.meta.env.VITE_TESTING_LEGACY ?? '').trim().toLowerCase()
    if (legacy === 'true' || legacy === '1' || legacy === 'yes') return true

    const refactor = String(import.meta.env.VITE_TESTING_REFACTOR ?? '').trim().toLowerCase()
    if (refactor === 'false' || refactor === '0' || refactor === 'no') return true

    return false
}

export function isTestingRefactoredEnabled(): boolean {
    return !isTestingLegacyEnabled()
}
