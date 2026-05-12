import axios from 'axios'

///@EPIC Frontend.ITEM APIClient.TOPIC Axios Base And Auth Interceptors [1]
///@ Базовый HTTP-клиент фронтенда: подставляет bearer token в запросы и
///@ централизованно обрабатывает 401 (сброс сессии и редирект на login).
export const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
    const token = localStorage.getItem('gin-token')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
})

api.interceptors.response.use(
    (res) => res,
    (err) => {
        if (err.response?.status === 401) {
            localStorage.removeItem('gin-token')
            localStorage.removeItem('gin-user')
            window.location.href = '/login'
        }
        return Promise.reject(err)
    },
)
