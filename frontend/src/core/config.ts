///@EPIC Frontend.ITEM Core.TOPIC FrontendSrcCoreConfig [1]
///@ Исходный модуль `frontend/src/core/config.ts` — автоматическая разметка для Obsidian Source Scanner.

export const config = {
    api: {
        base: '/api',
        endpoints: {
            login: '/auth/login',
            register: '/auth/register',
            logout: '/auth/logout',
            me: '/auth/me',
            tinvest: '/settings/tinvest'
        }
    },
    routes: {
        login: '/login',
        analytics: '/analytics',
        settings: '/settings',
        // trading: '/trading'
    }
};