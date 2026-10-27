import React, { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/services/api'
import type { ApiKeyItem } from '@/pages/settings/types'
import '@/pages/DashboardPage.css'

function isBybitType(tokenType: string, label?: string) {
    const val = String(tokenType || '').toLowerCase()
    const lbl = String(label || '').toLowerCase()
    return val === '2' || val === 'bybit' || lbl.includes('bybit')
}

type Props = {
    open: boolean
    onClose: () => void
    onCreated: () => void
}

export function CreateTokenModal({ open, onClose, onCreated }: Props) {
    const toast = useToast()
    const [tokenTypes, setTokenTypes] = useState<Array<{ value: string; label: string }>>([])
    const [newName, setNewName] = useState('')
    const [newToken, setNewToken] = useState('')
    const [newTokenType, setNewTokenType] = useState('')
    const [newTokenSecret, setNewTokenSecret] = useState('')
    const [saving, setSaving] = useState(false)
    const [testing, setTesting] = useState(false)
    const [testResult, setTestResult] = useState<string | null>(null)

    const selectedTokenType = tokenTypes.find(x => String(x.value) === String(newTokenType))
    const bybit = isBybitType(newTokenType, selectedTokenType?.label)

    const reset = useCallback(() => {
        setNewName('')
        setNewToken('')
        setNewTokenSecret('')
        setNewTokenType('')
        setTestResult(null)
    }, [])

    const loadTokenTypes = useCallback(async () => {
        try {
            const { data } = await api.post('/dictionary/data', { tableName: 'TOKEN', columnName: 'TYPE' })
            const opts = (Array.isArray(data) ? data : []).map((x: any) => ({
                value: String(x.numericValue ?? x.num_value ?? ''),
                label: String(x.name ?? x.stringValue ?? ''),
            })).filter((x: { value: string }) => !!x.value)
            setTokenTypes(opts)
            if (opts.length > 0) setNewTokenType(prev => prev || opts[0].value)
        } catch {
            setTokenTypes([])
        }
    }, [])

    useEffect(() => {
        if (open) {
            reset()
            void loadTokenTypes()
        }
    }, [open, reset, loadTokenTypes])

    const suggestName = () => {
        if (newName.trim()) return
        const label = selectedTokenType?.label || 'Токен'
        setNewName(`${label} ${new Date().toLocaleDateString('ru-RU')}`)
    }

    const canSubmit = Boolean(
        newName.trim() && newToken && newTokenType && (!bybit || newTokenSecret),
    )

    const handleTest = async () => {
        setTesting(true)
        setTestResult(null)
        try {
            const { data } = await api.post('/apikey/test', {
                token: newToken,
                key_type: newTokenType,
                token_secret: bybit ? newTokenSecret : null,
                testnet: false,
                account_type: 'UNIFIED',
            })
            const valid = Boolean(data?.is_valid)
            const msg = String(data?.message || '')
            setTestResult(valid ? `Валиден: ${msg}` : `Невалиден: ${msg}`)
        } catch (e: any) {
            setTestResult(`Ошибка проверки: ${e?.response?.data?.detail || e?.message || 'unknown'}`)
        }
        setTesting(false)
    }

    const handleSave = async () => {
        setSaving(true)
        try {
            await api.post('/apikey/create', {
                token: newToken,
                key_type: newTokenType,
                name: newName || null,
                token_secret: bybit ? newTokenSecret : null,
                testnet: bybit ? false : null,
                account_type: bybit ? 'UNIFIED' : null,
            })
            toast.show('Токен добавлен', 'success')
            onClose()
            onCreated()
        } catch (e: any) {
            const detail = e?.response?.data?.detail
            const message = typeof detail === 'object' && detail?.description
                ? String(detail.description)
                : (detail || e?.message || 'Ошибка')
            toast.show(String(message), 'error')
        }
        setSaving(false)
    }

    return (
        <Modal
            open={open}
            onClose={onClose}
            title="Токен"
            flush
            className="dash-quiet-modal dash-scene-modal"
            lead={(
                <div className="dash-scene__brand">
                    <p className="dash-scene__kicker">Настройки</p>
                    <p className="dash-scene__title">Добавить токен</p>
                    <p className="dash-scene__line">
                        Ключ брокера для роботов и синхронизации счетов. Можно сначала проверить соединение.
                    </p>
                </div>
            )}
        >
            <div className="dashboard-settings">
                <div className="dashboard-settings-list">
                    <section className="dashboard-settings-group">
                        <header className="dashboard-settings-group__head">
                            <div className="dashboard-settings-group__title-wrap">
                                <span className="dashboard-settings-group__cur">Брокер и ключ</span>
                            </div>
                            <button
                                type="button"
                                className="dashboard-settings-group__bulk"
                                onClick={() => void handleTest()}
                                disabled={testing || !newToken || !newTokenType || (bybit && !newTokenSecret)}
                            >
                                {testing ? 'Проверка…' : 'Проверить'}
                            </button>
                        </header>
                        <div className="settings-scene-fields">
                            <label className="settings-scene-field">
                                <span>Тип брокера</span>
                                <Select
                                    options={tokenTypes}
                                    value={newTokenType}
                                    onChange={setNewTokenType}
                                    placeholder="Выберите тип токена"
                                    size="md"
                                />
                            </label>
                            <label className="settings-scene-field">
                                <span>Название</span>
                                <input
                                    value={newName}
                                    onFocus={suggestName}
                                    onChange={e => setNewName(e.target.value)}
                                    placeholder="Брокерский счёт (торг)"
                                />
                            </label>
                            <label className="settings-scene-field">
                                <span>{bybit ? 'API Key' : 'Токен'}</span>
                                <input
                                    value={newToken}
                                    onChange={e => setNewToken(e.target.value)}
                                    placeholder={bybit ? 'ByBit API Key' : 't.xxx...'}
                                    autoComplete="off"
                                />
                            </label>
                            {bybit ? (
                                <label className="settings-scene-field">
                                    <span>API Secret</span>
                                    <input
                                        type="password"
                                        value={newTokenSecret}
                                        onChange={e => setNewTokenSecret(e.target.value)}
                                        placeholder="ByBit API Secret"
                                        autoComplete="new-password"
                                    />
                                </label>
                            ) : null}
                            {testResult ? (
                                <p
                                    className={`settings-scene-hint${
                                        testResult.startsWith('Валиден') ? ' settings-scene-hint--ok' : ' settings-scene-hint--warn'
                                    }`}
                                >
                                    {testResult}
                                </p>
                            ) : null}
                        </div>
                    </section>
                </div>
                <div className="dashboard-settings-actions">
                    <Button
                        type="button"
                        variant="ghost"
                        size="lg"
                        className="dashboard-settings-actions__apply"
                        loading={saving}
                        disabled={!canSubmit}
                        onClick={() => void handleSave()}
                    >
                        Сохранить
                    </Button>
                </div>
            </div>
        </Modal>
    )
}

type DeleteProps = {
    token: ApiKeyItem | null
    open: boolean
    loading: boolean
    onClose: () => void
    onConfirm: () => void
}

export function DeleteTokenModal({ token, open, loading, onClose, onConfirm }: DeleteProps) {
    const [ack, setAck] = useState(false)

    useEffect(() => {
        if (open) setAck(false)
    }, [open, token?.id])

    if (!token) return null

    return (
        <Modal
            open={open}
            onClose={onClose}
            title="Удаление"
            flush
            className="dash-quiet-modal dash-scene-modal"
            lead={(
                <div className="dash-scene__brand">
                    <p className="dash-scene__kicker">Настройки</p>
                    <p className="dash-scene__title">Удалить токен?</p>
                    <p className="dash-scene__line">
                        Роботы с этим ключом перестанут работать. Действие необратимо.
                    </p>
                </div>
            )}
        >
            <div className="dashboard-settings">
                <div className="dashboard-settings-list">
                    <section className="dashboard-settings-group">
                        <div className="settings-scene-fields">
                            <p className="settings-scene-hint">
                                Токен <strong>{token.name || 'API key'}</strong> будет удалён.
                            </p>
                            <label className="settings-delete-ack">
                                <input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />
                                <span>Я понимаю последствия</span>
                            </label>
                        </div>
                    </section>
                </div>
                <div className="dashboard-settings-actions">
                    <Button
                        type="button"
                        variant="danger"
                        size="lg"
                        className="dashboard-settings-actions__apply"
                        loading={loading}
                        disabled={!ack}
                        onClick={onConfirm}
                    >
                        Удалить
                    </Button>
                </div>
            </div>
        </Modal>
    )
}
