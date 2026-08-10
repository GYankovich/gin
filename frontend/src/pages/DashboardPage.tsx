import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { FormLabelTooltip } from '@/components/ui/FormLabelTooltip'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { dashboardService } from '@/services/dashboardService'
import type {
    DashboardAccountItem,
    DashboardAssetItem,
    DashboardCurrencyTotals,
    DashboardDataResponse,
} from '@/types/api'
import { PageHero } from '@/components/ui/PageHero'
import { StatTile } from '@/components/ui/StatTile'
import { RobotIllustration } from '@/components/ui/RobotIllustration'

///@EPIC Frontend.ITEM Dashboard.TOPIC Accounts Summary View [1]
///@ Дашборд: сводка + структура по валюте, скрытые счета, настройка видимости.
const DASHBOARD_RETRY_ANIM_MS = 1800

export default function DashboardPage() {
    const [data, setData] = useState<DashboardDataResponse | null>(null)
    const [loading, setLoading] = useState(true)
    const [retrying, setRetrying] = useState(false)
    const [settingsOpen, setSettingsOpen] = useState(false)
    const [savingVisibility, setSavingVisibility] = useState(false)
    const [draftHidden, setDraftHidden] = useState<Record<number, boolean>>({})

    const load = useCallback(async (opts?: { fromRetry?: boolean }) => {
        const fromRetry = Boolean(opts?.fromRetry)
        const startedAt = Date.now()
        if (fromRetry) setRetrying(true)
        else setLoading(true)
        let succeeded = false
        try {
            const res = await dashboardService.fetchData()
            setData(res)
            succeeded = true
        } catch { /* interceptor */ }
        // On retry failure keep the “alive robot” animation for ~1.5–2s.
        if (fromRetry && !succeeded) {
            const remain = DASHBOARD_RETRY_ANIM_MS - (Date.now() - startedAt)
            if (remain > 0) {
                await new Promise<void>((resolve) => {
                    window.setTimeout(resolve, remain)
                })
            }
        }
        setLoading(false)
        setRetrying(false)
    }, [])

    useEffect(() => {
        void load()
    }, [load])

    const isMobile = useMediaQuery('(max-width: 767px)')
    const [mobileView, setMobileView] = useState<string | null>(null)

    const currencyRows = useMemo(
        () => buildCurrencyRows(data?.totals ?? [], data?.assets ?? [], data?.accounts ?? []),
        [data?.totals, data?.assets, data?.accounts],
    )

    const currencyOptions = useMemo(
        () => currencyRows.map((row) => row.currency),
        [currencyRows],
    )

    useEffect(() => {
        if (!isMobile) return
        setMobileView((prev) => {
            if (prev && currencyOptions.includes(prev)) return prev
            if (currencyOptions.includes('RUB')) return 'RUB'
            if (currencyOptions.includes('USDT')) return 'USDT'
            return currencyOptions[0] ?? null
        })
    }, [currencyOptions, isMobile])

    const activeCurrencyRow = useMemo(() => {
        if (!mobileView) return null
        return currencyRows.find((row) => row.currency === mobileView) ?? null
    }, [currencyRows, mobileView])

    const settingsAccountGroups = useMemo(
        () => buildSettingsAccountGroups(data?.accounts ?? [], data?.totals ?? []),
        [data?.accounts, data?.totals],
    )

    const setGroupAccountsVisible = useCallback((accounts: DashboardAccountItem[], visible: boolean) => {
        setDraftHidden((prev) => {
            const next = { ...prev }
            for (const a of accounts) {
                next[a.account_id] = !visible
            }
            return next
        })
    }, [])

    const openSettings = () => {
        if (!data) return
        const next: Record<number, boolean> = {}
        for (const a of data.accounts) next[a.account_id] = Boolean(a.dashboard_hidden)
        setDraftHidden(next)
        setSettingsOpen(true)
    }

    const saveVisibility = async () => {
        if (!data) return
        const payload = data.accounts.map((a) => ({
            account_id: a.account_id,
            hidden: Boolean(draftHidden[a.account_id]),
        }))
        setSavingVisibility(true)
        try {
            await dashboardService.updateVisibility(payload)
            setSettingsOpen(false)
            await load()
        } catch { /* interceptor */ }
        setSavingVisibility(false)
    }

    if (loading) {
        return (
            <div className="page" data-page="dashboard">
                <PageHero eyebrow="PORTFOLIO NODE" title="ДАШБОРД" subtitle="Сводка капитала · структура · счета" />
                <DashboardSkeleton />
            </div>
        )
    }

    if (!data) {
        return (
            <div className="page" data-page="dashboard">
                <PageHero eyebrow="PORTFOLIO NODE" title="ДАШБОРД" subtitle="Сводка капитала · структура · счета" />
                <Card className={`dashboard-totals-card dashboard-error-card${retrying ? ' dashboard-error-card--retrying' : ''}`}>
                    <div className="dashboard-error-card__robot" aria-hidden>
                        {/* Same default SVG animation as robots-empty-fleet while waiting for the response */}
                        <RobotIllustration
                            size={96}
                            mode={retrying ? 'default' : 'inactive'}
                            interactive={false}
                        />
                    </div>
                    <p className="dashboard-empty">
                        {retrying
                            ? 'Подключаюсь к узлу… загружаю сводку.'
                            : 'Не удалось загрузить данные. Проверьте соединение или повторите попытку.'}
                    </p>
                    {retrying && (
                        <div className="dashboard-error-card__loader" aria-hidden>
                            <div className="soft-loading-bar" />
                        </div>
                    )}
                    <div className="dashboard-error-card__actions">
                        <Button
                            onClick={() => void load({ fromRetry: true })}
                            loading={retrying}
                            disabled={retrying}
                        >
                            Повторить
                        </Button>
                    </div>
                </Card>
            </div>
        )
    }

    const hasContent = currencyRows.length > 0 || data.accounts.length > 0
    const stickyTotals = data.totals

    return (
        <div className="page" data-page="dashboard">
            <PageHero
                eyebrow="PORTFOLIO NODE"
                title="ДАШБОРД"
                subtitle="Сводка капитала · структура · счета"
                actions={
                    <Button variant="ghost" size="sm" className="dashboard-hero__cfg" onClick={openSettings}>
                        Настроить
                    </Button>
                }
            />

            {!hasContent ? (
                <Card>
                    <p className="dashboard-empty">
                        Нет открытых счетов (статус OPEN). Добавьте счёт в T‑Invest или проверьте синхронизацию.
                    </p>
                </Card>
            ) : (
                <div className="dashboard-layout">
                    {isMobile && stickyTotals.length > 1 && (
                        <div
                            className="dashboard-sticky-strip"
                            role="tablist"
                            aria-label="Валюта дашборда"
                        >
                            {stickyTotals.map((t) => {
                                const currency = (t.currency || 'RUB').toUpperCase()
                                const active = mobileView === currency
                                return (
                                    <button
                                        key={currency}
                                        type="button"
                                        role="tab"
                                        aria-selected={active}
                                        className={`dashboard-sticky-chip${active ? ' dashboard-sticky-chip--active' : ''}`}
                                        onClick={() => setMobileView(currency)}
                                    >
                                        <span className="dashboard-sticky-chip__cur">{currency}</span>
                                        <span className="dashboard-sticky-chip__val mono">
                                            {formatMoneyCompact(t.total_value, currency)}
                                        </span>
                                    </button>
                                )
                            })}
                        </div>
                    )}

                    {isMobile ? (
                        activeCurrencyRow ? (
                            <CurrencyRowSection
                                currency={activeCurrencyRow.currency}
                                totals={activeCurrencyRow.totals}
                                assets={activeCurrencyRow.assets}
                                accounts={activeCurrencyRow.accounts}
                                showTitle={false}
                            />
                        ) : (
                            <Card>
                                <p className="dashboard-empty">Нет данных по выбранной валюте.</p>
                            </Card>
                        )
                    ) : (
                        currencyRows.map(({ currency, totals, assets, accounts }) => (
                            <CurrencyRowSection
                                key={currency}
                                currency={currency}
                                totals={totals}
                                assets={assets}
                                accounts={accounts}
                                showTitle
                            />
                        ))
                    )}
                </div>
            )}

            <Modal
                open={settingsOpen}
                onClose={() => setSettingsOpen(false)}
                title={
                    <>
                        Счета на дашборде
                        <FormLabelTooltip text="Снимите галочку, чтобы исключить счёт из сводки, структуры активов и списка счетов на дашборде." />
                    </>
                }
                width="520px"
                className="dashboard-modal"
            >
                <div className="dashboard-settings-list">
                    {settingsAccountGroups.map(({ currency, accounts }) => (
                        <DashboardSettingsGroup
                            key={currency}
                            currency={currency}
                            accounts={accounts}
                            draftHidden={draftHidden}
                            onDraftHiddenChange={setDraftHidden}
                            onSetGroupVisible={setGroupAccountsVisible}
                        />
                    ))}
                </div>
                <div className="dashboard-settings-actions">
                    <Button variant="ghost" onClick={() => setSettingsOpen(false)} disabled={savingVisibility}>
                        Отмена
                    </Button>
                    <Button onClick={() => void saveVisibility()} loading={savingVisibility}>
                        Сохранить
                    </Button>
                </div>
            </Modal>
        </div>
    )
}

