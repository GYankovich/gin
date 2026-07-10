import React from 'react'

type Props = {
    text: string
}

export function FormLabelTooltip({ text }: Props) {
    return (
        <span className="form-label-tooltip" data-tooltip={text} tabIndex={0} role="note" aria-label={text}>
            ⓘ
        </span>
    )
}
