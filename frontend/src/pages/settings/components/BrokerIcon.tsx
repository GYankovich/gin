import React from 'react'
import type { BrokerKind } from '@/pages/settings/types'
import { brokerLabel } from '@/pages/settings/utils'

type Props = {
    kind: BrokerKind
    className?: string
}

type IconProps = { className?: string }

/** Geometric T mark — T-Invest / T-Bank, cyber line style. */
function IconTinvest({ className }: IconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="2.75" y="2.75" width="18.5" height="18.5" rx="3" stroke="currentColor" strokeWidth="1.5" />
            <path
                d="M7.5 8.25h9M12 8.25v7.5"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="square"
            />
            <path
                className="token-row__broker-accent"
                d="M7.5 8.25h9"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="square"
                opacity="0.45"
            />
        </svg>
    )
}

/** Angular B mark — Bybit, cyber line style. */
function IconBybit({ className }: IconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="2.75" y="2.75" width="18.5" height="18.5" rx="3" stroke="currentColor" strokeWidth="1.5" />
            <path
                d="M8.25 7.5h5.1c1.85 0 3.15 1.1 3.15 2.65 0 1.15-.6 2.05-1.65 2.45 1.25.4 2 1.35 2 2.65 0 1.7-1.4 2.75-3.35 2.75H8.25V7.5Z"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinejoin="round"
            />
            <path
                className="token-row__broker-accent"
                d="M8.25 12.1h4.6"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="square"
                opacity="0.5"
            />
        </svg>
    )
}

/** Diamond mark — Binance, cyber line style. */
function IconBinance({ className }: IconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
                d="M12 3.5 15.2 6.7 12 9.9 8.8 6.7 12 3.5Z"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinejoin="round"
            />
            <path
                d="M6.7 8.8 9.9 12 6.7 15.2 3.5 12 6.7 8.8Z"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinejoin="round"
            />
            <path
                d="M17.3 8.8 20.5 12 17.3 15.2 14.1 12 17.3 8.8Z"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinejoin="round"
            />
            <path
                d="M12 14.1 15.2 17.3 12 20.5 8.8 17.3 12 14.1Z"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinejoin="round"
            />
            <path
                className="token-row__broker-accent"
                d="M9.9 12 12 14.1 14.1 12 12 9.9 9.9 12Z"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinejoin="round"
                opacity="0.55"
            />
        </svg>
    )
}

function IconOther({ className }: IconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="2.75" y="2.75" width="18.5" height="18.5" rx="3" stroke="currentColor" strokeWidth="1.5" />
            <path
                d="M7.5 9h9M7.5 12.5h6.5M7.5 16h4"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="square"
            />
        </svg>
    )
}

const ICONS: Record<BrokerKind, React.FC<IconProps>> = {
    tinvest: IconTinvest,
    bybit: IconBybit,
    binance: IconBinance,
    other: IconOther,
}

/** Broker marks in GIN cyber line style (currentColor, theme-aware). */
export function BrokerIcon({ kind, className = '' }: Props) {
    const label = brokerLabel(kind)
    const Icon = ICONS[kind]

    return (
        <span
            className={`token-row__broker-icon token-row__broker-icon--${kind} ${className}`.trim()}
            aria-label={label}
            role="img"
        >
            <Icon className="token-row__broker-svg" />
        </span>
    )
}