function DashboardSettingsGroup({
    currency,
    accounts,
    draftHidden,
    onDraftHiddenChange,
    onSetGroupVisible,
}: {
    currency: string
    accounts: DashboardAccountItem[]
    draftHidden: Record<number, boolean>
    onDraftHiddenChange: React.Dispatch<React.SetStateAction<Record<number, boolean>>>
    onSetGroupVisible: (accounts: DashboardAccountItem[], visible: boolean) => void
}) {
    const [open, setOpen] = useState(true)
    const allVisible = accounts.every((a) => !draftHidden[a.account_id])

    return (
        <section
            className={`dashboard-settings-group${open ? ' dashboard-settings-group--open' : ' dashboard-settings-group--collapsed'}`}
        >
            <div className="dashboard-settings-group__panel">
                <header className="dashboard-settings-group__head">
                    <button
                        type="button"
                        className="dashboard-settings-group__toggle"
                        aria-expanded={open}
                        onClick={() => setOpen((prev) => !prev)}
                    >
                        <span className="dashboard-settings-group__chevron" aria-hidden>
                            {open ? '▾' : '▸'}
                        </span>
                        <span className="dashboard-settings-group__cur">{currency}</span>
                        <span className="dashboard-settings-group__count mono">{accounts.length}</span>
                    </button>
                    <div className="dashboard-settings-group__head-actions">
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-settings-group__bulk"
                            onClick={() => onSetGroupVisible(accounts, !allVisible)}
                        >
                            {allVisible ? 'Снять все' : 'Выделить все'}
                        </Button>
                    </div>
                </header>
                {open && accounts.map((a) => {
                    const included = !draftHidden[a.account_id]
                    const title = a.account_name || a.external_account_id
                    const openedText = formatAccountOpenedText(a.account_opened)
                    const accountCurrency = (a.summary?.currency || 'RUB').toUpperCase()
                    return (
                        <label key={a.account_id} className="dashboard-settings-row">
                            <input
                                type="checkbox"
                                className="dashboard-settings-row__check"
                                checked={included}
                                onChange={(e) => {
                                    const on = e.target.checked
                                    onDraftHiddenChange((prev) => ({
                                        ...prev,
                                        [a.account_id]: !on,
                                    }))
                                }}
                                aria-label={included ? `Скрыть ${title}` : `Показать ${title}`}
                            />
                            <span className="dashboard-settings-row__body">
                                <span className="dashboard-settings-row__title">{title}</span>
                                <span className="dashboard-settings-row__meta mono">
                                    открыт {openedText} · {formatMoneyCompact(a.summary.value, accountCurrency)}
                                </span>
                            </span>
                        </label>
                    )
                })}
            </div>
        </section>
    )
}

