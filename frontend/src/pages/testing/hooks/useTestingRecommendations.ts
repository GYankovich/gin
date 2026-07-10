import { useCallback, useEffect, useState } from 'react'
import { recommendationsService } from '@/services/recommendationsService'
import type { RobotRecommendationsResponse } from '@/types/recommendations'

export function useTestingRecommendations(robotId: number | null) {
    const [data, setData] = useState<RobotRecommendationsResponse | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const refresh = useCallback(async () => {
        if (!robotId) {
            setData(null)
            setError(null)
            return
        }
        setLoading(true)
        setError(null)
        try {
            const res = await recommendationsService.getRobotRecommendations(robotId)
            setData(res)
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : 'Не удалось загрузить рекомендации'
            setError(msg)
            setData(null)
        } finally {
            setLoading(false)
        }
    }, [robotId])

    useEffect(() => {
        void refresh()
    }, [refresh])

    return { data, loading, error, refresh }
}
