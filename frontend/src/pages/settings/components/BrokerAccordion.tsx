import React, { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faChevronRight } from '@fortawesome/free-solid-svg-icons'
import { Card } from '@/components/ui/Card'
import { BrokerIcon } from '@/pages/settings/components/BrokerIcon'
import type { ApiKeyItem, BrokerKind, TokenHealth } from '@/pages/settings/types'
import { brokerLabel } from '@/pages/settings/utils'
import type { DashboardAccountItem } from '@/types/api'

export type BrokerBucket = {
    kind: BrokerKind
    tokens: ApiKeyItem[]
    accounts: DashboardAccountItem[]
}

function tokenWord(n: number): string {
    const mod10 = n % 10
    const mod100 = n % 100
    if (mod10 === 1 && mod100 !== 11) return 'токен'
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'токена'
    return 'токенов'
}

function accountWord(n: number): string {
    const mod10 = n % 10
    const mod100 = n % 100
    if (mod10 === 1 && mod100 !== 11) return 'счёт'
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'счёта'
    return 'счетов'
}

function bucketSummary(bucket: BrokerBucket): string {
    return [
        bucket.tokens.length ? `${bucket.tokens.length} ${tokenWord(bucket.tokens.length)}` : null,
        bucket.accounts.length
            ? `${bucket.accounts.length} ${accountWord(bucket.accounts.length)}`
            : null,
    ]
        .filter(Boolean)
        .join(' · ')
}

function bucketStatusClass(
    bucket: BrokerBucket,
    healthMap: Record<number, TokenHealth>,
): '' | 'is-warn' | 'is-err' | 'is-mute' {
    if (bucket.tokens.length === 0) return 'is-mute'
    let hasError = false
    let hasWarn = false
    for (const token of bucket.tokens) {
        const health = healthMap[token.id]
        if (health?.status === 'error' || token.status === 3) hasError = true
        else if (token.status !== 1) hasWarn = true
    }
    if (hasError) return 'is-err'
    if (hasWarn) return 'is-warn'
    return ''
}

type Props = {
    bucket: BrokerBucket
    healthMap: Record<number, TokenHealth>
    defaultOpen?: boolean
    children: React.ReactNode
}

/** Mobile stacked-sheet: broker card that expands to tokens + accounts. */
export function BrokerAccordionCard({
    bucket,
    healthMap,
    defaultOpen = false,
    children,
}: Props) {
    const [open, setOpen] = useState(defaultOpen)
    const summary = bucketSummary(bucket)
    const statusClass = bucketStatusClass(bucket, healthMap)

    return (
        <Card
            className={`dashboard-totals-card settings-broker-card settings-broker-accordion${open ? ' is-open' : ''}`}
        >
            <button
                type="button"
                className="settings-broker-accordion__toggle"
                aria-expanded={open}
                onClick={() => setOpen(v => !v)}
            >
                <span className="settings-broker-accordion__icon" aria-hidden>
                    <BrokerIcon kind={bucket.kind} className="dashboard-icon" />
                </span>
                <span className="settings-broker-accordion__text">
                    <span className="settings-broker-accordion__name">
                        {brokerLabel(bucket.kind)}
                    </span>
                    {summary ? (
                        <span className="settings-broker-accordion__meta">
                            <span
                                className={`settings-broker-accordion__dot${statusClass ? ` ${statusClass}` : ''}`}
                                aria-hidden
                            />
                            {summary}
                        </span>
                    ) : null}
                </span>
                <FontAwesomeIcon
                    icon={faChevronRight}
                    className="settings-broker-accordion__chev"
                    aria-hidden
                />
            </button>
            {open ? <div className="settings-broker-accordion__body">{children}</div> : null}
        </Card>
    )
}
