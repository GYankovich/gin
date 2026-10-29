import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowsRotate, faCopy, faPlus, faTrashCan } from '@fortawesome/free-solid-svg-icons'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { Toggle } from '@/components/ui/Toggle'
import { useToast } from '@/components/ui/Toast'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { ConnectBrokerEmpty } from '@/components/ConnectBrokerEmpty'
import { api } from '@/services/api'
import { dashboardService } from '@/services/dashboardService'
import { BrokerAccordionCard } from '@/pages/settings/components/BrokerAccordion'
import { BrokerIcon } from '@/pages/settings/components/BrokerIcon'
import {
    IconBrokerMark,
    SettingsSectionLabel,
} from '@/pages/settings/components/SettingsSectionLabel'
import { CreateTokenModal, DeleteTokenModal } from '@/pages/settings/components/TokenModals'
import type { ApiKeyItem, BrokerKind, TokenHealth } from '@/pages/settings/types'
import {
    BROKER_ORDER,
    brokerLabel,
    connectionStatusLabel,
    copyText,
    detectBrokerKind,
    formatRelativeTime,
    inferTokenRights,
    normalizeBrokerKind,
    sortTokens,
} from '@/pages/settings/utils'
import type { DashboardAccountItem } from '@/types/api'
import { formatPortfolioMoney } from '@/utils/portfolioFormat'

type Props = {
    createOpen: boolean
    onCreateOpenChange: (open: boolean) => void
    onCountChange?: (count: number) => void
    /** Mobile stacked-sheet layout (matches settings-mobile.html A). */
    sheet?: boolean
}

type RevealedCreds = {
    token: string
    secret: string | null
}

type BrokerBucket = {
    kind: BrokerKind
    tokens: ApiKeyItem[]
    accounts: DashboardAccountItem[]
}

