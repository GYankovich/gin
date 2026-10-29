///@EPIC Frontend.ITEM APIClient.TOPIC FrontendSrcServicesAuthservice [1]
///@ Исходный модуль `frontend/src/services/authService.ts` — автоматическая разметка для Obsidian Source Scanner.

import { api } from './api'

interface LoginPayload {
    login: string
    password: string
}

interface RegisterPayload {
    login: string
    email: string
    password: string
}

interface RegisterPending {
    status: string
    email: string
    dev_code?: string | null
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

function sessionFromToken(tokenData: TokenResponse): Promise<{ token: string; user: UserOut }> {
    localStorage.setItem('gin-token', tokenData.access_token)
    if (tokenData.user) {
        return Promise.resolve({ token: tokenData.access_token, user: tokenData.user })
    }
    return api.get<UserOut>('/auth/me').then(({ data: user }) => ({
        token: tokenData.access_token,
        user,
    }))
}

export const authService = {
    async login(payload: LoginPayload): Promise<{ token: string; user: UserOut }> {
        const { data: tokenData } = await api.post<TokenResponse>('/auth/login', payload)
        return sessionFromToken(tokenData)
    },

    async requestLoginCode(payload: LoginPayload): Promise<RegisterPending> {
        const { data } = await api.post<RegisterPending>('/auth', payload)
        return data
    },

    async confirmLogin(payload: { email: string; code: string }): Promise<{ token: string; user: UserOut }> {
        const { data: tokenData } = await api.post<TokenResponse>('/auth/confirm', payload)
        return sessionFromToken(tokenData)
    },

    async resendLoginCode(email: string): Promise<RegisterPending> {
        const { data } = await api.post<RegisterPending>('/auth/resend', { email })
        return data
    },

    async register(payload: RegisterPayload): Promise<RegisterPending> {
        const { data } = await api.post<RegisterPending>('/registration', payload)
        return data
    },

    async confirmRegistration(payload: { email: string; code: string }): Promise<{ token: string; user: UserOut }> {
        const { data: tokenData } = await api.post<TokenResponse>('/registration/confirm', payload)
        return sessionFromToken(tokenData)
    },

    async resendRegistrationCode(email: string): Promise<RegisterPending> {
        const { data } = await api.post<RegisterPending>('/registration/resend', { email })
        return data
    },

    async requestPasswordReset(login: string): Promise<{ status: string; dev_link?: string | null }> {
        const { data } = await api.post<{ status: string; dev_link?: string | null }>('/change_pass_request', { login })
        return data
    },

    async previewPasswordReset(token: string): Promise<{ login: string; email: string }> {
        const { data } = await api.get<{ login: string; email: string }>('/change_pass', { params: { token } })
        return data
    },

    async resetPassword(payload: { token: string; password: string }): Promise<void> {
        await api.post('/change_pass', payload)
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

    async listSessions(): Promise<AuthSession[]> {
        const { data } = await api.get<{ items: AuthSession[] }>('/auth/sessions')
        return data.items || []
    },

    async revokeSession(sessionId: number): Promise<void> {
        await api.delete(`/auth/sessions/${sessionId}`)
    },

    async revokeAllSessions(): Promise<void> {
        await api.post('/auth/sessions/revoke-all')
    },
}

export type AuthSession = {
    id: number
    device_label?: string | null
    geo_label?: string | null
    ip_masked?: string | null
    created_at: string
    expires_at: string
    last_seen_at?: string | null
    is_current: boolean
}
