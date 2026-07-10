import { useCallback, useEffect, useMemo, useState } from 'react'

const STORAGE_PREFIX = 'gin:testing:dismissed-recs:'

function loadDismissed(robotId: number | null): Set<string> {
    if (robotId == null || typeof window === 'undefined') return new Set()
    try {
        const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${robotId}`)
        if (!raw) return new Set()
        const parsed = JSON.parse(raw) as unknown
        if (!Array.isArray(parsed)) return new Set()
        return new Set(parsed.filter((x): x is string => typeof x === 'string'))
    } catch {
        return new Set()
    }
}

function saveDismissed(robotId: number | null, ids: Set<string>): void {
    if (robotId == null || typeof window === 'undefined') return
    try {
        window.localStorage.setItem(`${STORAGE_PREFIX}${robotId}`, JSON.stringify([...ids]))
    } catch {
        // ignore quota / private mode
    }
}

export function useDismissedRecommendations(robotId: number | null) {
    const [dismissedIds, setDismissedIds] = useState<Set<string>>(() => loadDismissed(robotId))

    useEffect(() => {
        setDismissedIds(loadDismissed(robotId))
    }, [robotId])

    const dismiss = useCallback(
        (id: string) => {
            setDismissedIds(prev => {
                const next = new Set(prev)
                next.add(id)
                saveDismissed(robotId, next)
                return next
            })
        },
        [robotId],
    )

    const restore = useCallback(
        (id: string) => {
            setDismissedIds(prev => {
                const next = new Set(prev)
                next.delete(id)
                saveDismissed(robotId, next)
                return next
            })
        },
        [robotId],
    )

    const clearAll = useCallback(() => {
        setDismissedIds(new Set())
        saveDismissed(robotId, new Set())
    }, [robotId])

    const isDismissed = useCallback((id: string) => dismissedIds.has(id), [dismissedIds])

    const dismissedCount = useMemo(() => dismissedIds.size, [dismissedIds])

    return { dismissedIds, dismiss, restore, clearAll, isDismissed, dismissedCount }
}
