import React, { useCallback, useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowsRotate, faTrashCan, faEllipsisVertical } from '@fortawesome/free-solid-svg-icons'
import { Button } from '@/components/ui/Button'
import { MobileDockDropdown } from '@/components/ui/MobileDockDropdown'
import { Tooltip } from '@/components/ui/Tooltip'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/services/api'
import { BrokerIcon } from '@/pages/settings/components/BrokerIcon'
import { useCopyGesture } from '@/pages/settings/hooks/useLongPressCopy'
import type { ApiKeyItem, TokenHealth } from '@/pages/settings/types'
import {
    connectionStatusLabel,
    copyText,
    detectBrokerKind,
    formatRelativeTime,
    inferTokenRights,
    tokenStatusChipVariant,
} from '@/pages/settings/utils'

type Props = {
    token: ApiKeyItem
    health: TokenHealth
    testing: boolean
    onTest: (id: number) => void
    onDelete: (token: ApiKeyItem) => void
    onRevealError?: (message: string) => void
}

type RevealedCreds = {
    token: string
    secret: string | null
}

const REVEAL_MS = 3000

function TokenSecretRow({
    label,
    value,
    revealed,
    onCopy,
    showActions,
}: {
    label: string
    value: string
    revealed: boolean
    onCopy: () => Promise<boolean>
    showActions: boolean
}) {
    const toast = useToast()
    const { className: copyClass, ...copyHandlers } = useCopyGesture(async () => {
        const ok = await onCopy()
        if (ok) toast.show('Скопировано', 'success')
        else toast.show('Не удалось скопировать', 'error')
    })

    return (
        <div className="token-row__secret">
            <span className="token-row__secret-label">{label}</span>
            {showActions ? (
                <code
                    className={`token-row__key mono ${copyClass}${revealed ? ' token-row__key--revealed' : ''}`}
                    {...copyHandlers}
                >
                    {value}
                </code>
            ) : (
                <code className={`token-row__key mono${revealed ? ' token-row__key--revealed' : ''}`}>
                    {value}
                </code>
            )}
        </div>
    )
}

