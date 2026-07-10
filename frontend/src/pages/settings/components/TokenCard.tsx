import React, { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEyeLowVision, faEyeSlash, faArrowsRotate, faTrashCan } from '@fortawesome/free-solid-svg-icons'
import { faClone } from '@fortawesome/free-regular-svg-icons'
import { Button } from '@/components/ui/Button'
import { api } from '@/services/api'
import type { ApiKeyItem, TokenHealth } from '@/pages/settings/types'
import {
    brokerLabel,
    connectionStatusLabel,
    connectionStatusVariant,
    copyText,
    detectBrokerKind,
    formatRelativeTime,
    inferTokenRights,
} from '@/pages/settings/utils'

type Props = {
    token: ApiKeyItem
    health: TokenHealth
    testing: boolean
    onTest: (id: number) => void
    onDelete: (token: ApiKeyItem) => void
    onRevealError?: (message: string) => void
}

const REVEAL_MS = 3000

export function TokenCard({ token, health, testing, onTest, onDelete, onRevealError }: Props) {
    const [revealedToken, setRevealedToken] = useState<string | null>(null)
    const [revealing, setRevealing] = useState(false)
    const broker = detectBrokerKind(token)
    const rights = inferTokenRights(token)
    const displayToken = revealedToken || token.masked_token
    const status =
        token.status === 3 ? 'expired' : token.status === 1 ? health.status : 'inactive'

    const tokenStatusDescription = String(token.status_description || '').trim()
    const statusLabel = connectionStatusLabel(status)
    const statusChipText = token.status_name?.trim() ? token.status_name.trim() : statusLabel

    useEffect(() => {
        if (!revealedToken) return
        const timer = window.setTimeout(() => setRevealedToken(null), REVEAL_MS)
        return () => window.clearTimeout(timer)
    }, [revealedToken])

    const fetchFullToken = async (): Promise<string | null> => {
        if (revealedToken) return revealedToken
        setRevealing(true)
        try {
            const { data } = await api.post(`/apikey/reveal/${token.id}`)
            const full = String(data?.token || '')
            setRevealedToken(full)
            return full
        } catch {
            onRevealError?.('Не удалось показать токен')
            return null
        } finally {
            setRevealing(false)
        }
    }

    const handleReveal = async () => {
        if (revealedToken) {
            setRevealedToken(null)
            return
        }
        await fetchFullToken()
    }

    const handleCopyToken = async () => {
        const full = await fetchFullToken()
        if (full) await copyText(full)
    }

    const lastUsed = formatRelativeTime(token.last_used_at)
    const createdAt = new Date(token.created_at).toLocaleDateString('ru-RU')

    return (
        <div className="token-row">
            <div className="token-row__identity">
                <span className="token-row__broker">{brokerLabel(broker)}</span>
                <strong className="token-row__name">{token.name || 'API key'}</strong>
            </div>

            <div className="token-row__secret">
                <code className={`token-row__key mono${revealedToken ? ' token-row__key--revealed' : ''}`}>
                    {displayToken}
                </code>
                <div className="token-row__secret-actions">
                    <button
                        type="button"
                        className="settings-icon-btn"
                        onClick={() => void handleReveal()}
                        disabled={revealing}
                        aria-label={revealedToken ? 'Скрыть токен' : 'Показать токен'}
                        title={revealedToken ? 'Скрыть' : 'Показать на 3 сек'}
                    >
                        <FontAwesomeIcon icon={revealedToken ? faEyeSlash : faEyeLowVision} />
                    </button>
                    <button
                        type="button"
                        className="settings-copy-btn"
                        onClick={() => void handleCopyToken()}
                        aria-label="Скопировать токен"
                        title="Скопировать токен"
                    >
                        <FontAwesomeIcon icon={faClone} />
                    </button>
                </div>
            </div>

            <div className="token-row__meta">
                <span
                    className={`token-chip token-chip--status token-chip--status-${connectionStatusVariant(status)}`}
                    title={status === 'expired' ? tokenStatusDescription : undefined}
                >
                    {statusChipText}
                </span>
                <span className={`token-row__rights token-row__rights--${rights.level}`}>{rights.label}</span>
            </div>

            <div className="token-row__dates">
                <span className="token-row__date">
                    <span className="token-row__date-label">Создан</span>
                    <span className="token-row__date-value mono">{createdAt}</span>
                </span>
                <span className="token-row__date">
                    <span className="token-row__date-label">Исп.</span>
                    <span className="token-row__date-value mono">{lastUsed || '—'}</span>
                </span>
            </div>

            <div className="token-row__actions">
                <Button
                    variant="ghost"
                    size="sm"
                    className="token-row__action token-row__action--test"
                    loading={testing}
                    onClick={() => onTest(token.id)}
                >
                    {!testing && <FontAwesomeIcon icon={faArrowsRotate} className="token-row__action-icon" />}
                    Проверить
                </Button>
                <Button
                    variant="danger"
                    size="sm"
                    className="token-row__action token-row__action--delete"
                    onClick={() => onDelete(token)}
                    aria-label="Удалить токен"
                    title="Удалить"
                >
                    <FontAwesomeIcon icon={faTrashCan} className="token-row__action-icon" />
                    <span className="token-row__action-label">Удалить</span>
                </Button>
            </div>
        </div>
    )
}
