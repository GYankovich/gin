import { api } from './api'
import type { DashboardDataResponse } from '@/types/api'

export type DashboardSortColumn =
    | 'account_name'
    | 'total_value'
    | 'own_funds'
    | 'day_over_day_delta'
    | 'last_account_sync'

export interface DashboardSortItem {
    columnName: DashboardSortColumn
    sortType: 'asc' | 'desc'
}

export const dashboardService = {
    async fetchData(sort?: DashboardSortItem[]): Promise<DashboardDataResponse> {
        const { data } = await api.post<DashboardDataResponse>('/dashboard/data', {
            sort: sort ?? [{ columnName: 'account_name', sortType: 'asc' }],
        })
        return data
    },
}