function DashboardSkeleton() {
    return (
        <div className="dashboard-layout dashboard-skeleton" aria-busy="true" aria-label="Загрузка дашборда">
            {[0, 1].map((row) => (
                <section key={row} className="dashboard-currency-row">
                    <Skeleton width="48px" height="14px" borderRadius="4px" />
                    <div className="dashboard-currency-grid" style={{ marginTop: 'var(--space-3)' }}>
                        <Card className="dashboard-totals-card dashboard-skeleton-card">
                            <div className="dashboard-totals-card__head">
                                <Skeleton width="72px" height="18px" borderRadius="4px" />
                            </div>
                            <div className="portfolio-stats-grid dashboard-summary-grid">
                                {[0, 1, 2, 3].map((i) => (
                                    <div key={i} className="portfolio-stat-tile">
                                        <Skeleton width="70%" height="12px" borderRadius="4px" />
                                        <div style={{ marginTop: 'var(--space-2)' }}>
                                            <Skeleton width="55%" height="20px" borderRadius="4px" />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </Card>
                        <Card className="dashboard-assets-card dashboard-skeleton-card">
                            <div className="dashboard-assets-card__head">
                                <Skeleton width="140px" height="18px" borderRadius="4px" />
                            </div>
                            <div className="dashboard-dist-list">
                                {[0, 1, 2, 3].map((i) => (
                                    <div key={i} className="dashboard-dist-row">
                                        <div className="dashboard-dist-row__main">
                                            <Skeleton width="88px" height="12px" borderRadius="4px" />
                                            <Skeleton width="160px" height="12px" borderRadius="4px" />
                                        </div>
                                        <Skeleton width="100%" height="4px" borderRadius="999px" />
                                    </div>
                                ))}
                            </div>
                        </Card>
                    </div>
                    <div style={{ marginTop: 'var(--space-3)' }}>
                        <Skeleton width="120px" height="36px" borderRadius="8px" />
                    </div>
                </section>
            ))}
        </div>
    )
}

function CurrencyRowSection({
    currency,
    totals,
    assets,
    accounts,
    showTitle,
}: {
    currency: string
    totals: DashboardCurrencyTotals | null
    assets: DashboardAssetItem[]
    accounts: DashboardAccountItem[]
    showTitle: boolean
}) {
    return (
        <section className="dashboard-currency-row" aria-label={`Сводка ${currency}`}>
            {showTitle && <h2 className="dashboard-section__title">{currency}</h2>}
            <div className="dashboard-currency-grid">
                {totals ? (
                    <TotalsBlock totals={totals} />
                ) : (
                    <Card className="dashboard-totals-card">
                        <p className="dashboard-empty">Нет сводки по {currency}.</p>
                    </Card>
                )}
                {assets.length > 0 ? (
                    <AssetsBlock currency={currency} items={assets} />
                ) : (
                    <Card className="dashboard-assets-card dashboard-error-card">
                        <div className="dashboard-error-card__robot" aria-hidden>
                            <RobotIllustration size={96} mode="inactive" interactive={false} />
                        </div>
                        <p className="dashboard-empty">Нет позиций по {currency}.</p>
                    </Card>
                )}
            </div>

            {accounts.length > 0 && (
                <CollapsibleSection
                    className="dashboard-accounts-collapse"
                    title="Счета "
                    badge={
                        <span className="dashboard-accounts-collapse__count">
                            {accounts.length}
                        </span>
                    }
                    defaultOpen={false}
                >
                    <div className="dashboard-account-stack">
                        {accounts.map((row) => (
                            <AccountSection key={row.account_id} row={row} />
                        ))}
                    </div>
                </CollapsibleSection>
            )}
        </section>
    )
}

function TotalsBlock({ totals }: { totals: DashboardCurrencyTotals }) {
    const d = totals.total_day_over_day_delta
    const dp = totals.total_day_over_day_delta_percent
    const showDayPct = dp != null && d != null && Math.abs(d) > 1e-9
    const showGainPct =
        totals.total_minus_own_funds_percent != null
        && Math.abs(totals.total_minus_own_funds) > 1e-9
    return (
        <Card className="dashboard-totals-card">
            <div className="dashboard-totals-card__head">
                <h3 className="dashboard-panel-title">Сводка</h3>
            </div>
            <div className="portfolio-stats-grid dashboard-summary-grid">
                <StatTile
                    label="Собственные средства"
                    value={formatMoney(totals.total_own_funds, totals.currency)}
                />
                <StatTile
                    label="Текущая стоимость"
                    value={formatMoney(totals.total_value, totals.currency)}
                />
                <StatTile
                    label="К портфелю vs вводы"
                    valueClassName={roiClass(totals.total_minus_own_funds)}
                    value={
                        <>
                            {formatMoneySigned(totals.total_minus_own_funds, totals.currency)}
                            {showGainPct && formatPercentSuffix(totals.total_minus_own_funds_percent)}
                        </>
                    }
                />
                <StatTile
                    label="Изменение к пред. дню"
                    valueClassName={d == null ? '' : roiClass(d)}
                    value={
                        <>
                            {d == null ? '—' : formatMoneySigned(d, totals.currency)}
                            {showDayPct && formatPercentSuffix(dp)}
                        </>
                    }
                />
            </div>
        </Card>
    )
}

function AssetsBlock({ currency, items }: { currency: string; items: DashboardAssetItem[] }) {
    const isMobile = useMediaQuery('(max-width: 767px)')

    const list = (
        <div className="dashboard-dist-list">
            {items.map((a) => {
                const d = a.day_over_day_delta
                const dp = a.day_over_day_delta_percent
                const showDayPct = dp != null && d != null && Math.abs(d) > 1e-9
                return (
                    <div key={`${currency}-${a.type}`} className="dashboard-dist-row">
                        <div className="dashboard-dist-row__main">
                            <span className="dashboard-dist-row__type">{a.type}</span>
                            <span className="dashboard-dist-row__figures mono">
                                <span className="dashboard-dist-row__value">
                                    {formatMoneyCompact(a.value, a.currency)}
                                </span>
                                <span className="dashboard-dist-row__pct">{Math.round(a.percent)}%</span>
                                <span className={`dashboard-dist-row__delta ${d == null ? 'dashboard-dist-row__delta-empty' : roiClass(d)}`}>
                                    {d == null
                                        ? '—'
                                        : `${formatMoneySignedCompact(d, a.currency)}${showDayPct ? formatPercentSuffix(dp) : ''}`}
                                </span>
                            </span>
                        </div>
                        <div className="dashboard-dist-bar-track" aria-hidden>
                            <div
                                className="dashboard-dist-bar-fill"
                                style={{ width: `${clampPercent(a.percent)}%` }}
                            />
                        </div>
                    </div>
                )
            })}
        </div>
    )

    if (isMobile) {
        return (
            <CollapsibleSection
                className="dashboard-assets-collapse"
                title="Структура активов "
                badge={
                    <span className="dashboard-assets-collapse__count">{items.length}</span>
                }
                defaultOpen={false}
            >
                {list}
            </CollapsibleSection>
        )
    }

    return (
        <Card className="dashboard-assets-card">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">Структура активов</h3>
            </div>
            {list}
        </Card>
    )
}

function AccountSection({ row }: { row: DashboardAccountItem }) {
    const navigate = useNavigate()
    const title = row.account_name || row.external_account_id
    const openedText = formatAccountOpenedText(row.account_opened)
    const syncText = formatAccountSyncText(row.last_account_sync)
    const s = row.summary
    const d = s.day_over_day_delta
    const dp = s.day_over_day_delta_percent
    const showDayPct = dp != null && d != null && Math.abs(d) > 1e-9
    const showGainPct =
        s.minus_own_funds_percent != null && Math.abs(s.minus_own_funds) > 1e-9

    const openPortfolio = () => {
        navigate(`/portfolio?accountId=${row.account_id}`)
    }

    return (
        <Card
            className="dashboard-account-card dashboard-account-card--link"
            onClick={openPortfolio}
        >
            <div className="dashboard-account-card__head">
                <h2 className="dashboard-account-card__title">
                    <span className="dashboard-account-card__name">{title}</span>
                    <span className="dashboard-account-card__open">Открыть →</span>
                </h2>
                <div className="dashboard-account-card__meta-sync">
                    <div className="dashboard-account-card__meta mono">
                        <span className="dashboard-account-card__meta-primary">
                            {row.external_account_id} · {row.account_type} · {row.account_status}
                        </span>
                        <span className="dashboard-account-card__meta-opened">
                            открыт {openedText}
                        </span>
                        <span className="dashboard-account-card__meta-sync-append">
                            {' · '}
                            {syncText}
                        </span>
                    </div>
                    <div className="dashboard-account-card__sync mono">
                        <span className="dashboard-account-card__sync-label">обновлено</span>
                        {syncText ? (
                            <span className="dashboard-account-card__sync-value">{syncText}</span>
                        ) : null}
                    </div>
                </div>
            </div>

            <div className="dashboard-account-card__stats">
                <div className="portfolio-stats-grid dashboard-summary-grid">
                    <StatTile
                        label="Собственные средства"
                        value={formatMoney(s.own_funds, s.currency)}
                    />
                    <StatTile
                        label="Текущая стоимость"
                        value={formatMoney(s.value, s.currency)}
                    />
                    <StatTile
                        label="К портфелю vs вводы"
                        valueClassName={roiClass(s.minus_own_funds)}
                        value={
                            <>
                                {formatMoneySigned(s.minus_own_funds, s.currency)}
                                {showGainPct && formatPercentSuffix(s.minus_own_funds_percent)}
                            </>
                        }
                    />
                    <StatTile
                        label="Изменение к пред. дню"
                        valueClassName={d == null ? '' : roiClass(d)}
                        value={
                            <>
                                {d == null ? '—' : formatMoneySigned(d, s.currency)}
                                {showDayPct && formatPercentSuffix(dp)}
                            </>
                        }
                    />
                </div>
            </div>
        </Card>
    )
}

function buildSettingsAccountGroups(
    accounts: DashboardAccountItem[],
    totals: DashboardCurrencyTotals[],
): Array<{
    currency: string
    accounts: DashboardAccountItem[]
    totalValue: number
}> {
    const totalsMap = new Map(
        totals.map((t) => [(t.currency || 'RUB').toUpperCase(), Number(t.total_value ?? 0)] as const),
    )
    const groupsMap = new Map<string, DashboardAccountItem[]>()
    for (const a of accounts) {
        const cur = (a.summary?.currency || 'RUB').toUpperCase()
        const list = groupsMap.get(cur)
        if (list) list.push(a)
        else groupsMap.set(cur, [a])
    }

    return Array.from(groupsMap.keys())
        .sort((a, b) => a.localeCompare(b))
        .map((currency) => {
            const groupAccounts = groupsMap.get(currency) ?? []
            const summed = groupAccounts.reduce(
                (acc, a) => acc + Number(a.summary?.value ?? 0),
                0,
            )
            return {
                currency,
                accounts: groupAccounts,
                totalValue: totalsMap.get(currency) ?? summed,
            }
        })
}

function buildCurrencyRows(
    totals: DashboardCurrencyTotals[],
    assets: DashboardAssetItem[],
    accounts: DashboardAccountItem[],
): Array<{
    currency: string
    totals: DashboardCurrencyTotals | null
    assets: DashboardAssetItem[]
    accounts: DashboardAccountItem[]
}> {
    const assetsMap = new Map<string, DashboardAssetItem[]>()
    for (const a of assets) {
        const cur = (a.currency || 'RUB').toUpperCase()
        const list = assetsMap.get(cur)
        if (list) list.push(a)
        else assetsMap.set(cur, [a])
    }

    const accountsMap = new Map<string, DashboardAccountItem[]>()
    for (const a of accounts) {
        if (a.dashboard_hidden) continue
        const cur = (a.summary?.currency || 'RUB').toUpperCase()
        const list = accountsMap.get(cur)
        if (list) list.push(a)
        else accountsMap.set(cur, [a])
    }

    const totalsMap = new Map(
        totals.map((t) => [(t.currency || 'RUB').toUpperCase(), t] as const),
    )

    const currencies = Array.from(
        new Set([...totalsMap.keys(), ...assetsMap.keys(), ...accountsMap.keys()]),
    ).sort((a, b) => a.localeCompare(b))

    return currencies.map((currency) => ({
        currency,
        totals: totalsMap.get(currency) ?? null,
        assets: assetsMap.get(currency) ?? [],
        accounts: accountsMap.get(currency) ?? [],
    }))
}

function clampPercent(val: number): number {
    if (!Number.isFinite(val)) return 0
    return Math.max(0, Math.min(100, val))
}

function formatAccountOpenedText(iso: string | null | undefined): string {
    if (!iso) return '—'
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return '—'
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    })
}

function formatAccountSyncText(iso: string | null | undefined): string {
    if (!iso) return '—'
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return '—'

    const time = date.toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    })
    const startOfDay = (value: Date) =>
        new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
    const diffDays = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86_400_000)

    if (diffDays === 0) return time
    if (diffDays === 1) return `вчера ${time}`
    const day = date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    })
    return `${day} ${time}`
}

