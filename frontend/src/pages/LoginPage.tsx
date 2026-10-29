import React, { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { authService } from '@/services/authService'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import logo from '@/assets/ginity-logo-infinity-g.png'
import './LoginPage.css'

type CardMode = 'login' | 'register'

function errorStatus(err: unknown): number | undefined {
    return (err as { response?: { status?: number } })?.response?.status
}

function isWrongCode(message: string): boolean {
    return message.trim().replace(/\.$/, '') === 'Неверный код'
}

function errorText(err: unknown, fallback: string): string {
    const data = (err as {
        response?: {
            data?: {
                detail?: unknown
                description?: string
                fields?: Record<string, { message?: string }>
            }
        }
    })?.response?.data
    const detail = data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail)) {
        const first = detail[0] as { msg?: string } | undefined
        if (first?.msg) return first.msg
    }
    const fieldMessages = Object.values(data?.fields ?? {})
        .map(field => field?.message)
        .filter((message): message is string => Boolean(message))
    if (fieldMessages.length) return fieldMessages.join(' ')
    if (data?.description) return data.description
    return fallback
}

function EyeIcon({ open }: { open: boolean }) {
    return open ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M3 3l18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M10.6 10.6A2 2 0 0 0 12 14a2 2 0 0 0 1.4-.6" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c5.2 0 8.8 4.2 10 7-0.4 1-1.2 2.4-2.4 3.6M6.1 6.7C4.2 8 2.9 10 2 12c1.2 2.8 4.8 7 10 7 1.4 0 2.7-.3 3.8-.8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
    ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M2 12c1.2-2.8 4.8-7 10-7s8.8 4.2 10 7c-1.2 2.8-4.8 7-10 7s-8.8-4.2-10-7Z" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <circle cx="12" cy="12" r="2.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
    )
}

function PasswordField({
    id,
    label,
    value,
    onChange,
    autoComplete,
    minLength,
    shown,
    onToggle,
}: {
    id: string
    label: string
    value: string
    onChange: (value: string) => void
    autoComplete: string
    minLength?: number
    shown: boolean
    onToggle: () => void
}) {
    return (
        <label className="auth-field" htmlFor={id}>
            <span>{label}</span>
            <span className="auth-password">
                <input
                    id={id}
                    type={shown ? 'text' : 'password'}
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    autoComplete={autoComplete}
                    minLength={minLength}
                    required
                />
                <button
                    type="button"
                    className="auth-eye"
                    onClick={onToggle}
                    aria-label={shown ? 'Скрыть пароль' : 'Показать пароль'}
                >
                    <EyeIcon open={shown} />
                </button>
            </span>
        </label>
    )
}

