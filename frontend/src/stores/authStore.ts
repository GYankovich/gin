///@EPIC Frontend.ITEM State.TOPIC FrontendSrcStoresAuthstore [1]
///@ Исходный модуль `frontend/src/stores/authStore.ts` — автоматическая разметка для Obsidian Source Scanner.

import { create } from 'zustand'

interface User {
    id: number
    login: string
    email?: string | null
    phone?: string | null
    created_at?: string | null
}

interface AuthState {
    user: User | null
    token: string | null
    loginAt: string | null
    setAuth: (user: User, token: string) => void
    updateUser: (user: User) => void
    logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
    user: JSON.parse(localStorage.getItem('gin-user') || 'null'),
    token: localStorage.getItem('gin-token'),
    loginAt: localStorage.getItem('gin-login-at'),
    setAuth: (user, token) => {
        const loginAt = new Date().toISOString()
        localStorage.setItem('gin-token', token)
        localStorage.setItem('gin-user', JSON.stringify(user))
        localStorage.setItem('gin-login-at', loginAt)
        set({ user, token, loginAt })
    },
    updateUser: (user) => {
        localStorage.setItem('gin-user', JSON.stringify(user))
        set({ user })
    },
    logout: () => {
        localStorage.removeItem('gin-token')
        localStorage.removeItem('gin-user')
        localStorage.removeItem('gin-login-at')
        set({ user: null, token: null, loginAt: null })
    },
}))