export function TokenCard({ token, health, testing, onTest, onDelete, onRevealError }: Props) {
    const [revealed, setRevealed] = useState<RevealedCreds | null>(null)
    const [detailsOpen, setDetailsOpen] = useState(false)
    const [actionsMenuOpen, setActionsMenuOpen] = useState(false)
    useEffect(() => {
        if (!detailsOpen) setActionsMenuOpen(false)
    }, [detailsOpen])

    const broker = detectBrokerKind(token)
    const rights = inferTokenRights(token)
    const hasSecret =
        broker === 'bybit' &&
        Boolean(
            token.masked_secret ||
                token.extra_data?.has_token_secret ||
                token.extra_data?.token_secret,
        )
    const displayToken = revealed?.token || token.masked_token
    const displaySecret = revealed?.secret || token.masked_secret || '••••••••'
    const status =
        token.status === 3 ? 'expired' : token.status === 1 ? health.status : 'inactive'
    const isExpired = status === 'expired'

    const statusLabel =
        health.status === 'error'
            ? connectionStatusLabel('error')
            : token.status_name?.trim()
              ? token.status_name.trim()
              : connectionStatusLabel(status)
    const statusVariant = tokenStatusChipVariant(token, health)

    useEffect(() => {
        if (!revealed) return
        const timer = window.setTimeout(() => setRevealed(null), REVEAL_MS)
        return () => window.clearTimeout(timer)
    }, [revealed])

    const fetchFullCreds = async (): Promise<RevealedCreds | null> => {
        if (revealed) return revealed
        try {
            const { data } = await api.post(`/apikey/reveal/${token.id}`)
            const next: RevealedCreds = {
                token: String(data?.token || ''),
                secret: data?.token_secret != null && String(data.token_secret) ? String(data.token_secret) : null,
            }
            setRevealed(next)
            return next
        } catch {
            onRevealError?.('Не удалось показать токен')
            return null
        }
    }

    const handleCopyToken = async (): Promise<boolean> => {
        const creds = await fetchFullCreds()
        if (!creds?.token) return false
        return copyText(creds.token)
    }

    const handleCopySecret = async (): Promise<boolean> => {
        const creds = await fetchFullCreds()
        if (!creds?.secret) return false
        return copyText(creds.secret)
    }

    const nameWrapRef = useRef<HTMLElement>(null)
    const nameTextRef = useRef<HTMLSpanElement>(null)
    const [marquee, setMarquee] = useState(false)
    const tokenTitle = token.name || 'API key'

    const syncNameMarquee = useCallback(() => {
        const wrap = nameWrapRef.current
        const text = nameTextRef.current
        if (!wrap || !text) {
            setMarquee(false)
            return
        }
        const truncated = text.scrollWidth > wrap.clientWidth + 1
        if (!truncated) {
            text.style.removeProperty('--marquee-shift')
            text.style.removeProperty('--marquee-duration')
            setMarquee(false)
            return
        }
        const shift = wrap.clientWidth - text.scrollWidth
        const durationSec = Math.min(14, Math.max(3, Math.abs(shift) / 24))
        text.style.setProperty('--marquee-shift', `${shift}px`)
        text.style.setProperty('--marquee-duration', `${durationSec}s`)
        setMarquee(true)
    }, [])

    useEffect(() => {
        syncNameMarquee()
        const wrap = nameWrapRef.current
        if (!wrap || typeof ResizeObserver === 'undefined') {
            window.addEventListener('resize', syncNameMarquee)
            return () => window.removeEventListener('resize', syncNameMarquee)
        }
        const ro = new ResizeObserver(() => syncNameMarquee())
        ro.observe(wrap)
        return () => ro.disconnect()
    }, [syncNameMarquee, tokenTitle])

    const toggleDetails = () => setDetailsOpen((prev) => !prev)

    const stopRowToggle = (e: React.SyntheticEvent) => {
        e.stopPropagation()
    }

    const renderTokenActions = (variant: 'desktop' | 'mobile') => {
        if (variant === 'desktop') {
            return (
                <div className="token-row__actions token-row__actions--desktop">
                    <Tooltip text="Проверить" className="token-row__tip">
                        <Button
                            variant="ghost"
                            size="sm"
                            className="token-row__action token-row__action--test"
                            loading={testing}
                            onClick={() => onTest(token.id)}
                            aria-label="Проверить токен"
                        >
                            {!testing && <FontAwesomeIcon icon={faArrowsRotate} className="token-row__action-icon" />}
                        </Button>
                    </Tooltip>
                    <Tooltip text="Удалить" className="token-row__tip">
                        <Button
                            variant="danger"
                            size="sm"
                            className="token-row__action token-row__action--delete"
                            onClick={() => onDelete(token)}
                            aria-label="Удалить токен"
                        >
                            <FontAwesomeIcon icon={faTrashCan} className="token-row__action-icon" />
                        </Button>
                    </Tooltip>
                </div>
            )
        }

        return (
            <MobileDockDropdown
                open={actionsMenuOpen}
                onOpenChange={setActionsMenuOpen}
                placement="below"
                portaled
                className="token-row__actions--mobile"
            >
                <MobileDockDropdown.Trigger
                    className="token-row__menu-trigger"
                    aria-label="Действия с токеном"
                    onClick={(e) => e.stopPropagation()}
                >
                    <FontAwesomeIcon icon={faEllipsisVertical} className="token-row__action-icon" />
                </MobileDockDropdown.Trigger>
                <MobileDockDropdown.Panel>
                    <MobileDockDropdown.Item
                        icon={<FontAwesomeIcon icon={faArrowsRotate} className="mobile-dock__dropdown-icon" />}
                        disabled={testing}
                        onClick={() => onTest(token.id)}
                    >
                        Проверить
                    </MobileDockDropdown.Item>
                    <MobileDockDropdown.Item
                        variant="danger"
                        icon={<FontAwesomeIcon icon={faTrashCan} className="mobile-dock__dropdown-icon" />}
                        onClick={() => onDelete(token)}
                    >
                        Удалить
                    </MobileDockDropdown.Item>
                </MobileDockDropdown.Panel>
            </MobileDockDropdown>
        )
    }

    const lastUsed = formatRelativeTime(token.last_used_at)
    const createdAt = new Date(token.created_at).toLocaleDateString('ru-RU')
    const isRevealed = Boolean(revealed)

    return (
        <div
            className={`token-row${detailsOpen ? ' token-row--open' : ''}${isExpired ? ' token-row--expired' : ''}`}
        >
            <div
                className="token-row__summary"
                role="button"
                tabIndex={0}
                aria-expanded={detailsOpen}
                aria-controls={`token-details-${token.id}`}
                onClick={toggleDetails}
                onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        toggleDetails()
                    }
                }}
            >
                <BrokerIcon kind={broker} />
                <div className="token-row__summary-text">
                    <strong
                        ref={nameWrapRef}
                        className={`token-row__name${marquee ? ' token-row__name--marquee' : ''}`}
                    >
                        <span ref={nameTextRef} className="token-row__name-text">
                            {tokenTitle}
                        </span>
                    </strong>
                    <div className="token-row__subline">
                        <span className={`token-row__status token-row__status--${statusVariant}`}>
                            {statusLabel}
                        </span>
                        <span className="token-row__last-used mono">
                            {lastUsed || ' '}
                        </span>
                    </div>
                </div>
                <div className="token-row__summary-end" onClick={stopRowToggle} onKeyDown={stopRowToggle}>
                    {renderTokenActions('desktop')}
                    {renderTokenActions('mobile')}
                </div>
            </div>

            {detailsOpen && (
                <div id={`token-details-${token.id}`} className="token-row__body">
                    <div className="token-row__details">
                        <div className={`token-row__secrets${hasSecret ? ' token-row__secrets--pair' : ''}`}>
                            <TokenSecretRow
                                label={hasSecret ? 'API Key' : 'Token'}
                                value={displayToken}
                                revealed={isRevealed}
                                onCopy={handleCopyToken}
                                showActions={!isExpired}
                            />
                            {hasSecret ? (
                                <TokenSecretRow
                                    label="API Secret"
                                    value={displaySecret}
                                    revealed={Boolean(revealed?.secret)}
                                    onCopy={handleCopySecret}
                                    showActions={!isExpired}
                                />
                            ) : null}
                        </div>

                        <div className="token-row__meta">
                            <div className="token-row__meta-item">
                                <span className="token-row__meta-label">Права</span>
                                <span className="token-row__meta-value">{rights.label}</span>
                            </div>
                            <div className="token-row__meta-item">
                                <span className="token-row__meta-label">Создан</span>
                                <span className="token-row__meta-value mono">{createdAt}</span>
                            </div>
                            {token.last_error ? (
                                <div className="token-row__meta-item token-row__meta-item--error">
                                    <span className="token-row__meta-label">Ошибка</span>
                                    <span className="token-row__meta-value">{token.last_error}</span>
                                </div>
                            ) : null}
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
