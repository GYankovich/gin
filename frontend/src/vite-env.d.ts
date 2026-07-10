/// <reference types="vite/client" />
///@EPIC Frontend.ITEM Src.TOPIC FrontendSrcViteEnvD [1]
///@ Исходный модуль `frontend/src/vite-env.d.ts` — автоматическая разметка для Obsidian Source Scanner.


interface ImportMetaEnv {
    readonly VITE_API_BASE: string
    /** @deprecated T6.1 — refactored UI is default; use `VITE_TESTING_LEGACY=true` to force legacy. */
    readonly VITE_TESTING_REFACTOR?: string
    /** T6.1 — when `true`, `/testing` uses legacy `useTestingPage` controller. */
    readonly VITE_TESTING_LEGACY?: string
}

interface ImportMeta {
    readonly env: ImportMetaEnv
}