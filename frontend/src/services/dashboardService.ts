///@EPIC Frontend.ITEM APIClient.TOPIC FrontendSrcServicesDashboardservice [1]
///@ Исходный модуль `frontend/src/services/dashboardService.ts` — автоматическая разметка для Obsidian Source Scanner.

import { api } from './api'
import type { DashboardDataResponse } from '@/types/api'

export type DashboardSortColumn =
    | 'account_name'
    | 'value'
    | 'own_funds'
    | 'day_over_day_delta'
    | 'last_account_sync'

export interface DashboardSortItem {
    columnName: DashboardSortColumn
    sortType: 'asc' | 'desc'
}

export interface DashboardVisibilityItem {
    account_id: number
    hidden: boolean
}

export const dashboardService = {
    async fetchData(sort?: DashboardSortItem[]): Promise<DashboardDataResponse> {
        const { data } = await api.post<DashboardDataResponse>('/dashboard/data', {
            sort: sort ?? [{ columnName: 'account_name', sortType: 'asc' }],
        })
        return data
    },

    async updateVisibility(accounts: DashboardVisibilityItem[]): Promise<{ updated: number }> {
        const { data } = await api.post<{ updated: number }>('/dashboard/visibility', { accounts })
        return data
    },
}
