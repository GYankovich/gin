import { api } from './api'
import type { TokenResponse } from '@/types/portfolio'

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

    async getTokens(): Promise<TokenResponse[]> {
        const { data } = await api.get('/tinvest/portfolio/tokens')
        return Array.isArray(data) ? data : data.items ?? []
    },

    async getToken(tokenId: number): Promise<TokenResponse> {
        const { data } = await api.get<TokenResponse>(`/tinvest/portfolio/tokens/${tokenId}`)
        return data
    },

    async createToken(payload: { token_name: string; token_value: string; token_type?: string }): Promise<TokenResponse> {
        const { data } = await api.post<TokenResponse>('/tinvest/portfolio/tokens', payload)
        return data
    },

    async updateToken(tokenId: number, payload: Record<string, any>): Promise<TokenResponse> {
        const { data } = await api.patch<TokenResponse>(`/tinvest/portfolio/tokens/${tokenId}`, payload)
        return data
    },

    async deleteToken(tokenId: number): Promise<void> {
        await api.delete(`/tinvest/portfolio/tokens/${tokenId}`)
    },

    async testToken(payload: { token_value: string }): Promise<{ is_valid: boolean; message: string }> {
        const { data } = await api.post('/tinvest/portfolio/tokens/test', payload)
        return data
    },
}
