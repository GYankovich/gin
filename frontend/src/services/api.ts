import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'

///@EPIC Frontend.ITEM APIClient.TOPIC Axios Base And Auth Interceptors [1]
///@ Базовый HTTP-клиент фронтенда: подставляет bearer token в запросы и
///@ централизованно обрабатывает 401 (сброс сессии и редирект на login).
export const api = axios.create({ baseURL: '/api' })

const MAX_TRANSPORT_RETRIES = 3
const RETRYABLE_STATUSES = new Set([502, 503, 504])

type RetryConfig = InternalAxiosRequestConfig & { __transportRetry?: number }

function isTransportFailure(err: AxiosError): boolean {
    if (!err.response) return true
    return RETRYABLE_STATUSES.has(err.response.status)
}

function retryDelayMs(attempt: number): number {
    return Math.min(1000 * 2 ** (attempt - 1), 8000)
}

api.interceptors.request.use((config) => {
    const token = localStorage.getItem('gin-token')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
})

api.interceptors.response.use(
    (res) => res,
    async (err: AxiosError) => {
        const config = err.config as RetryConfig | undefined
        if (config && isTransportFailure(err)) {
            const attempt = (config.__transportRetry ?? 0) + 1
            if (attempt <= MAX_TRANSPORT_RETRIES) {
                config.__transportRetry = attempt
                await new Promise((r) => setTimeout(r, retryDelayMs(attempt)))
                return api.request(config)
            }
        }
        if (err.response?.status === 401) {
            localStorage.removeItem('gin-token')
            localStorage.removeItem('gin-user')
            window.location.href = '/login'
        }
        return Promise.reject(err)
    },
)
