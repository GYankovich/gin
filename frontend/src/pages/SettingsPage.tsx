import React, { useEffect, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Skeleton } from '@/components/ui/Skeleton'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/services/api'

const TABS = ['Профиль', 'API токены', 'Оформление', 'Общие'] as const

export default function SettingsPage() {
    const [tab, setTab] = useState(0)
    const user = useAuthStore(s => s.user)
    const { theme, toggle: toggleTheme } = useThemeStore()
    const toast = useToast()

    type ApiKeyItem = {
        id: number
        name: string | null
        token_type: { type: number; typeName: string; typeDesc: string }
        is_active: boolean
        created_at: string
        masked_token: string
    }
    const [tokens, setTokens] = useState<ApiKeyItem[]>([])
    const [tokenTypes, setTokenTypes] = useState<Array<{ value: string; label: string }>>([])
    const [tokensLoading, setTokensLoading] = useState(false)
    const [addOpen, setAddOpen] = useState(false)
    const [newName, setNewName] = useState('')
    const [newToken, setNewToken] = useState('')
    const [newTokenType, setNewTokenType] = useState('')
    const [saving, setSaving] = useState(false)
    const [testing, setTesting] = useState(false)
    const [testResult, setTestResult] = useState<string | null>(null)

    useEffect(() => {
        if (tab === 1) loadTokens()
    }, [tab])

    const loadTokens = async () => {
        setTokensLoading(true)
        try {
            const { data } = await api.post('/apikey/data', {})
            setTokens(data?.keys ?? [])
        } catch { /* */ }
        setTokensLoading(false)
    }

    const loadTokenTypes = async () => {
        try {
            const { data } = await api.post('/dictionary/data', { tableName: 'TOKEN', columnName: 'TYPE' })
            const opts = (Array.isArray(data) ? data : []).map((x: any) => ({
                value: String(x.stringValue ?? x.name ?? ''),
                label: String(x.name ?? x.stringValue ?? ''),
            })).filter((x: any) => !!x.value)
            setTokenTypes(opts)
            if (!newTokenType && opts.length > 0) setNewTokenType(opts[0].value)
        } catch {
            setTokenTypes([])
        }
    }

    useEffect(() => {
        if (addOpen) loadTokenTypes()
    }, [addOpen])

    const handleAddToken = async () => {
        setSaving(true)
        try {
            await api.post('/apikey/create', {
                token: newToken,
                key_type: newTokenType,
                name: newName || null,
            })
            toast.show('Токен добавлен', 'success')
            setAddOpen(false)
            setNewName('')
            setNewToken('')
            setNewTokenType('')
            loadTokens()
        } catch (e: any) {
            toast.show(e.response?.data?.detail || 'Ошибка', 'error')
        }
        setSaving(false)
    }

    const handleDeleteToken = async (id: number) => {
        try {
            await api.post(`/apikey/delete/${id}`)
            toast.show('Токен удалён', 'success')
            loadTokens()
        } catch { toast.show('Ошибка удаления', 'error') }
    }

    const handleTestToken = async () => {
        setTesting(true)
        setTestResult(null)
        try {
            setTestResult('Проверка для /apikey не реализована')
        } catch (e: any) {
            setTestResult('Ошибка проверки')
        }
        setTesting(false)
    }

    return (
        <div className="page">
            <div className="dashboard-header">
                <h1 className="page__title">Настройки</h1>
                <RobotIllustration size={64} />
            </div>

            <div className="tabs">
                {TABS.map((t, i) => (
                    <button key={t} className={`tab-btn ${i === tab ? 'tab-btn--active' : ''}`} onClick={() => setTab(i)}>{t}</button>
                ))}
            </div>

            {tab === 0 && (
                <Card>
                    <div className="settings-profile">
                        <div className="settings-avatar">
                            <div className="navbar__avatar" style={{ width: 64, height: 64, fontSize: 'var(--text-xl)' }}>
                                {user?.login?.slice(0, 2).toUpperCase() || 'U'}
                            </div>
                        </div>
                        <div className="form-group">
                            <label className="form-label">Логин</label>
                            <input className="form-input" value={user?.login ?? ''} disabled />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Email</label>
                            <input className="form-input" value={user?.email ?? ''} disabled />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Телефон</label>
                            <input className="form-input" value={user?.phone ?? ''} disabled />
                        </div>
                    </div>
                </Card>
            )}

            {tab === 1 && (
                <div className="settings-tokens">
                    <div className="settings-tokens__toolbar">
                        <div className="settings-tokens__intro">
                            <h3 className="settings-tokens__title">API токены</h3>
                            <p className="settings-tokens__subtitle">Управление ключами доступа к внешним сервисам</p>
                        </div>
                        <Button className="settings-tokens__add-btn" variant="primary" glow onClick={() => setAddOpen(true)}>
                            + Добавить токен
                        </Button>
                    </div>

                    {tokensLoading ? <Skeleton height="80px" count={3} /> : (
                        <div className="tokens-list">
                            {tokens.length === 0 && <div className="event-feed__empty">Нет токенов</div>}
                            {tokens.map(t => (
                                <Card key={t.id} className="token-card">
                                    <div className="token-card__header">
                                        <span className="token-card__name">
                                            <span className="token-card__icon">🔑</span>
                                            {t.name || 'API key'}
                                        </span>
                                        <Badge variant={t.is_active ? 'up' : 'neutral'}>{t.is_active ? 'Активен' : 'Неактивен'}</Badge>
                                    </div>
                                    <div className="token-card__meta mono">{t.masked_token}</div>
                                    <div className="token-card__chips">
                                        {t.token_type?.typeName && (
                                            <span className="token-chip token-chip--type">Тип: {t.token_type.typeName}</span>
                                        )}
                                        <span className="token-chip">Создан: {new Date(t.created_at).toLocaleDateString('ru-RU')}</span>
                                    </div>
                                    <div className="token-card__actions">
                                        <Button variant="danger" size="sm" onClick={() => handleDeleteToken(t.id)}>Удалить</Button>
                                    </div>
                                </Card>
                            ))}
                        </div>
                    )}

                    <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Добавить токен" width="480px">
                        <div className="form-group">
                            <label className="form-label">Название</label>
                            <input className="form-input" value={newName} onChange={e => setNewName(e.target.value)} placeholder="Мой токен" />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Токен</label>
                            <input className="form-input" value={newToken} onChange={e => setNewToken(e.target.value)} placeholder="t.xxx..." />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Тип токена</label>
                            <Select
                                options={tokenTypes}
                                value={newTokenType}
                                onChange={setNewTokenType}
                                placeholder="Выберите тип токена"
                            />
                        </div>
                        {testResult && <div className="form-hint" style={{ color: testResult.startsWith('Валиден') ? 'var(--color-up)' : 'var(--color-down)' }}>{testResult}</div>}
                        <div className="form-actions">
                            <Button variant="ghost" size="sm" loading={testing} onClick={handleTestToken} disabled={!newToken}>Проверить</Button>
                            <Button variant="primary" loading={saving} onClick={handleAddToken} disabled={!newName || !newToken || !newTokenType}>Сохранить</Button>
                        </div>
                    </Modal>
                </div>
            )}

            {tab === 2 && (
                <Card>
                    <div className="form-group">
                        <label className="form-label">Тема оформления</label>
                        <div className="form-row" style={{ gap: 'var(--space-3)' }}>
                            <Button variant={theme === 'dark' ? 'primary' : 'secondary'} onClick={() => { if (theme !== 'dark') toggleTheme() }}>
                                🌙 Тёмная (киберпанк)
                            </Button>
                            <Button variant={theme === 'light' ? 'primary' : 'secondary'} onClick={() => { if (theme !== 'light') toggleTheme() }}>
                                ☀ Светлая
                            </Button>
                        </div>
                    </div>
                </Card>
            )}

            {tab === 3 && (
                <Card>
                    <div className="form-group">
                        <label className="form-label">Валюта</label>
                        <Select
                            options={[{ value: 'RUB', label: 'RUB (₽)' }, { value: 'USD', label: 'USD ($)' }]}
                            value="RUB"
                            onChange={() => {}}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Язык</label>
                        <Select
                            options={[{ value: 'ru', label: 'Русский' }, { value: 'en', label: 'English' }]}
                            value="ru"
                            onChange={() => {}}
                        />
                    </div>
                </Card>
            )}
        </div>
    )
}
