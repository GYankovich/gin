import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { useBackendStatusStore } from '@/stores/backendStatusStore'
import { probeBackendHealth } from '@/services/backendHealth'

///@EPIC Frontend.ITEM APIClient.TOPIC Axios Base And Auth Interceptors [1]
///@ Базовый HTTP-клиент фронтенда: подставляет bearer token в запросы и
///@ централизованно обрабатывает 401 (сброс сессии и редирект на login).
export const api = axios.create({ baseURL: '/api' })

const MAX_TRANSPORT_RETRIES = 3
const RETRYABLE_STATUSES = new Set([502, 503, 504])

type RetryConfig = InternalAxiosRequestConfig & {
    __transportRetry?: number
    __startedAt?: number
}

function isCanceled(err: AxiosError): boolean {
    return err.code === 'ERR_CANCELED' || err.name === 'CanceledError'
}

function isTransportFailure(err: AxiosError): boolean {
    if (isCanceled(err)) return false
    if (!err.response) return true
    return RETRYABLE_STATUSES.has(err.response.status)
}

function retryDelayMs(attempt: number): number {
    return Math.min(1000 * 2 ** (attempt - 1), 8000)
}

/** Vite historically maps ECONNREFUSED to 500; confirm via /health before banner. */
async function markDownIfHealthFails(startedAt: number): Promise<void> {
    const healthy = await probeBackendHealth()
    if (!healthy) {
        useBackendStatusStore.getState().markDown(startedAt)
    }
}

api.interceptors.request.use((config) => {
    const retryConfig = config as RetryConfig
    if (retryConfig.__startedAt == null) retryConfig.__startedAt = Date.now()
    const token = localStorage.getItem('gin-token')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
})

api.interceptors.response.use(
    (res) => {
        useBackendStatusStore.getState().markReachable()
        return res
    },
    async (err: AxiosError) => {
        const config = err.config as RetryConfig | undefined
        if (config && isTransportFailure(err)) {
            const attempt = (config.__transportRetry ?? 0) + 1
            if (attempt <= MAX_TRANSPORT_RETRIES) {
                config.__transportRetry = attempt
                await new Promise((r) => setTimeout(r, retryDelayMs(attempt)))
                return api.request(config)
            }
            useBackendStatusStore.getState().markDown(config.__startedAt ?? Date.now())
        } else if (err.response?.status === 500) {
            await markDownIfHealthFails(config?.__startedAt ?? Date.now())
        }
        if (err.response?.status === 401) {
            const url = config?.url ?? ''
            // Login/register 401 is a credential error — show it in UI, do not hard-reload.
            const path = url.split('?')[0]
            const isAuthCredentialRequest =
                path === '/auth' ||
                path.endsWith('/auth/confirm') ||
                path.endsWith('/auth/resend') ||
                path.includes('/registration') ||
                path.includes('/auth/login')
            if (!isAuthCredentialRequest) {
                localStorage.removeItem('gin-token')
                localStorage.removeItem('gin-user')
                if (!window.location.pathname.startsWith('/login')) {
                    window.location.href = '/login'
                }
            }
        }
        return Promise.reject(err)
    },
)
