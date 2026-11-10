///@EPIC Frontend.ITEM State.TOPIC FrontendSrcStoresAuthstore [1]
///@ Исходный модуль `frontend/src/stores/authStore.ts` — автоматическая разметка для Obsidian Source Scanner.

import { create } from 'zustand'
import { usePageCacheStore } from '@/stores/pageCacheStore'

export interface AuthUser {
    id: number
    login: string
    email?: string | null
    phone?: string | null
    created_at?: string | null
}

export interface AuthFeatures {
    dashboard: boolean
    portfolio: boolean
    robots: boolean
    backtest: boolean
}

const EMPTY_FEATURES: AuthFeatures = {
    dashboard: false,
    portfolio: false,
    robots: false,
    backtest: false,
}

function readJson<T>(key: string, fallback: T): T {
    try {
        const raw = localStorage.getItem(key)
        if (!raw) return fallback
        return JSON.parse(raw) as T
    } catch {
        return fallback
    }
}

interface AuthState {
    user: AuthUser | null
    token: string | null
    loginAt: string | null
    packageCode: number | null
    features: AuthFeatures
    featuresLoaded: boolean
    setAuth: (user: AuthUser, token: string) => void
    setMeInfo: (payload: {
        user: AuthUser
        packageCode: number
        features: AuthFeatures
    }) => void
    updateUser: (user: AuthUser) => void
    logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
    user: readJson<AuthUser | null>('gin-user', null),
    token: localStorage.getItem('gin-token'),
    loginAt: localStorage.getItem('gin-login-at'),
    packageCode: (() => {
        const raw = localStorage.getItem('gin-package-code')
        if (raw == null || raw === '') return null
        const n = Number(raw)
        return Number.isFinite(n) ? n : null
    })(),
    features: readJson<AuthFeatures>('gin-features', EMPTY_FEATURES),
    featuresLoaded: localStorage.getItem('gin-features') != null,
    setAuth: (user, token) => {
        const loginAt = new Date().toISOString()
        localStorage.setItem('gin-token', token)
        localStorage.setItem('gin-user', JSON.stringify(user))
        localStorage.setItem('gin-login-at', loginAt)
        set({ user, token, loginAt })
    },
    setMeInfo: ({ user, packageCode, features }) => {
        localStorage.setItem('gin-user', JSON.stringify(user))
        localStorage.setItem('gin-package-code', String(packageCode))
        localStorage.setItem('gin-features', JSON.stringify(features))
        set({
            user,
            packageCode,
            features,
            featuresLoaded: true,
        })
    },
    updateUser: (user) => {
        localStorage.setItem('gin-user', JSON.stringify(user))
        set({ user })
    },
    logout: () => {
        localStorage.removeItem('gin-token')
        localStorage.removeItem('gin-user')
        localStorage.removeItem('gin-login-at')
        localStorage.removeItem('gin-package-code')
        localStorage.removeItem('gin-features')
        usePageCacheStore.getState().clear()
        set({
            user: null,
            token: null,
            loginAt: null,
            packageCode: null,
            features: EMPTY_FEATURES,
            featuresLoaded: false,
        })
    },
}))
