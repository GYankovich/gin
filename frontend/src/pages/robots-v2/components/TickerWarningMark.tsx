import React from 'react'
import { Tooltip } from '@/components/ui/Tooltip'

export function TickerWarningMark({ text }: { text: string }) {
    return (
        <Tooltip text={text} className="robots-v2-ticker-warn">
            <svg
                className="robots-v2-ticker-warn__icon"
                viewBox="0 0 16 16"
                width="14"
                height="14"
                aria-hidden
            >
                <path
                    d="M8 1.4 15 14.2H1L8 1.4Z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.4"
                    strokeLinejoin="round"
                />
                <path d="M8 6.2v3.4" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                <circle cx="8" cy="11.6" r="0.7" fill="currentColor" />
            </svg>
        </Tooltip>
    )
}
