///@EPIC Frontend.ITEM State.TOPIC FrontendSrcStoresThemestore [1]
///@ Исходный модуль `frontend/src/stores/themeStore.ts` — автоматическая разметка для Obsidian Source Scanner.

import { create } from 'zustand'

export type ThemePreference = 'dark' | 'light' | 'system'
export type ResolvedTheme = 'dark' | 'light'

const STORAGE_KEY = 'gin-theme'

function resolveTheme(preference: ThemePreference): ResolvedTheme {
    if (preference === 'system') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return preference
}

function applyTheme(preference: ThemePreference) {
    document.documentElement.setAttribute('data-theme', resolveTheme(preference))
}

function readStoredPreference(): ThemePreference {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === 'dark' || raw === 'light' || raw === 'system') return raw
    return 'dark'
}

const initialPreference = readStoredPreference()
applyTheme(initialPreference)

interface ThemeState {
    preference: ThemePreference
    resolved: ResolvedTheme
    /** Resolved theme applied to the document */
    theme: ResolvedTheme
    setPreference: (preference: ThemePreference) => void
    /** @deprecated use setPreference */
    setTheme: (theme: ResolvedTheme) => void
    /** @deprecated use setPreference */
    toggle: () => void
}

export const useThemeStore = create<ThemeState>((set, get) => {
    const initialResolved = resolveTheme(initialPreference)
    return {
    preference: initialPreference,
    resolved: initialResolved,
    theme: initialResolved,
    setPreference: (preference) => {
        localStorage.setItem(STORAGE_KEY, preference)
        applyTheme(preference)
        const resolved = resolveTheme(preference)
        set({ preference, resolved, theme: resolved })
    },
    setTheme: (theme) => {
        get().setPreference(theme)
    },
    toggle: () => {
        const next = get().resolved === 'dark' ? 'light' : 'dark'
        get().setPreference(next)
    },
}})

if (typeof window !== 'undefined') {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onSystemChange = () => {
        const { preference } = useThemeStore.getState()
        if (preference !== 'system') return
        applyTheme('system')
        useThemeStore.setState({ resolved: resolveTheme('system'), theme: resolveTheme('system') })
    }
    media.addEventListener('change', onSystemChange)
}

export function themePreferenceLabel(preference: ThemePreference): string {
    if (preference === 'dark') return 'Тёмная'
    if (preference === 'light') return 'Светлая'
    return 'Системная'
}
