import { api } from './api'
import type {
    Robot,
    RobotListResponse,
    StrategyListResponse,
    RobotTradingDefaults,
    RobotHistoryBacktestResult,
} from '@/types/robot'

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
        const { data } = await api.post<Robot>('/robots/change_status', { robotId, status })
        return data
    },

    async deleteRobot(robotId: number): Promise<{ id: number; deleted: boolean }> {
        const { data } = await api.post<{ id: number; deleted: boolean }>('/robots/delete', { robotId })
        return data
    },

    async updateConfig(robotId: number, config: Record<string, any>): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/config', { robotId, config })
        return data
    },

    async getStrategies(): Promise<StrategyListResponse> {
        const { data } = await api.get<StrategyListResponse>('/robots/strategies')
        return data
    },

    async getTradingDefaults(): Promise<RobotTradingDefaults> {
        const { data } = await api.get<RobotTradingDefaults>('/robots/trading-defaults')
        return data
    },

    async runHistoryBacktest(payload: {
        robot_id: number
        from_date: string
        to_date: string
        initial_capital?: number
    }): Promise<RobotHistoryBacktestResult> {
        const { data } = await api.post<RobotHistoryBacktestResult>('/robots/history-backtest', payload)
        return data
    },

    async autoSelectInstruments(params: Record<string, any>): Promise<{ items: any[]; total: number }> {
        const { data } = await api.post('/robots/instruments/auto-select', params)
        return data
    },

    async runBacktest(returns: number[], initial_capital = 100000, fee_bps = 5) {
        const { data } = await api.post('/robots/research/backtest', { returns, initial_capital, fee_bps })
        return data
    },

    async runWalkForward(returns: number[], folds = 3, train_ratio = 0.7, initial_capital = 100000, fee_bps = 5) {
        const { data } = await api.post('/robots/research/walk-forward', {
            returns, folds, train_ratio, initial_capital, fee_bps,
        })
        return data
    },

    async setPaperMode(robotId: number, enabled: boolean) {
        const { data } = await api.post('/robots/paper-mode', { robotId, enabled })
        return data
    },
}
