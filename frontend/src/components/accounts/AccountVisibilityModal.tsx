import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { dashboardService } from '@/services/dashboardService'
import type { DashboardAccountItem } from '@/types/api'
import { formatPortfolioAccountPlatformTag, formatPortfolioMoney } from '@/utils/portfolioFormat'
import '@/pages/DashboardPage.css'

type AccountVisibilityModalProps = {
    open: boolean
    onClose: () => void
    onApplied: () => void | Promise<void>
    currency?: string | null
    broker?: string | null
    kicker: string
    headline: string
    line: string
}

export function AccountVisibilityGear({ onClick }: { onClick: () => void }) {
    return (
        <button type="button" className="dash-gear" onClick={onClick} aria-label="Настроить счета" title="Настроить счета">
            <IconGear />
        </button>
    )
}

export function AccountVisibilityModal({
    open,
    onClose,
    onApplied,
    currency,
    broker,
    kicker,
    headline,
    line,
}: AccountVisibilityModalProps) {
    const [accounts, setAccounts] = useState<DashboardAccountItem[]>([])
    const [draftHidden, setDraftHidden] = useState<Record<number, boolean>>({})
    const [ready, setReady] = useState(false)
    const [saving, setSaving] = useState(false)
    const onCloseRef = useRef(onClose)
    const onAppliedRef = useRef(onApplied)
    onCloseRef.current = onClose
    onAppliedRef.current = onApplied

    useEffect(() => {
        if (!open) {
            setReady(false)
            return
        }
        let cancelled = false
        setReady(false)
        ;(async () => {
            try {
                const rows = await dashboardService.fetchSettingsAccounts({
                    ...(currency ? { currency } : {}),
                    ...(broker ? { broker } : {}),
                })
                if (cancelled) return
                const next: Record<number, boolean> = {}
                for (const account of rows) next[account.account_id] = Boolean(account.dashboard_hidden)
                setAccounts(rows)
                setDraftHidden(next)
                setReady(true)
            } catch {
                if (!cancelled) onCloseRef.current()
            }
        })()
        return () => {
            cancelled = true
        }
    }, [open, currency, broker])

    const includedCount = useMemo(
        () => accounts.filter((account) => !draftHidden[account.account_id]).length,
        [accounts, draftHidden],
    )
    const allVisible = accounts.length > 0 && accounts.every((account) => !draftHidden[account.account_id])
    const currencyCode = (currency || '').trim().toUpperCase()
    const title = currencyCode
        ? `Счета ${currencyCode === 'RUB' ? '₽' : currencyCode}`
        : 'Счета'

    const setAllVisible = (visible: boolean) => {
        setDraftHidden((prev) => {
            const next = { ...prev }
            for (const account of accounts) next[account.account_id] = !visible
            return next
        })
    }

    const apply = async () => {
        setSaving(true)
        try {
            await dashboardService.updateVisibility(
                accounts.map((account) => ({
                    account_id: account.account_id,
                    hidden: Boolean(draftHidden[account.account_id]),
                })),
            )
            onCloseRef.current()
            await onAppliedRef.current()
        } catch { /* interceptor */ }
        setSaving(false)
    }

    return (
        <Modal
            open={open && ready}
            onClose={onClose}
            title={title}
            flush
            className="dash-quiet-modal dash-scene-modal"
            lead={(
                <div className="dash-scene__brand">
                    <p className="dash-scene__kicker">{kicker}</p>
                    <p className="dash-scene__title">{headline}</p>
                    <p className="dash-scene__line">{line}</p>
                </div>
            )}
        >
            <div className="dashboard-settings">
                <div className="dashboard-settings-list">
                    <section className="dashboard-settings-group">
                        {accounts.length > 0 ? (
                            <header className="dashboard-settings-group__head">
                                <div className="dashboard-settings-group__title-wrap">
                                    <span className="dashboard-settings-group__cur">
                                        В сводке {includedCount} из {accounts.length}
                                    </span>
                                </div>
                                <button
                                    type="button"
                                    className={`dashboard-settings-group__bulk${allVisible ? '' : ' dashboard-settings-group__bulk--on'}`}
                                    onClick={() => setAllVisible(!allVisible)}
                                >
                                    {allVisible ? 'Снять все' : 'Выделить все'}
                                </button>
                            </header>
                        ) : null}
                        <div className="dashboard-settings-group__rows">
                            {accounts.map((account) => {
                                const included = !draftHidden[account.account_id]
                                return (
                                    <AccountVisibilityRow
                                        key={account.account_id}
                                        account={account}
                                        included={included}
                                        onIncludedChange={(next) => {
                                            setDraftHidden((prev) => ({
                                                ...prev,
                                                [account.account_id]: !next,
                                            }))
                                        }}
                                    />
                                )
                            })}
                        </div>
                    </section>
                </div>
                <div className="dashboard-settings-actions">
                    <Button
                        type="button"
                        variant="ghost"
                        size="lg"
                        className="dashboard-settings-actions__apply"
                        onClick={() => void apply()}
                        loading={saving}
                        disabled={accounts.length === 0}
                    >
                        Применить
                    </Button>
                </div>
            </div>
        </Modal>
    )
}

function AccountVisibilityRow({
    account,
    included,
    onIncludedChange,
}: {
    account: DashboardAccountItem
    included: boolean
    onIncludedChange: (included: boolean) => void
}) {
    const title = account.account_name || account.external_account_id
    const titleMarquee = useOverflowMarquee(title)
    const currency = (account.summary?.currency || '').toUpperCase()

    return (
        <label className={`dashboard-settings-row${included ? '' : ' dashboard-settings-row--off'}`}>
            <input
                type="checkbox"
                className="dashboard-settings-row__check"
                checked={included}
                onChange={(event) => onIncludedChange(event.target.checked)}
                aria-label={included ? `Скрыть ${title}` : `Показать ${title}`}
            />
            <div className="dashboard-settings-row__main">
                <span
                    ref={titleMarquee.wrapRef}
                    className={`dashboard-settings-row__title${titleMarquee.marquee ? ' dashboard-settings-row__title--marquee' : ''}`}
                >
                    <span ref={titleMarquee.textRef} className="dashboard-settings-row__title-text">
                        {title}
                    </span>
                </span>
                <span className="dashboard-settings-row__tag">{formatPortfolioAccountPlatformTag(account.account_type)}</span>
            </div>
            <span className="dashboard-settings-row__value mono">
                {formatPortfolioMoney(account.summary.value, currency || 'RUB')}
            </span>
        </label>
    )
}

function useOverflowMarquee(content: string) {
    const wrapRef = useRef<HTMLElement>(null)
    const textRef = useRef<HTMLSpanElement>(null)
    const [marquee, setMarquee] = useState(false)

    useEffect(() => {
        const wrap = wrapRef.current
        const text = textRef.current
        if (!wrap || !text) return
        const sync = () => {
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
        }
        sync()
        if (typeof ResizeObserver === 'undefined') {
            window.addEventListener('resize', sync)
            return () => window.removeEventListener('resize', sync)
        }
        const observer = new ResizeObserver(() => sync())
        observer.observe(wrap)
        return () => observer.disconnect()
    }, [content])

    return { wrapRef, textRef, marquee }
}

function IconGear() {
    return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
                d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
            <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
        </svg>
    )
}
