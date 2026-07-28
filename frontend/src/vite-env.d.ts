/// <reference types="vite/client" />
///@EPIC Frontend.ITEM Src.TOPIC FrontendSrcViteEnvD [1]
///@ Исходный модуль `frontend/src/vite-env.d.ts` — автоматическая разметка для Obsidian Source Scanner.


interface ImportMetaEnv {
    readonly VITE_API_BASE: string
    /** Live WS gateway base, e.g. `ws://localhost:8001` or `localhost:8001`. */
    readonly VITE_WS_BASE?: string
    /** Live WS port used in DEV when VITE_WS_BASE is unset (default 8001). */
    readonly VITE_WS_PORT?: string
    /** @deprecated T6.1 — refactored UI is default; use `VITE_TESTING_LEGACY=true` to force legacy. */
    readonly VITE_TESTING_REFACTOR?: string
    /** T6.1 — when `true`, `/testing` uses legacy `useTestingPage` controller. */
    readonly VITE_TESTING_LEGACY?: string
}

interface ImportMeta {
    readonly env: ImportMetaEnv
}