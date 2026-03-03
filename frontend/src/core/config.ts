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
        settings: '/settings'
    }
};