import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { dashboardService } from '@/services/dashboardService'
import type {
    DashboardAccountItem,
    DashboardAssetItem,
    DashboardCurrencyTotals,
    DashboardDataResponse,
} from '@/types/api'
import { PageHero } from '@/components/ui/PageHero'
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
                <PageHero className="dashboard-hero--node" eyebrow="PORTFOLIO NODE" title="ДАШБОРД" />
                <DashboardSkeleton />
            </div>
        )
    }

    if (!data) {
        return (
            <div className="page" data-page="dashboard">
                <PageHero className="dashboard-hero--node" eyebrow="PORTFOLIO NODE" title="ДАШБОРД" />
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
                className="dashboard-hero--node"
                eyebrow="PORTFOLIO NODE"
                title="ДАШБОРД"
                actions={
                    <Button
                        variant="ghost"
                        size="sm"
                        className="dashboard-hero__cfg"
                        onClick={openSettings}
                        aria-label="Настроить"
                    >
                        <IconSliders />
                        <span className="dashboard-hero__cfg-text">Настроить</span>
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
                        <DashboardStickyStrip
                            totals={stickyTotals}
                            activeCurrency={mobileView}
                            onSelect={setMobileView}
                        />
                    )}

                    {isMobile ? (
                        activeCurrencyRow ? (
                            <CurrencyRowSection
                                currency={activeCurrencyRow.currency}
                                totals={activeCurrencyRow.totals}
                                assets={activeCurrencyRow.assets}
                                accounts={activeCurrencyRow.accounts}
                                showTitle={false}
                                compact
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
                                showTitle={currencyRows.length > 1}
                            />
                        ))
                    )}
                </div>
            )}

            <Modal
                open={settingsOpen}
                onClose={() => setSettingsOpen(false)}
                title="Видимость счетов"
                width="560px"
                className="dashboard-modal"
            >
                <div className="dashboard-settings">
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
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-settings-actions__cancel"
                            onClick={() => setSettingsOpen(false)}
                            disabled={savingVisibility}
                        >
                            Отмена
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="dashboard-settings-actions__apply"
                            onClick={() => void saveVisibility()}
                            loading={savingVisibility}
                        >
                            Применить
                        </Button>
                    </div>
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
    const allVisible = accounts.every((a) => !draftHidden[a.account_id])

    return (
        <section className="dashboard-settings-group">
            <header className="dashboard-settings-group__head">
                <div className="dashboard-settings-group__title-wrap">
                    <span className="dashboard-settings-group__cur">{currency}</span>
                </div>
                <div className="dashboard-settings-group__head-actions">
                    <button
                        type="button"
                        className={`dashboard-settings-group__bulk${allVisible ? '' : ' dashboard-settings-group__bulk--on'}`}
                        onClick={() => onSetGroupVisible(accounts, !allVisible)}
                    >
                        {allVisible ? 'Снять все' : 'Выделить все'}
                    </button>
                </div>
            </header>
            <div className="dashboard-settings-group__rows">
                {accounts.map((a) => (
                    <DashboardSettingsRow
                        key={a.account_id}
                        account={a}
                        included={!draftHidden[a.account_id]}
                        onIncludedChange={(on) => {
                            onDraftHiddenChange((prev) => ({
                                ...prev,
                                [a.account_id]: !on,
                            }))
                        }}
                    />
                ))}
            </div>
        </section>
    )
}

function useOverflowMarquee(content: string) {
    const wrapRef = useRef<HTMLElement>(null)
    const textRef = useRef<HTMLSpanElement>(null)
    const [marquee, setMarquee] = useState(false)

    const sync = useCallback(() => {
        const wrap = wrapRef.current
        const text = textRef.current
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
        sync()
        const wrap = wrapRef.current
        if (!wrap || typeof ResizeObserver === 'undefined') {
            window.addEventListener('resize', sync)
            return () => window.removeEventListener('resize', sync)
        }
        const ro = new ResizeObserver(() => sync())
        ro.observe(wrap)
        return () => ro.disconnect()
    }, [sync, content])

    return { wrapRef, textRef, marquee }
}

