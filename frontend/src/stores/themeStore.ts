///@EPIC Frontend.ITEM State.TOPIC FrontendSrcStoresThemestore [1]
///@ Исходный модуль `frontend/src/stores/themeStore.ts` — автоматическая разметка для Obsidian Source Scanner.

import { create } from 'zustand'

type Theme = 'dark' | 'light'

interface ThemeState {
    theme: Theme
    setTheme: (t: Theme) => void
    toggle: () => void
}

export const useThemeStore = create<ThemeState>((set, get) => ({
    theme: (localStorage.getItem('gin-theme') as Theme) || 'dark',
    setTheme: (t) => {
        localStorage.setItem('gin-theme', t)
        document.documentElement.setAttribute('data-theme', t)
        set({ theme: t })
    },
    toggle: () => {
        const next = get().theme === 'dark' ? 'light' : 'dark'
        get().setTheme(next)
    },
}))
