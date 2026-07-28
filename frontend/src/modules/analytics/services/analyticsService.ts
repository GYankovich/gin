///@EPIC Frontend.ITEM Modules.TOPIC FrontendSrcModulesAnalyticsServicesAnalyticsservice [1]
///@ Исходный модуль `frontend/src/modules/analytics/services/analyticsService.ts` — автоматическая разметка для Obsidian Source Scanner.

import { apiFetch } from '../../../core/api';
import type { OverallSummary, AccountDetail, RobotMetricsResponse } from '../types';

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

    async getRobotMetrics(robotId: number, recentLimit = 20): Promise<RobotMetricsResponse> {
        return apiFetch<RobotMetricsResponse>(
            `/analytics/robots/${robotId}/metrics?recent_limit=${recentLimit}`
        );
    }
}

export const analyticsService = new AnalyticsService();