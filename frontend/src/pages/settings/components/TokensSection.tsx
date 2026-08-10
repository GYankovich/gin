import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPlus } from '@fortawesome/free-solid-svg-icons'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/services/api'
import { TokenCard } from '@/pages/settings/components/TokenCard'
import { CreateTokenModal, DeleteTokenModal } from '@/pages/settings/components/TokenModals'
import type { ApiKeyItem, TokenHealth } from '@/pages/settings/types'
import { sortTokens } from '@/pages/settings/utils'

type Props = {
    createOpen: boolean
    onCreateOpenChange: (open: boolean) => void
    onCountChange?: (count: number) => void
}

export function TokensSection({ createOpen, onCreateOpenChange, onCountChange }: Props) {
    const toast = useToast()
    const [tokens, setTokens] = useState<ApiKeyItem[]>([])
    const [loading, setLoading] = useState(true)
    const [testingId, setTestingId] = useState<number | null>(null)
    const [healthMap, setHealthMap] = useState<Record<number, TokenHealth>>({})
    const [deleteTarget, setDeleteTarget] = useState<ApiKeyItem | null>(null)
    const [deleting, setDeleting] = useState(false)
    const [removingId, setRemovingId] = useState<number | null>(null)

    const loadTokens = useCallback(async () => {
        setLoading(true)
        try {
            const { data } = await api.post('/apikey/data', {})
            const next = sortTokens(data?.keys ?? [])
            setTokens(next)
            onCountChange?.(next.length)
        } catch {
            toast.show('Не удалось загрузить токены', 'error')
        }
        setLoading(false)
    }, [toast, onCountChange])

    useEffect(() => {
        void loadTokens()
    }, [loadTokens])

    const sortedTokens = useMemo(() => sortTokens(tokens), [tokens])

    const activeCount = useMemo(
        () =>
            sortedTokens.filter(
                (t) => t.status === 1 && (healthMap[t.id]?.status ?? 'unknown') !== 'error',
            ).length,
        [sortedTokens, healthMap],
    )

    const handleTest = async (id: number) => {
        setTestingId(id)
        try {
            const { data } = await api.post(`/apikey/test-stored/${id}`)
            const valid = Boolean(data?.is_valid)
            setHealthMap(prev => ({
                ...prev,
                [id]: {
                    status: valid ? 'active' : 'error',
                    message: valid ? undefined : String(data?.message || 'Ошибка подключения'),
                    checkedAt: new Date().toISOString(),
                },
            }))
            if (valid) {
                setTokens(prev =>
                    prev.map(t =>
                        t.id === id
                            ? {
                                  ...t,
                                  status: 1,
                                  status_name: 'Активный',
                                  status_description: 'Токен активен',
                                  last_error: null,
                                  last_error_at: null,
                              }
                            : t,
                    ),
                )
            }
            toast.show(
                valid ? 'Токен работает' : String(data?.message || 'Ошибка подключения'),
                valid ? 'success' : 'error',
            )
        } catch (e: any) {
            const message = e?.response?.data?.detail || 'Не удалось проверить токен'
            setHealthMap(prev => ({
                ...prev,
                [id]: { status: 'error', message: String(message), checkedAt: new Date().toISOString() },
            }))
            toast.show(String(message), 'error')
        }
        setTestingId(null)
    }

    const handleDelete = async () => {
        if (!deleteTarget) return
        setDeleting(true)
        try {
            await api.post(`/apikey/delete/${deleteTarget.id}`)
            setRemovingId(deleteTarget.id)
            window.setTimeout(() => {
                setTokens(prev => {
                    const next = prev.filter(t => t.id !== deleteTarget.id)
                    onCountChange?.(next.length)
                    return next
                })
                setRemovingId(null)
            }, 220)
            toast.show('Токен удалён', 'success')
            setDeleteTarget(null)
        } catch {
            toast.show('Ошибка удаления', 'error')
        }
        setDeleting(false)
    }

    return (
        <>
            {loading ? (
                <Skeleton height="56px" count={3} />
            ) : sortedTokens.length === 0 ? (
                <div className="empty-state settings-tokens__empty">
                    <p>Нет сохранённых токенов</p>
                    <p className="settings-tokens__hint">
                        Токены нужны для подключения роботов к брокерам. Создайте первый ключ.
                    </p>
                    <button
                        type="button"
                        className="settings-tokens__add"
                        onClick={() => onCreateOpenChange(true)}
                        aria-label="Добавить токен"
                    >
                        <FontAwesomeIcon icon={faPlus} className="settings-tokens__add-icon" />
                    </button>
                </div>
            ) : (
                <>
                    {activeCount === 1 && sortedTokens.length > 1 && (
                        <p className="settings-tokens__warning" role="status">
                            Остался только 1 активный токен — рекомендуем добавить резервный.
                        </p>
                    )}
                    <div className="tokens-list" role="list">
                        {sortedTokens.map((token, index) => {
                            const health = healthMap[token.id] || {
                                status: token.status === 1 ? 'unknown' : 'inactive',
                            }
                            const isTesting = testingId === token.id
                            const isRemoving = removingId === token.id
                            return (
                                <div
                                    key={token.id}
                                    role="listitem"
                                    className={[
                                        'settings-token-wrap',
                                        isTesting ? 'settings-token-wrap--testing' : '',
                                        isRemoving ? 'settings-token-wrap--removing' : '',
                                    ]
                                        .filter(Boolean)
                                        .join(' ')}
                                    style={{ animationDelay: `${Math.min(index, 5) * 40}ms` }}
                                >
                                    <TokenCard
                                        token={token}
                                        health={health}
                                        testing={isTesting}
                                        onTest={handleTest}
                                        onDelete={setDeleteTarget}
                                        onRevealError={msg => toast.show(msg, 'error')}
                                    />
                                </div>
                            )
                        })}
                    </div>
                </>
            )}

            <CreateTokenModal
                open={createOpen}
                onClose={() => onCreateOpenChange(false)}
                onCreated={() => void loadTokens()}
            />
            <DeleteTokenModal
                token={deleteTarget}
                open={Boolean(deleteTarget)}
                loading={deleting}
                onClose={() => setDeleteTarget(null)}
                onConfirm={() => void handleDelete()}
            />
        </>
    )
}
