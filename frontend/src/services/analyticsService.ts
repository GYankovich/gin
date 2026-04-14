import { api } from './api'
import type {
    OverallSummary,
    AccountDetail,
    HistoryResponse,
    AccountSummary,
    AccountStatisticsResponse,
    PortfolioStatisticsExtendedResponse,
    AnalyticsChartSeriesResponse,
} from '@/types/api'
import type { RobotMetricsResponse, UserRobotsTradingOverview } from '@/types/robot'

export const analyticsService = {
    async getSummary(): Promise<OverallSummary> {
        const { data } = await api.get<OverallSummary>('/analytics/summary')
        return data
    },

    async getAccounts(): Promise<AccountSummary[]> {
        const { data } = await api.get<AccountSummary[]>('/analytics/accounts')
        return data
    },

    async getAccountDetail(accountId: number, days = 365): Promise<AccountDetail> {
        const { data } = await api.get<AccountDetail>(`/analytics/accounts/${accountId}`, {
            params: { days },
        })
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

    async getRobotsTradingOverview(): Promise<UserRobotsTradingOverview> {
        const { data } = await api.get<UserRobotsTradingOverview>('/analytics/robots/trading-overview')
        return data
    },

    async getAccountPositions(accountId: number, snapshotId?: number): Promise<any[]> {
        const params: Record<string, any> = {}
        if (snapshotId) params.snapshot_id = snapshotId
        const { data } = await api.get(`/analytics/accounts/${accountId}/positions`, { params })
        return data.positions ?? []
    },

    async getSnapshotsByPeriod(payload: { account_id: number; from_date: string; to_date: string }): Promise<{ history: any[] }> {
        const { data } = await api.post('/analytics/snapshots', payload)
        return data
    },

    async getOperationsByPeriod(payload: { account_id: number; from_date: string; to_date: string; operation_type?: string }): Promise<{ items: any[]; total: number }> {
        const { data } = await api.post('/analytics/operations', payload)
        return data
    },

    async getAccountStatistics(payload: { account_id: number; from_date: string; to_date: string }): Promise<AccountStatisticsResponse> {
        const { data } = await api.post<AccountStatisticsResponse>('/analytics/statistics', payload)
        return data
    },

    async getAccountStatisticsExtended(payload: { account_id: number; from_date: string; to_date: string }): Promise<PortfolioStatisticsExtendedResponse> {
        const { data } = await api.post<PortfolioStatisticsExtendedResponse>('/analytics/statistics_extended', payload)
        return data
    },

    async getAccountChartSeries(payload: { account_id: number; from_date: string; to_date: string; figis?: string[] }): Promise<AnalyticsChartSeriesResponse> {
        const { data } = await api.post<AnalyticsChartSeriesResponse>('/analytics/chart_series', payload)
        return data
    },

    async syncOperations(payload: { account_id: string; from_date: string; to_date: string; tokenId: number; state?: string }): Promise<any> {
        const { data } = await api.post('/analytics/sync_operations', payload)
        return data
    },
}