function TokenLine({
    token,
    health,
    testing,
    onTest,
    onDelete,
    sheet = false,
}: {
    token: ApiKeyItem
    health: TokenHealth
    testing: boolean
    onTest: (id: number) => void
    onDelete: (token: ApiKeyItem) => void
    sheet?: boolean
}) {
    const toast = useToast()
    const [open, setOpen] = useState(false)
    const [revealed, setRevealed] = useState<RevealedCreds | null>(null)

    const broker = detectBrokerKind(token)
    const rights = inferTokenRights(token)
    const hasSecret =
        broker === 'bybit' &&
        Boolean(
            token.masked_secret ||
                token.extra_data?.has_token_secret ||
                token.extra_data?.token_secret,
        )

    const status =
        token.status === 3 ? 'expired' : token.status === 1 ? health.status : 'inactive'
    const statusLabel =
        health.status === 'error'
            ? connectionStatusLabel('error')
            : token.status_name?.trim()
              ? token.status_name.trim()
              : connectionStatusLabel(status)

    const statusClass =
        health.status === 'error' || token.status === 3
            ? 'is-error'
            : token.status === 1
              ? ''
              : 'is-muted'

    const statusDotClass =
        health.status === 'error' || token.status === 3
            ? 'is-err'
            : token.status === 1
              ? ''
              : 'is-warn'

    const lastUsed = formatRelativeTime(token.last_used_at)
    const createdAt = new Date(token.created_at).toLocaleDateString('ru-RU')
    const displayToken = revealed?.token || token.masked_token
    const displaySecret = revealed?.secret || token.masked_secret || '••••••••'

    useEffect(() => {
        if (!revealed) return
        const timer = window.setTimeout(() => setRevealed(null), 3000)
        return () => window.clearTimeout(timer)
    }, [revealed])

    const fetchFullCreds = async (): Promise<RevealedCreds | null> => {
        if (revealed) return revealed
        try {
            const { data } = await api.post(`/apikey/reveal/${token.id}`)
            const next: RevealedCreds = {
                token: String(data?.token || ''),
                secret:
                    data?.token_secret != null && String(data.token_secret)
                        ? String(data.token_secret)
                        : null,
            }
            setRevealed(next)
            return next
        } catch {
            toast.show('Не удалось показать токен', 'error')
            return null
        }
    }

    const copyCred = async (kind: 'token' | 'secret') => {
        const creds = await fetchFullCreds()
        const value = kind === 'token' ? creds?.token : creds?.secret
        if (!value) return
        const ok = await copyText(value)
        toast.show(ok ? 'Скопировано' : 'Не удалось скопировать', ok ? 'success' : 'error')
    }

    if (sheet) {
        return (
            <div className={`settings-sheet-seg-token${open ? ' is-open' : ''}`}>
                <div className="settings-sheet-seg-token__row">
                    <button
                        type="button"
                        className="settings-sheet-seg-token__main"
                        onClick={() => setOpen(v => !v)}
                        aria-expanded={open}
                    >
                        <span className="settings-sheet-seg-token__title">
                            <span
                                className={`settings-sheet-seg-token__dot${statusDotClass ? ` ${statusDotClass}` : ''}`}
                                aria-hidden
                            />
                            <span className="settings-sheet-seg-token__name">
                                {token.name || 'API key'}
                            </span>
                        </span>
                        {lastUsed ? (
                            <span className="settings-sheet-seg-token__meta">{lastUsed}</span>
                        ) : null}
                    </button>
                    <button
                        type="button"
                        className="settings-sheet-seg-token__delete"
                        onClick={() => onDelete(token)}
                        aria-label="Удалить токен"
                    >
                        <FontAwesomeIcon icon={faTrashCan} className="settings-token-line__delete-icon" />
                    </button>
                </div>
                {open ? (
                    <div className="settings-token-details settings-sheet-seg-token__details">
                        <div className="settings-sheet-token-well">
                            <div className="settings-sheet-token-well__top">
                                <div className="settings-sheet-token-well__cred">
                                    <span className="settings-sheet-token-well__lab">
                                        {hasSecret ? 'API Key' : 'Token'}
                                    </span>
                                    <button
                                        type="button"
                                        className="settings-sheet-token-well__val"
                                        onClick={() => void copyCred('token')}
                                    >
                                        {displayToken}
                                    </button>
                                </div>
                                <div className="settings-sheet-token-well__acts">
                                    <button
                                        type="button"
                                        className="settings-sheet-token-well__act"
                                        onClick={() => void copyCred('token')}
                                        aria-label="Копировать"
                                    >
                                        <FontAwesomeIcon
                                            icon={faCopy}
                                            className="settings-sheet-token-well__act-icon"
                                        />
                                    </button>
                                    <button
                                        type="button"
                                        className="settings-sheet-token-well__act"
                                        onClick={() => onTest(token.id)}
                                        disabled={testing}
                                        aria-label={testing ? 'Проверка…' : 'Проверить'}
                                    >
                                        <FontAwesomeIcon
                                            icon={faArrowsRotate}
                                            spin={testing}
                                            className="settings-sheet-token-well__act-icon"
                                        />
                                    </button>
                                </div>
                            </div>
                            {hasSecret ? (
                                <div className="settings-sheet-token-well__cred">
                                    <span className="settings-sheet-token-well__lab">API Secret</span>
                                    <button
                                        type="button"
                                        className="settings-sheet-token-well__val"
                                        onClick={() => void copyCred('secret')}
                                    >
                                        {displaySecret}
                                    </button>
                                </div>
                            ) : null}
                            <p className="settings-token-meta">
                                <span>{rights.label}</span>
                                <span aria-hidden>·</span>
                                <span>создан {createdAt}</span>
                            </p>
                            {token.last_error ? (
                                <p className="settings-hint settings-hint--warn" role="status">
                                    {token.last_error}
                                </p>
                            ) : null}
                        </div>
                    </div>
                ) : null}
            </div>
        )
    }

    return (
        <div className={`settings-detail-row-wrap${open ? ' is-open' : ''}`}>
            <div className="settings-detail-row settings-token-line">
                <button
                    type="button"
                    className="settings-token-line__main"
                    onClick={() => setOpen(v => !v)}
                    aria-expanded={open}
                >
                    <span className="settings-token-line__name">{token.name || 'API key'}</span>
                </button>
                <span className="settings-token-line__meta">
                    <b className={statusClass || undefined}>{statusLabel}</b>
                    {lastUsed ? <span>{lastUsed}</span> : null}
                </span>
                <button
                    type="button"
                    className="settings-token-line__delete"
                    onClick={() => onDelete(token)}
                    aria-label="Удалить токен"
                >
                    <FontAwesomeIcon icon={faTrashCan} className="settings-token-line__delete-icon" />
                </button>
            </div>

            {open && (
                <div className="settings-token-details">
                    <div className="settings-field settings-field--cred">
                        <span>{hasSecret ? 'API Key' : 'Token'}</span>
                        <div className="settings-field__cred-row">
                            <button
                                type="button"
                                className="settings-field__value is-copyable"
                                onClick={() => void copyCred('token')}
                            >
                                {displayToken}
                            </button>
                            <button
                                type="button"
                                className="settings-field__refresh"
                                onClick={() => onTest(token.id)}
                                disabled={testing}
                                aria-label={testing ? 'Проверка…' : 'Проверить'}
                            >
                                <FontAwesomeIcon
                                    icon={faArrowsRotate}
                                    spin={testing}
                                    className="settings-field__refresh-icon"
                                />
                            </button>
                        </div>
                    </div>
                    {hasSecret ? (
                        <div className="settings-field settings-field--cred">
                            <span>API Secret</span>
                            <button
                                type="button"
                                className="settings-field__value is-copyable"
                                onClick={() => void copyCred('secret')}
                            >
                                {displaySecret}
                            </button>
                        </div>
                    ) : null}
                    <p className="settings-token-meta">
                        <span>{rights.label}</span>
                        <span aria-hidden>·</span>
                        <span>создан {createdAt}</span>
                    </p>
                    {token.last_error ? (
                        <p className="settings-hint settings-hint--warn" role="status">
                            {token.last_error}
                        </p>
                    ) : null}
                </div>
            )}
        </div>
    )
}

