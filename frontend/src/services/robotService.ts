import { api } from './api'
import type {
    Robot,
    RobotListResponse,
    StrategyListResponse,
    GrainSeedConfig,
    RobotTradingDefaults,
    RobotHistoryBacktestResult,
    RobotBacktestHistoryResponse,
    RobotBacktestRunDetails,
} from '@/types/robot'

///@EPIC Frontend.ITEM APIClient.TOPIC Robots Service Facade [1]
///@ Клиентский фасад для /robots и связанных endpoints: CRUD, backtest, live snapshot,
///@ DMS preview и вспомогательные методы для экранов настройки/тестирования.
export const robotService = {
    async list(limit = 50, offset = 0): Promise<RobotListResponse> {
        const { data } = await api.post<RobotListResponse>('/robots/data', { limit, offset })
        return data
    },

    async create(payload: { name: string; token_id: number; type?: 1 | 2 }): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/create', payload)
        return data
    },

    async getById(robotId: number): Promise<Robot> {
        const { data } = await api.get<Robot>(`/robots/id/${robotId}`)
        return data
    },

    async updateRobot(robotId: number, patch: Partial<{
        name: string
        token_id: number
        type: 1 | 2
        status: number
        config: Record<string, any>
        poll_interval_hours: number
        trading_hours_start: string
        trading_hours_end: string
        allowed_weekdays: number
    }>): Promise<Robot> {
        const normalized: Record<string, any> = { ...patch }
        if (normalized.token_id != null) {
            normalized.token_id = Number(normalized.token_id)
        }
        const { data } = await api.post<Robot>('/robots/update', { robotId, patch: normalized })
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

    async updateConfig(robotId: number, config: GrainSeedConfig): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/config', { robotId, config })
        return data
    },

    async updateSchedule(robotId: number, payload: {
        poll_interval_hours: number
        trading_hours_start: string
        trading_hours_end: string
        allowed_weekdays: number
    }): Promise<Robot> {
        const { data } = await api.post<Robot>('/robots/schedule', { robotId, ...payload })
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
        token_id?: number
        type?: number
        poll_interval_hours?: number
        trading_hours_start?: string
        trading_hours_end?: string
        allowed_weekdays?: number
        config?: Record<string, any>
    }): Promise<RobotHistoryBacktestResult> {
        const { data } = await api.post<RobotHistoryBacktestResult>('/robots/history-backtest', payload)
        return data
    },

    async listHistoryBacktests(payload: { robotId: number; limit?: number }): Promise<RobotBacktestHistoryResponse> {
        const { data } = await api.post<RobotBacktestHistoryResponse>('/robots/history-backtest/list', payload)
        return data
    },

    async getHistoryBacktestRun(runId: number): Promise<RobotBacktestRunDetails> {
        const { data } = await api.post<RobotBacktestRunDetails>('/robots/history-backtest/run', { runId })
        return data
    },

    async getLiveSnapshot(robotId: number): Promise<{
        robot_id: number
        status: number
        broker_type: string
        strategy: string
        account_id?: string | null
        active_positions: any[]
        recent_signals: any[]
        recent_orders: any[]
        stream_health: Record<string, any>
    }> {
        const { data } = await api.post('/robots/live/snapshot', { robotId })
        return data
    },

    async autoSelectInstruments(params: Record<string, any>): Promise<{ items: any[]; total: number }> {
        const { data } = await api.post('/robots/instruments/auto-select', params)
        return data
    },

    async subscribeDms(payload: {
        robot_id: number
        board?: string
        include_candles?: boolean
        candle_interval?: string | null
        candle_depth?: number
        snapshot_hour?: number | null
        ttl_minutes?: number
    }): Promise<any> {
        const { data } = await api.post('/dms/subscribe', payload)
        return data
    },

    async listDmsSubscriptions(): Promise<any[]> {
        const { data } = await api.get('/dms/subscriptions')
        return data
    },

    async listDmsSnapshots(board?: string): Promise<any[]> {
        const { data } = await api.get('/dms/snapshots', { params: board ? { board } : {} })
        return data
    },

    async createDmsSnapshot(payload?: { board?: string; ttl_minutes?: number; is_manual?: boolean }): Promise<any> {
        const { data } = await api.post('/dms/snapshots/create', payload || { board: 'TQBR', ttl_minutes: 5, is_manual: true })
        return data
    },

    async processDmsQueue(): Promise<any> {
        const { data } = await api.post('/dms/process-queue')
        return data
    },

    async listDailyUniverse(params?: { robot_id?: number; trade_date?: string }): Promise<{ total: number; items: any[] }> {
        const { data } = await api.get('/dms/daily-universe', { params: params || {} })
        return data
    },

    async getDmsFilterLog(params?: { robot_id?: number; trade_date?: string; limit?: number }): Promise<{
        total_checked: number
        passed: number
        rejected: number
        items: any[]
    }> {
        const { data } = await api.get('/dms/filter-log', { params: params || {} })
        return data
    },

    async previewDmsPipeline(payload: {
        robot_id: number
        board?: string
        filters: Array<Record<string, any>>
        mode?: 'ALL' | 'ANY'
    }): Promise<{
        total_checked: number
        passed: number
        rejected: number
        sample: Array<Record<string, any>>
    }> {
        const { data } = await api.post('/dms/pipeline/preview', payload)
        return data
    },

}
