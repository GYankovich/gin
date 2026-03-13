import { apiFetch } from '../../../core/api';
import type { OverallSummary, AccountDetail, AccountSummary } from '../types';

class AnalyticsService {
    async getOverallSummary(): Promise<OverallSummary> {
        return apiFetch<OverallSummary>('/analytics/summary');
    }

    async getAccountDetail(accountId: number): Promise<AccountDetail> {
        return apiFetch<AccountDetail>(`/analytics/accounts/${accountId}`);
    }

    async getAccountHistory(accountId: number, days: number = 30): Promise<{ account_id: number; days: number; history: any[] }> {
        return apiFetch(`/analytics/accounts/${accountId}/history?days=${days}`);
    }
}

export const analyticsService = new AnalyticsService();