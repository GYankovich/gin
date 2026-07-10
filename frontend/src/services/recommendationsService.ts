import { api } from './api'
import type { RobotRecommendationsResponse } from '@/types/recommendations'

export const recommendationsService = {
    async getRobotRecommendations(
        robotId: number,
        backtestLimit = 15,
    ): Promise<RobotRecommendationsResponse> {
        const { data } = await api.get<RobotRecommendationsResponse>(
            `/recommendations/robots/${robotId}`,
            { params: { backtest_limit: backtestLimit } },
        )
        return data
    },
}