function DashboardSettingsRow({
    account,
    included,
    onIncludedChange,
}: {
    account: DashboardAccountItem
    included: boolean
    onIncludedChange: (included: boolean) => void
}) {
    const title = account.account_name || account.external_account_id
    const tag = formatAccountPlatformTag(account.account_type)
    const accountCurrency = (account.summary?.currency || 'RUB').toUpperCase()
    const titleMarquee = useOverflowMarquee(title)

    return (
        <label className={`dashboard-settings-row${included ? '' : ' dashboard-settings-row--off'}`}>
            <input
                type="checkbox"
                className="dashboard-settings-row__check"
                checked={included}
                onChange={(e) => onIncludedChange(e.target.checked)}
                aria-label={included ? `Скрыть ${title}` : `Показать ${title}`}
            />
            <div className="dashboard-settings-row__main">
                <span
                    ref={titleMarquee.wrapRef}
                    className={`dashboard-settings-row__title${
                        titleMarquee.marquee ? ' dashboard-settings-row__title--marquee' : ''
                    }`}
                >
                    <span ref={titleMarquee.textRef} className="dashboard-settings-row__title-text">
                        {title}
                    </span>
                </span>
                <div className="dashboard-settings-row__meta">
                    <span className="dashboard-settings-row__tag">{tag}</span>
                    <span className="dashboard-settings-row__value mono">
                        {formatMoney(account.summary.value, accountCurrency)}
                    </span>
                </div>
            </div>
        </label>
    )
}

