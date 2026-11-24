///@EPIC Frontend.ITEM APIClient.TOPIC FrontendSrcServicesPortfolioservice [1]
///@ Исходный модуль `frontend/src/services/portfolioService.ts` — автоматическая разметка для Obsidian Source Scanner.

import { api } from './api'

export const portfolioService = {
    async getPortfolioData(): Promise<any> {
        const { data } = await api.get('/tinvest/portfolio/data')
        return data
    },

    async getAccounts(): Promise<any[]> {
        const { data } = await api.get('/tinvest/portfolio/accounts')
        return data
    },

    async getAccountsDb(): Promise<{ total: number; accounts: any[] }> {
        const { data } = await api.get('/tinvest/portfolio/accounts/db')
        return data
    },

    async refreshAll(): Promise<any> {
        const { data } = await api.post('/tinvest/portfolio/refresh-all')
        return data
    },

    async getSnapshots(accountId: string): Promise<any> {
        const { data } = await api.get(`/tinvest/portfolio/snapshots/${accountId}`)
        return data
    },

    async syncOperations(payload: {
        account_id: string
        from_date: string
        to_date: string
        state?: string
    }): Promise<any> {
        const { data } = await api.post('/tinvest/portfolio/operations/sync', payload)
        return data
    },

    async getOperations(
        accountId: number,
        params?: { from_date?: string; to_date?: string; limit?: number },
    ): Promise<{ account_id: number; from_date: string; to_date: string; total: number; items: any[] }> {
        const { data } = await api.get(`/tinvest/portfolio/operations/${accountId}`, { params })
        return data
    },
}
