///@EPIC Frontend.ITEM State.TOPIC FrontendSrcStoresAuthstore [1]
///@ Исходный модуль `frontend/src/stores/authStore.ts` — автоматическая разметка для Obsidian Source Scanner.

import { create } from 'zustand'

interface User {
    id: number
    login: string
    email?: string | null
    phone?: string | null
}

interface AuthState {
    user: User | null
    token: string | null
    setAuth: (user: User, token: string) => void
    logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
    user: JSON.parse(localStorage.getItem('gin-user') || 'null'),
    token: localStorage.getItem('gin-token'),
    setAuth: (user, token) => {
        localStorage.setItem('gin-token', token)
        localStorage.setItem('gin-user', JSON.stringify(user))
        set({ user, token })
    },
    logout: () => {
        localStorage.removeItem('gin-token')
        localStorage.removeItem('gin-user')
        set({ user: null, token: null })
    },
}))