///@EPIC Frontend.ITEM Auth.TOPIC Login Flow [1]
///@ Карточка входа: код в модалке, регистрация на месте, восстановление по ссылке из письма.
export default function LoginPage() {
    const navigate = useNavigate()
    const location = useLocation()
    const [searchParams] = useSearchParams()
    const setAuth = useAuthStore(s => s.setAuth)
    const theme = useThemeStore(s => s.theme)
    const toggleTheme = useThemeStore(s => s.toggle)
    const toast = useToast()
    const isReset = location.pathname === '/reset'
    const resetToken = searchParams.get('token') || ''

    const [card, setCard] = useState<CardMode>(searchParams.get('mode') === 'register' ? 'register' : 'login')
    const [loginName, setLoginName] = useState('')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [passwordAgain, setPasswordAgain] = useState('')
    const [showPassword, setShowPassword] = useState(false)
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    const [codeOpen, setCodeOpen] = useState(false)
    const [codePurpose, setCodePurpose] = useState<CardMode>('login')
    const [pendingEmail, setPendingEmail] = useState<string | null>(null)
    const [code, setCode] = useState('')
    const [devCode, setDevCode] = useState<string | null>(null)
    const [codeError, setCodeError] = useState('')
    const codeDigitRefs = useRef<Array<HTMLInputElement | null>>([])
    const loginInputRef = useRef<HTMLInputElement>(null)
    const busyRef = useRef(false)
    const autoSubmitRef = useRef(false)

    useEffect(() => {
        if (isReset) return
        const frame = window.requestAnimationFrame(() => {
            loginInputRef.current?.focus({ preventScroll: true })
        })
        return () => window.cancelAnimationFrame(frame)
    }, [isReset, card])

    const runBusy = async (task: () => Promise<void>) => {
        if (busyRef.current) return
        busyRef.current = true
        let shownAt = 0
        const timer = window.setTimeout(() => {
            shownAt = Date.now()
            setLoading(true)
        }, 500)
        try {
            await task()
        } finally {
            window.clearTimeout(timer)
            if (shownAt) {
                const remain = 1000 - (Date.now() - shownAt)
                if (remain > 0) await new Promise(resolve => window.setTimeout(resolve, remain))
            }
            setLoading(false)
            busyRef.current = false
        }
    }

    const [forgotOpen, setForgotOpen] = useState(false)
    const [forgotId, setForgotId] = useState('')
    const [forgotSent, setForgotSent] = useState(false)
    const [forgotDevLink, setForgotDevLink] = useState<string | null>(null)
    const [forgotError, setForgotError] = useState('')

    const [resetLogin, setResetLogin] = useState('')
    const [resetEmail, setResetEmail] = useState('')
    const [resetReady, setResetReady] = useState(false)
    const [resetError, setResetError] = useState('')

    useEffect(() => {
        if (!isReset) return
        if (resetToken.length < 20) {
            setResetError('Ссылка недействительна или устарела.')
            return
        }
        let cancelled = false
        authService.previewPasswordReset(resetToken)
            .then(data => {
                if (cancelled) return
                setResetLogin(data.login)
                setResetEmail(data.email)
                setResetReady(true)
            })
            .catch((err: unknown) => {
                if (!cancelled) setResetError(errorText(err, 'Ссылка недействительна или устарела.'))
            })
        return () => { cancelled = true }
    }, [isReset, resetToken])

    useEffect(() => {
        if (!forgotOpen || !forgotSent || forgotDevLink) return
        const timer = window.setTimeout(() => {
            setForgotOpen(false)
            setForgotSent(false)
        }, 3000)
        return () => window.clearTimeout(timer)
    }, [forgotOpen, forgotSent, forgotDevLink])

    useEffect(() => {
        if (!codeOpen) return
        autoSubmitRef.current = false
        const frame = window.requestAnimationFrame(() => {
            const firstEmpty = Math.min(Math.max(code.length, 0), 5)
            codeDigitRefs.current[firstEmpty]?.focus({ preventScroll: true })
        })
        return () => window.cancelAnimationFrame(frame)
    }, [codeOpen])

    const switchCard = (next: CardMode) => {
        setCard(next)
        setError('')
        setPassword('')
        setPasswordAgain('')
        setShowPassword(false)
    }

    const openForgot = () => {
        setForgotId(loginName)
        setForgotSent(false)
        setForgotDevLink(null)
        setForgotError('')
        setForgotOpen(true)
    }

    const openCode = (purpose: CardMode, pending: { email: string; dev_code?: string | null }) => {
        setCodePurpose(purpose)
        setPendingEmail(pending.email)
        setDevCode(pending.dev_code ?? null)
        setCode(pending.dev_code ?? '')
        setCodeError('')
        setError('')
        setCodeOpen(true)
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (card === 'register') {
            if (!/^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$/.test(loginName.trim())) {
                setError('Логин: 3–32 символа, латиница, цифры, точка, _ или -')
                return
            }
            if (password.length < 8) {
                setError('Пароль — минимум 8 символов')
                return
            }
            if (password !== passwordAgain) {
                setError('Пароли не совпадают')
                return
            }
        }
        await runBusy(async () => {
            try {
                const pending = card === 'register'
                    ? await authService.register({
                        login: loginName.trim(),
                        email: email.trim(),
                        password,
                    })
                    : await authService.requestLoginCode({
                        login: loginName.trim(),
                        password,
                    })
                if (pending.status !== 'confirmation_code_required') {
                    setError('Не удалось отправить код')
                    return
                }
                openCode(card, pending)
            } catch (err: unknown) {
                if (errorStatus(err) === 429) {
                    const knownEmail = card === 'register'
                        ? email.trim().toLowerCase()
                        : (loginName.includes('@') ? loginName.trim().toLowerCase() : '')
                    if (knownEmail) {
                        openCode(card, { email: knownEmail })
                        setCodeError('Код уже отправлен. Проверьте почту или подождите минуту.')
                        return
                    }
                }
                setError(errorText(err, card === 'register' ? 'Не удалось зарегистрироваться' : 'Ошибка входа'))
            }
        })
    }

    const submitCode = async (rawCode: string) => {
        if (!pendingEmail) return
        const nextCode = rawCode.replace(/\D/g, '').slice(0, 6)
        if (nextCode.length !== 6) return
        setCodeError('')
        await runBusy(async () => {
            try {
                const session = codePurpose === 'register'
                    ? await authService.confirmRegistration({ email: pendingEmail, code: nextCode })
                    : await authService.confirmLogin({ email: pendingEmail, code: nextCode })
                setAuth(session.user, session.token)
                navigate('/dashboard', { replace: true })
            } catch (err: unknown) {
                setCodeError(errorText(err, 'Неверный код'))
                setCode('')
                autoSubmitRef.current = false
                window.requestAnimationFrame(() => {
                    codeDigitRefs.current[0]?.focus({ preventScroll: true })
                })
            }
        })
    }

    const confirmCode = async (e: React.FormEvent) => {
        e.preventDefault()
        await submitCode(code)
    }

    const setCodeDigits = (nextRaw: string, focusIndex?: number) => {
        const next = nextRaw.replace(/\D/g, '').slice(0, 6)
        setCode(next)
        if (isWrongCode(codeError)) setCodeError('')
        if (typeof focusIndex === 'number') {
            const idx = Math.min(Math.max(focusIndex, 0), 5)
            window.requestAnimationFrame(() => {
                codeDigitRefs.current[idx]?.focus({ preventScroll: true })
                codeDigitRefs.current[idx]?.select()
            })
        }
        if (next.length === 6 && !autoSubmitRef.current) {
            autoSubmitRef.current = true
            void submitCode(next)
        }
    }

    const resendCode = async () => {
        if (!pendingEmail) return
        setCodeError('')
        await runBusy(async () => {
            try {
                const pending = codePurpose === 'register'
                    ? await authService.resendRegistrationCode(pendingEmail)
                    : await authService.resendLoginCode(pendingEmail)
                setDevCode(pending.dev_code ?? null)
                if (pending.dev_code) setCode(pending.dev_code)
            } catch (err: unknown) {
                setCodeError(errorText(err, 'Не удалось отправить код'))
            }
        })
    }

    const sendResetLink = async (e: React.FormEvent) => {
        e.preventDefault()
        setForgotError('')
        await runBusy(async () => {
            try {
                const result = await authService.requestPasswordReset(forgotId.trim())
                setForgotDevLink(result.dev_link ?? null)
                setForgotSent(true)
            } catch (err: unknown) {
                setForgotError(errorText(err, 'Не удалось отправить письмо'))
            }
        })
    }

    const savePassword = async (e: React.FormEvent) => {
        e.preventDefault()
        setResetError('')
        if (password.length < 8) {
            setResetError('Пароль — минимум 8 символов')
            return
        }
        if (password !== passwordAgain) {
            setResetError('Пароли не совпадают')
            return
        }
        await runBusy(async () => {
            try {
                await authService.resetPassword({ token: resetToken, password })
                toast.show('Пароль изменен', 'success')
                navigate('/login', { replace: true })
            } catch (err: unknown) {
                setResetError(errorText(err, 'Не удалось сохранить пароль'))
            }
        })
    }

    return (
        <div className="auth-screen">
            <button
                type="button"
                className="auth-theme"
                onClick={() => toggleTheme()}
                aria-label={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
                title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
            >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="12" r="8.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M12 3.75a8.25 8.25 0 0 0 0 16.5V3.75Z" fill="currentColor" />
                </svg>
            </button>
            <div className="auth-screen__glow" aria-hidden="true" />
            <div className="auth-screen__grid" aria-hidden="true" />
            <div className="auth-stage">
                <div className="auth-brand">
                    <img className="auth-logo" src={logo} alt="Ginity" />
                    <p className="auth-brand__line">Портфель, бэктест и роботы — в одном кабинете.</p>
                    {!isReset && (
                        <button type="button" className="auth-demo-link" onClick={() => navigate('/demo')}>
                            Посмотреть демо
                        </button>
                    )}
                </div>

                <section className="auth-panel" aria-label="Вход в Ginity">
                    {isReset ? (
                        <form key="reset" className="auth-form auth-swap" onSubmit={savePassword}>
                            <h1 className="auth-title">Создание нового пароля</h1>
                            {resetReady ? (
                                <>
                                    <label className="auth-field">
                                        <span>Логин</span>
                                        <input value={resetLogin} disabled />
                                    </label>
                                    <label className="auth-field">
                                        <span>Почта</span>
                                        <input value={resetEmail} disabled />
                                    </label>
                                    <PasswordField
                                        id="auth-new-password"
                                        label="Новый пароль"
                                        value={password}
                                        onChange={setPassword}
                                        autoComplete="new-password"
                                        minLength={8}
                                        shown={showPassword}
                                        onToggle={() => setShowPassword(v => !v)}
                                    />
                                    <PasswordField
                                        id="auth-new-password-again"
                                        label="Повтор пароля"
                                        value={passwordAgain}
                                        onChange={setPasswordAgain}
                                        autoComplete="new-password"
                                        minLength={8}
                                        shown={showPassword}
                                        onToggle={() => setShowPassword(v => !v)}
                                    />
                                    {resetError && <div className="auth-error" role="alert">{resetError}</div>}
                                    <Button type="submit" variant="primary" size="lg" loading={loading} className="auth-submit">
                                        Сохранить пароль
                                    </Button>
                                </>
                            ) : (
                                <>
                                    {resetError && <div className="auth-error" role="alert">{resetError}</div>}
                                    <button type="button" className="auth-text-link" onClick={() => navigate('/login')}>
                                        Вернуться ко входу
                                    </button>
                                </>
                            )}
                        </form>
                    ) : (
                        <form key={card} className="auth-form auth-swap" onSubmit={handleSubmit}>
                            <h1 className="auth-title">{card === 'login' ? 'Вход' : 'Регистрация'}</h1>
                            <label className="auth-field" htmlFor="auth-login">
                                <span>{card === 'login' ? 'Логин или почта' : 'Логин'}</span>
                                <input
                                    id="auth-login"
                                    ref={loginInputRef}
                                    value={loginName}
                                    onChange={e => setLoginName(e.target.value)}
                                    autoComplete="username"
                                    required
                                />
                            </label>
                            {card === 'register' && (
                                <label className="auth-field" htmlFor="auth-email">
                                    <span>Почта</span>
                                    <input
                                        id="auth-email"
                                        type="email"
                                        value={email}
                                        onChange={e => setEmail(e.target.value)}
                                        autoComplete="email"
                                        required
                                    />
                                </label>
                            )}
                            <PasswordField
                                id="auth-password"
                                label="Пароль"
                                value={password}
                                onChange={setPassword}
                                autoComplete={card === 'register' ? 'new-password' : 'current-password'}
                                minLength={card === 'register' ? 8 : 3}
                                shown={showPassword}
                                onToggle={() => setShowPassword(v => !v)}
                            />
                            {card === 'login' && (
                                <div className="auth-forgot-row">
                                    <button type="button" className="auth-text-link" onClick={openForgot}>
                                        Забыли пароль?
                                    </button>
                                </div>
                            )}
                            {card === 'register' && (
                                <PasswordField
                                    id="auth-password-again"
                                    label="Повтор пароля"
                                    value={passwordAgain}
                                    onChange={setPasswordAgain}
                                    autoComplete="new-password"
                                    minLength={8}
                                    shown={showPassword}
                                    onToggle={() => setShowPassword(v => !v)}
                                />
                            )}
                            {error && (
                                <div className="auth-error" role="alert">
                                    <span>{error}</span>
                                </div>
                            )}
                            <Button type="submit" variant="primary" size="lg" loading={loading} className="auth-submit">
                                {card === 'login' ? 'Войти' : 'Зарегистрироваться'}
                            </Button>
                            <div className="auth-links">
                                {card === 'login' ? (
                                    <p className="auth-switch">
                                        Нет аккаунта?{' '}
                                        <button type="button" onClick={() => switchCard('register')}>Зарегистрироваться</button>
                                    </p>
                                ) : (
                                    <p className="auth-switch">
                                        Уже есть аккаунт?{' '}
                                        <button type="button" onClick={() => switchCard('login')}>Войти</button>
                                    </p>
                                )}
                            </div>
                        </form>
                    )}
                </section>
            </div>

            <Modal
                open={codeOpen}
                onClose={() => setCodeOpen(false)}
                title={codePurpose === 'register' ? 'Подтверждение почты' : 'Подтверждение входа'}
                width="420px"
                className="auth-modal"
            >
                <form className="auth-form" onSubmit={confirmCode}>
                    <p className="auth-hint">
                        Код отправлен на <span>{pendingEmail}</span>. Он действует 15 минут.
                    </p>
                    {devCode && (
                        <p className="auth-hint auth-hint--dev">
                            Почтовый сервер не настроен. Код для разработки: {devCode}
                        </p>
                    )}
                    <div className="auth-field">
                        <span id="auth-code-label">Код из письма</span>
                        <div
                            className={isWrongCode(codeError) ? 'auth-otp auth-otp--invalid' : 'auth-otp'}
                            role="group"
                            aria-labelledby="auth-code-label"
                        >
                            {Array.from({ length: 6 }, (_, index) => (
                                <input
                                    key={index}
                                    ref={el => { codeDigitRefs.current[index] = el }}
                                    id={index === 0 ? 'auth-code' : undefined}
                                    className="auth-otp__cell"
                                    inputMode="numeric"
                                    autoComplete={index === 0 ? 'one-time-code' : 'off'}
                                    pattern="\d*"
                                    maxLength={1}
                                    value={code[index] ?? ''}
                                    aria-label={`Цифра ${index + 1}`}
                                    aria-invalid={isWrongCode(codeError) || undefined}
                                    required={index === 0}
                                    onChange={e => {
                                        const digit = e.target.value.replace(/\D/g, '').slice(-1)
                                        if (!digit) {
                                            setCodeDigits(code.slice(0, index), index)
                                            return
                                        }
                                        // После ошибки любой новый символ начинает код заново
                                        if (codeError) {
                                            setCodeDigits(digit, 1)
                                            return
                                        }
                                        const next = `${code.slice(0, index)}${digit}${code.slice(index + 1)}`.slice(0, 6)
                                        setCodeDigits(next, Math.min(index + 1, 5))
                                    }}
                                    onKeyDown={e => {
                                        if (e.key === 'Backspace' && !code[index] && index > 0) {
                                            e.preventDefault()
                                            setCodeDigits(code.slice(0, index - 1), index - 1)
                                        }
                                    }}
                                    onPaste={e => {
                                        e.preventDefault()
                                        const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
                                        setCodeDigits(pasted, Math.min(Math.max(pasted.length, 1) - 1, 5))
                                    }}
                                />
                            ))}
                        </div>
                    </div>
                    {codeError && !isWrongCode(codeError) && <div className="auth-error" role="alert">{codeError}</div>}
                    <Button type="submit" variant="primary" size="lg" loading={loading} className="auth-submit">
                        Подтвердить
                    </Button>
                    <button type="button" className="auth-text-link" onClick={resendCode} disabled={loading}>
                        Отправить ещё раз
                    </button>
                </form>
            </Modal>

            <Modal
                open={forgotOpen}
                onClose={() => setForgotOpen(false)}
                title="Восстановление пароля"
                width="420px"
                className="auth-modal"
            >
                {forgotSent ? (
                    <div className="auth-form">
                        <p className="auth-hint">Если такой пользователь существует, письмо отправлено.</p>
                        {forgotDevLink && (
                            <p className="auth-hint auth-hint--dev">
                                Почтовый сервер не настроен. Ссылка для разработки:{' '}
                                <a href={forgotDevLink}>{forgotDevLink}</a>
                            </p>
                        )}
                    </div>
                ) : (
                    <form className="auth-form" onSubmit={sendResetLink}>
                        <p className="auth-hint">Введите логин или email, указанный при регистрации.</p>
                        <label className="auth-field" htmlFor="auth-forgot">
                            <span>Логин или почта</span>
                            <input
                                id="auth-forgot"
                                value={forgotId}
                                onChange={e => setForgotId(e.target.value)}
                                autoFocus
                                required
                            />
                        </label>
                        {forgotError && <div className="auth-error" role="alert">{forgotError}</div>}
                        <Button type="submit" variant="primary" size="lg" loading={loading} className="auth-submit">
                            Отправить ссылку
                        </Button>
                    </form>
                )}
            </Modal>
        </div>
    )
}
