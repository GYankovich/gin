///@EPIC Frontend.ITEM APIClient.TOPIC FrontendSrcServicesAuthservice [1]
///@ Исходный модуль `frontend/src/services/authService.ts` — автоматическая разметка для Obsidian Source Scanner.

import { api } from './api'

interface LoginPayload {
    login: string
    password: string
}

interface UserOut {
    id: number
    login: string
    email?: string | null
    phone?: string | null
    created_at?: string | null
}

interface TokenResponse {
    access_token: string
    token_type: string
    expires_at: string
    user?: UserOut | null
}

export const authService = {
    async login(payload: LoginPayload): Promise<{ token: string; user: UserOut }> {
        const { data: tokenData } = await api.post<TokenResponse>('/auth/login', payload)
        localStorage.setItem('gin-token', tokenData.access_token)
        if (tokenData.user) {
            return { token: tokenData.access_token, user: tokenData.user }
        }
        const { data: user } = await api.get<UserOut>('/auth/me')
        return { token: tokenData.access_token, user }
    },

    async me(): Promise<UserOut> {
        const { data } = await api.get<UserOut>('/auth/me')
        return data
    },

    async changeUser(payload: {
        login: string
        email?: string | null
        phone?: string | null
        current_password?: string
        new_password?: string
    }): Promise<UserOut> {
        const { data } = await api.post<UserOut>('/users/change', payload)
        return data
    },

    async logout(): Promise<void> {
        try { await api.post('/auth/logout') } catch { /* ignore */ }
    },
}