function AccountLine({
    account,
    saving,
    onToggle,
    sheet = false,
}: {
    account: DashboardAccountItem
    saving: boolean
    onToggle: (account: DashboardAccountItem, included: boolean) => void
    sheet?: boolean
}) {
    const included = !account.dashboard_hidden
    const title = account.account_name || account.external_account_id
    const currency = (account.summary?.currency || '').toUpperCase() || 'RUB'
    const money = formatPortfolioMoney(account.summary?.value, currency)
    const idPart =
        account.external_account_id && account.external_account_id !== title
            ? account.external_account_id
            : null

    if (sheet) {
        return (
            <div className={`settings-sheet-seg-acct${included ? '' : ' is-off'}`}>
                <div className="settings-sheet-seg-acct__body">
                    <span className="settings-sheet-seg-acct__name">{title}</span>
                    {idPart ? (
                        <span className="settings-sheet-seg-acct__meta">{idPart}</span>
                    ) : null}
                </div>
                {money ? (
                    <span className="settings-sheet-seg-acct__money">{money}</span>
                ) : null}
                <Toggle
                    checked={included}
                    disabled={saving}
                    aria-label={
                        included
                            ? `${title}: в сводке дашборда`
                            : `${title}: скрыт из сводки дашборда`
                    }
                    onChange={(next) => onToggle(account, next)}
                />
            </div>
        )
    }

    return (
        <div className={`settings-detail-row settings-account-line${included ? '' : ' is-off'}`}>
            <span className="settings-account-line__name">{title}</span>
            <span className="settings-account-line__meta">{money}</span>
            <Toggle
                checked={included}
                disabled={saving}
                aria-label={
                    included
                        ? `${title}: в сводке дашборда`
                        : `${title}: скрыт из сводки дашборда`
                }
                onChange={(next) => onToggle(account, next)}
            />
        </div>
    )
}

