import { api } from './api'
import type {
    OptimizationBatchStatusResponse,
    OptimizationGoal,
    OptimizationMode,
    OptimizationBatchStartedResponse,
    OptimizationPlanResponse,
    OptimizationRankResponse,
    OptimizationRunRequest,
    OptimizationSessionFailuresResponse,
} from '@/types/optimization'

export const optimizationService = {
    async rankBacktests(
        robotId: number,
        goal: OptimizationGoal = 'balanced',
        limit = 50,
    ): Promise<OptimizationRankResponse> {
        const { data } = await api.get<OptimizationRankResponse>(
            `/recommendations/robots/${robotId}/optimize/rank`,
            { params: { goal, limit } },
        )
        return data
    },

    async sessionFailures(limit = 20): Promise<OptimizationSessionFailuresResponse> {
        const { data } = await api.get<OptimizationSessionFailuresResponse>(
            '/recommendations/optimize/session-failures',
            { params: { limit } },
        )
        return data
    },

    async planOptimization(
        robotId: number,
        goal: OptimizationGoal = 'balanced',
        mode: OptimizationMode = 'speed',
    ): Promise<OptimizationPlanResponse> {
        const { data } = await api.post<OptimizationPlanResponse>(
            `/recommendations/robots/${robotId}/optimize/plan`,
            { goal, mode },
        )
        return data
    },

    async runOptimizationBatch(
        robotId: number,
        body: OptimizationRunRequest,
    ): Promise<OptimizationBatchStartedResponse> {
        const { data } = await api.post<OptimizationBatchStartedResponse>(
            `/recommendations/robots/${robotId}/optimize/run`,
            body,
        )
        return data
    },

    async getBatchStatus(robotId: number, batchId: number): Promise<OptimizationBatchStatusResponse> {
        const { data } = await api.get<OptimizationBatchStatusResponse>(
            `/recommendations/robots/${robotId}/optimize/batches/${batchId}`,
        )
        return data
    },

    async getActiveBatch(robotId: number): Promise<OptimizationBatchStatusResponse | null> {
        const { data } = await api.get<OptimizationBatchStatusResponse | null>(
            `/recommendations/robots/${robotId}/optimize/batches/active`,
        )
        return data
    },

    async cancelBatch(robotId: number, batchId: number): Promise<void> {
        await api.post(`/recommendations/robots/${robotId}/optimize/batches/${batchId}/cancel`)
    },
}
