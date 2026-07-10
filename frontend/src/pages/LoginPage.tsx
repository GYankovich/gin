import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { authService } from '@/services/authService'
import { Button } from '@/components/ui/Button'
import { RobotIllustration } from '@/components/ui/RobotIllustration'

///@EPIC Frontend.ITEM Auth.TOPIC Login Flow [1]
///@ Страница входа: отправка credential в auth API, сохранение сессии в store
///@ и навигация пользователя в защищенную часть приложения.
export default function LoginPage() {
    const navigate = useNavigate()
    const setAuth = useAuthStore(s => s.setAuth)
    const [login, setLogin] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        setLoading(true)
        try {
            const { token, user } = await authService.login({ login, password })
            setAuth(user, token)
            navigate('/dashboard', { replace: true })
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Ошибка входа')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="login-page">
            <div className="login-card">
                <div className="login-card__header">
                    <div className="login-logo" data-text="GIN">
                        <span className="logo-g">G</span>
                        <span className="logo-i">I</span>
                        <span className="logo-n">N</span>
                    </div>
                    <RobotIllustration size={80} />
                </div>

                <form onSubmit={handleSubmit} className="login-form">
                    <div className="form-group">
                        <label className="form-label">Логин</label>
                        <input
                            className="form-input"
                            type="text"
                            value={login}
                            onChange={e => setLogin(e.target.value)}
                            placeholder="Введите логин"
                            autoFocus
                            required
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Пароль</label>
                        <input
                            className="form-input"
                            type="password"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            placeholder="Введите пароль"
                            required
                        />
                    </div>

                    {error && <div className="login-error">{error}</div>}

                    <Button type="submit" variant="primary" size="lg" glow loading={loading} style={{ width: '100%' }}>
                        Войти
                    </Button>
                </form>
            </div>

            <div className="login-bg-grid" />
        </div>
    )
}