function BrokerDetail({
    bucket,
    healthMap,
    testingId,
    savingAccountId,
    onAddToken,
    onTest,
    onDelete,
    onToggleAccount,
    embedded = false,
}: {
    bucket: BrokerBucket
    healthMap: Record<number, TokenHealth>
    testingId: number | null
    savingAccountId: number | null
    onAddToken: () => void
    onTest: (id: number) => void
    onDelete: (token: ApiKeyItem) => void
    onToggleAccount: (account: DashboardAccountItem, included: boolean) => void
    embedded?: boolean
}) {
    const [sheetTab, setSheetTab] = useState<'tokens' | 'accounts'>('tokens')

    if (embedded) {
        return (
            <div className="settings-sheet-feed settings-sheet-feed--seg">
                <div className="settings-sheet-seg" role="tablist" aria-label="Раздел брокера">
                    <button
                        type="button"
                        role="tab"
                        aria-selected={sheetTab === 'tokens'}
                        className={sheetTab === 'tokens' ? 'is-on' : undefined}
                        onClick={() => setSheetTab('tokens')}
                    >
                        Токены
                        {bucket.tokens.length > 0 ? (
                            <span className="settings-sheet-seg__count">{bucket.tokens.length}</span>
                        ) : null}
                    </button>
                    <button
                        type="button"
                        role="tab"
                        aria-selected={sheetTab === 'accounts'}
                        className={sheetTab === 'accounts' ? 'is-on' : undefined}
                        onClick={() => setSheetTab('accounts')}
                    >
                        Счета
                        {bucket.accounts.length > 0 ? (
                            <span className="settings-sheet-seg__count">{bucket.accounts.length}</span>
                        ) : null}
                    </button>
                </div>

                {sheetTab === 'tokens' ? (
                    <div className="settings-sheet-seg-panel" role="tabpanel">
                        {bucket.tokens.length === 0 ? (
                            <p className="settings-broker-card__empty">Нет токенов</p>
                        ) : (
                            <div className="settings-sheet-feed__list" role="list">
                                {bucket.tokens.map(token => {
                                    const health = healthMap[token.id] || {
                                        status: token.status === 1 ? 'unknown' : 'inactive',
                                    }
                                    return (
                                        <div key={token.id} role="listitem">
                                            <TokenLine
                                                token={token}
                                                health={health}
                                                testing={testingId === token.id}
                                                onTest={onTest}
                                                onDelete={onDelete}
                                                sheet
                                            />
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                        <button
                            type="button"
                            className="settings-sheet-seg-panel__add-row"
                            onClick={onAddToken}
                        >
                            <FontAwesomeIcon icon={faPlus} className="settings-sheet-seg-panel__add-row-icon" />
                            Добавить токен
                        </button>
                    </div>
                ) : (
                    <div className="settings-sheet-seg-panel" role="tabpanel">
                        <p className="settings-sheet-seg-panel__hint">
                            Тумблер — показывать счёт в сводке дашборда
                        </p>
                        {bucket.accounts.length === 0 ? (
                            <p className="settings-broker-card__empty">Нет счетов</p>
                        ) : (
                            <div className="settings-sheet-feed__list" role="list">
                                {bucket.accounts.map(account => (
                                    <div key={account.account_id} role="listitem">
                                        <AccountLine
                                            account={account}
                                            saving={savingAccountId === account.account_id}
                                            onToggle={onToggleAccount}
                                            sheet
                                        />
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        )
    }

    return (
        <Card className="dashboard-totals-card settings-broker-card settings-broker-rail__panel">
            <div className="settings-detail-feed">
                <div className="settings-detail-feed__head">
                    <h3 className="settings-detail-feed__label">Токены</h3>
                    <button
                        type="button"
                        className="settings-detail-feed__add"
                        onClick={onAddToken}
                        aria-label="Добавить токен"
                    >
                        <FontAwesomeIcon icon={faPlus} className="settings-detail-feed__add-icon" />
                    </button>
                </div>
                {bucket.tokens.length === 0 ? (
                    <p className="settings-broker-card__empty">Нет токенов</p>
                ) : (
                    <div className="settings-detail-feed__list" role="list">
                        {bucket.tokens.map(token => {
                            const health = healthMap[token.id] || {
                                status: token.status === 1 ? 'unknown' : 'inactive',
                            }
                            return (
                                <div key={token.id} role="listitem">
                                    <TokenLine
                                        token={token}
                                        health={health}
                                        testing={testingId === token.id}
                                        onTest={onTest}
                                        onDelete={onDelete}
                                    />
                                </div>
                            )
                        })}
                    </div>
                )}

                <div className="settings-detail-feed__accounts-head">
                    <h3 className="settings-detail-feed__label settings-detail-feed__label--next">
                        Счета
                    </h3>
                    <p className="settings-detail-feed__hint">
                        Тумблер — в сводке дашборда
                    </p>
                </div>
                {bucket.accounts.length === 0 ? (
                    <p className="settings-broker-card__empty">Нет счетов</p>
                ) : (
                    <div className="settings-detail-feed__list" role="list">
                        {bucket.accounts.map(account => (
                            <div key={account.account_id} role="listitem">
                                <AccountLine
                                    account={account}
                                    saving={savingAccountId === account.account_id}
                                    onToggle={onToggleAccount}
                                />
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </Card>
    )
}

export function TokensSection({
    createOpen,
    onCreateOpenChange,
    onCountChange,
    sheet: sheetProp,
}: Props) {
    const [searchParams] = useSearchParams()
    // Preview: /settings?emptyBrokers=1
    const previewEmptyBrokers = searchParams.get('emptyBrokers') === '1'
    const toast = useToast()
    const isMobileMq = useMediaQuery('(max-width: 767px)')
    const isMobile = sheetProp ?? isMobileMq
    const [tokens, setTokens] = useState<ApiKeyItem[]>([])
    const [accounts, setAccounts] = useState<DashboardAccountItem[]>([])
    const [loading, setLoading] = useState(true)
    const [testingId, setTestingId] = useState<number | null>(null)
    const [healthMap, setHealthMap] = useState<Record<number, TokenHealth>>({})
    const [deleteTarget, setDeleteTarget] = useState<ApiKeyItem | null>(null)
    const [deleting, setDeleting] = useState(false)
    const [savingAccountId, setSavingAccountId] = useState<number | null>(null)
    const [selectedKind, setSelectedKind] = useState<BrokerKind | null>(null)

    const loadAll = useCallback(async () => {
        setLoading(true)
        try {
            const [tokenRes, accountRows] = await Promise.all([
                api.post('/apikey/data', {}),
                dashboardService.fetchSettingsAccounts(),
            ])
            const nextTokens = sortTokens(tokenRes.data?.keys ?? [])
            setTokens(nextTokens)
            setAccounts(accountRows)
            onCountChange?.(nextTokens.length)
        } catch {
            toast.show('Не удалось загрузить брокеров', 'error')
        }
        setLoading(false)
    }, [toast, onCountChange])

    useEffect(() => {
        void loadAll()
    }, [loadAll])

    const buckets = useMemo(() => {
        const map = new Map<BrokerKind, BrokerBucket>()
        const ensure = (kind: BrokerKind): BrokerBucket => {
            let bucket = map.get(kind)
            if (!bucket) {
                bucket = { kind, tokens: [], accounts: [] }
                map.set(kind, bucket)
            }
            return bucket
        }

        for (const token of sortTokens(tokens)) {
            ensure(detectBrokerKind(token)).tokens.push(token)
        }
        for (const account of accounts) {
            ensure(normalizeBrokerKind(account.broker)).accounts.push(account)
        }

        return BROKER_ORDER
            .filter(kind => kind !== 'other')
            .map(kind => map.get(kind))
            .filter((bucket): bucket is BrokerBucket => Boolean(bucket))
    }, [tokens, accounts])

    useEffect(() => {
        if (buckets.length === 0) {
            setSelectedKind(null)
            return
        }
        setSelectedKind(prev =>
            prev && buckets.some(bucket => bucket.kind === prev) ? prev : buckets[0].kind,
        )
    }, [buckets])

    const selectedBucket = useMemo(
        () => buckets.find(bucket => bucket.kind === selectedKind) ?? null,
        [buckets, selectedKind],
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
                toast.show('Токен активен', 'success')
            } else {
                toast.show(String(data?.message || 'Ошибка подключения'), 'error')
            }
        } catch {
            setHealthMap(prev => ({
                ...prev,
                [id]: { status: 'error', message: 'Ошибка проверки', checkedAt: new Date().toISOString() },
            }))
            toast.show('Не удалось проверить токен', 'error')
        }
        setTestingId(null)
    }

    const handleDelete = async () => {
        if (!deleteTarget) return
        setDeleting(true)
        try {
            await api.post(`/apikey/delete/${deleteTarget.id}`)
            setTokens(prev => {
                const next = prev.filter(t => t.id !== deleteTarget.id)
                onCountChange?.(next.length)
                return next
            })
            toast.show('Токен удалён', 'success')
            setDeleteTarget(null)
        } catch {
            toast.show('Ошибка удаления', 'error')
        }
        setDeleting(false)
    }

    const handleToggleAccount = async (account: DashboardAccountItem, included: boolean) => {
        const hidden = !included
        setSavingAccountId(account.account_id)
        const previous = account.dashboard_hidden
        setAccounts(prev =>
            prev.map(row =>
                row.account_id === account.account_id
                    ? { ...row, dashboard_hidden: hidden }
                    : row,
            ),
        )
        try {
            await dashboardService.updateVisibility([
                { account_id: account.account_id, hidden },
            ])
        } catch {
            setAccounts(prev =>
                prev.map(row =>
                    row.account_id === account.account_id
                        ? { ...row, dashboard_hidden: previous }
                        : row,
                ),
            )
            toast.show('Не удалось обновить счёт', 'error')
        }
        setSavingAccountId(null)
    }

    if (loading) {
        return (
            <div className="settings-brokers" id="tokens">
                <Skeleton height="160px" count={2} />
            </div>
        )
    }

    const showFirstRun = buckets.length === 0 || previewEmptyBrokers

    return (
        <div className="settings-brokers" id="tokens">
            {!showFirstRun && isMobile ? (
                <SettingsSectionLabel
                    icon={<IconBrokerMark />}
                    end={(
                        <button
                            type="button"
                            className="settings-section-label__action"
                            onClick={() => onCreateOpenChange(true)}
                        >
                            + брокер
                        </button>
                    )}
                >
                    Брокеры
                </SettingsSectionLabel>
            ) : null}
            {!showFirstRun && !isMobile ? (
                <div className="settings-brokers__toolbar">
                    <span className="settings-brokers__toolbar-label">Брокеры</span>
                </div>
            ) : null}

            {showFirstRun ? (
                <div className="settings-brokers__first-run">
                    <ConnectBrokerEmpty onConnect={() => onCreateOpenChange(true)} />
                </div>
            ) : isMobile ? (
                <div className="settings-broker-stack" role="list">
                    {buckets.map(bucket => (
                        <div key={bucket.kind} role="listitem">
                            <BrokerAccordionCard
                                bucket={bucket}
                                healthMap={healthMap}
                            >
                                <BrokerDetail
                                    bucket={bucket}
                                    healthMap={healthMap}
                                    testingId={testingId}
                                    savingAccountId={savingAccountId}
                                    onAddToken={() => onCreateOpenChange(true)}
                                    onTest={handleTest}
                                    onDelete={setDeleteTarget}
                                    onToggleAccount={handleToggleAccount}
                                    embedded
                                />
                            </BrokerAccordionCard>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="settings-broker-rail">
                    <nav className="settings-broker-rail__nav" aria-label="Брокеры">
                        {buckets.map(bucket => {
                            const selected = bucket.kind === selectedKind
                            const summary = [
                                bucket.tokens.length
                                    ? `${bucket.tokens.length} ток.`
                                    : null,
                                bucket.accounts.length
                                    ? `${bucket.accounts.length} сч.`
                                    : null,
                            ]
                                .filter(Boolean)
                                .join(' · ')
                            return (
                                <button
                                    key={bucket.kind}
                                    type="button"
                                    className={`settings-broker-rail__item${selected ? ' is-active' : ''}`}
                                    aria-current={selected ? 'page' : undefined}
                                    onClick={() => setSelectedKind(bucket.kind)}
                                >
                                    <BrokerIcon kind={bucket.kind} className="dashboard-icon" />
                                    <span className="settings-broker-rail__item-text">
                                        <span className="settings-broker-rail__item-name">
                                            {brokerLabel(bucket.kind)}
                                        </span>
                                        {summary ? (
                                            <span className="settings-broker-rail__item-meta">
                                                {summary}
                                            </span>
                                        ) : null}
                                    </span>
                                </button>
                            )
                        })}
                        <button
                            type="button"
                            className="settings-broker-rail__add"
                            onClick={() => onCreateOpenChange(true)}
                        >
                            + брокер
                        </button>
                    </nav>

                    {selectedBucket ? (
                        <BrokerDetail
                            key={selectedBucket.kind}
                            bucket={selectedBucket}
                            healthMap={healthMap}
                            testingId={testingId}
                            savingAccountId={savingAccountId}
                            onAddToken={() => onCreateOpenChange(true)}
                            onTest={handleTest}
                            onDelete={setDeleteTarget}
                            onToggleAccount={handleToggleAccount}
                        />
                    ) : null}
                </div>
            )}

            <CreateTokenModal
                open={createOpen}
                onClose={() => onCreateOpenChange(false)}
                onCreated={() => void loadAll()}
            />
            <DeleteTokenModal
                token={deleteTarget}
                open={Boolean(deleteTarget)}
                loading={deleting}
                onClose={() => setDeleteTarget(null)}
                onConfirm={() => void handleDelete()}
            />
        </div>
    )
}
