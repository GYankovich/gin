import { api } from './api'
import type { Robot, RobotListResponse, StrategyListResponse } from '@/types/robot'

export const robotService = {
    async list(limit = 50, offset = 0): Promise<RobotListResponse> {
        const { data } = await api.post<RobotListResponse>('/robots/data', { limit, offset })
        return data
    },

    async create(payload: Record<string, any>): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/create', payload)
        return data
    },

    async changeStatus(robotId: number, status: number): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/change_status', { robot_id: robotId, status })
        return data
    },

    async updateConfig(robotId: number, config: Record<string, any>): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/config', { robot_id: robotId, ...config })
        return data
    },

    async getStrategies(): Promise<StrategyListResponse> {
        const { data } = await api.get<StrategyListResponse>('/robots/strategies')
        return data
    },

    async autoSelectInstruments(params: Record<string, any>): Promise<{ items: any[]; total: number }> {
        const { data } = await api.post('/robots/instruments/auto-select', params)
        return data
    },
}