function formatMoney(val: any, currency = 'RUB'): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val ?? 0)
    const sym = currency === 'RUB' ? '₽' : currency
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ' + sym
}

function formatMoneyCompact(val: any, currency = 'RUB'): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    const sym = currency === 'RUB' ? '₽' : currency
    const abs = Math.abs(n)
    if (abs >= 1_000_000) {
        return `${(n / 1_000_000).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} млн ${sym}`
    }
    if (abs >= 10_000) {
        return `${Math.round(n).toLocaleString('ru-RU')} ${sym}`
    }
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ' + sym
}

function formatMoneySigned(val: any, currency = 'RUB'): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    const sym = currency === 'RUB' ? '₽' : currency
    return `${n >= 0 ? '+' : ''}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${sym}`
}

function formatMoneySignedCompact(val: any, currency = 'RUB'): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    const sym = currency === 'RUB' ? '₽' : currency
    const abs = Math.abs(n)
    const sign = n >= 0 ? '+' : ''
    if (abs >= 10_000) {
        return `${sign}${Math.round(n).toLocaleString('ru-RU')} ${sym}`
    }
    return `${sign}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${sym}`
}

function formatPercentSuffix(val: number | null | undefined): string {
    if (val == null || Number.isNaN(Number(val))) return ''
    const n = Number(val)
    return ` (${n >= 0 ? '+' : ''}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%)`
}

function roiClass(val: number | null | undefined, drawdown = false): string {
    if (val == null || Number.isNaN(Number(val))) return ''
    const n = Number(val)
    if (drawdown) return n > 0 ? 'color-down' : 'color-up'
    return n >= 0 ? 'color-up' : 'color-down'
}