function DashboardSkeleton() {
    const isMobile = useMediaQuery('(max-width: 767px)')
    const useAccountCards = useMediaQuery('(max-width: 767px)')

    return (
        <div className="dashboard-layout dashboard-skeleton" aria-busy="true" aria-label="Загрузка дашборда">
            <section className="dashboard-currency-row">
                <div className="dashboard-currency-grid">
                    <Card className="dashboard-totals-card dashboard-skeleton-card">
                        {!isMobile && (
                            <div className="dashboard-totals-card__head">
                                <Skeleton width="72px" height="12px" borderRadius="4px" />
                            </div>
                        )}
                        {isMobile ? (
                            <div className="dashboard-summary-metrics dashboard-summary-metrics--compact">
                                <div className="dashboard-summary-hero">
                                    <div className="dashboard-summary-hero__head">
                                        <Skeleton width="48%" height="10px" borderRadius="4px" />
                                        <Skeleton width="28%" height="10px" borderRadius="4px" />
                                    </div>
                                    <Skeleton width="72%" height="28px" borderRadius="4px" />
                                </div>
                                <div className="dashboard-summary-divider" aria-hidden />
                                <div className="dashboard-summary-hero">
                                    <div className="dashboard-summary-hero__head">
                                        <Skeleton width="48%" height="10px" borderRadius="4px" />
                                        <Skeleton width="28%" height="10px" borderRadius="4px" />
                                    </div>
                                    <Skeleton width="64%" height="28px" borderRadius="4px" />
                                </div>
                            </div>
                        ) : (
                            <div className="dashboard-summary-metrics">
                                <div className="dashboard-summary-metric dashboard-summary-metric--own dashboard-summary-metric--primary">
                                    <Skeleton width="70%" height="10px" borderRadius="4px" />
                                    <div style={{ marginTop: 'var(--space-2)' }}>
                                        <Skeleton width="55%" height="14px" borderRadius="4px" />
                                    </div>
                                </div>
                                <div className="dashboard-summary-metric dashboard-summary-metric--value dashboard-summary-metric--primary">
                                    <Skeleton width="40%" height="10px" borderRadius="4px" />
                                    <div style={{ marginTop: 'var(--space-2)' }}>
                                        <Skeleton width="70%" height="22px" borderRadius="4px" />
                                    </div>
                                </div>
                                <div className="dashboard-summary-metric dashboard-summary-metric--gain">
                                    <Skeleton width="60%" height="10px" borderRadius="4px" />
                                    <div style={{ marginTop: 'var(--space-2)' }}>
                                        <Skeleton width="75%" height="14px" borderRadius="4px" />
                                    </div>
                                </div>
                                <div className="dashboard-summary-metric dashboard-summary-metric--day">
                                    <Skeleton width="48%" height="10px" borderRadius="4px" />
                                    <div style={{ marginTop: 'var(--space-2)' }}>
                                        <Skeleton width="50%" height="14px" borderRadius="4px" />
                                    </div>
                                </div>
                            </div>
                        )}
                    </Card>
                    <Card className="dashboard-assets-card dashboard-skeleton-card">
                        <div className="dashboard-assets-card__head">
                            <Skeleton width="160px" height="12px" borderRadius="4px" />
                        </div>
                        <div className="dashboard-dist-list">
                            {[0, 1, 2, 3].map((i) => (
                                <div key={i} className="dashboard-dist-row">
                                    <div className="dashboard-dist-row__main">
                                        <Skeleton width="88px" height="12px" borderRadius="4px" />
                                        <Skeleton width="36px" height="12px" borderRadius="4px" />
                                    </div>
                                    <Skeleton width="100%" height="6px" borderRadius="999px" />
                                </div>
                            ))}
                        </div>
                    </Card>
                </div>
                {useAccountCards ? (
                    <div className="dashboard-accounts-reveal dashboard-skeleton-reveal">
                        <div className="dashboard-accounts-reveal__strip">
                            <Skeleton width="100%" height="36px" borderRadius="8px" />
                        </div>
                    </div>
                ) : (
                    <div className="dashboard-accounts-collapse dashboard-skeleton-table">
                        <Skeleton width="88px" height="16px" borderRadius="4px" />
                        <div style={{ marginTop: 'var(--space-4)' }}>
                            {[0, 1, 2].map((i) => (
                                <div key={i} className="dashboard-accounts-skel-row">
                                    <Skeleton width="28%" height="14px" borderRadius="4px" />
                                    <Skeleton width="18%" height="14px" borderRadius="4px" />
                                    <Skeleton width="22%" height="14px" borderRadius="4px" />
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </section>
        </div>
    )
}

function DashboardStickyStrip({
    totals,
    activeCurrency,
    onSelect,
}: {
    totals: DashboardCurrencyTotals[]
    activeCurrency: string | null
    onSelect: (currency: string) => void
}) {
    const sentinelRef = useRef<HTMLDivElement>(null)
    const [pinned, setPinned] = useState(false)

    useEffect(() => {
        const sentinel = sentinelRef.current
        if (!sentinel || typeof IntersectionObserver === 'undefined') return
        const observer = new IntersectionObserver(
            ([entry]) => {
                setPinned(!entry.isIntersecting)
            },
            { threshold: 0, rootMargin: '0px 0px 0px 0px' },
        )
        observer.observe(sentinel)
        return () => observer.disconnect()
    }, [])

    return (
        <>
            <div ref={sentinelRef} className="dashboard-sticky-strip-sentinel" aria-hidden />
            <div
                className={`dashboard-sticky-strip${pinned ? ' dashboard-sticky-strip--pinned' : ''}`}
                role="tablist"
                aria-label="Валюта дашборда"
            >
                {totals.map((t) => {
                    const currency = (t.currency || 'RUB').toUpperCase()
                    const active = activeCurrency === currency
                    return (
                        <button
                            key={currency}
                            type="button"
                            role="tab"
                            aria-selected={active}
                            className={`dashboard-sticky-chip${active ? ' dashboard-sticky-chip--active' : ''}`}
                            onClick={() => onSelect(currency)}
                        >
                            <span className="dashboard-sticky-chip__cur">{currency}</span>
                        </button>
                    )
                })}
            </div>
        </>
    )
}

function CurrencyRowSection({
    currency,
    totals,
    assets,
    accounts,
    showTitle,
    compact = false,
}: {
    currency: string
    totals: DashboardCurrencyTotals | null
    assets: DashboardAssetItem[]
    accounts: DashboardAccountItem[]
    showTitle: boolean
    compact?: boolean
}) {
    return (
        <section className="dashboard-currency-row" aria-label={`Сводка ${currency}`}>
            <div className="dashboard-currency-grid">
                {totals ? (
                    <TotalsBlock totals={totals} compact={compact} showCurrency={showTitle} />
                ) : (
                    <Card className="dashboard-totals-card">
                        {showTitle ? (
                            <div className="dashboard-totals-card__head">
                                <h3 className="dashboard-panel-title">Сводка</h3>
                                <span className="dashboard-panel-title">{currency}</span>
                            </div>
                        ) : null}
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
                <AccountsSection accounts={accounts} />
            )}
        </section>
    )
}

function AccountsSection({ accounts }: { accounts: DashboardAccountItem[] }) {
    const useReveal = useMediaQuery('(max-width: 767px)')
    const [open, setOpen] = useState(false)

    if (!useReveal) {
        return (
            <CollapsibleSection
                className="dashboard-accounts-collapse"
                title={
                    <span className="dashboard-collapse__label">
                        <IconWallet />
                        Счета
                    </span>
                }
            >
                <AccountsTable accounts={accounts} forceTable />
            </CollapsibleSection>
        )
    }

    return (
        <div className={`dashboard-accounts-reveal${open ? ' dashboard-accounts-reveal--open' : ''}`}>
            <div className="dashboard-accounts-reveal__strip">
                <button
                    type="button"
                    className={`dashboard-sticky-chip dashboard-accounts-reveal__btn${
                        open ? ' dashboard-sticky-chip--active dashboard-accounts-reveal__btn--active' : ''
                    }`}
                    aria-expanded={open}
                    onClick={() => setOpen((v) => !v)}
                >
                    <span className="dashboard-sticky-chip__cur dashboard-accounts-reveal__btn-label">
                        {open ? 'Скрыть счета' : 'Показать счета'}
                    </span>
                    <span className="dashboard-accounts-reveal__btn-count mono">{accounts.length}</span>
                </button>
            </div>
            <div className="dashboard-accounts-reveal__panel" aria-hidden={!open}>
                <div className="dashboard-accounts-reveal__inner">
                    <AccountsTable accounts={accounts} forceCards />
                </div>
            </div>
        </div>
    )
}

function TotalsBlock({
    totals,
    compact = false,
    showCurrency = false,
}: {
    totals: DashboardCurrencyTotals
    compact?: boolean
    showCurrency?: boolean
}) {
    const d = totals.total_day_over_day_delta
    const dp = totals.total_day_over_day_delta_percent
    const gain = totals.total_minus_own_funds
    const gainPct = totals.total_minus_own_funds_percent
    const currency = (totals.currency || 'RUB').toUpperCase()

    return (
        <Card className="dashboard-totals-card">
            <div className="dashboard-totals-card__head">
                <h3 className="dashboard-panel-title">Сводка</h3>
                {showCurrency ? <span className="dashboard-panel-title">{currency}</span> : null}
            </div>
            {compact ? (
                <div className="dashboard-summary-metrics dashboard-summary-metrics--compact">
                    <div className="dashboard-summary-hero">
                        <div className="dashboard-summary-hero__head">
                            <span className="dashboard-summary-metric__label">Текущая стоимость</span>
                            <span className={`dashboard-summary-hero__day mono ${roiClass(d)}`}>
                                {formatAbsWithPercent(d, dp, totals.currency)}
                            </span>
                        </div>
                        <div className="dashboard-summary-hero__value mono">
                            {formatMoney(totals.total_value, totals.currency)}
                        </div>
                    </div>
                    <div className="dashboard-summary-divider" role="separator" />
                    <div className="dashboard-summary-hero">
                        <div className="dashboard-summary-hero__head">
                            <span className="dashboard-summary-metric__label">Собственные</span>
                            <span className={`dashboard-summary-hero__day mono ${roiClass(gain)}`}>
                                {formatAbsWithPercent(gain, gainPct, totals.currency)}
                            </span>
                        </div>
                        <div className="dashboard-summary-hero__value mono">
                            {formatMoney(totals.total_own_funds, totals.currency)}
                        </div>
                    </div>
                </div>
            ) : (
                <div className="dashboard-summary-metrics">
                    <div className="dashboard-summary-metric dashboard-summary-metric--own dashboard-summary-metric--primary">
                        <span className="dashboard-summary-metric__label">Собственные средства</span>
                        <span className="dashboard-summary-metric__value mono">
                            {formatMoney(totals.total_own_funds, totals.currency)}
                        </span>
                    </div>
                    <div className="dashboard-summary-metric dashboard-summary-metric--value dashboard-summary-metric--primary">
                        <span className="dashboard-summary-metric__label">Текущая стоимость</span>
                        <span className="dashboard-summary-metric__value mono">
                            {formatMoney(totals.total_value, totals.currency)}
                        </span>
                    </div>
                    <div className="dashboard-summary-metric dashboard-summary-metric--gain">
                        <span className="dashboard-summary-metric__label">Общее изменение</span>
                        <span className={`dashboard-summary-metric__value mono ${roiClass(gain)}`}>
                            {formatAbsWithPercent(gain, gainPct, totals.currency)}
                        </span>
                    </div>
                    <div className="dashboard-summary-metric dashboard-summary-metric--day">
                        <span className="dashboard-summary-metric__label">За день</span>
                        <span className={`dashboard-summary-metric__value mono ${roiClass(d)}`}>
                            {formatAbsWithPercent(d, dp, totals.currency)}
                        </span>
                    </div>
                </div>
            )}
        </Card>
    )
}

function AssetsBlock({ currency, items }: { currency: string; items: DashboardAssetItem[] }) {
    const list = (
        <div className="dashboard-dist-list">
            {items.map((a, index) => (
                <div
                    key={`${currency}-${a.type}`}
                    className={`dashboard-dist-row dashboard-dist-row--${assetBarTone(a.type, index)}`}
                    title={formatMoneyCompact(a.value, a.currency)}
                >
                    <div className="dashboard-dist-row__main">
                        <span className="dashboard-dist-row__type">{a.type}</span>
                        <span className="dashboard-dist-row__pct mono">
                            {formatMoneyCompact(a.value, a.currency)} ({Math.round(a.percent)} %)
                        </span>
                    </div>
                    <div className="dashboard-dist-bar-track" aria-hidden>
                        <div
                            className="dashboard-dist-bar-fill"
                            style={{ width: `${clampPercent(a.percent)}%` }}
                        />
                    </div>
                </div>
            ))}
        </div>
    )

    return (
        <Card className="dashboard-assets-card">
            <div className="dashboard-assets-card__head">
                <h3 className="dashboard-panel-title">
                    <IconPie />
                    Структура активов
                </h3>
            </div>
            {list}
        </Card>
    )
}

function AccountCard({
    row,
    index = 0,
    onNavigate,
}: {
    row: DashboardAccountItem
    index?: number
    onNavigate: (accountId: string) => void
}) {
    const title = row.account_name || row.external_account_id
    const active = isAccountActive(row)
    const s = row.summary
    const gain = s.minus_own_funds
    const gainPct = s.minus_own_funds_percent
    const day = s.day_over_day_delta
    const dayPct = s.day_over_day_delta_percent

    const nameWrapRef = useRef<HTMLElement>(null)
    const nameTextRef = useRef<HTMLSpanElement>(null)
    const [nameMarquee, setNameMarquee] = useState(false)

    const syncNameMarquee = useCallback(() => {
        const wrap = nameWrapRef.current
        const text = nameTextRef.current
        if (!wrap || !text) {
            setNameMarquee(false)
            return
        }
        const truncated = text.scrollWidth > wrap.clientWidth + 1
        if (!truncated) {
            text.style.removeProperty('--marquee-shift')
            text.style.removeProperty('--marquee-duration')
            setNameMarquee(false)
            return
        }
        const shift = wrap.clientWidth - text.scrollWidth
        const durationSec = Math.min(14, Math.max(3, Math.abs(shift) / 24))
        text.style.setProperty('--marquee-shift', `${shift}px`)
        text.style.setProperty('--marquee-duration', `${durationSec}s`)
        setNameMarquee(true)
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
    }, [syncNameMarquee, title])

    return (
        <article
            className="dashboard-accounts-card"
            style={{ '--account-card-i': index } as React.CSSProperties}
            role="button"
            tabIndex={0}
            onClick={() => onNavigate(row.account_id)}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onNavigate(row.account_id)
                }
            }}
        >
            <header className="dashboard-accounts-card__head">
                <span
                    className={`dashboard-status-dot${active ? ' dashboard-status-dot--on' : ''}`}
                    aria-hidden
                />
                <div className="dashboard-accounts-card__identity">
                    <div className="dashboard-accounts-card__title-row">
                        <span
                            ref={nameWrapRef}
                            className={`dashboard-accounts-card__name${
                                nameMarquee ? ' dashboard-accounts-card__name--marquee' : ''
                            }`}
                        >
                            <span ref={nameTextRef} className="dashboard-accounts-card__name-text">
                                {title}
                            </span>
                        </span>
                        <span className="dashboard-accounts-card__sync mono">
                            {formatAccountSyncCompact(row.last_account_sync)}
                        </span>
                    </div>
                    <div className="dashboard-accounts-card__meta mono">
                        {formatAccountOpenedText(row.account_opened)}
                    </div>
                </div>
            </header>

            <div className="dashboard-accounts-card__body">
                <div className="dashboard-accounts-card__row">
                    <span className="dashboard-accounts-card__value mono">
                        {formatMoney(s.value, s.currency)}
                    </span>
                    <span className={`dashboard-accounts-card__day mono ${roiClass(day)}`}>
                        {formatPercent(dayPct)}
                    </span>
                </div>
                <div className="dashboard-accounts-card__row dashboard-accounts-card__row--sub">
                    <span className={`dashboard-accounts-card__gain mono ${roiClass(gain)}`}>
                        {formatAbsWithPercent(gain, gainPct, s.currency)}
                    </span>
                    <span className="dashboard-accounts-card__own mono">
                        {formatMoneyCompact(s.own_funds, s.currency)}
                    </span>
                </div>
            </div>
        </article>
    )
}

function AccountsTable({
    accounts,
    forceCards,
    forceTable,
}: {
    accounts: DashboardAccountItem[]
    forceCards?: boolean
    forceTable?: boolean
}) {
    const navigate = useNavigate()
    const cardsQuery = useMediaQuery('(max-width: 767px)')
    const useCards = forceTable ? false : forceCards ? true : cardsQuery

    if (useCards) {
        return (
            <div className="dashboard-accounts-cards">
                {accounts.map((row, index) => (
                    <AccountCard
                        key={row.account_id}
                        row={row}
                        index={index}
                        onNavigate={(accountId) => navigate(`/portfolio?accountId=${accountId}`)}
                    />
                ))}
            </div>
        )
    }

    return (
        <div className="dashboard-accounts-table-wrap">
            <table className="dashboard-accounts-table">
                <thead>
                    <tr>
                        <th>Счёт</th>
                        <th>Обновлено</th>
                        <th className="dashboard-accounts-table__num">Свои средства</th>
                        <th className="dashboard-accounts-table__num">Текущая стоимость</th>
                        <th className="dashboard-accounts-table__num">Дельта</th>
                        <th className="dashboard-accounts-table__num">За день</th>
                    </tr>
                </thead>
                <tbody>
                    {accounts.map((row) => {
                        const title = row.account_name || row.external_account_id
                        const active = isAccountActive(row)
                        const s = row.summary
                        const gain = s.minus_own_funds
                        const gainPct = s.minus_own_funds_percent
                        const day = s.day_over_day_delta
                        const dayPct = s.day_over_day_delta_percent
                        return (
                            <tr
                                key={row.account_id}
                                className="dashboard-accounts-table__row"
                                onClick={() => navigate(`/portfolio?accountId=${row.account_id}`)}
                            >
                                <td>
                                    <span className="dashboard-account-cell">
                                        <span className="dashboard-account-name">
                                            <span
                                                className={`dashboard-status-dot${active ? ' dashboard-status-dot--on' : ''}`}
                                                aria-hidden
                                            />
                                            <span className="dashboard-account-name__text">{title}</span>
                                        </span>
                                        <span className="dashboard-account-opened">
                                            <span className="dashboard-account-opened__label">открыт </span>
                                            {formatAccountOpenedText(row.account_opened)}
                                        </span>
                                    </span>
                                </td>
                                <td className="mono">{formatAccountSyncText(row.last_account_sync)}</td>
                                <td className="dashboard-accounts-table__num mono">
                                    {formatMoney(s.own_funds, s.currency)}
                                </td>
                                <td className="dashboard-accounts-table__num dashboard-accounts-table__sum mono">
                                    {formatMoney(s.value, s.currency)}
                                </td>
                                <td className={`dashboard-accounts-table__num mono ${roiClass(gain)}`}>
                                    {formatAbsWithPercent(gain, gainPct, s.currency)}
                                </td>
                                <td className={`dashboard-accounts-table__num mono ${roiClass(day)}`}>
                                    {formatAbsWithPercent(day, dayPct, s.currency)}
                                </td>
                            </tr>
                        )
                    })}
                </tbody>
            </table>
        </div>
    )
}

function IconSliders() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" d="M5 4v16M12 4v16M19 4v16" />
            <circle cx="5" cy="9" r="2.1" fill="var(--bg-card)" stroke="currentColor" strokeWidth="1.7" />
            <circle cx="12" cy="15" r="2.1" fill="var(--bg-card)" stroke="currentColor" strokeWidth="1.7" />
            <circle cx="19" cy="11" r="2.1" fill="var(--bg-card)" stroke="currentColor" strokeWidth="1.7" />
        </svg>
    )
}

