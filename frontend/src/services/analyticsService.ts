import { api } from './api'
import type { OverallSummary, AccountDetail, HistoryResponse, AccountSummary } from '@/types/api'
import type { RobotMetricsResponse } from '@/types/robot'

export const analyticsService = {
    async getSummary(): Promise<OverallSummary> {
        const { data } = await api.get<OverallSummary>('/analytics/summary')
        return data
    },

    async getAccounts(): Promise<AccountSummary[]> {
        const { data } = await api.get<AccountSummary[]>('/analytics/accounts')
        return data
    },

    async getAccountDetail(accountId: number): Promise<AccountDetail> {
        const { data } = await api.get<AccountDetail>(`/analytics/accounts/${accountId}`)
        return data
    },

    async getAccountHistory(accountId: number, days = 365, interval?: string): Promise<HistoryResponse> {
        const params: Record<string, any> = { days }
        if (interval) params.interval = interval
        const { data } = await api.get<HistoryResponse>(`/analytics/accounts/${accountId}/history`, { params })
        return data
    },

    async getRobotMetrics(robotId: number): Promise<RobotMetricsResponse> {
        const { data } = await api.get<RobotMetricsResponse>(`/analytics/robots/${robotId}/metrics`)
        return data
    },

    async getAccountPositions(accountId: number, snapshotId?: number): Promise<any[]> {
        const params: Record<string, any> = {}
        if (snapshotId) params.snapshot_id = snapshotId
        const { data } = await api.get(`/analytics/accounts/${accountId}/positions`, { params })
        return data.positions ?? []
    },
}
