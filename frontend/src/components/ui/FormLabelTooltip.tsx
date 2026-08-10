import React from 'react'
import { Tooltip } from '@/components/ui/Tooltip'

type Props = {
    text: string
}

/** Classic light square-question–style mark (FA Pro Light not in free packages). */
function SquareQuestionIcon() {
    return (
        <svg className="form-label-tooltip__icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden>
            <rect
                x="1.25"
                y="1.25"
                width="13.5"
                height="13.5"
                rx="1.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.25"
            />
            <path
                d="M6.15 6.05c0-1.05.88-1.85 1.85-1.85s1.85.8 1.85 1.85c0 .72-.4 1.2-1.05 1.48-.48.2-.7.48-.7.92v.35"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.25"
                strokeLinecap="round"
            />
            <circle cx="8" cy="11.15" r="0.85" fill="currentColor" />
        </svg>
    )
}

/** Dashboard/settings hint mark — thin wrapper over shared Tooltip. */
export function FormLabelTooltip({ text }: Props) {
    return (
        <Tooltip text={text}>
            <SquareQuestionIcon />
        </Tooltip>
    )
}