function IconPie() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <path fill="none" stroke="currentColor" strokeWidth="1.7" d="M12 3.6a8.4 8.4 0 1 1-8.4 8.4" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" d="M12 3.6V12h8.4" />
        </svg>
    )
}

function IconWallet() {
    return (
        <svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden>
            <rect x="3.2" y="6.2" width="17.6" height="11.6" rx="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
            <path fill="none" stroke="currentColor" strokeWidth="1.7" d="M3.2 9.4h17.6" />
            <circle cx="16.4" cy="13.6" r="1.05" fill="currentColor" />
        </svg>
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

function assetBarTone(type: string, index: number): 'cyan' | 'magenta' | 'violet' | 'up' | 'warn' {
    const t = type.toLowerCase()
    if (/etf|фонд/.test(t)) return 'cyan'
    if (/share|equity|акци|stock/.test(t)) return 'magenta'
    if (/bond|облиг/.test(t)) return 'warn'
    if (/currenc|cash|валют|деньг|money|currency/.test(t)) return 'up'
    const tones = ['cyan', 'magenta', 'violet', 'warn', 'up'] as const
    return tones[index % tones.length]
}

function isAccountActive(row: DashboardAccountItem): boolean {
    const status = (row.account_status || '').toUpperCase()
    return status === 'OPEN' || status === 'ACTIVE'
}

function formatAccountPlatformTag(type: string | null | undefined): string {
    const raw = String(type || '').trim()
    const t = raw.toLowerCase().replace(/^account_type_/, '')
    if (/tinkoff|t-bank|tbank|broker/.test(t)) return 'T-BANK'
    if (/bybit|unified|contract|spot/.test(t)) return 'BYBIT'
    if (/sber/.test(t)) return 'SBER'
    if (/binance/.test(t)) return 'BINANCE'
    if (!raw) return 'ACC'
    return raw.replace(/_/g, ' ').slice(0, 12).toUpperCase()
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

function formatAccountSyncCompact(iso: string | null | undefined): string {
    if (!iso) return '—'
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return '—'
    const time = date.toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
    })
    const startOfDay = (value: Date) =>
        new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
    const diffDays = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86_400_000)
    if (diffDays === 0) return time
    if (diffDays === 1) return `вчера ${time}`
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
    })
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

function formatMoneySigned(val: number, currency = 'RUB'): string {
    const n = Number(val)
    const sym = currency === 'RUB' ? '₽' : currency
    return `${n >= 0 ? '+' : ''}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${sym}`
}

function formatPercent(val: number | null | undefined): string {
    if (val == null || Number.isNaN(Number(val))) return '—'
    const n = Number(val)
    return `${n >= 0 ? '+' : ''}${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} %`
}

/** Absolute signed amount + optional percent, e.g. `-7 832 ₽ (-0,32 %)`. */
function formatAbsWithPercent(
    abs: number | null | undefined,
    pct: number | null | undefined,
    currency: string,
): string {
    if (abs == null || Number.isNaN(Number(abs))) return '—'
    const money = formatMoneySigned(Number(abs), currency)
    if (pct == null || Number.isNaN(Number(pct))) return money
    return `${money} (${formatPercent(pct)})`
}

function roiClass(val: number | null | undefined): string {
    if (val == null || Number.isNaN(Number(val))) return 'dashboard-delta--flat'
    const n = Number(val)
    if (Math.abs(n) <= 1e-9) return 'dashboard-delta--flat'
    return n > 0 ? 'color-up' : 'color-down'
}
